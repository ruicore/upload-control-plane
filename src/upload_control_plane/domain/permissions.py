"""Pure permission-code evaluation over loaded permission grants."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class SubjectType(StrEnum):
    USER = "user"
    GROUP = "group"
    DEVICE = "device"
    API_KEY = "api_key"


class ResourceType(StrEnum):
    TENANT = "tenant"
    PROJECT = "project"
    DATASET = "dataset"
    UPLOAD_SESSION = "upload_session"
    UPLOAD_TASK = "upload_task"
    DEVICE = "device"
    TAG_CATEGORY = "tag_category"
    TAG = "tag"
    STORAGE_POLICY = "storage_policy"


class PermissionEffect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


@dataclass(frozen=True, slots=True)
class SubjectRef:
    subject_type: SubjectType
    subject_id: UUID


@dataclass(frozen=True, slots=True)
class ResourceRef:
    resource_type: ResourceType
    resource_id: UUID


@dataclass(frozen=True, slots=True)
class PermissionGrant:
    tenant_id: UUID
    subject_type: SubjectType
    subject_id: UUID
    resource_type: ResourceType
    resource_id: UUID
    permission_code: str
    effect: PermissionEffect
    expires_at: datetime | None = None


RESOURCE_INHERITANCE: Mapping[ResourceType, frozenset[ResourceType]] = {
    ResourceType.TENANT: frozenset({ResourceType.TENANT}),
    ResourceType.PROJECT: frozenset({ResourceType.TENANT, ResourceType.PROJECT}),
    ResourceType.DATASET: frozenset(
        {ResourceType.TENANT, ResourceType.PROJECT, ResourceType.DATASET}
    ),
    ResourceType.UPLOAD_TASK: frozenset(
        {ResourceType.TENANT, ResourceType.PROJECT, ResourceType.UPLOAD_TASK}
    ),
    ResourceType.UPLOAD_SESSION: frozenset(
        {
            ResourceType.TENANT,
            ResourceType.PROJECT,
            ResourceType.DATASET,
            ResourceType.UPLOAD_SESSION,
        }
    ),
    ResourceType.DEVICE: frozenset(
        {
            ResourceType.TENANT,
            ResourceType.PROJECT,
            ResourceType.DEVICE,
        }
    ),
    ResourceType.TAG_CATEGORY: frozenset(
        {ResourceType.TENANT, ResourceType.PROJECT, ResourceType.TAG_CATEGORY}
    ),
    ResourceType.TAG: frozenset({ResourceType.TENANT, ResourceType.PROJECT, ResourceType.TAG}),
    ResourceType.STORAGE_POLICY: frozenset(
        {ResourceType.TENANT, ResourceType.PROJECT, ResourceType.STORAGE_POLICY}
    ),
}


def _is_active(grant: PermissionGrant, at: datetime) -> bool:
    return grant.expires_at is None or grant.expires_at > at


def _matches_subject(grant: PermissionGrant, subjects: frozenset[SubjectRef]) -> bool:
    return SubjectRef(grant.subject_type, grant.subject_id) in subjects


def _matches_resource(
    grant: PermissionGrant,
    tenant_id: UUID,
    target: ResourceRef,
    resource_parents: Mapping[ResourceType, UUID],
) -> bool:
    if grant.tenant_id != tenant_id:
        return False
    if grant.resource_type not in RESOURCE_INHERITANCE[target.resource_type]:
        return False
    if grant.resource_type is ResourceType.TENANT:
        return grant.resource_id == tenant_id
    if grant.resource_type is target.resource_type:
        return grant.resource_id == target.resource_id
    return resource_parents.get(grant.resource_type) == grant.resource_id


def matching_permission_grants(
    *,
    grants: Iterable[PermissionGrant],
    tenant_id: UUID,
    subjects: Iterable[SubjectRef],
    target: ResourceRef,
    resource_parents: Mapping[ResourceType, UUID],
    at: datetime,
) -> list[PermissionGrant]:
    subject_set = frozenset(subjects)
    return [
        grant
        for grant in grants
        if _is_active(grant, at)
        and _matches_subject(grant, subject_set)
        and _matches_resource(grant, tenant_id, target, resource_parents)
    ]


def effective_permissions(
    *,
    grants: Iterable[PermissionGrant],
    tenant_id: UUID,
    subjects: Iterable[SubjectRef],
    target: ResourceRef,
    resource_parents: Mapping[ResourceType, UUID],
    at: datetime,
) -> tuple[str, ...]:
    matched = matching_permission_grants(
        grants=grants,
        tenant_id=tenant_id,
        subjects=subjects,
        target=target,
        resource_parents=resource_parents,
        at=at,
    )
    denied = {grant.permission_code for grant in matched if grant.effect is PermissionEffect.DENY}
    allowed = {grant.permission_code for grant in matched if grant.effect is PermissionEffect.ALLOW}
    return tuple(sorted(allowed - denied))


def has_permission(
    *,
    permission_code: str,
    grants: Iterable[PermissionGrant],
    tenant_id: UUID,
    subjects: Iterable[SubjectRef],
    target: ResourceRef,
    resource_parents: Mapping[ResourceType, UUID],
    at: datetime,
) -> bool:
    return permission_code in effective_permissions(
        grants=grants,
        tenant_id=tenant_id,
        subjects=subjects,
        target=target,
        resource_parents=resource_parents,
        at=at,
    )
