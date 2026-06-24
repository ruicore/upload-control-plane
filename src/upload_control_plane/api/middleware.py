from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from upload_control_plane.api.request_context import (
    REQUEST_ID_HEADER,
    new_request_id,
    reset_request_id,
    set_request_id,
)


async def request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
    request.state.request_id = request_id
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_id(token)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response
