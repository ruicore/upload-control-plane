from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from upload_control_plane.application.errors import ApiError
from upload_control_plane.domain.fingerprints import assert_json_value, generate_request_fingerprint
from upload_control_plane.infrastructure.db.models import IdempotencyRecord


def resolve_idempotency[T](
    session: Session,
    *,
    tenant_id: uuid.UUID,
    idempotency_key: str | None,
    request_path: str,
    request_body: dict[str, Any],
    result_loader: Callable[[dict[str, Any]], T],
) -> T | None:
    if idempotency_key is None:
        return None
    fingerprint = generate_request_fingerprint(
        method="POST",
        path=request_path,
        tenant_id=tenant_id,
        body=assert_json_value(request_body),
    )
    record = session.scalars(
        select(IdempotencyRecord)
        .where(IdempotencyRecord.tenant_id == tenant_id)
        .where(IdempotencyRecord.key == idempotency_key)
        .with_for_update()
    ).one_or_none()
    if record is None:
        session.add(
            IdempotencyRecord(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                key=idempotency_key,
                request_method="POST",
                request_path=request_path,
                request_fingerprint=fingerprint,
                response_status=None,
                response_body=None,
                locked_until=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        session.flush()
        return None
    if record.request_fingerprint != fingerprint:
        raise ApiError(
            status_code=409,
            code="idempotency.key_reused_with_different_request",
            message="Idempotency key was reused with a different request.",
        )
    if record.response_status == 200 and record.response_body is not None:
        return result_loader(record.response_body)
    raise ApiError(
        status_code=409,
        code="idempotency.request_in_progress",
        message="An idempotent request with this key is still in progress.",
    )


def store_idempotency_response(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    idempotency_key: str | None,
    response_status: int,
    response_body: dict[str, Any],
) -> None:
    if idempotency_key is None:
        return
    record = session.scalars(
        select(IdempotencyRecord)
        .where(IdempotencyRecord.tenant_id == tenant_id)
        .where(IdempotencyRecord.key == idempotency_key)
    ).one()
    record.response_status = response_status
    record.response_body = response_body
    record.locked_until = None
    record.updated_at = datetime.now(UTC)


def rollback_idempotency_on_failure(
    session: Session,
    tenant_id: uuid.UUID,
    idempotency_key: str | None,
) -> None:
    session.rollback()
    if idempotency_key is None:
        return
    session.execute(
        delete(IdempotencyRecord)
        .where(IdempotencyRecord.tenant_id == tenant_id)
        .where(IdempotencyRecord.key == idempotency_key)
        .where(IdempotencyRecord.response_status.is_(None))
    )
    session.commit()
