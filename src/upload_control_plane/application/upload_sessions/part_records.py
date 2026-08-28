from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from upload_control_plane.domain.parts import get_part_range
from upload_control_plane.infrastructure.db.models import UploadPart, UploadSession


class UploadPartStore:
    """Persistence owner for upload-part records within an existing transaction."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(
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

    def uploaded_count(self, session_id: uuid.UUID) -> int:
        return int(
            self._session.execute(
                select(func.count())
                .select_from(UploadPart)
                .where(UploadPart.session_id == session_id)
                .where(UploadPart.status == "UPLOADED")
            ).scalar_one()
        )

    def load(self, session_id: uuid.UUID) -> list[UploadPart]:
        return list(
            self._session.scalars(
                select(UploadPart)
                .where(UploadPart.session_id == session_id)
                .order_by(UploadPart.part_number.asc())
            )
        )
