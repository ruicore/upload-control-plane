from __future__ import annotations

import uuid
from abc import abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.application.errors import ApiError
from upload_control_plane.application.upload_sessions.contracts import (
    ListRuntimePartsResult,
    PartListSource,
    RuntimePartState,
)
from upload_control_plane.application.upload_sessions.part_records import UploadPartStore
from upload_control_plane.domain.parts import get_part_range
from upload_control_plane.domain.session_state import UploadSessionStatus
from upload_control_plane.domain.storage import (
    ListedPart,
    ListPartsRequest,
    ObjectStorage,
    StorageError,
)
from upload_control_plane.infrastructure.db.models import UploadPart, UploadSession


class UploadSessionPartObservationMixin:
    """Part observation and storage reconciliation responsibilities."""

    if TYPE_CHECKING:

        @property
        @abstractmethod
        def _session(self) -> Session: ...

        @property
        @abstractmethod
        def _storage(self) -> ObjectStorage: ...

        _part_store: UploadPartStore

        def __getattr__(self, name: str) -> Any: ...
    else:

        def __getattr__(self, name: str) -> Any:
            """Declare facade-provided dependencies for static mixin checking."""
            raise AttributeError(name)

    def list_parts(
        self,
        *,
        tenant_id: uuid.UUID,
        actor: AuthenticatedActor,
        session_id: uuid.UUID,
        source: PartListSource,
        request_id: str,
    ) -> ListRuntimePartsResult:
        upload_session = self._get_session(tenant_id=tenant_id, session_id=session_id)
        storage_observed: tuple[RuntimePartState, ...] | None = None
        terminal_session = UploadSessionStatus(upload_session.status) in {
            UploadSessionStatus.COMPLETED,
            UploadSessionStatus.ABORTED,
            UploadSessionStatus.FAILED,
            UploadSessionStatus.EXPIRED,
        }
        if source in {"storage", "reconcile"} and not (source == "reconcile" and terminal_session):
            storage_observed = self._observe_storage_parts(
                upload_session=upload_session,
                actor=actor,
                request_id=request_id,
                reconcile=source == "reconcile",
            )
        if source == "storage":
            parts = storage_observed or ()
            uploaded_part_count = len(parts)
            uploaded_part_numbers = {part.part_number for part in parts}
        else:
            db_parts = self._part_store.load(upload_session.id)
            parts = tuple(self._part_result(part) for part in db_parts)
            uploaded_part_count = len([part for part in db_parts if part.status == "UPLOADED"])
            uploaded_part_numbers = {
                part.part_number for part in db_parts if part.status == "UPLOADED"
            }
        if source == "reconcile":
            upload_session.uploaded_part_count = uploaded_part_count
            upload_session.updated_at = datetime.now(UTC)
            self._session.commit()
        missing = tuple(
            part_number
            for part_number in range(1, upload_session.part_count + 1)
            if part_number not in uploaded_part_numbers
        )
        return ListRuntimePartsResult(
            session_id=upload_session.id,
            source=source,
            part_count=upload_session.part_count,
            uploaded_part_count=uploaded_part_count,
            missing_part_numbers=missing,
            parts=parts,
        )

    def _observe_storage_parts(
        self,
        *,
        upload_session: UploadSession,
        actor: AuthenticatedActor,
        request_id: str,
        reconcile: bool,
    ) -> tuple[RuntimePartState, ...]:
        if upload_session.storage_upload_id is None:
            raise ApiError(
                status_code=409,
                code="upload.storage_upload_missing",
                message="Upload session has no storage multipart upload ID.",
            )

        observed_parts: list[ListedPart] = []
        marker: int | None = None
        try:
            while True:
                page = self._storage.list_parts(
                    ListPartsRequest(
                        bucket=upload_session.bucket_name,
                        object_key=upload_session.object_key,
                        upload_id=upload_session.storage_upload_id,
                        part_number_marker=marker,
                    )
                )
                observed_parts.extend(page.parts)
                if not page.is_truncated:
                    break
                marker = page.next_part_number_marker
                if marker is None:
                    break
        except StorageError as exc:
            raise ApiError(
                status_code=502,
                code="storage.list_parts_failed",
                message="Storage ListParts failed.",
                details={"operation": exc.operation, "provider_code": exc.provider_code},
            ) from exc

        if reconcile:
            now = datetime.now(UTC)
            for observed in observed_parts:
                self._part_store.upsert(
                    upload_session=upload_session,
                    part_number=observed.part_number,
                    status="UPLOADED",
                    now=now,
                    etag=observed.etag,
                    size_bytes=observed.size_bytes,
                    checksum_sha256=observed.checksum.get("sha256"),
                    uploaded_at=observed.last_modified or now,
                    source="storage",
                )
            self._add_event(
                upload_session,
                actor=actor,
                request_id=request_id,
                event_type="upload.parts_reconciled",
                payload={"observed_part_numbers": [part.part_number for part in observed_parts]},
            )
        return tuple(self._storage_part_result(upload_session, part) for part in observed_parts)

    def _part_result(self, part: UploadPart) -> RuntimePartState:
        return RuntimePartState(
            part_number=part.part_number,
            etag=part.etag,
            size_bytes=part.size_bytes,
            status=part.status,
            uploaded_at=part.uploaded_at,
            expected_size_bytes=part.expected_size_bytes,
            offset_start=part.offset_start,
            offset_end_exclusive=part.offset_end_exclusive,
            last_presigned_at=part.last_presigned_at,
            presign_expires_at=part.presign_expires_at,
        )

    def _storage_part_result(
        self,
        upload_session: UploadSession,
        part: ListedPart,
    ) -> RuntimePartState:
        part_range = get_part_range(
            upload_session.file_size_bytes,
            upload_session.part_size_bytes,
            part.part_number,
        )
        return RuntimePartState(
            part_number=part.part_number,
            etag=part.etag,
            size_bytes=part.size_bytes,
            status="UPLOADED",
            uploaded_at=part.last_modified,
            expected_size_bytes=part_range.expected_size,
            offset_start=part_range.offset_start,
            offset_end_exclusive=part_range.offset_end_exclusive,
            last_presigned_at=None,
            presign_expires_at=None,
        )
