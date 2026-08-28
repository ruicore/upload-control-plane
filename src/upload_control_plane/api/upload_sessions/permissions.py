from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from upload_control_plane.api.auth import AuthenticatedActor
from upload_control_plane.api.authorization import AuthorizationService
from upload_control_plane.api.upload_sessions.schemas import PresignPartsRequest
from upload_control_plane.domain.permissions import ResourceType
from upload_control_plane.infrastructure.db.models import UploadSession


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
    if actor.actor_type == "device" and upload_session.source_device_id != actor.device_id:
        from upload_control_plane.api.errors import ApiError

        raise ApiError(
            status_code=403,
            code="device.session_not_authorized",
            message="Device credential is not authorized for this upload session.",
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
