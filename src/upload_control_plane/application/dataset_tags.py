"""Tag-category and tag application operations."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from upload_control_plane.application.errors import ApiError
from upload_control_plane.infrastructure.db.models import (
    DatasetTag,
    Project,
    Tag,
    TagCategory,
)


@dataclass(frozen=True, slots=True)
class TagCategoryResult:
    category_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    color: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TagResult:
    tag_id: uuid.UUID
    project_id: uuid.UUID
    category_id: uuid.UUID | None
    name: str
    color: str | None
    created_at: datetime
    updated_at: datetime


class DatasetTagService:
    """Own tag-category and tag CRUD for datasets."""

    def __init__(self, *, session: Session) -> None:
        self._session = session

    def list_tag_categories(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> tuple[TagCategoryResult, ...]:
        self._require_project(tenant_id=tenant_id, project_id=project_id)
        rows = self._session.scalars(
            select(TagCategory)
            .where(TagCategory.tenant_id == tenant_id)
            .where(TagCategory.project_id == project_id)
            .order_by(TagCategory.sort_order.asc(), TagCategory.name.asc())
        ).all()
        return tuple(_category_result(row) for row in rows)

    def create_tag_category(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        name: str,
        color: str | None,
        sort_order: int,
    ) -> TagCategoryResult:
        self._require_project(tenant_id=tenant_id, project_id=project_id)
        now = datetime.now(UTC)
        category = TagCategory(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            name=name,
            color=color,
            sort_order=sort_order,
            created_at=now,
            updated_at=now,
        )
        self._session.add(category)
        self._session.commit()
        return _category_result(category)

    def update_tag_category(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        category_id: uuid.UUID,
        name: str | None,
        color: str | None,
        sort_order: int | None,
    ) -> TagCategoryResult:
        category = self._get_tag_category(
            tenant_id=tenant_id, project_id=project_id, category_id=category_id
        )
        if name is not None:
            category.name = name
        if color is not None:
            category.color = color
        if sort_order is not None:
            category.sort_order = sort_order
        category.updated_at = datetime.now(UTC)
        self._session.commit()
        return _category_result(category)

    def delete_tag_category(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        category_id: uuid.UUID,
    ) -> None:
        category = self._get_tag_category(
            tenant_id=tenant_id, project_id=project_id, category_id=category_id
        )
        self._session.delete(category)
        self._session.commit()

    def list_tags(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> tuple[TagResult, ...]:
        self._require_project(tenant_id=tenant_id, project_id=project_id)
        rows = self._session.scalars(
            select(Tag)
            .where(Tag.tenant_id == tenant_id)
            .where(Tag.project_id == project_id)
            .order_by(Tag.name.asc(), Tag.id.asc())
        ).all()
        return tuple(_tag_result(row) for row in rows)

    def create_tag(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        category_id: uuid.UUID | None,
        name: str,
        color: str | None,
    ) -> TagResult:
        self._require_project(tenant_id=tenant_id, project_id=project_id)
        if category_id is not None:
            self._get_tag_category(
                tenant_id=tenant_id,
                project_id=project_id,
                category_id=category_id,
            )
        now = datetime.now(UTC)
        tag = Tag(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            project_id=project_id,
            category_id=category_id,
            name=name,
            color=color,
            created_at=now,
            updated_at=now,
        )
        self._session.add(tag)
        self._session.commit()
        return _tag_result(tag)

    def update_tag(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        tag_id: uuid.UUID,
        category_id: uuid.UUID | None,
        name: str | None,
        color: str | None,
    ) -> TagResult:
        tag = self._get_tag(
            tenant_id=tenant_id,
            project_id=project_id,
            tag_id=tag_id,
        )
        if category_id is not None:
            self._get_tag_category(
                tenant_id=tenant_id,
                project_id=project_id,
                category_id=category_id,
            )
            tag.category_id = category_id
        if name is not None:
            tag.name = name
        if color is not None:
            tag.color = color
        tag.updated_at = datetime.now(UTC)
        self._session.commit()
        return _tag_result(tag)

    def delete_tag(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        tag_id: uuid.UUID,
    ) -> None:
        self._get_tag(
            tenant_id=tenant_id,
            project_id=project_id,
            tag_id=tag_id,
        )
        self._session.execute(delete(DatasetTag).where(DatasetTag.tag_id == tag_id))
        self._session.execute(delete(Tag).where(Tag.id == tag_id))
        self._session.commit()

    def _require_project(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
    ) -> Project:
        project = self._session.get(Project, project_id)
        if project is None or project.tenant_id != tenant_id or project.deleted_at is not None:
            raise ApiError(
                status_code=404,
                code="project.not_found",
                message="Project not found.",
            )
        return project

    def _get_tag_category(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        category_id: uuid.UUID,
    ) -> TagCategory:
        category = self._session.get(TagCategory, category_id)
        if category is None or category.tenant_id != tenant_id or category.project_id != project_id:
            raise ApiError(
                status_code=404,
                code="tag_category.not_found",
                message="Tag category not found.",
            )
        return category

    def _get_tag(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        tag_id: uuid.UUID,
    ) -> Tag:
        tag = self._session.get(Tag, tag_id)
        if tag is None or tag.tenant_id != tenant_id or tag.project_id != project_id:
            raise ApiError(
                status_code=404,
                code="tag.not_found",
                message="Tag not found.",
            )
        return tag


def _category_result(category: TagCategory) -> TagCategoryResult:
    return TagCategoryResult(
        category_id=category.id,
        project_id=category.project_id,
        name=category.name,
        color=category.color,
        sort_order=category.sort_order,
        created_at=category.created_at,
        updated_at=category.updated_at,
    )


def _tag_result(tag: Tag) -> TagResult:
    return TagResult(
        tag_id=tag.id,
        project_id=tag.project_id,
        category_id=tag.category_id,
        name=tag.name,
        color=tag.color,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
    )
