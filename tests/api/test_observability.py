from __future__ import annotations

import json
import logging
import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from upload_control_plane.api.auth import get_db_session
from upload_control_plane.api.request_context import REQUEST_ID_HEADER
from upload_control_plane.api.upload_tasks import get_object_storage
from upload_control_plane.config import get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    CompletedObject,
    CompleteMultipartUploadRequest,
    CreateMultipartUploadRequest,
    CreateMultipartUploadResult,
    DeleteObjectRequest,
    HeadObjectRequest,
    HeadObjectResult,
    ListedPart,
    ListedPartsPage,
    ListPartsRequest,
    PresignDownloadObjectRequest,
    PresignedDownloadUrl,
    PresignedPartUrl,
    PresignUploadPartRequest,
    StorageCapabilities,
)
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Dataset,
    IdempotencyRecord,
    OutboxEvent,
    PermissionGrant,
    UploadEvent,
    UploadObject,
    UploadPart,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import (
    DEV_API_KEY_VALUE,
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory
from upload_control_plane.main import create_app


def test_metrics_returns_prometheus_text_and_expected_metric_names() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    dead_letter_id = dev_seed_uuid("test-outbox:metrics-dead-letter")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        outbox = session.get(OutboxEvent, dead_letter_id)
        if outbox is None:
            outbox = OutboxEvent(id=dead_letter_id)
            session.add(outbox)
        outbox.tenant_id = seed.tenant_id
        outbox.aggregate_type = "dataset"
        outbox.aggregate_id = seed.dataset_id
        outbox.event_type = "dataset.validation_failed"
        outbox.payload = {"dataset_id": str(seed.dataset_id)}
        outbox.status = "DEAD_LETTERED"
        outbox.attempts = 12
        outbox.next_attempt_at = datetime.now(UTC)

    try:
        response = _client(session_factory).get("/metrics")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        body = response.text
        assert "api_requests_total" in body
        assert "api_request_duration_seconds_bucket" in body
        assert "storage_operation_duration_seconds_bucket" in body
        assert "upload_sessions_by_status" in body
        assert "validation_queue_depth" in body
        assert "cleanup_expired_sessions_backlog" in body
        assert "outbox_events_pending" in body
        assert "outbox_events_dead_lettered" in body
    finally:
        with _session_scope(session_factory) as session:
            session.execute(delete(OutboxEvent).where(OutboxEvent.id == dead_letter_id))


def test_request_logging_carries_request_and_path_context_without_query(
    caplog: pytest.LogCaptureFixture,
) -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = ObservabilityFakeObjectStorage()
    idempotency_key = "idem-observability-log"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(created["objects"][0]["session_id"])

        caplog.set_level(logging.INFO, logger="upload_control_plane.api")
        response = client.get(
            f"/v1/uploads/{session_id}?debug_url=http://storage.local/o?X-Amz-Signature=secret",
            headers=_auth_headers("req-observe-log"),
        )

        assert response.status_code == 200
        record = next(
            item
            for item in caplog.records
            if getattr(item, "request_id", None) == "req-observe-log"
        )
        record_any = cast(Any, record)
        assert record_any.operation == "/v1/uploads/{session_id}"
        assert record_any.path == f"/v1/uploads/{session_id}"
        assert record_any.status == 200
        assert record_any.session_id == str(session_id)
        assert "X-Amz-Signature" not in json.dumps(record.__dict__)
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_audit_endpoint_requires_audit_view_and_redacts_secret_url_material() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    audit_id = dev_seed_uuid("test-audit:observability-redaction")
    deny_grant_id = dev_seed_uuid("test-grant:audit-view-deny")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        audit = session.get(AuditEvent, audit_id)
        if audit is None:
            audit = AuditEvent(id=audit_id)
            session.add(audit)
        audit.tenant_id = seed.tenant_id
        audit.project_id = seed.project_id
        audit.dataset_id = seed.dataset_id
        audit.actor_type = "api_key"
        audit.actor_id = str(seed.api_key_id)
        audit.action = "dataset.download_url"
        audit.resource_type = "dataset"
        audit.resource_id = str(seed.dataset_id)
        audit.result = "success"
        audit.request_id = "req-audit-redact"
        audit.before_state = {
            "url": "http://storage.local/object?X-Amz-Signature=secret&X-Amz-Credential=cred"
        }
        audit.after_state = None
        audit.metadata_ = {
            "safe_url": "http://storage.local/object?X-Amz-Signature=secret",
            "access_key": "AKIA-should-not-leak",
        }

    try:
        client = _client(session_factory)
        allowed = client.get(
            f"/v1/projects/{seed.project_id}/audit-events",
            headers=_auth_headers("req-audit-allowed"),
        )

        assert allowed.status_code == 200
        encoded = json.dumps(allowed.json())
        assert "X-Amz-Signature" not in encoded
        assert "X-Amz-Credential" not in encoded
        assert "AKIA-should-not-leak" not in encoded
        assert "http://storage.local/object" in encoded

        with _session_scope(session_factory) as session:
            _upsert_deny_grant(
                session,
                grant_id=deny_grant_id,
                resource_id=seed.project_id,
                permission_code="audit.view",
            )

        denied = client.get(
            f"/v1/projects/{seed.project_id}/audit-events",
            headers=_auth_headers("req-audit-denied"),
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "authorization.permission_denied"
    finally:
        with _session_scope(session_factory) as session:
            session.execute(delete(AuditEvent).where(AuditEvent.id == audit_id))
            session.execute(delete(PermissionGrant).where(PermissionGrant.id == deny_grant_id))


def test_structured_json_formatter_redacts_presigned_query_strings() -> None:
    from upload_control_plane.observability import JsonLogFormatter

    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="storage url",
        args=(),
        exc_info=None,
    )
    record.request_id = "req-json-log"
    record.path = "http://storage.local/object?X-Amz-Signature=secret"

    encoded = JsonLogFormatter().format(record)

    assert "X-Amz-Signature" not in encoded
    assert "http://storage.local/object" in encoded


def _create_upload_task(
    client: TestClient,
    project_id: uuid.UUID,
    idempotency_key: str,
) -> dict[str, Any]:
    response = client.post(
        f"/v1/projects/{project_id}/upload-tasks",
        headers={
            **_auth_headers(f"req-create-{idempotency_key}"),
            "Idempotency-Key": idempotency_key,
        },
        json={
            "task_name": f"observability-{idempotency_key}",
            "task_initiator": "api",
            "objects": [
                {
                    "dataset_name": f"observability-{idempotency_key}",
                    "object_name": f"observability-{idempotency_key}.bin",
                    "file_size_bytes": DEFAULT_PART_SIZE,
                    "part_size_bytes": DEFAULT_PART_SIZE,
                }
            ],
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def _db_session_factory_or_skip() -> sessionmaker[Session]:
    settings = get_settings()
    url = make_url(settings.database_url)
    host = url.host or "localhost"
    port = url.port or 5432
    try:
        with socket.create_connection((host, port), timeout=1):
            pass
    except OSError as exc:
        pytest.skip(f"PostgreSQL integration database is not reachable at {host}:{port}: {exc}")

    engine = build_engine(settings)
    try:
        with engine.connect() as connection:
            connection.execute(select(1))
    except (OperationalError, ProgrammingError) as exc:
        pytest.skip(f"PostgreSQL integration database is not available or migrated: {exc}")
    return build_session_factory(engine)


def _client(
    session_factory: sessionmaker[Session],
    *,
    storage: ObservabilityFakeObjectStorage | None = None,
) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    if storage is not None:
        app.dependency_overrides[get_object_storage] = lambda: storage
    return TestClient(app)


def _auth_headers(request_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {DEV_API_KEY_VALUE}",
        REQUEST_ID_HEADER: request_id,
    }


@contextmanager
def _session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def _upsert_deny_grant(
    session: Session,
    *,
    grant_id: uuid.UUID,
    resource_id: uuid.UUID,
    permission_code: str,
) -> None:
    seed = build_dev_seed_result()
    grant = session.get(PermissionGrant, grant_id)
    if grant is None:
        grant = PermissionGrant(id=grant_id)
        session.add(grant)
    grant.tenant_id = seed.tenant_id
    grant.subject_type = "api_key"
    grant.subject_id = seed.api_key_id
    grant.resource_type = "project"
    grant.resource_id = resource_id
    grant.permission_code = permission_code
    grant.effect = "DENY"
    grant.conditions = {}
    grant.source = "test"
    grant.created_by = seed.api_key_id
    grant.expires_at = datetime.now(UTC) + timedelta(hours=1)


def _delete_upload_artifacts(session_factory: sessionmaker[Session], idempotency_key: str) -> None:
    with _session_scope(session_factory) as session:
        task_ids = list(
            session.scalars(
                select(UploadTask.id).where(UploadTask.idempotency_key == idempotency_key)
            )
        )
        if not task_ids:
            session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key)
            )
            return
        object_ids = list(
            session.scalars(
                select(UploadObject.id).where(UploadObject.upload_task_id.in_(task_ids))
            )
        )
        dataset_ids = list(
            session.scalars(
                select(UploadObject.dataset_id).where(UploadObject.upload_task_id.in_(task_ids))
            )
        )
        session_ids = list(
            session.scalars(
                select(UploadSession.id).where(UploadSession.upload_task_id.in_(task_ids))
            )
        )
        if session_ids:
            session.execute(delete(UploadPart).where(UploadPart.session_id.in_(session_ids)))
        session.execute(delete(UploadEvent).where(UploadEvent.upload_task_id.in_(task_ids)))
        session.execute(
            delete(AuditEvent)
            .where(AuditEvent.resource_type == "upload_task")
            .where(AuditEvent.resource_id.in_(str(task_id) for task_id in task_ids))
        )
        session.execute(delete(UploadSession).where(UploadSession.upload_task_id.in_(task_ids)))
        if object_ids:
            session.execute(delete(UploadObject).where(UploadObject.id.in_(object_ids)))
        session.execute(delete(UploadTask).where(UploadTask.id.in_(task_ids)))
        if dataset_ids:
            session.execute(delete(Dataset).where(Dataset.id.in_(dataset_ids)))
        session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key))


