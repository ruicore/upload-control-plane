from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.application.errors import ApiError
from upload_control_plane.application.upload_tasks.contracts import (
    CreatedUploadObject,
    CreatedUploadTask,
    CreateUploadTaskCommand,
)
from upload_control_plane.domain.fingerprints import (
    assert_json_value,
    generate_request_fingerprint,
)
from upload_control_plane.infrastructure.db.models import IdempotencyRecord


class UploadTaskIdempotency:
    """Owns create-upload-task idempotency persistence and replay."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def fingerprint(self, command: CreateUploadTaskCommand) -> str:
        return generate_request_fingerprint(
            method="POST",
            path=command.request_path,
            tenant_id=command.tenant_id,
            body=assert_json_value(command.request_body),
        )

    def resolve(
        self,
        command: CreateUploadTaskCommand,
        fingerprint: str,
    ) -> CreatedUploadTask | None:
        if command.idempotency_key is None:
            return None
        record = self._session.scalars(
            select(IdempotencyRecord)
            .where(IdempotencyRecord.tenant_id == command.tenant_id)
            .where(IdempotencyRecord.key == command.idempotency_key)
            .with_for_update()
        ).one_or_none()
        if record is None:
            now = datetime.now(UTC)
            self._session.add(
                IdempotencyRecord(
                    id=uuid.uuid4(),
                    tenant_id=command.tenant_id,
                    key=command.idempotency_key,
                    request_method="POST",
                    request_path=command.request_path,
                    request_fingerprint=fingerprint,
                    response_status=None,
                    response_body=None,
                    locked_until=now + timedelta(seconds=30),
                    expires_at=now + timedelta(days=1),
                )
            )
            self._session.flush()
            return None
        if record.request_fingerprint != fingerprint:
            raise ApiError(
                status_code=409,
                code="idempotency.key_reused_with_different_request",
                message="Idempotency key was reused with a different request.",
            )
        if record.response_status == 201 and record.response_body is not None:
            return _result_from_json(record.response_body)
        raise ApiError(
            status_code=409,
            code="idempotency.request_in_progress",
            message="An idempotent request with this key is still in progress.",
        )

    def store_response(
        self,
        command: CreateUploadTaskCommand,
        fingerprint: str,
        result: CreatedUploadTask,
    ) -> None:
        if command.idempotency_key is None:
            return
        record = self._session.scalars(
            select(IdempotencyRecord)
            .where(IdempotencyRecord.tenant_id == command.tenant_id)
            .where(IdempotencyRecord.key == command.idempotency_key)
        ).one()
        record.request_fingerprint = fingerprint
        record.response_status = 201
        record.response_body = _result_to_json(result)
        record.locked_until = None
        record.updated_at = datetime.now(UTC)


def _result_to_json(result: CreatedUploadTask) -> dict[str, Any]:
    return {
        "task_id": str(result.task_id),
        "project_id": str(result.project_id),
        "status": result.status,
        "object_count": result.object_count,
        "total_size_bytes": result.total_size_bytes,
        "objects": [
            {
                "object_id": str(item.object_id),
                "dataset_id": str(item.dataset_id),
                "session_id": str(item.session_id),
                "status": item.status,
                "object_name": item.object_name,
                "bucket": item.bucket,
                "object_key": item.object_key,
                "file_size_bytes": item.file_size_bytes,
                "part_size_bytes": item.part_size_bytes,
                "part_count": item.part_count,
                "expires_at": item.expires_at.isoformat(),
            }
            for item in result.objects
        ],
        "created_at": result.created_at.isoformat(),
    }


def _result_from_json(value: dict[str, Any]) -> CreatedUploadTask:
    return CreatedUploadTask(
        task_id=uuid.UUID(value["task_id"]),
        project_id=uuid.UUID(value["project_id"]),
        status=value["status"],
        object_count=value["object_count"],
        total_size_bytes=value["total_size_bytes"],
        objects=tuple(
            CreatedUploadObject(
                object_id=uuid.UUID(item["object_id"]),
                dataset_id=uuid.UUID(item["dataset_id"]),
                session_id=uuid.UUID(item["session_id"]),
                status=item["status"],
                object_name=item["object_name"],
                bucket=item["bucket"],
                object_key=item["object_key"],
                file_size_bytes=item["file_size_bytes"],
                part_size_bytes=item["part_size_bytes"],
                part_count=item["part_count"],
                expires_at=datetime.fromisoformat(item["expires_at"]),
            )
            for item in value["objects"]
        ),
        created_at=datetime.fromisoformat(value["created_at"]),
    )
