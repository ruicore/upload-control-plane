from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from upload_control_plane.api.auth import AuthenticatedActor
from upload_control_plane.api.errors import ApiError
from upload_control_plane.domain.permissions import (
    PermissionEffect,
    ResourceRef,
    ResourceType,
    SubjectRef,
    SubjectType,
    effective_permissions,
)
from upload_control_plane.domain.permissions import (
    PermissionGrant as DomainPermissionGrant,
)
from upload_control_plane.infrastructure.db.models import Dataset, PermissionGrant, Project


@dataclass(frozen=True)
class AuthorizationTarget:
    resource_type: ResourceType
    resource_id: uuid.UUID
    resource_parents: Mapping[ResourceType, uuid.UUID]


def actor_subjects(actor: AuthenticatedActor) -> tuple[SubjectRef, ...]:
    if actor.actor_type == "device":
        if actor.device_id is None:
            return ()
        return (SubjectRef(SubjectType.DEVICE, actor.device_id),)

    subjects: list[SubjectRef] = []
    if actor.api_key_id is not None:
        subjects.append(SubjectRef(SubjectType.API_KEY, actor.api_key_id))
    if actor.api_key_id is None or actor.subject_id != actor.api_key_id:
        subjects.append(SubjectRef(SubjectType.USER, actor.subject_id))
    return tuple(subjects)


class AuthorizationService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def visible_projects(self, actor: AuthenticatedActor) -> list[Project]:
        projects = self._session.scalars(
            select(Project)
            .where(Project.tenant_id == actor.tenant_id)
            .where(Project.deleted_at.is_(None))
            .order_by(Project.name.asc(), Project.id.asc())
        ).all()
        grants = self._load_grants(actor.tenant_id, actor_subjects(actor))
        now = datetime.now(UTC)
        return [
            project
            for project in projects
            if "project.view"
            in self._effective_permissions_from_grants(
                grants=grants,
                actor=actor,
                target=AuthorizationTarget(
                    resource_type=ResourceType.PROJECT,
                    resource_id=project.id,
                    resource_parents={ResourceType.TENANT: actor.tenant_id},
                ),
                at=now,
            )
        ]

    def effective_permissions(
        self,
        *,
        actor: AuthenticatedActor,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
    ) -> tuple[str, ...]:
        target = self.resolve_target(
            tenant_id=actor.tenant_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        return self._effective_permissions_from_grants(
            grants=self._load_grants(actor.tenant_id, actor_subjects(actor)),
            actor=actor,
            target=target,
            at=datetime.now(UTC),
        )

    def has_permission(
        self,
        *,
        actor: AuthenticatedActor,
        permission_code: str,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
    ) -> bool:
        return permission_code in self.effective_permissions(
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def has_any_permission(
        self,
        *,
        actor: AuthenticatedActor,
        permission_codes: Iterable[str],
        resource_type: ResourceType,
        resource_id: uuid.UUID,
    ) -> bool:
        effective = set(
            self.effective_permissions(
                actor=actor,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )
        return any(permission_code in effective for permission_code in permission_codes)

    def require_permission(
        self,
        *,
        actor: AuthenticatedActor,
        permission_code: str,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
    ) -> tuple[str, ...]:
        permissions = self.effective_permissions(
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if permission_code not in permissions:
            raise_permission_denied(permission_code=permission_code, resource_type=resource_type)
        return permissions

    def require_any_permission(
        self,
        *,
        actor: AuthenticatedActor,
        permission_codes: Iterable[str],
        resource_type: ResourceType,
        resource_id: uuid.UUID,
    ) -> tuple[str, ...]:
        requested = tuple(permission_codes)
        permissions = self.effective_permissions(
            actor=actor,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        if not any(permission_code in permissions for permission_code in requested):
            raise_permission_denied(
                permission_code=" or ".join(requested),
                resource_type=resource_type,
            )
        return permissions

    def resolve_target(
        self,
        *,
        tenant_id: uuid.UUID,
        resource_type: ResourceType,
        resource_id: uuid.UUID,
    ) -> AuthorizationTarget:
        if resource_type is ResourceType.TENANT:
            if resource_id != tenant_id:
                raise_not_found(resource_type)
            return AuthorizationTarget(resource_type, resource_id, {})

        if resource_type is ResourceType.PROJECT:
            project = self._session.get(Project, resource_id)
            if project is None or project.tenant_id != tenant_id or project.deleted_at is not None:
                raise_not_found(resource_type)
            return AuthorizationTarget(
                resource_type=resource_type,
                resource_id=resource_id,
                resource_parents={ResourceType.TENANT: tenant_id},
            )

        if resource_type is ResourceType.DATASET:
            dataset = self._session.get(Dataset, resource_id)
            if dataset is None:
                raise_not_found(resource_type)
            if dataset.tenant_id != tenant_id:
                raise_not_found(resource_type)
            return AuthorizationTarget(
                resource_type=resource_type,
                resource_id=resource_id,
                resource_parents={
                    ResourceType.TENANT: tenant_id,
                    ResourceType.PROJECT: dataset.project_id,
                },
            )

        raise ApiError(
            status_code=400,
            code="authorization.resource_unsupported",
            message="Unsupported authorization resource.",
            details={"resource_type": resource_type.value},
        )

    def _load_grants(
        self,
        tenant_id: uuid.UUID,
        subjects: Iterable[SubjectRef],
    ) -> tuple[DomainPermissionGrant, ...]:
        subject_pairs = tuple(
            (subject.subject_type.value, subject.subject_id) for subject in subjects
        )
        if not subject_pairs:
            return ()

        rows = self._session.scalars(
            select(PermissionGrant).where(
                PermissionGrant.tenant_id == tenant_id,
                tuple_(PermissionGrant.subject_type, PermissionGrant.subject_id).in_(subject_pairs),
            )
        ).all()
        return tuple(_to_domain_grant(row) for row in rows)

    def _effective_permissions_from_grants(
        self,
        *,
        grants: Iterable[DomainPermissionGrant],
        actor: AuthenticatedActor,
        target: AuthorizationTarget,
        at: datetime,
    ) -> tuple[str, ...]:
        return effective_permissions(
            grants=grants,
            tenant_id=actor.tenant_id,
            subjects=actor_subjects(actor),
            target=ResourceRef(target.resource_type, target.resource_id),
            resource_parents=target.resource_parents,
            at=at,
        )


def raise_permission_denied(*, permission_code: str, resource_type: ResourceType) -> NoReturn:
    raise ApiError(
        status_code=403,
        code="authorization.permission_denied",
        message="Permission denied.",
        details={
            "permission_code": permission_code,
            "resource_type": resource_type.value,
        },
    )


def raise_not_found(resource_type: ResourceType) -> NoReturn:
    raise ApiError(
        status_code=404,
        code=f"{resource_type.value}.not_found",
        message=f"{resource_type.value.replace('_', ' ').title()} not found.",
    )


def _to_domain_grant(row: PermissionGrant) -> DomainPermissionGrant:
    return DomainPermissionGrant(
        tenant_id=row.tenant_id,
        subject_type=SubjectType(row.subject_type),
        subject_id=row.subject_id,
        resource_type=ResourceType(row.resource_type),
        resource_id=row.resource_id,
        permission_code=row.permission_code,
        effect=PermissionEffect(row.effect),
        expires_at=row.expires_at,
    )
