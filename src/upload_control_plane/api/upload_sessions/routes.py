from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import DB_SESSION, AuthenticatedActor, require_api_key
from upload_control_plane.api.request_context import get_request_id
from upload_control_plane.api.upload_sessions.mappers import (
    _abort_response,
    _ack_response,
    _complete_response,
    _list_parts_response,
    _pause_response,
    _presign_response,
    _resume_response,
    _status_response,
)
from upload_control_plane.api.upload_sessions.permissions import (
    _load_owned_session,
    _require_runtime_permission,
    _resolve_part_numbers,
)
from upload_control_plane.api.upload_sessions.schemas import (
    AbortUploadSessionRequest,
    AbortUploadSessionResponse,
    AckPartsRequest,
    AckPartsResponse,
    CompleteUploadSessionRequest,
    CompleteUploadSessionResponse,
    ListPartsResponse,
    PauseUploadSessionRequest,
    PauseUploadSessionResponse,
    PresignPartsRequest,
    PresignPartsResponse,
    ResumeUploadSessionRequest,
    ResumeUploadSessionResponse,
    UploadSessionStatusResponse,
)
from upload_control_plane.api.upload_tasks import OBJECT_STORAGE, SETTINGS_DEPENDENCY
from upload_control_plane.application.upload_sessions import (
    AckUploadedPartsInput,
    PartListSource,
    UploadSessionRuntimeService,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.storage import ObjectStorage

router = APIRouter(prefix="/v1/uploads", tags=["upload-sessions"])
AUTH_ACTOR = Depends(require_api_key)
IDEMPOTENCY_KEY_HEADER = Header(default=None, alias="Idempotency-Key")


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


@router.post("/{session_id}/pause", response_model=PauseUploadSessionResponse)
def pause_upload_session(
    session_id: uuid.UUID,
    request: PauseUploadSessionRequest,
    fastapi_request: Request,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
    idempotency_key: str | None = IDEMPOTENCY_KEY_HEADER,
) -> PauseUploadSessionResponse:
    upload_session = _load_owned_session(session, actor, session_id)
    _require_runtime_permission(
        session,
        actor=actor,
        upload_session=upload_session,
        permission_codes=("upload.pause",),
    )
    service = UploadSessionRuntimeService(session=session, storage=storage, settings=settings)
    result = service.pause_upload_session(
        tenant_id=actor.tenant_id,
        actor=actor,
        session_id=session_id,
        request_path=fastapi_request.url.path,
        request_body=request.model_dump(mode="json"),
        idempotency_key=idempotency_key,
        request_id=get_request_id(),
        reason=request.reason,
        client_inflight_behavior=request.client_inflight_behavior,
    )
    return _pause_response(result)


@router.post("/{session_id}/resume", response_model=ResumeUploadSessionResponse)
def resume_upload_session(
    session_id: uuid.UUID,
    request: ResumeUploadSessionRequest,
    fastapi_request: Request,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
    idempotency_key: str | None = IDEMPOTENCY_KEY_HEADER,
) -> ResumeUploadSessionResponse:
    upload_session = _load_owned_session(session, actor, session_id)
    _require_runtime_permission(
        session,
        actor=actor,
        upload_session=upload_session,
        permission_codes=("upload.resume",),
    )
    service = UploadSessionRuntimeService(session=session, storage=storage, settings=settings)
    result = service.resume_upload_session(
        tenant_id=actor.tenant_id,
        actor=actor,
        session_id=session_id,
        request_path=fastapi_request.url.path,
        request_body=request.model_dump(mode="json"),
        idempotency_key=idempotency_key,
        request_id=get_request_id(),
        reason=request.reason,
    )
    return _resume_response(result)


@router.post("/{session_id}/complete", response_model=CompleteUploadSessionResponse)
def complete_upload_session(
    session_id: uuid.UUID,
    request: CompleteUploadSessionRequest,
    fastapi_request: Request,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
    idempotency_key: str | None = IDEMPOTENCY_KEY_HEADER,
) -> CompleteUploadSessionResponse:
    upload_session = _load_owned_session(session, actor, session_id)
    _require_runtime_permission(
        session,
        actor=actor,
        upload_session=upload_session,
        permission_codes=("upload.complete",),
    )
    service = UploadSessionRuntimeService(session=session, storage=storage, settings=settings)
    result = service.complete_upload_session(
        tenant_id=actor.tenant_id,
        actor=actor,
        session_id=session_id,
        request_path=fastapi_request.url.path,
        request_body=request.model_dump(mode="json"),
        idempotency_key=idempotency_key,
        request_id=get_request_id(),
        checksum_sha256=request.checksum_sha256,
    )
    return _complete_response(result)


@router.post("/{session_id}/abort", response_model=AbortUploadSessionResponse)
def abort_upload_session(
    session_id: uuid.UUID,
    request: AbortUploadSessionRequest,
    fastapi_request: Request,
    actor: AuthenticatedActor = AUTH_ACTOR,
    session: Session = DB_SESSION,
    settings: Settings = SETTINGS_DEPENDENCY,
    storage: ObjectStorage = OBJECT_STORAGE,
    idempotency_key: str | None = IDEMPOTENCY_KEY_HEADER,
) -> AbortUploadSessionResponse:
    upload_session = _load_owned_session(session, actor, session_id)
    _require_runtime_permission(
        session,
        actor=actor,
        upload_session=upload_session,
        permission_codes=("upload.abort",),
    )
    service = UploadSessionRuntimeService(session=session, storage=storage, settings=settings)
    result = service.abort_upload_session(
        tenant_id=actor.tenant_id,
        actor=actor,
        session_id=session_id,
        request_path=fastapi_request.url.path,
        request_body=request.model_dump(mode="json"),
        idempotency_key=idempotency_key,
        request_id=get_request_id(),
        reason=request.reason,
    )
    return _abort_response(result)
