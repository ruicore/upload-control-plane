from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import AuthenticatedActor, hash_api_key
from upload_control_plane.api.errors import ApiError
from upload_control_plane.infrastructure.db.models import (
    AuditEvent,
    Device,
    DeviceCredential,
    PermissionGrant,
    Project,
)

DEFAULT_DEVICE_CREDENTIAL_TTL_SECONDS = 90 * 24 * 60 * 60
DEVICE_UPLOAD_PERMISSION_CODES = (
    "project.view",
    "dataset.view",
    "dataset.upload",
    "upload.create",
    "upload.pause",
    "upload.resume",
    "upload.complete",
    "upload.abort",
)


@dataclass(frozen=True, slots=True)
class ProvisionedCredential:
    credential_id: uuid.UUID
    credential_version: int
    credential_material: str
    issued_at: datetime
    expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    device_id: uuid.UUID
    project_id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    device_code: str | None
    device_type: str
    status: str
    credential_version: int
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None
    last_ip: str | None
    client_version: str | None


@dataclass(frozen=True, slots=True)
class DeviceWithCredential:
    device: DeviceRecord
    credential: ProvisionedCredential


class DeviceService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_project_devices(
        self, *, tenant_id: uuid.UUID, project_id: uuid.UUID
    ) -> list[DeviceRecord]:
        self._require_project(tenant_id=tenant_id, project_id=project_id)
        device_ids = self._device_ids_for_project(tenant_id=tenant_id, project_id=project_id)
        if not device_ids:
            return []
        devices = self._session.scalars(
            select(Device)
            .where(Device.tenant_id == tenant_id)
            .where(Device.id.in_(device_ids))
            .where(Device.status != "DELETED")
            .order_by(Device.name.asc(), Device.id.asc())
        ).all()
        return [self._record(device, project_id) for device in devices]

    def get_project_device(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        device_id: uuid.UUID,
    ) -> DeviceRecord:
        device = self._require_device_for_project(
            tenant_id=tenant_id,
            project_id=project_id,
            device_id=device_id,
        )
        return self._record(device, project_id)

    def register_device(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
        name: str,
        device_code: str | None,
        device_type: str,
        metadata: dict[str, Any],
        credential_expires_in_seconds: int | None,
        upload_permission_codes: tuple[str, ...] = DEVICE_UPLOAD_PERMISSION_CODES,
    ) -> DeviceWithCredential:
        self._require_project(tenant_id=tenant_id, project_id=project_id)
        now = datetime.now(UTC)
        device = Device(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=name,
            device_code=device_code,
            device_type=device_type,
            status="ACTIVE",
            credential_version=1,
            credential_hash=None,
            metadata_=dict(metadata),
            created_at=now,
            updated_at=now,
        )
        self._session.add(device)
        self._session.flush()
        credential = self._create_credential(
            tenant_id=tenant_id,
            device=device,
            version=1,
            expires_in_seconds=credential_expires_in_seconds,
            now=now,
        )
        for permission_code in upload_permission_codes:
            self._session.add(
                PermissionGrant(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    subject_type="device",
                    subject_id=device.id,
                    resource_type="project",
                    resource_id=project_id,
                    permission_code=permission_code,
                    effect="ALLOW",
                    conditions={},
                    source="device_registration",
                    created_by=actor.subject_id,
                    created_at=now,
                    expires_at=None,
                )
            )
        self._add_audit(
            tenant_id=tenant_id,
            project_id=project_id,
            actor=actor,
            action="device.register",
            resource_id=device.id,
            result="SUCCESS",
            request_id=request_id,
            after_state={"device_code": device.device_code, "credential_version": 1},
        )
        self._session.commit()
        return DeviceWithCredential(device=self._record(device, project_id), credential=credential)

    def update_device(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        device_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
        name: str | None,
        device_code: str | None,
        device_type: str | None,
        metadata: dict[str, Any] | None,
    ) -> DeviceRecord:
        device = self._require_device_for_project(
            tenant_id=tenant_id,
            project_id=project_id,
            device_id=device_id,
        )
        before = self._device_state(device)
        if name is not None:
            device.name = name
        if device_code is not None:
            device.device_code = device_code
        if device_type is not None:
            device.device_type = device_type
        if metadata is not None:
            device.metadata_ = dict(metadata)
        device.updated_at = datetime.now(UTC)
        self._add_audit(
            tenant_id=tenant_id,
            project_id=project_id,
            actor=actor,
            action="device.update",
            resource_id=device.id,
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._device_state(device),
        )
        self._session.commit()
        return self._record(device, project_id)

    def set_device_status(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        device_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
        status: str,
    ) -> DeviceRecord:
        device = self._require_device_for_project(
            tenant_id=tenant_id,
            project_id=project_id,
            device_id=device_id,
        )
        if device.status == "REVOKED" and status == "ACTIVE":
            raise ApiError(
                status_code=409,
                code="device.revoked",
                message="Revoked devices cannot be enabled.",
            )
        before = self._device_state(device)
        device.status = status
        device.updated_at = datetime.now(UTC)
        self._add_audit(
            tenant_id=tenant_id,
            project_id=project_id,
            actor=actor,
            action=f"device.{status.lower()}",
            resource_id=device.id,
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._device_state(device),
        )
        self._session.commit()
        return self._record(device, project_id)

    def rotate_credential(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        device_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
        expires_in_seconds: int | None,
        overlap_seconds: int,
    ) -> DeviceWithCredential:
        device = self._require_device_for_project(
            tenant_id=tenant_id,
            project_id=project_id,
            device_id=device_id,
        )
        if device.status in {"REVOKED", "DELETED"}:
            raise ApiError(
                status_code=409,
                code="device.invalid_state",
                message="Device state does not allow credential rotation.",
                details={"status": device.status},
            )
        now = datetime.now(UTC)
        for credential in self._active_credentials(device.id, now):
            if overlap_seconds <= 0:
                credential.revoked_at = now
            else:
                overlap_expires_at = now + timedelta(seconds=overlap_seconds)
                if credential.expires_at is None or credential.expires_at > overlap_expires_at:
                    credential.expires_at = overlap_expires_at
        next_version = device.credential_version + 1
        new_credential = self._create_credential(
            tenant_id=tenant_id,
            device=device,
            version=next_version,
            expires_in_seconds=expires_in_seconds,
            now=now,
        )
        self._add_audit(
            tenant_id=tenant_id,
            project_id=project_id,
            actor=actor,
            action="device.credentials.rotate",
            resource_id=device.id,
            result="SUCCESS",
            request_id=request_id,
            after_state={
                "credential_version": next_version,
                "overlap_seconds": overlap_seconds,
            },
        )
        self._session.commit()
        return DeviceWithCredential(
            device=self._record(device, project_id),
            credential=new_credential,
        )

    def revoke_credentials(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        device_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
    ) -> DeviceRecord:
        device = self._require_device_for_project(
            tenant_id=tenant_id,
            project_id=project_id,
            device_id=device_id,
        )
        now = datetime.now(UTC)
        for credential in self._active_credentials(device.id, now):
            credential.revoked_at = now
        before = self._device_state(device)
        device.status = "REVOKED"
        device.updated_at = now
        self._add_audit(
            tenant_id=tenant_id,
            project_id=project_id,
            actor=actor,
            action="device.credentials.revoke",
            resource_id=device.id,
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._device_state(device),
        )
        self._session.commit()
        return self._record(device, project_id)

    def _create_credential(
        self,
        *,
        tenant_id: uuid.UUID,
        device: Device,
        version: int,
        expires_in_seconds: int | None,
        now: datetime,
    ) -> ProvisionedCredential:
        material = f"ucp_device_{secrets.token_urlsafe(32)}"
        expires_at = now + timedelta(
            seconds=expires_in_seconds or DEFAULT_DEVICE_CREDENTIAL_TTL_SECONDS
        )
        credential = DeviceCredential(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            device_id=device.id,
            credential_version=version,
            credential_hash=hash_api_key(material),
            issued_at=now,
            expires_at=expires_at,
            revoked_at=None,
            metadata_={},
        )
        self._session.add(credential)
        device.credential_version = version
        device.credential_hash = credential.credential_hash
        device.updated_at = now
        self._session.flush()
        return ProvisionedCredential(
            credential_id=credential.id,
            credential_version=version,
            credential_material=material,
            issued_at=now,
            expires_at=expires_at,
        )

    def _active_credentials(self, device_id: uuid.UUID, now: datetime) -> list[DeviceCredential]:
        return list(
            self._session.scalars(
                select(DeviceCredential)
                .where(DeviceCredential.device_id == device_id)
                .where(DeviceCredential.revoked_at.is_(None))
                .where(
                    (DeviceCredential.expires_at.is_(None)) | (DeviceCredential.expires_at > now)
                )
            )
        )

    def _device_ids_for_project(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> set[uuid.UUID]:
        return set(
            self._session.scalars(
                select(PermissionGrant.subject_id)
                .where(PermissionGrant.tenant_id == tenant_id)
                .where(PermissionGrant.subject_type == "device")
                .where(PermissionGrant.resource_type == "project")
                .where(PermissionGrant.resource_id == project_id)
            )
        )

    def _require_project(self, *, tenant_id: uuid.UUID, project_id: uuid.UUID) -> Project:
        project = self._session.get(Project, project_id)
        if project is None or project.tenant_id != tenant_id or project.deleted_at is not None:
            raise ApiError(status_code=404, code="project.not_found", message="Project not found.")
        return project

    def _require_device_for_project(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        device_id: uuid.UUID,
    ) -> Device:
        self._require_project(tenant_id=tenant_id, project_id=project_id)
        if device_id not in self._device_ids_for_project(
            tenant_id=tenant_id, project_id=project_id
        ):
            raise ApiError(status_code=404, code="device.not_found", message="Device not found.")
        device = self._session.get(Device, device_id)
        if device is None or device.tenant_id != tenant_id or device.status == "DELETED":
            raise ApiError(status_code=404, code="device.not_found", message="Device not found.")
        return device

    def _add_audit(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        actor: AuthenticatedActor,
        action: str,
        resource_id: uuid.UUID,
        result: str,
        request_id: str | None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AuditEvent(
                tenant_id=tenant_id,
                project_id=project_id,
                actor_type=actor.actor_type,
                actor_id=str(actor.subject_id),
                action=action,
                resource_type="device",
                resource_id=str(resource_id),
                result=result,
                request_id=request_id,
                before_state=before_state,
                after_state=after_state,
                metadata_={"source": "device_service"},
            )
        )

    def _record(self, device: Device, project_id: uuid.UUID) -> DeviceRecord:
        return DeviceRecord(
            device_id=device.id,
            project_id=project_id,
            tenant_id=device.tenant_id,
            name=device.name,
            device_code=device.device_code,
            device_type=device.device_type,
            status=device.status,
            credential_version=device.credential_version,
            metadata=dict(device.metadata_ or {}),
            created_at=device.created_at,
            updated_at=device.updated_at,
            last_seen_at=device.last_seen_at,
            last_ip=device.last_ip,
            client_version=device.client_version,
        )

    def _device_state(self, device: Device) -> dict[str, Any]:
        return {
            "device_id": str(device.id),
            "name": device.name,
            "device_code": device.device_code,
            "device_type": device.device_type,
            "status": device.status,
            "credential_version": device.credential_version,
        }
