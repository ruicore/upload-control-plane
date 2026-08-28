from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from upload_control_plane.api.request_context import (
    REQUEST_ID_HEADER,
    new_request_id,
    reset_request_id,
    set_request_id,
)
from upload_control_plane.observability import (
    metrics_registry,
    milliseconds_since,
    monotonic_time,
    route_context,
)

logger = logging.getLogger("upload_control_plane.api")


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
    request.state.request_id = request_id
    token = set_request_id(request_id)
    started_at = monotonic_time()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception:
        latency_ms = milliseconds_since(started_at)
        _record_request(
            request=request,
            request_id=request_id,
            status_code=status_code,
            latency_ms=latency_ms,
            exc_info=True,
        )
        raise
    finally:
        reset_request_id(token)
    latency_ms = milliseconds_since(started_at)
    _record_request(
        request=request,
        request_id=request_id,
        status_code=status_code,
        latency_ms=latency_ms,
        exc_info=False,
    )
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def _record_request(
    *,
    request: Request,
    request_id: str,
    status_code: int,
    latency_ms: float,
    exc_info: bool,
) -> None:
    route = request.scope.get("route")
    operation = getattr(route, "path", request.url.path)
    labels = {
        "method": request.method,
        "path": str(operation),
        "status_code": str(status_code),
    }
    metrics_registry.increment("api_requests_total", labels)
    metrics_registry.observe("api_request_duration_seconds", latency_ms / 1000, labels)
    context = route_context(request.path_params)
    logger.info(
        "api_request",
        extra={
            "request_id": request_id,
            "operation": str(operation),
            "path": request.url.path,
            "method": request.method,
            "status": status_code,
            "status_code": status_code,
            "latency_ms": latency_ms,
            **context,
        },
        exc_info=exc_info,
    )
