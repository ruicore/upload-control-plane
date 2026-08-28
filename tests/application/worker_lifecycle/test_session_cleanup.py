from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from upload_control_plane.application.worker_lifecycle import WorkerLifecycleService
from upload_control_plane.config import get_settings
from upload_control_plane.domain.storage import AbortMultipartUploadRequest, StorageError
from upload_control_plane.infrastructure.db.models import (
    Dataset,
    IdempotencyRecord,
    OutboxEvent,
    UploadEvent,
    UploadObject,
    UploadSession,
    UploadTask,
)
from upload_control_plane.infrastructure.db.seed import seed_dev_data

from .support import (
    WorkerFakeObjectStorage,
    _db_session_factory_or_skip,
    _delete_lifecycle_test_artifacts,
    _insert_upload_graph,
    _session_scope,
    _test_settings,
)


def test_expired_session_transitions_to_aborted_and_is_retry_safe() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_lifecycle_test_artifacts(session)
        ids = _insert_upload_graph(
            session, key="ucp-test-lifecycle-expired", status="PAUSED", expires_at=now
        )

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            assert service.expire_old_sessions(now=now + timedelta(seconds=1)) == 1
            upload_session = session.get(UploadSession, ids.session_id)
            assert upload_session is not None
            assert upload_session.status == "EXPIRED"

        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            summary = service.abort_expired_multipart_uploads(now=now + timedelta(seconds=2))
            assert summary.aborted_sessions == 1
            assert summary.errors == 0
            upload_session = session.get(UploadSession, ids.session_id)
            upload_task = session.get(UploadTask, ids.task_id)
            upload_object = session.get(UploadObject, ids.object_id)
            assert upload_session is not None
            assert upload_session.status == "ABORTED"
            assert upload_task is not None
            assert upload_task.status == "CANCELLED"
            assert upload_object is not None
            assert upload_object.status == "CANCELLED"

        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            rerun = service.run_once(now=now + timedelta(seconds=3))
            assert rerun.expired_sessions == 0
            assert rerun.aborted_sessions == 0
            events = list(
                session.scalars(
                    select(UploadEvent)
                    .where(UploadEvent.session_id == ids.session_id)
                    .order_by(UploadEvent.created_at.asc())
                )
            )
            assert [event.event_type for event in events] == [
                "upload.expired",
                "upload.abort_requested",
                "upload.aborted",
            ]
            assert [event.actor_type for event in events] == ["system", "system", "system"]
            assert [event.actor_id for event in events] == [
                "worker:lifecycle",
                "worker:lifecycle",
                "worker:lifecycle",
            ]
            assert [event.request_id for event in events] == [None, None, None]
            assert [event.payload for event in events] == [
                {
                    "previous_status": "PAUSED",
                    "expires_at": now.isoformat(),
                },
                {"reason": "expired_session_cleanup"},
                {"reason": "expired_session_cleanup"},
            ]
            assert [event.created_at for event in events] == [
                now + timedelta(seconds=1),
                now + timedelta(seconds=2),
                now + timedelta(seconds=2),
            ]
            outbox_events = list(
                session.scalars(
                    select(OutboxEvent)
                    .where(OutboxEvent.aggregate_id == ids.session_id)
                    .where(
                        OutboxEvent.event_type.in_(
                            ("upload.expired", "upload.abort_requested", "upload.aborted")
                        )
                    )
                    .order_by(OutboxEvent.created_at.asc())
                )
            )
            assert [event.event_type for event in outbox_events] == [
                "upload.expired",
                "upload.abort_requested",
                "upload.aborted",
            ]
            assert [event.payload["status"] for event in outbox_events] == [
                "EXPIRED",
                "ABORTING",
                "ABORTED",
            ]
            assert [event.payload["event"] for event in outbox_events] == [
                {
                    "previous_status": "PAUSED",
                    "expires_at": now.isoformat(),
                },
                {"reason": "expired_session_cleanup"},
                {"reason": "expired_session_cleanup"},
            ]
            assert [event.created_at for event in outbox_events] == [
                now + timedelta(seconds=1),
                now + timedelta(seconds=2),
                now + timedelta(seconds=2),
            ]
            assert [event.next_attempt_at for event in outbox_events] == [
                now + timedelta(seconds=1),
                now + timedelta(seconds=2),
                now + timedelta(seconds=2),
            ]
        assert storage.abort_calls == [
            (
                "robot-data",
                "ucp-test-lifecycle/ucp-test-lifecycle-expired.bin",
                "upload-ucp-test-lifecycle-expired",
            )
        ]
    finally:
        with _session_scope(session_factory) as session:
            _delete_lifecycle_test_artifacts(session)


