from fastapi import Depends

from upload_control_plane.api.auth import require_api_key
from upload_control_plane.api.upload_tasks import OBJECT_STORAGE, SETTINGS_DEPENDENCY

AUTH_ACTOR = Depends(require_api_key)

__all__ = ["AUTH_ACTOR", "OBJECT_STORAGE", "SETTINGS_DEPENDENCY"]
