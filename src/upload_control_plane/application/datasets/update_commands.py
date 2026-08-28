from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from upload_control_plane.application.authentication import AuthenticatedActor
from upload_control_plane.application.datasets.audit import DatasetAuditWriter
from upload_control_plane.application.datasets.contracts import DatasetDetail
from upload_control_plane.application.datasets.queries import DatasetQueryService
from upload_control_plane.application.errors import ApiError
from upload_control_plane.domain.datasets import DatasetStatus
from upload_control_plane.infrastructure.db.models import Dataset, DatasetTag, Tag


class DatasetUpdateCommandService:
    """Own dataset metadata updates and dataset-tag replacement."""

    def __init__(
        self,
        *,
        session: Session,
        queries: DatasetQueryService,
        audit: DatasetAuditWriter,
    ) -> None:
        self._session = session
        self._queries = queries
        self._audit = audit

    def update_dataset(
        self,
        *,
        tenant_id: uuid.UUID,
        project_id: uuid.UUID,
        dataset_id: uuid.UUID,
        actor: AuthenticatedActor,
        request_id: str | None,
        name: str | None,
        metadata: dict[str, Any] | None,
        labels: tuple[str, ...] | None,
        tag_ids: tuple[uuid.UUID, ...] | None,
    ) -> DatasetDetail:
        dataset = self._queries.get_dataset_model(
            tenant_id=tenant_id,
            project_id=project_id,
            dataset_id=dataset_id,
        )
        if dataset.status in {DatasetStatus.DELETED.value, DatasetStatus.PURGED.value}:
            raise ApiError(
                status_code=409,
                code="dataset.invalid_state",
                message="Dataset cannot be updated in its current lifecycle state.",
                details={"status": dataset.status},
            )

        before = self._audit.snapshot(dataset)
        now = datetime.now(UTC)
        if name is not None:
            dataset.name = name
        if metadata is not None:
            dataset.metadata_ = dict(metadata)
        if labels is not None:
            dataset.labels = list(labels)
        if tag_ids is not None:
            self._replace_dataset_tags(dataset, tag_ids)
        dataset.updated_at = now
        self._audit.add(
            dataset,
            actor=actor,
            action="dataset.update",
            result="SUCCESS",
            request_id=request_id,
            before_state=before,
            after_state=self._audit.snapshot(dataset),
        )
        self._session.commit()
        return self._queries.detail(dataset)

    def _replace_dataset_tags(self, dataset: Dataset, tag_ids: tuple[uuid.UUID, ...]) -> None:
        if len(set(tag_ids)) != len(tag_ids):
            raise ApiError(
                status_code=422,
                code="tag.duplicate_ids",
                message="Dataset tag IDs must not contain duplicates.",
            )
        if tag_ids:
            count = self._session.scalar(
                select(func.count())
                .select_from(Tag)
                .where(Tag.tenant_id == dataset.tenant_id)
                .where(Tag.project_id == dataset.project_id)
                .where(Tag.id.in_(tag_ids))
            )
            if count != len(tag_ids):
                raise ApiError(status_code=404, code="tag.not_found", message="Tag not found.")

        self._session.execute(delete(DatasetTag).where(DatasetTag.dataset_id == dataset.id))
        for tag_id in tag_ids:
            self._session.add(DatasetTag(dataset_id=dataset.id, tag_id=tag_id))
