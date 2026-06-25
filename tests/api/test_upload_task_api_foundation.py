from __future__ import annotations

import socket
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session, sessionmaker

from upload_control_plane.api.auth import get_db_session
from upload_control_plane.api.request_context import REQUEST_ID_HEADER
from upload_control_plane.api.upload_tasks import get_object_storage
from upload_control_plane.config import Settings, get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE, MIN_PART_SIZE
from upload_control_plane.domain.storage import (
    AbortMultipartUploadRequest,
    CompletedObject,
    CompleteMultipartUploadRequest,
    CreateMultipartUploadRequest,
    CreateMultipartUploadResult,
    HeadObjectRequest,
    HeadObjectResult,
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
    PermissionGrant,
    Project,
    UploadEvent,
    UploadObject,
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


def test_upload_task_create_requires_bearer_auth() -> None:
    client = TestClient(create_app())
    project_id = uuid.uuid4()

    response = client.post(
        f"/v1/projects/{project_id}/upload-tasks",
        headers={REQUEST_ID_HEADER: "req-upload-missing-auth"},
        json=_valid_payload(),
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "auth.api_key_missing",
            "message": "Missing API key.",
            "details": {},
            "request_id": "req-upload-missing-auth",
        }
    }


def test_upload_task_create_rejects_actor_without_upload_permission() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    denied_project_id = dev_seed_uuid("test-project:upload-create-denied")

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _upsert_project(session, denied_project_id, slug="upload-denied", name="Upload Denied")
        _upsert_grant(
            session,
            grant_id=dev_seed_uuid("test-grant:upload-denied-view"),
            resource_id=denied_project_id,
            permission_code="project.view",
        )

    try:
        client = _client(session_factory)
        response = client.post(
            f"/v1/projects/{denied_project_id}/upload-tasks",
            headers=_auth_headers("req-upload-denied"),
            json=_valid_payload(),
        )

        assert response.status_code == 403
        assert response.json() == {
            "error": {
                "code": "authorization.permission_denied",
                "message": "Permission denied.",
                "details": {
                    "permission_code": "dataset.upload or upload.create",
                    "resource_type": "project",
                },
                "request_id": "req-upload-denied",
            }
        }
    finally:
        _delete_test_projects(session_factory, denied_project_id)
        _delete_test_grants(session_factory, dev_seed_uuid("test-grant:upload-denied-view"))
        _ = seed


