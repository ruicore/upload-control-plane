from __future__ import annotations

import uuid
from abc import abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.application.errors import ApiError
from upload_control_plane.application.storage_backpressure import reject_if_storage_backpressure
from upload_control_plane.application.upload_sessions.contracts import (
    AckUploadedPartsInput,
    AckUploadedPartsResult,
    PresignedRuntimePart,
    PresignRuntimePartsResult,
    RuntimeUploadSession,
)
from upload_control_plane.application.upload_sessions.part_records import UploadPartStore
from upload_control_plane.config import Settings
from upload_control_plane.domain.parts import get_part_range
from upload_control_plane.domain.session_state import UploadSessionStatus, can_presign
from upload_control_plane.domain.storage import (
    ObjectStorage,
    PresignUploadPartRequest,
    StorageError,
)
from upload_control_plane.infrastructure.db.models import UploadSession


class UploadSessionPartsMixin:
    """Paired part commands and upload-session status responsibilities."""

    if TYPE_CHECKING:

        @property
        @abstractmethod
        def _session(self) -> Session: ...

        @property
        @abstractmethod
        def _storage(self) -> ObjectStorage: ...

        @property
        @abstractmethod
        def _settings(self) -> Settings: ...

        _part_store: UploadPartStore

        def __getattr__(self, name: str) -> Any: ...
    else:

        def __getattr__(self, name: str) -> Any:
            """Declare facade-provided dependencies for static mixin checking."""
            raise AttributeError(name)

    def get_upload_session(
        self,
        *,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> RuntimeUploadSession:
        upload_session = self._get_session(tenant_id=tenant_id, session_id=session_id)
        uploaded_part_count = self._part_store.uploaded_count(upload_session.id)
        if upload_session.uploaded_part_count != uploaded_part_count:
            upload_session.uploaded_part_count = uploaded_part_count
            upload_session.updated_at = datetime.now(UTC)
            self._session.commit()
        return self._session_result(upload_session, uploaded_part_count)

    def presign_parts(
        self,
        *,
        tenant_id: uuid.UUID,
        actor: AuthenticatedActor,
        session_id: uuid.UUID,
        part_numbers: tuple[int, ...],
        expires_in_seconds: int,
        request_id: str,
    ) -> PresignRuntimePartsResult:
        upload_session = self._get_session(tenant_id=tenant_id, session_id=session_id)
        status = UploadSessionStatus(upload_session.status)
        if not can_presign(status):
            raise ApiError(
                status_code=409,
                code="upload.invalid_state",
                message="Upload session is not in a state that allows presigning parts.",
                details={"status": upload_session.status},
            )
        if upload_session.storage_upload_id is None:
            raise ApiError(
                status_code=409,
                code="upload.storage_upload_missing",
                message="Upload session has no storage multipart upload ID.",
            )
        reject_if_storage_backpressure(self._settings)

        bounded_expiry = min(expires_in_seconds, self._settings.max_presign_expiry_seconds)
        now = datetime.now(UTC)
        presigned_parts: list[PresignedRuntimePart] = []
        try:
            for part_number in part_numbers:
                part_range = get_part_range(
                    upload_session.file_size_bytes,
                    upload_session.part_size_bytes,
                    part_number,
                )
                presigned = self._storage.presign_upload_part(
                    PresignUploadPartRequest(
                        bucket=upload_session.bucket_name,
                        object_key=upload_session.object_key,
                        upload_id=upload_session.storage_upload_id,
                        part_number=part_number,
                        expires_in_seconds=bounded_expiry,
                    )
                )
                self._part_store.upsert(
                    upload_session=upload_session,
                    part_number=part_number,
                    status="PRESIGNED",
                    now=now,
                    last_presigned_at=now,
                    presign_expires_at=presigned.expires_at,
                    preserve_uploaded=True,
                )
                presigned_parts.append(
                    PresignedRuntimePart(
                        part_number=part_number,
                        url=presigned.url,
                        expected_size_bytes=part_range.expected_size,
                        offset_start=part_range.offset_start,
                        offset_end_exclusive=part_range.offset_end_exclusive,
                        required_headers=dict(presigned.required_headers),
                    )
                )
        except StorageError as exc:
            raise ApiError(
                status_code=502,
                code="storage.presign_failed",
                message="Storage presign failed.",
                details={"operation": exc.operation, "provider_code": exc.provider_code},
            ) from exc

        if upload_session.status == UploadSessionStatus.INITIATED.value:
            upload_session.status = UploadSessionStatus.UPLOADING.value
        upload_session.updated_at = now
        updated_parts = [
            part
            for part in self._part_store.load(upload_session.id)
            if part.part_number in part_numbers
        ]
        self._add_event(
            upload_session,
            actor=actor,
            request_id=request_id,
            event_type="upload.presign_issued",
            payload={
                "part_numbers": list(part_numbers),
                "expires_at": min(
                    part.presign_expires_at for part in updated_parts if part.presign_expires_at
                ).isoformat(),
            },
        )
        self._session.commit()
        expires_at = min(
            part.presign_expires_at for part in updated_parts if part.presign_expires_at
        )
        return PresignRuntimePartsResult(
            session_id=upload_session.id,
            method="PUT",
            expires_at=expires_at,
            parts=tuple(presigned_parts),
        )

    def ack_uploaded_parts(
        self,
        *,
        tenant_id: uuid.UUID,
        actor: AuthenticatedActor,
        session_id: uuid.UUID,
        parts: tuple[AckUploadedPartsInput, ...],
        request_id: str,
    ) -> AckUploadedPartsResult:
        upload_session = self._get_session(tenant_id=tenant_id, session_id=session_id)
        status = UploadSessionStatus(upload_session.status)
        if status in {
            UploadSessionStatus.COMPLETING,
            UploadSessionStatus.COMPLETED,
            UploadSessionStatus.ABORTING,
            UploadSessionStatus.ABORTED,
            UploadSessionStatus.FAILED,
        }:
            raise ApiError(
                status_code=409,
                code="upload.invalid_state",
                message="Upload session is not in a state that allows acknowledging parts.",
                details={"status": upload_session.status},
            )

        now = datetime.now(UTC)
        for item in parts:
            part_range = get_part_range(
                upload_session.file_size_bytes,
                upload_session.part_size_bytes,
                item.part_number,
            )
            if item.size_bytes != part_range.expected_size:
                raise ApiError(
                    status_code=422,
                    code="upload_part.size_mismatch",
                    message="Acknowledged part size does not match the expected byte range.",
                    details={
                        "part_number": item.part_number,
                        "expected_size_bytes": part_range.expected_size,
                        "size_bytes": item.size_bytes,
                    },
                )
            self._part_store.upsert(
                upload_session=upload_session,
                part_number=item.part_number,
                status="UPLOADED",
                now=now,
                etag=item.etag,
                size_bytes=item.size_bytes,
                checksum_sha256=item.checksum_sha256,
                uploaded_at=now,
                source="db",
            )

        if upload_session.status == UploadSessionStatus.INITIATED.value:
            upload_session.status = UploadSessionStatus.UPLOADING.value
        uploaded_part_count = self._part_store.uploaded_count(upload_session.id)
        upload_session.uploaded_part_count = uploaded_part_count
        upload_session.updated_at = now
        self._add_event(
            upload_session,
            actor=actor,
            request_id=request_id,
            event_type="upload.part_acknowledged",
            payload={"part_numbers": [item.part_number for item in parts]},
        )
        self._session.commit()
        return AckUploadedPartsResult(
            session_id=upload_session.id,
            acknowledged_part_count=len(parts),
            uploaded_part_count=uploaded_part_count,
        )

    def _session_result(
        self,
        upload_session: UploadSession,
        uploaded_part_count: int,
    ) -> RuntimeUploadSession:
        return RuntimeUploadSession(
            session_id=upload_session.id,
            project_id=upload_session.project_id,
            dataset_id=upload_session.dataset_id,
            status=upload_session.status,
            bucket=upload_session.bucket_name,
            object_key=upload_session.object_key,
            original_filename=upload_session.original_filename,
            file_size_bytes=upload_session.file_size_bytes,
            part_size_bytes=upload_session.part_size_bytes,
            part_count=upload_session.part_count,
            uploaded_part_count=uploaded_part_count,
            missing_part_count=upload_session.part_count - uploaded_part_count,
            paused_at=self._paused_at(upload_session),
            pause_reason=self._pause_reason(upload_session),
            expires_at=upload_session.expires_at,
            created_at=upload_session.created_at,
            updated_at=upload_session.updated_at,
        )
