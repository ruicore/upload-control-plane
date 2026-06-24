from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from upload_control_plane.api.request_context import get_request_id


class ApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = dict(details or {})
        super().__init__(message)


def build_error_payload(
    *,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
    request_id: str | None = None,
) -> dict[str, dict[str, Any]]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": jsonable_encoder(dict(details or {})),
            "request_id": request_id or get_request_id(),
        }
    }


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=build_error_payload(code=code, message=message, details=details),
    )


async def api_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, ApiError):
        raise exc
    return error_response(
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def http_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
    return error_response(
        status_code=exc.status_code,
        code=_http_error_code(exc.status_code),
        message=message,
    )


async def validation_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    return error_response(
        status_code=422,
        code="request.validation_failed",
        message="Request validation failed.",
        details={"errors": exc.errors()},
    )


def _http_error_code(status_code: int) -> str:
    if status_code == 404:
        return "request.not_found"
    if status_code == 405:
        return "request.method_not_allowed"
    return "request.http_error"
