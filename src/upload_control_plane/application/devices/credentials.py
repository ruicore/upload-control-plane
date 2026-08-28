from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import hash_api_key
from upload_control_plane.infrastructure.db.models import Device, DeviceCredential

DEFAULT_DEVICE_CREDENTIAL_TTL_SECONDS = 90 * 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class ProvisionedCredential:
    credential_id: uuid.UUID
    credential_version: int
    credential_material: str
    issued_at: datetime
    expires_at: datetime | None


class DeviceCredentialLifecycle:
    def __init__(self, session: Session) -> None:
        self._session = session

    def provision(
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

    def rotate(
        self,
        *,
        tenant_id: uuid.UUID,
        device: Device,
        expires_in_seconds: int | None,
        overlap_seconds: int,
        now: datetime,
    ) -> ProvisionedCredential:
        for credential in self._active_credentials(device.id, now):
            if overlap_seconds <= 0:
                credential.revoked_at = now
            else:
                overlap_expires_at = now + timedelta(seconds=overlap_seconds)
                if credential.expires_at is None or credential.expires_at > overlap_expires_at:
                    credential.expires_at = overlap_expires_at
        return self.provision(
            tenant_id=tenant_id,
            device=device,
            version=device.credential_version + 1,
            expires_in_seconds=expires_in_seconds,
            now=now,
        )

    def revoke(self, *, device_id: uuid.UUID, now: datetime) -> None:
        for credential in self._active_credentials(device_id, now):
            credential.revoked_at = now

    def _active_credentials(
        self,
        device_id: uuid.UUID,
        now: datetime,
    ) -> list[DeviceCredential]:
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
