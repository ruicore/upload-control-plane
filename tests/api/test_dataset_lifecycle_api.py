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
    IdempotencyRecord,
    PermissionGrant,
    StoragePolicy,
    Tag,
    TagCategory,
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


def test_dataset_list_detail_update_download_and_lifecycle_controls() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DatasetFakeObjectStorage()
    idempotency_key = "idem-dataset-lifecycle"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])

        listed = client.get(
            f"/v1/projects/{seed.project_id}/datasets?search=dataset-lifecycle",
            headers=_auth_headers("req-dataset-list"),
        )
        assert listed.status_code == 200
        assert str(dataset_id) in {item["dataset_id"] for item in listed.json()["datasets"]}

        updated = client.patch(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-dataset-update"),
            json={"name": "dataset-lifecycle-renamed", "labels": ["ready", "robotics"]},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "dataset-lifecycle-renamed"
        assert updated.json()["labels"] == ["ready", "robotics"]

        download = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/download-url",
            headers=_auth_headers("req-dataset-download"),
            json={"expires_in_seconds": 600, "purpose": "test"},
        )
        assert download.status_code == 200
        assert download.json()["method"] == "GET"
        assert "download-signature=1" in download.json()["url"]
        assert storage.download_calls == [(created["bucket"], created["object_key"], 600)]

        archived = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/archive",
            headers=_auth_headers("req-dataset-archive"),
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "ARCHIVED"

        deleted = client.delete(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-dataset-delete"),
        )
        assert deleted.status_code == 200
        assert deleted.json()["status"] == "DELETED"

        normal_list = client.get(
            f"/v1/projects/{seed.project_id}/datasets",
            headers=_auth_headers("req-dataset-list-hidden"),
        )
        assert str(dataset_id) not in {
            item["dataset_id"] for item in normal_list.json()["datasets"]
        }
        recycle_list = client.get(
            f"/v1/projects/{seed.project_id}/datasets?include_deleted=true",
            headers=_auth_headers("req-dataset-list-deleted"),
        )
        assert str(dataset_id) in {item["dataset_id"] for item in recycle_list.json()["datasets"]}

        restored = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/restore",
            headers=_auth_headers("req-dataset-restore"),
        )
        assert restored.status_code == 200
        assert restored.json()["status"] == "ARCHIVED"

        with _session_scope(session_factory) as session:
            actions = set(
                session.scalars(
                    select(AuditEvent.action).where(AuditEvent.dataset_id == dataset_id)
                )
            )
        assert {
            "dataset.update",
            "dataset.download_url",
            "dataset.archive",
            "dataset.delete",
            "dataset.restore",
        }.issubset(actions)
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


@pytest.mark.parametrize(
    ("dataset_status", "validation_status", "recovery_status"),
    [
        ("QUARANTINED", "PASSED", "NORMAL"),
        ("REJECTED", "PASSED", "NORMAL"),
        ("READY", "FAILED", "NORMAL"),
        ("READY", "PASSED", "RECOVERY_MISSING_OBJECT"),
    ],
)
def test_dataset_download_rejects_blocked_exposure_states(
    dataset_status: str,
    validation_status: str,
    recovery_status: str,
) -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DatasetFakeObjectStorage()
    idempotency_key = f"idem-download-blocked-{dataset_status.lower()}-{validation_status.lower()}"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        with _session_scope(session_factory) as session:
            dataset = session.get(Dataset, dataset_id)
            assert dataset is not None
            dataset.status = dataset_status
            dataset.validation_status = validation_status
            dataset.recovery_status = recovery_status

        response = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/download-url",
            headers=_auth_headers("req-download-blocked"),
            json={},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "dataset.exposure_denied"
        assert storage.download_calls == []
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_dataset_download_requires_current_dataset_download_permission() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DatasetFakeObjectStorage()
    idempotency_key = "idem-dataset-download-denied"
    deny_grant_id = dev_seed_uuid("test-grant:deny-dataset-download-t09")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        with _session_scope(session_factory) as session:
            _upsert_grant(
                session,
                grant_id=deny_grant_id,
                resource_id=seed.project_id,
                permission_code="dataset.download",
                effect="DENY",
            )

        response = client.post(
            f"/v1/projects/{seed.project_id}/datasets/{created['dataset_id']}/download-url",
            headers=_auth_headers("req-download-denied"),
            json={},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "authorization.permission_denied"
        assert storage.download_calls == []
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)
        _delete_test_grants(session_factory, deny_grant_id)