class ObservabilityFakeObjectStorage:
    def __init__(self) -> None:
        self.create_calls: list[CreateMultipartUploadRequest] = []

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities()

    def create_multipart_upload(
        self,
        request: CreateMultipartUploadRequest,
    ) -> CreateMultipartUploadResult:
        self.create_calls.append(request)
        return CreateMultipartUploadResult(upload_id=f"fake-upload-{len(self.create_calls)}")

    def presign_upload_part(self, request: PresignUploadPartRequest) -> PresignedPartUrl:
        return PresignedPartUrl(
            part_number=request.part_number,
            url=f"http://storage.local/object?X-Amz-Signature=secret-{request.part_number}",
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds),
        )

    def list_parts(self, request: ListPartsRequest) -> ListedPartsPage:
        _ = request
        return ListedPartsPage(
            parts=(ListedPart(part_number=1, etag='"etag"', size_bytes=DEFAULT_PART_SIZE),)
        )

    def complete_multipart_upload(self, request: CompleteMultipartUploadRequest) -> CompletedObject:
        return CompletedObject(bucket=request.bucket, object_key=request.object_key)

    def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
        _ = request

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        return HeadObjectResult(
            bucket=request.bucket, object_key=request.object_key, etag=None, size_bytes=0
        )

    def presign_download_object(
        self,
        request: PresignDownloadObjectRequest,
    ) -> PresignedDownloadUrl:
        return PresignedDownloadUrl(
            url=f"http://storage.local/{request.object_key}?X-Amz-Signature=secret",
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds),
        )

    def delete_object(self, request: DeleteObjectRequest) -> None:
        _ = request
