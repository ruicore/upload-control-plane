from __future__ import annotations

import uuid

from _upload_session_runtime_support import (
    RuntimeFakeObjectStorage,
    _auth_headers,
    _client,
    _create_upload_task,
    _created_object,
    _db_session_factory_or_skip,
    _delete_test_grants,
    _delete_upload_artifacts,
    _session_scope,
    _upsert_grant,
)
from sqlalchemy import select

from upload_control_plane.config import get_settings
from upload_control_plane.domain.parts import DEFAULT_PART_SIZE
from upload_control_plane.domain.storage import ListedPart, StorageChecksumMismatchError
from upload_control_plane.infrastructure.db.models import (
    Dataset,
    IdempotencyRecord,
    OutboxEvent,
    UploadEvent,
    UploadObject,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import (
    build_dev_seed_result,
    dev_seed_uuid,
    seed_dev_data,
)


def test_complete_re_evaluates_current_permissions_after_part_upload() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(part_number=1, etag='"storage-etag-1"', size_bytes=DEFAULT_PART_SIZE),
    )
    idempotency_key = "idem-runtime-complete-permission-revoked"
    deny_grant = dev_seed_uuid("test-grant:runtime-deny-upload-complete")
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])
        with _session_scope(session_factory) as session:
            _upsert_grant(
                session,
                grant_id=deny_grant,
                resource_id=uuid.UUID(_created_object(created)["dataset_id"]),
                resource_type="dataset",
                permission_code="upload.complete",
                effect="DENY",
            )

        response = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={
                **_auth_headers("req-complete-permission-revoked"),
                "Idempotency-Key": "idem-complete-permission-revoked",
            },
            json={},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "authorization.permission_denied"
        assert storage.complete_calls == []
    finally:
        _delete_upload_artifacts(
            session_factory,
            idempotency_key,
            "idem-complete-permission-revoked",
        )
        _delete_test_grants(session_factory, deny_grant)


def test_complete_uses_storage_list_parts_not_db_ack_rows_for_missing_parts() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(part_number=1, etag='"storage-etag-1"', size_bytes=DEFAULT_PART_SIZE),
    )
    idempotency_key = "idem-runtime-complete-missing"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(
            client,
            seed.project_id,
            idempotency_key,
            file_size_bytes=DEFAULT_PART_SIZE * 2,
            part_size_bytes=DEFAULT_PART_SIZE,
        )
        session_id = uuid.UUID(_created_object(created)["session_id"])
        ack = client.post(
            f"/v1/uploads/{session_id}/parts/ack",
            headers=_auth_headers("req-ack-two-db-only"),
            json={
                "parts": [
                    {"part_number": 1, "etag": '"db-etag-1"', "size_bytes": DEFAULT_PART_SIZE},
                    {"part_number": 2, "etag": '"db-etag-2"', "size_bytes": DEFAULT_PART_SIZE},
                ]
            },
        )
        assert ack.status_code == 200

        complete = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={**_auth_headers("req-complete-missing"), "Idempotency-Key": "idem-missing"},
            json={},
        )

        assert complete.status_code == 409
        error = complete.json()["error"]
        assert error["code"] == "upload.missing_parts"
        assert error["details"]["missing_part_count"] == 1
        assert error["details"]["missing_part_numbers"] == [2]
        assert storage.list_calls
        assert storage.complete_calls == []
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            assert upload_session is not None
            assert upload_session.status == "UPLOADING"
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key, "idem-missing")


def test_complete_succeeds_from_storage_parts_without_db_ack_and_is_idempotent() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(part_number=1, etag='"storage-etag-1"', size_bytes=DEFAULT_PART_SIZE),
    )
    idempotency_key = "idem-runtime-complete-storage"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])

        first = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={**_auth_headers("req-complete-1"), "Idempotency-Key": "idem-complete"},
            json={},
        )
        assert first.status_code == 200
        body = first.json()
        assert body["status"] == "COMPLETED"
        assert body["etag"] == '"final-etag"'
        assert body["object_size_bytes"] == DEFAULT_PART_SIZE

        second = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={**_auth_headers("req-complete-2"), "Idempotency-Key": "idem-complete"},
            json={},
        )
        assert second.status_code == 200
        assert second.json() == body
        assert len(storage.complete_calls) == 1
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            dataset = session.get(Dataset, uuid.UUID(_created_object(created)["dataset_id"]))
            assert upload_session is not None
            assert dataset is not None
            assert upload_session.status == "COMPLETED"
            assert upload_session.object_etag == '"final-etag"'
            assert dataset.object_size_bytes == DEFAULT_PART_SIZE
    finally:
        _delete_upload_artifacts(session_factory, idempotency_key, "idem-complete")


