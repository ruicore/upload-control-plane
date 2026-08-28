from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from upload_control_plane.application.upload_sessions.event_writer import UploadEventWriter
from upload_control_plane.application.upload_sessions.lifecycle import UploadSessionLifecycleMixin
from upload_control_plane.application.upload_sessions.part_observation import (
    UploadSessionPartObservationMixin,
)
from upload_control_plane.application.upload_sessions.part_records import UploadPartStore
from upload_control_plane.application.upload_sessions.parts import UploadSessionPartsMixin
from upload_control_plane.application.upload_sessions.persisted_projection import (
    PersistedUploadAggregateProjector,
)
from upload_control_plane.config import Settings
from upload_control_plane.domain.storage import ObjectStorage


class UploadSessionRuntimeService(
    UploadSessionPartsMixin,
    UploadSessionPartObservationMixin,
    UploadSessionLifecycleMixin,
):
    """Composed application boundary for upload-session runtime operations."""

    if TYPE_CHECKING:
        _session: Session
        _storage: ObjectStorage
        _settings: Settings
        _part_store: UploadPartStore
        _projection: PersistedUploadAggregateProjector
        _event_writer: UploadEventWriter

    def __init__(self, *, session: Session, storage: ObjectStorage, settings: Settings) -> None:
        self._session = session
        self._storage = storage
        self._settings = settings
        self._part_store = UploadPartStore(session)
        self._projection = PersistedUploadAggregateProjector(
            session=session,
            settings=settings,
        )
        self._event_writer = UploadEventWriter(session)
