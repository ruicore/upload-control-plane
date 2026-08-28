from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

_REQUEST_CONTEXT_KEYS = ("project_id", "dataset_id", "session_id")


def monotonic_time() -> float:
    return time.perf_counter()


def milliseconds_since(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 3)


def route_context(path_params: Mapping[str, Any]) -> dict[str, str]:
    context: dict[str, str] = {}
    for key in _REQUEST_CONTEXT_KEYS:
        value = path_params.get(key)
        if value is not None:
            context[key] = str(value)
    return context
