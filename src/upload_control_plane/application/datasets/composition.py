from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from upload_control_plane.application.dataset_tags import DatasetTagService
from upload_control_plane.application.datasets.audit import DatasetAuditWriter
from upload_control_plane.application.datasets.download import DatasetDownloadService
from upload_control_plane.application.datasets.lifecycle_commands import (
    DatasetLifecycleCommandService,
)
from upload_control_plane.application.datasets.purge_commands import DatasetPurgeCommandService
from upload_control_plane.application.datasets.queries import DatasetQueryService
from upload_control_plane.application.datasets.update_commands import (
    DatasetUpdateCommandService,
)
from upload_control_plane.application.datasets.validation_commands import (
    DatasetValidationCommandService,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.storage import ObjectStorage


@dataclass(frozen=True, slots=True)
class DatasetServices:
    """Composition-only boundary exposing the named dataset capability owners."""

    queries: DatasetQueryService
    tags: DatasetTagService
    validation: DatasetValidationCommandService
    updates: DatasetUpdateCommandService
    downloads: DatasetDownloadService
    lifecycle: DatasetLifecycleCommandService
    purge: DatasetPurgeCommandService


def compose_dataset_services(
    *,
    session: Session,
    storage: ObjectStorage,
    settings: Settings,
) -> DatasetServices:
    tags = DatasetTagService(session=session)
    queries = DatasetQueryService(session=session)
    audit = DatasetAuditWriter(session)
    validation = DatasetValidationCommandService(session=session, audit=audit)
    updates = DatasetUpdateCommandService(
        session=session,
        queries=queries,
        audit=audit,
    )
    lifecycle = DatasetLifecycleCommandService(
        session=session,
        queries=queries,
        audit=audit,
    )
    purge = DatasetPurgeCommandService(
        session=session,
        storage=storage,
        queries=queries,
        audit=audit,
    )
    downloads = DatasetDownloadService(
        session=session,
        storage=storage,
        settings=settings,
        queries=queries,
        audit=audit,
    )
    return DatasetServices(
        queries=queries,
        tags=tags,
        validation=validation,
        updates=updates,
        downloads=downloads,
        lifecycle=lifecycle,
        purge=purge,
    )
