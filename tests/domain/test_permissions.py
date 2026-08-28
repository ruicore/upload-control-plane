from datetime import UTC, datetime, timedelta
from uuid import UUID

from upload_control_plane.domain.permissions import (
    PermissionEffect,
    PermissionGrant,
    ResourceRef,
    ResourceType,
    SubjectRef,
    SubjectType,
    effective_permissions,
    has_permission,
)

TENANT_ID = UUID("00000000-0000-4000-8000-000000000001")
PROJECT_ID = UUID("00000000-0000-4000-8000-000000000002")
DATASET_ID = UUID("00000000-0000-4000-8000-000000000003")
USER_ID = UUID("00000000-0000-4000-8000-000000000004")
GROUP_ID = UUID("00000000-0000-4000-8000-000000000005")
OTHER_TENANT_ID = UUID("00000000-0000-4000-8000-000000000006")
NOW = datetime(2026, 6, 24, 8, 30, tzinfo=UTC)


def grant(
    *,
    permission_code: str,
    effect: PermissionEffect = PermissionEffect.ALLOW,
    subject_type: SubjectType = SubjectType.USER,
    subject_id: UUID = USER_ID,
    resource_type: ResourceType = ResourceType.PROJECT,
    resource_id: UUID = PROJECT_ID,
    tenant_id: UUID = TENANT_ID,
    expires_at: datetime | None = None,
) -> PermissionGrant:
    return PermissionGrant(
        tenant_id=tenant_id,
        subject_type=subject_type,
        subject_id=subject_id,
        resource_type=resource_type,
        resource_id=resource_id,
        permission_code=permission_code,
        effect=effect,
        expires_at=expires_at,
    )


def test_effective_permissions_include_inherited_project_and_group_grants() -> None:
    permissions = effective_permissions(
        grants=[
            grant(permission_code="dataset.view"),
            grant(
                permission_code="dataset.download",
                subject_type=SubjectType.GROUP,
                subject_id=GROUP_ID,
            ),
        ],
        tenant_id=TENANT_ID,
        subjects=[
            SubjectRef(SubjectType.USER, USER_ID),
            SubjectRef(SubjectType.GROUP, GROUP_ID),
        ],
        target=ResourceRef(ResourceType.DATASET, DATASET_ID),
        resource_parents={ResourceType.PROJECT: PROJECT_ID},
        at=NOW,
    )

    assert permissions == ("dataset.download", "dataset.view")


def test_expired_and_other_tenant_grants_are_ignored() -> None:
    permissions = effective_permissions(
        grants=[
            grant(permission_code="dataset.view", expires_at=NOW - timedelta(seconds=1)),
            grant(permission_code="dataset.download", tenant_id=OTHER_TENANT_ID),
        ],
        tenant_id=TENANT_ID,
        subjects=[SubjectRef(SubjectType.USER, USER_ID)],
        target=ResourceRef(ResourceType.DATASET, DATASET_ID),
        resource_parents={ResourceType.PROJECT: PROJECT_ID},
        at=NOW,
    )

    assert permissions == ()


def test_deny_overrides_allow_from_same_or_inherited_scope() -> None:
    permissions = effective_permissions(
        grants=[
            grant(permission_code="dataset.download"),
            grant(
                permission_code="dataset.download",
                effect=PermissionEffect.DENY,
                resource_type=ResourceType.DATASET,
                resource_id=DATASET_ID,
            ),
            grant(permission_code="dataset.view"),
        ],
        tenant_id=TENANT_ID,
        subjects=[SubjectRef(SubjectType.USER, USER_ID)],
        target=ResourceRef(ResourceType.DATASET, DATASET_ID),
        resource_parents={ResourceType.PROJECT: PROJECT_ID},
        at=NOW,
    )

    assert permissions == ("dataset.view",)


def test_has_permission_uses_effective_permission_evaluation() -> None:
    grants = [grant(permission_code="dataset.download")]

    assert has_permission(
        permission_code="dataset.download",
        grants=grants,
        tenant_id=TENANT_ID,
        subjects=[SubjectRef(SubjectType.USER, USER_ID)],
        target=ResourceRef(ResourceType.DATASET, DATASET_ID),
        resource_parents={ResourceType.PROJECT: PROJECT_ID},
        at=NOW,
    )
    assert not has_permission(
        permission_code="dataset.purge",
        grants=grants,
        tenant_id=TENANT_ID,
        subjects=[SubjectRef(SubjectType.USER, USER_ID)],
        target=ResourceRef(ResourceType.DATASET, DATASET_ID),
        resource_parents={ResourceType.PROJECT: PROJECT_ID},
        at=NOW,
    )