def test_upload_task_create_single_file_transactionally_creates_records() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    idempotency_key = "idem-upload-single"

    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        before_count = session.scalar(select(func.count()).select_from(UploadTask))

    try:
        client = _client(session_factory, storage=storage)
        response = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-create"), "Idempotency-Key": idempotency_key},
            json=_valid_payload(),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["project_id"] == str(seed.project_id)
        assert body["status"] == "PENDING"
        assert body["object_count"] == 1
        assert body["total_size_bytes"] == DEFAULT_PART_SIZE
        assert len(body["objects"]) == 1
        created = body["objects"][0]
        assert created["status"] == "PENDING"
        assert created["object_name"] == "front_camera.hdf5"
        assert created["bucket"] == get_settings().s3_bucket
        assert "/front_camera.hdf5" in created["object_key"]
        assert not created["object_key"].startswith("front_camera")
        assert storage.create_calls == [
            {
                "bucket": created["bucket"],
                "object_key": created["object_key"],
                "content_type": "application/x-hdf5",
            }
        ]

        with _session_scope(session_factory) as session:
            after_count = session.scalar(select(func.count()).select_from(UploadTask))
            task = session.get(UploadTask, uuid.UUID(body["task_id"]))
            upload_object = session.get(UploadObject, uuid.UUID(created["object_id"]))
            dataset = session.get(Dataset, uuid.UUID(created["dataset_id"]))
            upload_session = session.get(UploadSession, uuid.UUID(created["session_id"]))
            events = session.scalars(
                select(UploadEvent).where(UploadEvent.upload_task_id == uuid.UUID(body["task_id"]))
            ).all()
            audits = session.scalars(
                select(AuditEvent).where(AuditEvent.resource_id == body["task_id"])
            ).all()

        assert before_count is not None
        assert after_count == before_count + 1
        assert task is not None
        assert upload_object is not None
        assert dataset is not None
        assert upload_session is not None
        assert upload_session.storage_upload_id == "fake-upload-1"
        assert upload_session.status == "INITIATED"
        assert upload_object.upload_session_id == upload_session.id
        assert dataset.object_key == created["object_key"]
        assert {event.event_type for event in events} == {
            "upload_task.created",
            "upload_session.storage_initiated",
        }
        assert [audit.action for audit in audits] == ["upload_task.create"]
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_upload_task_create_multi_file_creates_one_object_and_session_per_item() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    idempotency_key = "idem-upload-multi"
    payload = _valid_payload(
        objects=[
            {
                "dataset_name": "front-camera",
                "object_name": "front_camera.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
            },
            {
                "dataset_name": "rear-camera",
                "object_name": "rear_camera.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
            },
        ]
    )
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        response = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-multi"), "Idempotency-Key": idempotency_key},
            json=payload,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["object_count"] == 2
        assert len(body["objects"]) == 2
        assert len({item["object_id"] for item in body["objects"]}) == 2
        assert len({item["session_id"] for item in body["objects"]}) == 2
        assert len(storage.create_calls) == 2
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_upload_task_create_idempotent_retry_returns_same_response_without_storage_call() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    idempotency_key = "idem-upload-retry"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        first = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-retry-1"), "Idempotency-Key": idempotency_key},
            json=_valid_payload(),
        )
        second = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-retry-2"), "Idempotency-Key": idempotency_key},
            json=_valid_payload(),
        )

        assert first.status_code == 201
        assert second.status_code == 201
        first_body = first.json()
        second_body = second.json()
        assert second_body == first_body
        assert len(storage.create_calls) == 1
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_upload_task_create_rejects_idempotency_key_reused_with_different_request() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    idempotency_key = "idem-upload-conflict"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        first = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-conflict-1"), "Idempotency-Key": idempotency_key},
            json=_valid_payload(),
        )
        second = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={**_auth_headers("req-upload-conflict-2"), "Idempotency-Key": idempotency_key},
            json=_valid_payload(
                objects=[
                    {
                        "dataset_name": "rear",
                        "object_name": "rear.hdf5",
                        "file_size_bytes": DEFAULT_PART_SIZE,
                    }
                ]
            ),
        )

        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "idempotency.key_reused_with_different_request"
        assert len(storage.create_calls) == 1
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


@pytest.mark.parametrize(
    ("case", "expected_message"),
    [
        ("empty_objects", "List should have at least 1 item"),
        ("zero_file_size", "Input should be greater than 0"),
        ("part_too_small", "part size must be at least 5 MiB"),
        ("unsafe_object_name", "object name must not contain path separators"),
        ("client_storage_key", "Extra inputs are not permitted"),
    ],
)
def test_upload_task_create_rejects_invalid_request_shape(
    case: str,
    expected_message: str,
) -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    client = _client(session_factory)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers=_auth_headers("req-upload-validation"),
        json=_invalid_payload(case),
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "request.validation_failed"
    assert body["error"]["request_id"] == "req-upload-validation"
    assert expected_message in str(body["error"]["details"]["errors"])


def test_upload_task_create_validation_happens_before_storage() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    client = _client(session_factory, storage=storage)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers={
            **_auth_headers("req-upload-invalid-no-storage"),
            "Idempotency-Key": "idem-invalid-no-storage",
        },
        json=_invalid_payload("zero_file_size"),
    )

    assert response.status_code == 422
    assert storage.create_calls == []


