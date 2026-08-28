from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from .redaction import sanitize_for_observability


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        for key in (
            "request_id",
            "trace_id",
            "tenant_id",
            "project_id",
            "task_id",
            "object_id",
            "dataset_id",
            "session_id",
            "actor_id",
            "operation",
            "path",
            "method",
            "status",
            "status_code",
            "latency_ms",
            "error_code",
            "storage_operation",
        ):
            if hasattr(record, key):
                payload[key] = sanitize_for_observability(getattr(record, key))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def configure_logging(*, level: str, app_env: str) -> None:
    logger = logging.getLogger("upload_control_plane")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter: logging.Formatter
    if app_env == "local":
        formatter = logging.Formatter("%(levelname)s %(name)s %(message)s")
    else:
        formatter = JsonLogFormatter()
    if not logger.handlers:
        logger.addHandler(logging.StreamHandler())
    for handler in logger.handlers:
        handler.setFormatter(formatter)
