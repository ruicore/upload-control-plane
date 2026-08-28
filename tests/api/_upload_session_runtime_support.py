from __future__ import annotations

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
from upload_control_plane.config import Settings, get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    CompletedObject,
    CompleteMultipartUploadRequest,
    CreateMultipartUploadRequest,
    CreateMultipartUploadResult,
    HeadObjectRequest,
    HeadObjectResult,
    ListedPart,
    ListedPartsPage,
    ListPartsRequest,
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
)
from upload_control_plane.infrastructure.db.session import build_engine, build_session_factory
from upload_control_plane.main import create_app


def _create_upload_task(
    client: TestClient,
    project_id: uuid.UUID,
    idempotency_key: str,
    *,
    file_size_bytes: int = DEFAULT_PART_SIZE,
    part_size_bytes: int = DEFAULT_PART_SIZE,
) -> dict[str, Any]:
    response = client.post(
        f"/v1/projects/{project_id}/upload-tasks",
        headers={
            **_auth_headers(f"req-create-{idempotency_key}"),
            "Idempotency-Key": idempotency_key,
        },
        json={
            "task_name": f"runtime-{idempotency_key}",
            "task_initiator": "api",
            "objects": [
                {
                    "dataset_name": f"runtime-{idempotency_key}",
                    "object_name": f"runtime-{idempotency_key}.bin",
                    "file_size_bytes": file_size_bytes,
                    "part_size_bytes": part_size_bytes,
                }
            ],
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def _created_object(created: dict[str, Any]) -> dict[str, Any]:
    objects = created["objects"]
    assert isinstance(objects, list)
    first = objects[0]
    assert isinstance(first, dict)
    return first


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
    storage: RuntimeFakeObjectStorage,
    settings: Settings | None = None,
) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_object_storage] = lambda: storage
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
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
    resource_type: str = "project",
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
    grant.resource_type = resource_type
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


def _delete_upload_artifacts(
    session_factory: sessionmaker[Session],
    idempotency_key: str,
    *extra_idempotency_keys: str,
) -> None:
    with _session_scope(session_factory) as session:
        idempotency_keys = (idempotency_key, *extra_idempotency_keys)
        task_ids = list(
            session.scalars(
                select(UploadTask.id).where(UploadTask.idempotency_key.in_(idempotency_keys))
            )
        )
        if not task_ids:
            session.execute(
                delete(IdempotencyRecord).where(IdempotencyRecord.key.in_(idempotency_keys))
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
        aggregate_ids = [*task_ids, *object_ids, *dataset_ids, *session_ids]
        if aggregate_ids:
            session.execute(delete(OutboxEvent).where(OutboxEvent.aggregate_id.in_(aggregate_ids)))
        session.execute(delete(UploadSession).where(UploadSession.upload_task_id.in_(task_ids)))
        if object_ids:
            session.execute(delete(UploadObject).where(UploadObject.id.in_(object_ids)))
        session.execute(delete(UploadTask).where(UploadTask.id.in_(task_ids)))
        if dataset_ids:
            session.execute(delete(Dataset).where(Dataset.id.in_(dataset_ids)))
        session.execute(
            delete(IdempotencyRecord).where(IdempotencyRecord.key.in_(idempotency_keys))
        )


def _settings_override(**values: object) -> Settings:
    return get_settings().model_copy(update=values)


class RuntimeFakeObjectStorage:
    def __init__(self) -> None:
        self.create_calls: list[CreateMultipartUploadRequest] = []
        self.presign_calls: list[tuple[str, int, int]] = []
        self.list_calls: list[ListPartsRequest] = []
        self.complete_calls: list[CompleteMultipartUploadRequest] = []
        self.abort_calls: list[AbortMultipartUploadRequest] = []
        self.listed_parts: tuple[ListedPart, ...] = ()
        self.complete_error: Exception | None = None
        self.abort_error: Exception | None = None

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
        self.presign_calls.append((request.bucket, request.part_number, request.expires_in_seconds))
        return PresignedPartUrl(
            part_number=request.part_number,
            url=(
                f"http://storage.local/{request.bucket}/{request.object_key}"
                f"?partNumber={request.part_number}&uploadId={request.upload_id}&fake-signature=1"
            ),
            expires_at=datetime.now(UTC) + timedelta(seconds=request.expires_in_seconds),
            required_headers={},
        )

    def list_parts(self, request: ListPartsRequest) -> ListedPartsPage:
        self.list_calls.append(request)
        return ListedPartsPage(parts=self.listed_parts)

    def complete_multipart_upload(self, request: CompleteMultipartUploadRequest) -> CompletedObject:
        self.complete_calls.append(request)
        if self.complete_error is not None:
            raise self.complete_error
        return CompletedObject(
            bucket=request.bucket,
            object_key=request.object_key,
            etag='"final-etag"',
            size_bytes=sum(
                part.size_bytes
                for part in self.listed_parts
                if part.part_number in {item.part_number for item in request.parts}
            ),
        )

    def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
        self.abort_calls.append(request)
        if self.abort_error is not None:
            raise self.abort_error

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        return HeadObjectResult(
            bucket=request.bucket,
            object_key=request.object_key,
            etag='"final-etag"',
            size_bytes=sum(part.size_bytes for part in self.listed_parts),
        )