def test_upload_task_create_rejects_too_many_objects_before_storage() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    settings = _settings_override(max_open_upload_tasks_per_project=1)
    payload = _valid_payload(
        objects=[
            {
                "dataset_name": "front-camera",
                "object_name": "front_camera.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
            },
            {
                "dataset_name": "rear-camera",
                "object_name": "rear_camera.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
            },
        ]
    )
    with _session_scope(session_factory) as session:
        seed_dev_data(session, settings)

    client = _client(session_factory, storage=storage, settings=settings)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers={
            **_auth_headers("req-upload-too-many-objects"),
            "Idempotency-Key": "idem-quota-too-many-objects",
        },
        json=payload,
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_task.too_many_objects"
    assert storage.create_calls == []


def test_upload_task_create_rejects_open_task_quota_before_storage() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    settings = _settings_override(max_open_upload_tasks_per_project=1)
    existing_task_idempotency_key = "idem-quota-existing-open-task"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, settings)
        _insert_open_upload_task(session, idempotency_key=existing_task_idempotency_key)

    try:
        client = _client(session_factory, storage=storage, settings=settings)
        response = client.post(
            f"/v1/projects/{seed.project_id}/upload-tasks",
            headers={
                **_auth_headers("req-upload-open-quota"),
                "Idempotency-Key": "idem-quota-open",
            },
            json=_valid_payload(),
        )

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "quota.open_upload_tasks_exceeded"
        assert storage.create_calls == []
    finally:
        _delete_upload_artifacts(session_factory, existing_task_idempotency_key)


def test_upload_task_create_rejects_project_byte_quota_before_storage() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = FakeObjectStorage()
    settings = _settings_override(max_bytes_per_project=DEFAULT_PART_SIZE - 1)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, settings)

    client = _client(session_factory, storage=storage, settings=settings)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers={
            **_auth_headers("req-upload-project-bytes"),
            "Idempotency-Key": "idem-quota-project-bytes",
        },
        json=_valid_payload(),
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "quota.project_bytes_exceeded"
    assert storage.create_calls == []


def _invalid_payload(case: str) -> dict[str, object]:
    if case == "empty_objects":
        return {**_valid_payload(), "objects": []}
    if case == "zero_file_size":
        return _valid_payload(
            objects=[
                {
                    "dataset_name": "front-camera",
                    "object_name": "front_camera.hdf5",
                    "file_size_bytes": 0,
                }
            ]
        )
    if case == "part_too_small":
        return _valid_payload(
            objects=[
                {
                    "dataset_name": "front-camera",
                    "object_name": "front_camera.hdf5",
                    "file_size_bytes": 1024,
                    "part_size_bytes": MIN_PART_SIZE - 1,
                }
            ]
        )
    if case == "unsafe_object_name":
        return _valid_payload(
            objects=[
                {
                    "dataset_name": "front-camera",
                    "object_name": "../front_camera.hdf5",
                    "file_size_bytes": DEFAULT_PART_SIZE,
                }
            ]
        )
    if case == "client_storage_key":
        return {**_valid_payload(), "storage_key": "client-controlled-key"}
    raise AssertionError(f"Unknown invalid payload case: {case}")