def test_lifecycle_cleanup_preserves_unrelated_generic_job_prefixes() -> None:
    session_factory = _db_session_factory_or_skip()
    suffix = uuid.uuid4().hex
    now = datetime.now(UTC)
    owned_key = f"ucp-test-lifecycle-cleanup-counterexample-{suffix}"
    unrelated_key = f"job-unrelated-{suffix}"
    idempotency_record_id = uuid.uuid4()

    with session_factory() as session:
        seed_dev_data(session, get_settings())
        _delete_lifecycle_test_artifacts(session)
        owned_ids = _insert_upload_graph(
            session,
            key=owned_key,
            status="PAUSED",
            expires_at=now,
        )
        unrelated_ids = _insert_upload_graph(
            session,
            key=unrelated_key,
            status="PAUSED",
            expires_at=now,
        )
        session.flush()
        unrelated_dataset = session.get(Dataset, unrelated_ids.dataset_id)
        unrelated_session = session.get(UploadSession, unrelated_ids.session_id)
        assert unrelated_dataset is not None
        assert unrelated_session is not None
        unrelated_object_key = f"job/unrelated-{suffix}.bin"
        unrelated_dataset.object_key = unrelated_object_key
        unrelated_session.object_key = unrelated_object_key
        session.add(
            IdempotencyRecord(
                id=idempotency_record_id,
                tenant_id=unrelated_dataset.tenant_id,
                key=unrelated_key,
                request_method="POST",
                request_path="/unrelated-lifecycle-cleanup",
                request_fingerprint=f"unrelated-{suffix}",
                expires_at=now,
            )
        )
        session.flush()

        _delete_lifecycle_test_artifacts(session)
        session.flush()

        assert session.get(Dataset, owned_ids.dataset_id) is None
        assert session.get(UploadTask, owned_ids.task_id) is None
        assert session.get(Dataset, unrelated_ids.dataset_id) is not None
        assert session.get(UploadTask, unrelated_ids.task_id) is not None
        assert session.get(UploadSession, unrelated_ids.session_id) is not None
        assert session.get(IdempotencyRecord, idempotency_record_id) is not None
        assert unrelated_dataset.object_key == unrelated_object_key
        session.rollback()


def test_completed_session_is_not_aborted_by_expiry_worker() -> None:
    session_factory = _db_session_factory_or_skip()
    storage = WorkerFakeObjectStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_lifecycle_test_artifacts(session)
        ids = _insert_upload_graph(
            session, key="ucp-test-lifecycle-completed", status="COMPLETED", expires_at=now
        )

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session, storage=storage, settings=_test_settings()
            )
            summary = service.run_once(now=now + timedelta(days=1))
            upload_session = session.get(UploadSession, ids.session_id)
            assert upload_session is not None
            assert upload_session.status == "COMPLETED"
            assert summary.expired_sessions == 0
            assert summary.aborted_sessions == 0
        assert storage.abort_calls == []
        assert storage.delete_calls == []
    finally:
        with _session_scope(session_factory) as session:
            _delete_lifecycle_test_artifacts(session)


def test_expired_session_storage_abort_failure_remains_retryable_and_redacts_outbox() -> None:
    session_factory = _db_session_factory_or_skip()

    class FailingAbortStorage(WorkerFakeObjectStorage):
        def abort_multipart_upload(self, request: AbortMultipartUploadRequest) -> None:
            super().abort_multipart_upload(request)
            raise StorageError(
                "abort failed with secret-token",
                operation="abort_multipart_upload",
                provider_code="ServiceUnavailable",
                retryable=True,
            )

    storage = FailingAbortStorage()
    now = datetime.now(UTC)
    with _session_scope(session_factory) as session:
        seed_dev_data(session, get_settings())
        _delete_lifecycle_test_artifacts(session)
        ids = _insert_upload_graph(
            session,
            key="ucp-test-lifecycle-expired-error",
            status="PAUSED",
            expires_at=now,
        )

    try:
        with _session_scope(session_factory) as session:
            service = WorkerLifecycleService(
                session=session,
                storage=storage,
                settings=_test_settings(),
            )
            assert service.expire_old_sessions(now=now + timedelta(seconds=1)) == 1
            summary = service.abort_expired_multipart_uploads(now=now + timedelta(seconds=2))
            assert summary.aborted_sessions == 0
            assert summary.errors == 1

            upload_session = session.get(UploadSession, ids.session_id)
            upload_task = session.get(UploadTask, ids.task_id)
            upload_object = session.get(UploadObject, ids.object_id)
            assert upload_session is not None
            assert upload_session.status == "ABORTING"
            assert upload_session.last_error_code == "storage.abort_failed"
            assert upload_session.last_error_message == "abort failed with secret-token"
            assert upload_session.aborted_at is None
            assert upload_task is not None
            assert upload_task.status == "CANCELLED"
            assert upload_task.cancelled_at is None
            assert upload_object is not None
            assert upload_object.status == "CANCELLED"

            events = list(
                session.scalars(
                    select(UploadEvent)
                    .where(UploadEvent.session_id == ids.session_id)
                    .order_by(UploadEvent.created_at.asc())
                )
            )
            assert [event.event_type for event in events] == [
                "upload.expired",
                "upload.abort_requested",
                "upload.cleanup_failed",
            ]
            outbox = session.scalar(
                select(OutboxEvent).where(
                    (OutboxEvent.aggregate_id == ids.session_id)
                    & (OutboxEvent.event_type == "upload.cleanup_failed")
                )
            )
            assert outbox is not None
            assert outbox.payload["status"] == "ABORTING"
            assert outbox.payload["event"] == {
                "operation": "abort_multipart_upload",
                "provider_code": "ServiceUnavailable",
            }
            assert "secret-token" not in str(outbox.payload)
        assert storage.abort_calls == [
            (
                "robot-data",
                "ucp-test-lifecycle/ucp-test-lifecycle-expired-error.bin",
                "upload-ucp-test-lifecycle-expired-error",
            )
        ]
    finally:
        with _session_scope(session_factory) as session:
            _delete_lifecycle_test_artifacts(session)