def test_dataset_purge_requires_confirmation_and_retention_policy_approval() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DatasetFakeObjectStorage()
    idempotency_key = "idem-dataset-purge"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        deleted = client.delete(
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
            headers=_auth_headers("req-purge-delete"),
        )
        assert deleted.status_code == 200

        missing_confirmation = client.request(
            "DELETE",
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/purge",
            headers=_auth_headers("req-purge-no-confirm"),
            json={"confirm_purge": False},
        )
        assert missing_confirmation.status_code == 409
        assert missing_confirmation.json()["error"]["details"]["reason"] == "confirmation_required"
        assert storage.delete_calls == []

        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            assert policy is not None
            policy.retention_days = 30

        retention_denied = client.request(
            "DELETE",
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/purge",
            headers=_auth_headers("req-purge-retention"),
            json={"confirm_purge": True},
        )
        assert retention_denied.status_code == 409
        assert retention_denied.json()["error"]["details"]["reason"] == "retention_active"
        assert storage.delete_calls == []

        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            dataset = session.get(Dataset, dataset_id)
            assert policy is not None
            assert dataset is not None
            policy.retention_days = 0
            dataset.deleted_at = datetime.now(UTC) - timedelta(seconds=1)

        purged = client.request(
            "DELETE",
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/purge",
            headers=_auth_headers("req-purge-ok"),
            json={"confirm_purge": True},
        )
        assert purged.status_code == 200
        assert purged.json()["status"] == "PURGED"
        assert storage.delete_calls == [(created["bucket"], created["object_key"])]

        with _session_scope(session_factory) as session:
            denied_audits = session.scalars(
                select(AuditEvent).where(
                    AuditEvent.dataset_id == dataset_id,
                    AuditEvent.action == "dataset.purge",
                    AuditEvent.result == "DENIED",
                )
            ).all()
        assert {event.metadata_["reason"] for event in denied_audits} == {
            "confirmation_required",
            "retention_active",
        }
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_dataset_purge_rejects_object_lock_and_legal_hold_policy() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    idempotency_key = "idem-dataset-object-lock"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=DatasetFakeObjectStorage())
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        dataset_id = uuid.UUID(created["dataset_id"])
        assert (
            client.delete(
                f"/v1/projects/{seed.project_id}/datasets/{dataset_id}",
                headers=_auth_headers("req-lock-delete"),
            ).status_code
            == 200
        )
        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            dataset = session.get(Dataset, dataset_id)
            assert policy is not None
            assert dataset is not None
            policy.retention_days = None
            policy.object_lock_mode = "GOVERNANCE"
            dataset.deleted_at = datetime.now(UTC) - timedelta(days=1)

        response = client.request(
            "DELETE",
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/purge",
            headers=_auth_headers("req-lock-purge"),
            json={"confirm_purge": True},
        )
        assert response.status_code == 409
        assert response.json()["error"]["details"]["reason"] == "object_lock"

        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            assert policy is not None
            policy.object_lock_mode = None
            policy.legal_hold_default = True

        legal_hold = client.request(
            "DELETE",
            f"/v1/projects/{seed.project_id}/datasets/{dataset_id}/purge",
            headers=_auth_headers("req-legal-hold-purge"),
            json={"confirm_purge": True},
        )
        assert legal_hold.status_code == 409
        assert legal_hold.json()["error"]["details"]["reason"] == "legal_hold"
    finally:
        with _session_scope(session_factory) as session:
            policy = session.get(StoragePolicy, seed.storage_policy_id)
            if policy is not None:
                policy.object_lock_mode = None
                policy.legal_hold_default = False
        _delete_upload_artifacts(session_factory, idempotency_key)


def test_tag_category_and_tag_crud_and_dataset_tag_update() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = DatasetFakeObjectStorage()
    idempotency_key = "idem-dataset-tags"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_ready_dataset(client, session_factory, seed.project_id, idempotency_key)
        category = client.post(
            f"/v1/projects/{seed.project_id}/tag-categories",
            headers=_auth_headers("req-tag-category-create"),
            json={"name": "sensor", "color": "#3366ff", "sort_order": 10},
        )
        assert category.status_code == 201
        category_id = category.json()["category_id"]

        tag = client.post(
            f"/v1/projects/{seed.project_id}/tags",
            headers=_auth_headers("req-tag-create"),
            json={"name": "front-camera", "category_id": category_id, "color": "#ff6633"},
        )
        assert tag.status_code == 201
        tag_id = tag.json()["tag_id"]

        updated_dataset = client.patch(
            f"/v1/projects/{seed.project_id}/datasets/{created['dataset_id']}",
            headers=_auth_headers("req-dataset-tag-attach"),
            json={"tag_ids": [tag_id]},
        )
        assert updated_dataset.status_code == 200
        assert updated_dataset.json()["tag_ids"] == [tag_id]

        tags = client.get(
            f"/v1/projects/{seed.project_id}/tags",
            headers=_auth_headers("req-tag-list"),
        )
        assert tags.status_code == 200
        assert tag_id in {item["tag_id"] for item in tags.json()["tags"]}

        deleted = client.delete(
            f"/v1/projects/{seed.project_id}/tags/{tag_id}",
            headers=_auth_headers("req-tag-delete"),
        )
        assert deleted.status_code == 204
    finally:
        _delete_tag_artifacts(session_factory)
        _delete_upload_artifacts(session_factory, idempotency_key)


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


def _delete_tag_artifacts(session_factory: sessionmaker[Session]) -> None:
    with _session_scope(session_factory) as session:
        session.execute(delete(DatasetTag))
        session.execute(delete(Tag))
        session.execute(delete(TagCategory))


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
            session.execute(delete(AuditEvent).where(AuditEvent.dataset_id.in_(dataset_ids)))
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
