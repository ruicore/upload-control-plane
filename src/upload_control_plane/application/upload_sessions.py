from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import AuthenticatedActor
from upload_control_plane.api.errors import ApiError
from upload_control_plane.config import Settings
from upload_control_plane.domain.parts import get_part_range
from upload_control_plane.domain.session_state import UploadSessionStatus, can_presign
from upload_control_plane.domain.storage import (
    ListedPart,
    ListPartsRequest,
    ObjectStorage,
    PresignUploadPartRequest,
    StorageError,
)
from upload_control_plane.infrastructure.db.models import (
    UploadEvent,
    UploadPart,
    UploadSession,
)

PartListSource = Literal["db", "storage", "reconcile"]


@dataclass(frozen=True, slots=True)
class RuntimeUploadSession:
    session_id: uuid.UUID
    project_id: uuid.UUID | None
    dataset_id: uuid.UUID | None
    status: str
    bucket: str
    object_key: str
    original_filename: str
    file_size_bytes: int
    part_size_bytes: int
    part_count: int
    uploaded_part_count: int
    missing_part_count: int
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PresignedRuntimePart:
    part_number: int
    url: str
    expected_size_bytes: int
    offset_start: int
    offset_end_exclusive: int
    required_headers: dict[str, str]


@dataclass(frozen=True, slots=True)
class PresignRuntimePartsResult:
    session_id: uuid.UUID
    method: str
    expires_at: datetime
    parts: tuple[PresignedRuntimePart, ...]


@dataclass(frozen=True, slots=True)
class AckUploadedPartsInput:
    part_number: int
    etag: str
    size_bytes: int
    checksum_sha256: str | None


@dataclass(frozen=True, slots=True)
class AckUploadedPartsResult:
    session_id: uuid.UUID
    acknowledged_part_count: int
    uploaded_part_count: int


@dataclass(frozen=True, slots=True)
class RuntimePartState:
    part_number: int
    etag: str | None
    size_bytes: int | None
    status: str
    uploaded_at: datetime | None
    expected_size_bytes: int
    offset_start: int
    offset_end_exclusive: int
    last_presigned_at: datetime | None
    presign_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class ListRuntimePartsResult:
    session_id: uuid.UUID
    source: PartListSource
    part_count: int
    uploaded_part_count: int
    missing_part_numbers: tuple[int, ...]
    parts: tuple[RuntimePartState, ...]


class UploadSessionRuntimeService:
    """Application boundary for T06 upload session runtime operations."""

    def __init__(self, *, session: Session, storage: ObjectStorage, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings

    def get_upload_session(
        self,
        *,
        tenant_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> RuntimeUploadSession:
        upload_session = self._get_session(tenant_id=tenant_id, session_id=session_id)
        uploaded_part_count = self._uploaded_part_count(upload_session.id)
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
                self._upsert_part(
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
            part for part in self._load_parts(upload_session.id) if part.part_number in part_numbers
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
            self._upsert_part(
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
        uploaded_part_count = self._uploaded_part_count(upload_session.id)
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
        if source in {"storage", "reconcile"}:
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
            db_parts = self._load_parts(upload_session.id)
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

    def _get_session(self, *, tenant_id: uuid.UUID, session_id: uuid.UUID) -> UploadSession:
        upload_session = self._session.get(UploadSession, session_id)
        if upload_session is None or upload_session.tenant_id != tenant_id:
            raise ApiError(
                status_code=404,
                code="upload_session.not_found",
                message="Upload session not found.",
            )
        return upload_session

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
                self._upsert_part(
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

    def _upsert_part(
        self,
        *,
        upload_session: UploadSession,
        part_number: int,
        status: str,
        now: datetime,
        etag: str | None = None,
        size_bytes: int | None = None,
        checksum_sha256: str | None = None,
        last_presigned_at: datetime | None = None,
        presign_expires_at: datetime | None = None,
        uploaded_at: datetime | None = None,
        source: str = "db",
        preserve_uploaded: bool = False,
    ) -> UploadPart:
        part_range = get_part_range(
            upload_session.file_size_bytes,
            upload_session.part_size_bytes,
            part_number,
        )
        part = self._session.get(UploadPart, (upload_session.id, part_number))
        if part is None:
            part = UploadPart(
                session_id=upload_session.id,
                part_number=part_number,
                offset_start=part_range.offset_start,
                offset_end_exclusive=part_range.offset_end_exclusive,
                expected_size_bytes=part_range.expected_size,
                created_at=now,
            )
            self._session.add(part)
        part.offset_start = part_range.offset_start
        part.offset_end_exclusive = part_range.offset_end_exclusive
        part.expected_size_bytes = part_range.expected_size
        if not (preserve_uploaded and part.status == "UPLOADED"):
            part.status = status
        if etag is not None:
            part.etag = etag
        if size_bytes is not None:
            part.size_bytes = size_bytes
        if checksum_sha256 is not None:
            part.checksum_sha256 = checksum_sha256
        if last_presigned_at is not None:
            part.last_presigned_at = last_presigned_at
        if presign_expires_at is not None:
            part.presign_expires_at = presign_expires_at
        if uploaded_at is not None:
            part.uploaded_at = uploaded_at
        part.source = source
        part.updated_at = now
        self._session.flush()
        return part

    def _uploaded_part_count(self, session_id: uuid.UUID) -> int:
        return self._count(
            select(func.count())
            .select_from(UploadPart)
            .where(UploadPart.session_id == session_id)
            .where(UploadPart.status == "UPLOADED")
        )

    def _load_parts(self, session_id: uuid.UUID) -> list[UploadPart]:
        return list(
            self._session.scalars(
                select(UploadPart)
                .where(UploadPart.session_id == session_id)
                .order_by(UploadPart.part_number.asc())
            )
        )

    def _add_event(
        self,
        upload_session: UploadSession,
        *,
        actor: AuthenticatedActor,
        request_id: str,
        event_type: str,
        payload: dict[str, object],
    ) -> None:
        self._session.add(
            UploadEvent(
                tenant_id=upload_session.tenant_id,
                project_id=upload_session.project_id,
                dataset_id=upload_session.dataset_id,
                upload_task_id=upload_session.upload_task_id,
                upload_object_id=upload_session.upload_object_id,
                session_id=upload_session.id,
                event_type=event_type,
                actor_type="api_key",
                actor_id=str(actor.subject_id),
                request_id=request_id,
                payload=payload,
            )
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
            expires_at=upload_session.expires_at,
            created_at=upload_session.created_at,
            updated_at=upload_session.updated_at,
        )

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

    def _count(self, statement: Select[tuple[int]]) -> int:
        return int(self._session.execute(statement).scalar_one())
