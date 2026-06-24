from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import DB_SESSION, AuthenticatedActor, require_api_key
from upload_control_plane.api.authorization import AuthorizationService
from upload_control_plane.api.request_context import get_request_id
from upload_control_plane.api.upload_tasks import OBJECT_STORAGE, SETTINGS_DEPENDENCY
from upload_control_plane.application.upload_sessions import (
    AckUploadedPartsInput,
    AckUploadedPartsResult,
    ListRuntimePartsResult,
    PartListSource,
    PresignRuntimePartsResult,
    RuntimeUploadSession,
    UploadSessionRuntimeService,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.permissions import ResourceType
from upload_control_plane.domain.storage import ObjectStorage
from upload_control_plane.infrastructure.db.models import UploadSession

router = APIRouter(prefix="/v1/uploads", tags=["upload-sessions"])
AUTH_ACTOR = Depends(require_api_key)


class UploadSessionStatusResponse(BaseModel):
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
    paused_at: None = None
    pause_reason: None = None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class PresignPartsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_numbers: list[int] | None = None
    part_number_start: int | None = Field(default=None, ge=1)
    part_number_end: int | None = Field(default=None, ge=1)
    expires_in_seconds: int = Field(default=900, gt=0)

    @field_validator("part_numbers")
    @classmethod
    def validate_part_numbers(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("part_numbers must not be empty")
        if any(part_number < 1 for part_number in value):
            raise ValueError("part_numbers must be positive")
        if len(set(value)) != len(value):
            raise ValueError("part_numbers must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_part_selection(self) -> PresignPartsRequest:
        has_list = self.part_numbers is not None
        has_range = self.part_number_start is not None or self.part_number_end is not None
        if has_list == has_range:
            raise ValueError("provide either part_numbers or part_number_start and part_number_end")
        if has_range and (self.part_number_start is None or self.part_number_end is None):
            raise ValueError("part_number_start and part_number_end must be provided together")
        if (
            self.part_number_start is not None
            and self.part_number_end is not None
            and self.part_number_end < self.part_number_start
        ):
            raise ValueError("part_number_end must be greater than or equal to part_number_start")
        return self


class PresignedPartResponse(BaseModel):
    part_number: int
    url: str
    expected_size_bytes: int
    offset_start: int
    offset_end_exclusive: int
    required_headers: dict[str, str]


class PresignPartsResponse(BaseModel):
    session_id: uuid.UUID
    method: Literal["PUT"]
    expires_at: datetime
    parts: list[PresignedPartResponse]


class AckUploadedPartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_number: int = Field(ge=1)
    etag: str = Field(min_length=1)
    size_bytes: int = Field(gt=0)
    checksum_sha256: str | None = Field(default=None, min_length=64, max_length=64)

    @field_validator("checksum_sha256")
    @classmethod
    def validate_checksum_sha256(cls, value: str | None) -> str | None:
        hex_characters = "0123456789abcdefABCDEF"
        if value is not None and any(character not in hex_characters for character in value):
            raise ValueError("checksum_sha256 must be a hex string")
        return value


class AckPartsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: list[AckUploadedPartRequest] = Field(min_length=1)

    @field_validator("parts")
    @classmethod
    def validate_unique_parts(
        cls,
        value: list[AckUploadedPartRequest],
    ) -> list[AckUploadedPartRequest]:
        part_numbers = [item.part_number for item in value]
        if len(set(part_numbers)) != len(part_numbers):
            raise ValueError("parts must not contain duplicate part numbers")
        return value


class AckPartsResponse(BaseModel):
    session_id: uuid.UUID
    acknowledged_part_count: int
    uploaded_part_count: int


class RuntimePartResponse(BaseModel):
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


class ListPartsResponse(BaseModel):
    session_id: uuid.UUID
    source: PartListSource
    part_count: int
    uploaded_part_count: int
    missing_part_numbers: list[int]
    parts: list[RuntimePartResponse]


@router.get("/{session_id}", response_model=UploadSessionStatusResponse)
def get_upload_session(
    session_id: uuid.UUID,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> UploadSessionStatusResponse:
    upload_session = _load_owned_session(session, actor, session_id)
    _require_runtime_permission(
        session,
        actor=actor,
        upload_session=upload_session,
        permission_codes=("project.view",),
    )
    service = UploadSessionRuntimeService(session=session, storage=storage, settings=settings)
    return _status_response(
        service.get_upload_session(tenant_id=actor.tenant_id, session_id=session_id)
    )


@router.post("/{session_id}/parts/presign", response_model=PresignPartsResponse)
def presign_parts(
    session_id: uuid.UUID,
    request: PresignPartsRequest,
    response: Response,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> PresignPartsResponse:
    upload_session = _load_owned_session(session, actor, session_id)
    _require_runtime_permission(
        session,
        actor=actor,
        upload_session=upload_session,
        permission_codes=("dataset.upload", "upload.create"),
    )
    part_numbers = _resolve_part_numbers(
        request,
        max_parts_per_request=settings.max_parts_per_presign_request,
        session_part_count=upload_session.part_count,
    )
    response.headers["Cache-Control"] = "no-store"
    service = UploadSessionRuntimeService(session=session, storage=storage, settings=settings)
    result = service.presign_parts(
        tenant_id=actor.tenant_id,
        actor=actor,
        session_id=session_id,
        part_numbers=part_numbers,
        expires_in_seconds=request.expires_in_seconds,
        request_id=get_request_id(),
    )
    return _presign_response(result)


@router.post("/{session_id}/parts/ack", response_model=AckPartsResponse)
def ack_parts(
    session_id: uuid.UUID,
    request: AckPartsRequest,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> AckPartsResponse:
    upload_session = _load_owned_session(session, actor, session_id)
    _require_runtime_permission(
        session,
        actor=actor,
        upload_session=upload_session,
        permission_codes=("dataset.upload", "upload.create"),
    )
    service = UploadSessionRuntimeService(session=session, storage=storage, settings=settings)
    result = service.ack_uploaded_parts(
        tenant_id=actor.tenant_id,
        actor=actor,
        session_id=session_id,
        parts=tuple(
            AckUploadedPartsInput(
                part_number=item.part_number,
                etag=item.etag,
                size_bytes=item.size_bytes,
                checksum_sha256=item.checksum_sha256,
            )
            for item in request.parts
        ),
        request_id=get_request_id(),
    )
    return _ack_response(result)


@router.get("/{session_id}/parts", response_model=ListPartsResponse)
def list_parts(
    session_id: uuid.UUID,
    source: PartListSource = "db",
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
) -> ListPartsResponse:
    upload_session = _load_owned_session(session, actor, session_id)
    _require_runtime_permission(
        session,
        actor=actor,
        upload_session=upload_session,
        permission_codes=("project.view",),
    )
    service = UploadSessionRuntimeService(session=session, storage=storage, settings=settings)
    result = service.list_parts(
        tenant_id=actor.tenant_id,
        actor=actor,
        session_id=session_id,
        source=source,
        request_id=get_request_id(),
    )
    return _list_parts_response(result)


def _load_owned_session(
    session: Session,
    actor: AuthenticatedActor,
    session_id: uuid.UUID,
) -> UploadSession:
    upload_session = session.get(UploadSession, session_id)
    if upload_session is None or upload_session.tenant_id != actor.tenant_id:
        from upload_control_plane.api.errors import ApiError

        raise ApiError(
            status_code=404,
            code="upload_session.not_found",
            message="Upload session not found.",
        )
    return upload_session


def _require_runtime_permission(
    session: Session,
    *,
    actor: AuthenticatedActor,
    upload_session: UploadSession,
    permission_codes: tuple[str, ...],
) -> tuple[str, ...]:
    authorization = AuthorizationService(session)
    if upload_session.dataset_id is not None:
        return authorization.require_any_permission(
            actor=actor,
            permission_codes=permission_codes,
            resource_type=ResourceType.DATASET,
            resource_id=upload_session.dataset_id,
        )
    if upload_session.project_id is None:
        from upload_control_plane.api.errors import ApiError

        raise ApiError(
            status_code=409,
            code="upload_session.authorization_target_missing",
            message="Upload session has no project or dataset authorization target.",
        )
    return authorization.require_any_permission(
        actor=actor,
        permission_codes=permission_codes,
        resource_type=ResourceType.PROJECT,
        resource_id=upload_session.project_id,
    )


def _resolve_part_numbers(
    request: PresignPartsRequest,
    *,
    max_parts_per_request: int,
    session_part_count: int,
) -> tuple[int, ...]:
    if request.part_numbers is not None:
        part_numbers = tuple(request.part_numbers)
    else:
        assert request.part_number_start is not None
        assert request.part_number_end is not None
        part_numbers = tuple(range(request.part_number_start, request.part_number_end + 1))
    if len(part_numbers) > max_parts_per_request:
        from upload_control_plane.api.errors import ApiError

        raise ApiError(
            status_code=413,
            code="upload_part.too_many_presign_parts",
            message="Too many part URLs requested.",
            details={"max_parts_per_request": max_parts_per_request},
        )
    invalid = [part_number for part_number in part_numbers if part_number > session_part_count]
    if invalid:
        from upload_control_plane.api.errors import ApiError

        raise ApiError(
            status_code=422,
            code="upload_part.part_number_out_of_range",
            message="Part number is outside the upload session part range.",
            details={"part_count": session_part_count, "invalid_part_numbers": invalid},
        )
    return part_numbers


def _status_response(result: RuntimeUploadSession) -> UploadSessionStatusResponse:
    return UploadSessionStatusResponse(
        session_id=result.session_id,
        project_id=result.project_id,
        dataset_id=result.dataset_id,
        status=result.status,
        bucket=result.bucket,
        object_key=result.object_key,
        original_filename=result.original_filename,
        file_size_bytes=result.file_size_bytes,
        part_size_bytes=result.part_size_bytes,
        part_count=result.part_count,
        uploaded_part_count=result.uploaded_part_count,
        missing_part_count=result.missing_part_count,
        expires_at=result.expires_at,
        created_at=result.created_at,
        updated_at=result.updated_at,
    )


def _presign_response(result: PresignRuntimePartsResult) -> PresignPartsResponse:
    return PresignPartsResponse(
        session_id=result.session_id,
        method="PUT",
        expires_at=result.expires_at,
        parts=[
            PresignedPartResponse(
                part_number=part.part_number,
                url=part.url,
                expected_size_bytes=part.expected_size_bytes,
                offset_start=part.offset_start,
                offset_end_exclusive=part.offset_end_exclusive,
                required_headers=part.required_headers,
            )
            for part in result.parts
        ],
    )


def _ack_response(result: AckUploadedPartsResult) -> AckPartsResponse:
    return AckPartsResponse(
        session_id=result.session_id,
        acknowledged_part_count=result.acknowledged_part_count,
        uploaded_part_count=result.uploaded_part_count,
    )


def _list_parts_response(result: ListRuntimePartsResult) -> ListPartsResponse:
    return ListPartsResponse(
        session_id=result.session_id,
        source=result.source,
        part_count=result.part_count,
        uploaded_part_count=result.uploaded_part_count,
        missing_part_numbers=list(result.missing_part_numbers),
        parts=[
            RuntimePartResponse(
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
            for part in result.parts
        ],
    )