def test_upload_task_create_rejects_multipart_file_byte_input() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    client = _client(session_factory)
    response = client.post(
        f"/v1/projects/{seed.project_id}/upload-tasks",
        headers=_auth_headers("req-upload-file-bytes"),
        files={"file": ("front_camera.hdf5", b"file-bytes", "application/x-hdf5")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request.validation_failed"


def _valid_payload(
    *,
    objects: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "task_name": "robot-run-2026-06-10-line-3",
        "task_initiator": "cli",
        "source_device_code": "robot-17",
        "objects": objects
        or [
            {
                "dataset_name": "front-camera-2026-06-10",
                "object_name": "front_camera.hdf5",
                "file_size_bytes": DEFAULT_PART_SIZE,
                "content_type": "application/x-hdf5",
                "part_size_bytes": DEFAULT_PART_SIZE,
                "checksum_sha256": "a" * 64,
                "metadata": {"camera": "front"},
            }
        ],
        "metadata": {"site": "factory-shanghai"},
    }


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
    storage: FakeObjectStorage | None = None,
    settings: Settings | None = None,
) -> TestClient:
    app = create_app()

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    if storage is not None:
        app.dependency_overrides[get_object_storage] = lambda: storage
    return TestClient(app)


def _auth_headers(request_id: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {DEV_API_KEY_VALUE}",
        "X-Request-ID": request_id,
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


def _upsert_project(session: Session, project_id: uuid.UUID, *, slug: str, name: str) -> None:
    seed = build_dev_seed_result()
    project = session.get(Project, project_id)
    if project is None:
        project = Project(id=project_id)
        session.add(project)
    project.tenant_id = seed.tenant_id
    project.storage_policy_id = seed.storage_policy_id
    project.slug = slug
    project.name = name
    project.description = None
    project.status = "ACTIVE"
    project.metadata_schema = {}
    project.metadata_ = {"seed": "test"}
    project.created_by = seed.api_key_id
    project.archived_at = None
    project.deleted_at = None


def _upsert_grant(
    session: Session,
    *,
    grant_id: uuid.UUID,
    resource_id: uuid.UUID,
    permission_code: str,
    effect: str = "ALLOW",
    expires_at: datetime | None = None,
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
    grant.expires_at = expires_at or datetime.now(UTC) + timedelta(hours=1)


def _delete_test_projects(session_factory: sessionmaker[Session], *project_ids: uuid.UUID) -> None:
    with _session_scope(session_factory) as session:
        session.execute(delete(PermissionGrant).where(PermissionGrant.resource_id.in_(project_ids)))
        session.execute(delete(Project).where(Project.id.in_(project_ids)))


def _delete_test_grants(session_factory: sessionmaker[Session], *grant_ids: uuid.UUID) -> None:
    with _session_scope(session_factory) as session:
        session.execute(delete(PermissionGrant).where(PermissionGrant.id.in_(grant_ids)))


def _settings_override(**values: object) -> Settings:
    return get_settings().model_copy(update=values)


def _insert_open_upload_task(session: Session, *, idempotency_key: str) -> None:
    seed = build_dev_seed_result()
    now = datetime.now(UTC)
    session.add(
        UploadTask(
            id=uuid.uuid4(),
            tenant_id=seed.tenant_id,
            project_id=seed.project_id,
            storage_policy_id=seed.storage_policy_id,
            status="PENDING",
            task_initiator="cli",
            source_device_id=None,
            source_device_code=None,
            object_count=1,
            completed_object_count=0,
            failed_object_count=0,
            total_size_bytes=DEFAULT_PART_SIZE,
            uploaded_size_bytes=0,
            idempotency_key=idempotency_key,
            metadata_={"seed": "quota-test"},
            created_by=seed.api_key_id,
            created_at=now,
            updated_at=now,
        )
    )


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


class FakeObjectStorage:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, str | None]] = []

    @property
    def capabilities(self) -> StorageCapabilities:
        return StorageCapabilities()

    def create_multipart_upload(
        self,
        request: CreateMultipartUploadRequest,
    ) -> CreateMultipartUploadResult:
        self.create_calls.append(
            {
                "bucket": request.bucket,
                "object_key": request.object_key,
                "content_type": request.content_type,
            }
        )
        return CreateMultipartUploadResult(upload_id=f"fake-upload-{len(self.create_calls)}")

    def presign_upload_part(self, request: PresignUploadPartRequest) -> PresignedPartUrl:
        raise NotImplementedError

    def list_parts(self, request: ListPartsRequest) -> ListedPartsPage:
        raise NotImplementedError

    def complete_multipart_upload(self, request: CompleteMultipartUploadRequest) -> CompletedObject:
        raise NotImplementedError

    def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
        raise NotImplementedError

    def head_object(self, request: HeadObjectRequest) -> HeadObjectResult:
        raise NotImplementedError
