from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import cast

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
    DatasetTag,
    DatasetValidationResult,
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
)
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory
from upload_control_plane.main import create_app


def _create_ready_dataset(
    client: TestClient,
    session_factory: sessionmaker[Session],
    project_id: uuid.UUID,
    idempotency_key: str,
) -> dict[str, str]:
    response = client.post(
        f"/v1/projects/{project_id}/upload-tasks",
        headers={
            **_auth_headers(f"req-create-{idempotency_key}"),
            "Idempotency-Key": idempotency_key,
        },
        json={
            "task_name": idempotency_key,
            "task_initiator": "api",
            "objects": [
                {
                    "dataset_name": idempotency_key,
                    "object_name": f"{idempotency_key}.bin",
                    "file_size_bytes": DEFAULT_PART_SIZE,
                    "part_size_bytes": DEFAULT_PART_SIZE,
                }
            ],
        },
    )
    assert response.status_code == 201
    body = response.json()
    item = body["objects"][0]
    with _session_scope(session_factory) as session:
        dataset = session.get(Dataset, uuid.UUID(item["dataset_id"]))
        upload_session = session.get(UploadSession, uuid.UUID(item["session_id"]))
        assert dataset is not None
        assert upload_session is not None
        dataset.status = "READY"
        dataset.validation_status = "PASSED"
        dataset.recovery_status = "NORMAL"
        dataset.ready_at = datetime.now(UTC)
        dataset.object_etag = '"final-etag"'
        dataset.object_size_bytes = DEFAULT_PART_SIZE
        upload_session.status = "COMPLETED"
        upload_session.completed_at = datetime.now(UTC)
    return cast(dict[str, str], item)


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
    session_factory: sessionmaker[Session], *, storage: DatasetFakeObjectStorage
) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
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


def _upsert_grant(
    session: Session,
    *,
    grant_id: uuid.UUID,
    resource_id: uuid.UUID,
    permission_code: str,
    effect: str = "ALLOW",
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
    grant.effect = effect
    grant.conditions = {}
    grant.source = "test"
    grant.created_by = seed.api_key_id
    grant.expires_at = datetime.now(UTC) + timedelta(hours=1)


def _delete_test_grants(session_factory: sessionmaker[Session], *grant_ids: uuid.UUID) -> None:
    with _session_scope(session_factory) as session:
        session.execute(delete(PermissionGrant).where(PermissionGrant.id.in_(grant_ids)))


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
        if dataset_ids:
            session.execute(delete(DatasetTag).where(DatasetTag.dataset_id.in_(dataset_ids)))
            session.execute(
                delete(DatasetValidationResult).where(
                    DatasetValidationResult.dataset_id.in_(dataset_ids)
                )
            )
            session.execute(delete(AuditEvent).where(AuditEvent.dataset_id.in_(dataset_ids)))
            session.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(dataset_ids)))
        session.execute(delete(UploadSession).where(UploadSession.upload_task_id.in_(task_ids)))
        if object_ids:
            session.execute(delete(UploadObject).where(UploadObject.id.in_(object_ids)))
        session.execute(delete(UploadTask).where(UploadTask.id.in_(task_ids)))
        if dataset_ids:
            session.execute(delete(Dataset).where(Dataset.id.in_(dataset_ids)))
        session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.key == idempotency_key))


class DatasetFakeObjectStorage:
    def __init__(self) -> None:
        self.create_calls: list[CreateMultipartUploadRequest] = []
        self.download_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[tuple[str, str]] = []

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
            url="http://storage.local/upload?signature=1",
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds),
        )

    def list_parts(self, _request: ListPartsRequest) -> ListedPartsPage:
        return ListedPartsPage(parts=())

    def complete_multipart_upload(self, request: CompleteMultipartUploadRequest) -> CompletedObject:
        return CompletedObject(bucket=request.bucket, object_key=request.object_key)

    def abort_multipart_upload(self, _request: AbortMultipartUploadRequest) -> None:
        return None

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        return HeadObjectResult(
            bucket=request.bucket,
            object_key=request.object_key,
            etag='"final-etag"',
            size_bytes=DEFAULT_PART_SIZE,
        )

    def presign_download_object(
        self,
        request: PresignDownloadObjectRequest,
    ) -> PresignedDownloadUrl:
        self.download_calls.append((request.bucket, request.object_key, request.expires_in_seconds))
        return PresignedDownloadUrl(
            url=f"http://storage.local/{request.bucket}/{request.object_key}?download-signature=1",
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds),
        )

    def delete_object(self, request: DeleteObjectRequest) -> None:
        self.delete_calls.append((request.bucket, request.object_key))