def test_completed_session_with_fresh_idempotency_key_skips_storage() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(part_number=1, etag='"storage-etag-1"', size_bytes=DEFAULT_PART_SIZE),
    )
    idempotency_key = "idem-runtime-complete-fresh-key"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])

        first = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={
                **_auth_headers("req-complete-fresh-key-first"),
                "Idempotency-Key": "idem-complete-first",
            },
            json={},
        )
        assert first.status_code == 200
        list_call_count = len(storage.list_calls)
        complete_call_count = len(storage.complete_calls)

        replay = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={
                **_auth_headers("req-complete-fresh-key-replay"),
                "Idempotency-Key": "idem-complete-fresh",
            },
            json={},
        )

        assert replay.status_code == 200
        assert replay.json() == first.json()
        assert len(storage.list_calls) == list_call_count
        assert len(storage.complete_calls) == complete_call_count
        with _session_scope(session_factory) as session:
            record = session.scalars(
                select(IdempotencyRecord).where(IdempotencyRecord.key == "idem-complete-fresh")
            ).one()
            assert record.response_status == 200
    finally:
        _delete_upload_artifacts(
            session_factory,
            idempotency_key,
            "idem-complete-first",
            "idem-complete-fresh",
        )


def test_complete_missing_parts_restores_paused_session() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(part_number=1, etag='"storage-etag-1"', size_bytes=DEFAULT_PART_SIZE),
    )
    idempotency_key = "idem-runtime-complete-paused-missing"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(
            client,
            seed.project_id,
            idempotency_key,
            file_size_bytes=DEFAULT_PART_SIZE * 2,
            part_size_bytes=DEFAULT_PART_SIZE,
        )
        created_object = _created_object(created)
        session_id = uuid.UUID(created_object["session_id"])
        dataset_id = uuid.UUID(created_object["dataset_id"])
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            assert upload_session is not None
            upload_session.status = "PAUSED"

        response = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={
                **_auth_headers("req-complete-paused-missing"),
                "Idempotency-Key": "idem-complete-paused-missing",
            },
            json={},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "upload.missing_parts"
        assert storage.complete_calls == []
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            dataset = session.get(Dataset, dataset_id)
            assert upload_session is not None
            assert dataset is not None
            assert upload_session.status == "PAUSED"
            assert upload_session.last_error_code == "upload.missing_parts"
            assert dataset.status == "PAUSED"
    finally:
        _delete_upload_artifacts(
            session_factory,
            idempotency_key,
            "idem-complete-paused-missing",
        )


def test_complete_rejects_wrong_sized_storage_part() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(
            part_number=1,
            etag='"storage-etag-1"',
            size_bytes=DEFAULT_PART_SIZE - 1,
        ),
    )
    idempotency_key = "idem-runtime-complete-size-mismatch"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        session_id = uuid.UUID(_created_object(created)["session_id"])

        response = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={
                **_auth_headers("req-complete-size-mismatch"),
                "Idempotency-Key": "idem-complete-size-mismatch",
            },
            json={},
        )

        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "upload.missing_parts"
        assert error["details"]["missing_part_count"] == 0
        assert error["details"]["size_mismatches"] == [
            {
                "part_number": 1,
                "expected_size_bytes": DEFAULT_PART_SIZE,
                "size_bytes": DEFAULT_PART_SIZE - 1,
            }
        ]
        assert storage.complete_calls == []
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            assert upload_session is not None
            assert upload_session.status == "UPLOADING"
    finally:
        _delete_upload_artifacts(
            session_factory,
            idempotency_key,
            "idem-complete-size-mismatch",
        )


