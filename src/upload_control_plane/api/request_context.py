from __future__ import annotations

from contextvars import ContextVar, Token
from uuid import uuid4

REQUEST_ID_HEADER = "X-Request-ID"

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return str(uuid4())


def get_request_id() -> str:
    return _request_id.get() or new_request_id()


def set_request_id(request_id: str) -> Token[str | None]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)