def test_complete_success_updates_projections_and_records_events() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(part_number=1, etag='"storage-etag-1"', size_bytes=DEFAULT_PART_SIZE),
    )
    idempotency_key = "idem-runtime-complete-projections"
    checksum_sha256 = "a" * 64
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        created_object = _created_object(created)
        session_id = uuid.UUID(created_object["session_id"])
        dataset_id = uuid.UUID(created_object["dataset_id"])
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            assert upload_session is not None
            assert upload_session.upload_object_id is not None
            assert upload_session.upload_task_id is not None
            upload_object_id = upload_session.upload_object_id
            upload_task_id = upload_session.upload_task_id

        response = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={
                **_auth_headers("req-complete-projections"),
                "Idempotency-Key": "idem-complete-projections",
            },
            json={"checksum_sha256": checksum_sha256},
        )

        assert response.status_code == 200
        assert storage.complete_calls[-1].checksum == {"sha256": checksum_sha256}
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            upload_object = session.get(UploadObject, upload_object_id)
            upload_task = session.get(UploadTask, upload_task_id)
            dataset = session.get(Dataset, dataset_id)
            assert upload_session is not None
            assert upload_object is not None
            assert upload_task is not None
            assert dataset is not None
            assert upload_session.status == "COMPLETED"
            assert upload_session.completed_part_count == 1
            assert upload_object.status == "COMPLETED"
            assert upload_object.completed_at is not None
            assert upload_task.status == "COMPLETED"
            assert upload_task.completed_object_count == 1
            assert upload_task.completed_at is not None
            assert dataset.status == "PROCESSING"
            assert dataset.object_etag == '"final-etag"'
            assert dataset.object_size_bytes == DEFAULT_PART_SIZE
            events = list(
                session.scalars(
                    select(UploadEvent)
                    .where(UploadEvent.session_id == session_id)
                    .where(
                        UploadEvent.event_type.in_(
                            ("upload.complete_requested", "upload.completed")
                        )
                    )
                    .order_by(UploadEvent.created_at.asc())
                )
            )
            assert [event.event_type for event in events] == [
                "upload.complete_requested",
                "upload.completed",
            ]
            assert [event.actor_type for event in events] == ["api_key", "api_key"]
            assert [event.actor_id for event in events] == [
                str(seed.api_key_id),
                str(seed.api_key_id),
            ]
            assert [event.request_id for event in events] == [
                "req-complete-projections",
                "req-complete-projections",
            ]
            assert [event.payload for event in events] == [
                {"checksum_sha256": checksum_sha256},
                {
                    "etag": '"final-etag"',
                    "object_size_bytes": DEFAULT_PART_SIZE,
                    "object_version_id": None,
                },
            ]
            assert all(event.created_at is not None for event in events)
            assert (
                session.scalar(
                    select(OutboxEvent).where(
                        (OutboxEvent.aggregate_id == session_id)
                        & OutboxEvent.event_type.in_(
                            ("upload.complete_requested", "upload.completed")
                        )
                    )
                )
                is None
            )
    finally:
        _delete_upload_artifacts(
            session_factory,
            idempotency_key,
            "idem-complete-projections",
        )


def test_storage_native_checksum_mismatch_does_not_mark_dataset_ready() -> None:
    session_factory = _db_session_factory_or_skip()
    seed = build_dev_seed_result()
    storage = RuntimeFakeObjectStorage()
    storage.listed_parts = (
        ListedPart(
            part_number=1,
            etag='"storage-etag-1"',
            size_bytes=DEFAULT_PART_SIZE,
            checksum={"sha256": "a" * 64},
        ),
    )
    storage.complete_error = StorageChecksumMismatchError(
        "BadDigest",
        operation="complete_multipart_upload",
        provider_code="BadDigest",
    )
    idempotency_key = "idem-runtime-checksum-mismatch"
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())

    try:
        client = _client(session_factory, storage=storage)
        created = _create_upload_task(client, seed.project_id, idempotency_key)
        created_object = _created_object(created)
        session_id = uuid.UUID(created_object["session_id"])
        dataset_id = uuid.UUID(created_object["dataset_id"])

        response = client.post(
            f"/v1/uploads/{session_id}/complete",
            headers={
                **_auth_headers("req-complete-checksum-mismatch"),
                "Idempotency-Key": "idem-complete-checksum-mismatch",
            },
            json={"checksum_sha256": "b" * 64},
        )

        assert response.status_code == 502
        assert response.json()["error"]["code"] == "storage.complete_failed"
        assert response.json()["error"]["details"]["provider_code"] == "BadDigest"
        with _session_scope(session_factory) as session:
            upload_session = session.get(UploadSession, session_id)
            dataset = session.get(Dataset, dataset_id)
            assert upload_session is not None
            assert dataset is not None
            assert upload_session.status == "INITIATED"
            assert upload_session.last_error_code == "storage.complete_failed"
            assert dataset.status == "UPLOAD_PENDING"
            assert dataset.object_etag is None
    finally:
        _delete_upload_artifacts(
            session_factory,
            idempotency_key,
            "idem-complete-checksum-mismatch",
        )
