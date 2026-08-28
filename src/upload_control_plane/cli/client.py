"""HTTP client for the public upload control-plane API."""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from upload_control_plane.cli.manifest import redact_url


class UploadApiError(RuntimeError):
    def __init__(self, *, status_code: int, code: str, message: str, details: Mapping[str, Any]):
        self.status_code = status_code
        self.code = code
        self.details = dict(details)
        super().__init__(f"{status_code} {code}: {message}")


@dataclass(frozen=True, slots=True)
class ControlPlaneClient:
    api_url: str
    api_key: str
    timeout_seconds: float = 30.0

    def create_upload_task(
        self,
        *,
        project_id: str,
        idempotency_key: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/v1/projects/{project_id}/upload-tasks",
            json=payload,
            idempotency_key=idempotency_key,
        )

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self._request_json("GET", f"/v1/uploads/{session_id}")

    def presign_parts(
        self,
        *,
        session_id: str,
        part_numbers: list[int],
        expires_in_seconds: int,
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/v1/uploads/{session_id}/parts/presign",
            json={"part_numbers": part_numbers, "expires_in_seconds": expires_in_seconds},
        )

    def ack_parts(self, *, session_id: str, parts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/v1/uploads/{session_id}/parts/ack",
            json={"parts": parts},
        )

    def list_parts(self, *, session_id: str, source: str = "reconcile") -> dict[str, Any]:
        return self._request_json(
            "GET",
            f"/v1/uploads/{session_id}/parts",
            params={"source": source},
        )

    def complete(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        client_reported_parts: Sequence[Mapping[str, Any]],
        checksum_sha256: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"client_reported_parts": client_reported_parts}
        if checksum_sha256 is not None:
            payload["checksum_sha256"] = checksum_sha256
        return self._request_json(
            "POST",
            f"/v1/uploads/{session_id}/complete",
            json=payload,
            idempotency_key=idempotency_key,
        )

    def pause(
        self,
        *,
        session_id: str,
        idempotency_key: str,
        reason: str,
        client_inflight_behavior: str = "allow_finish",
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/v1/uploads/{session_id}/pause",
            json={"reason": reason, "client_inflight_behavior": client_inflight_behavior},
            idempotency_key=idempotency_key,
        )

    def resume(self, *, session_id: str, idempotency_key: str, reason: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/v1/uploads/{session_id}/resume",
            json={"reason": reason},
            idempotency_key=idempotency_key,
        )

    def abort(self, *, session_id: str, idempotency_key: str, reason: str) -> dict[str, Any]:
        return self._request_json(
            "POST",
            f"/v1/uploads/{session_id}/abort",
            json={"reason": reason},
            idempotency_key=idempotency_key,
        )

    def put_presigned_part(
        self,
        *,
        url: str,
        body: Iterator[bytes],
        size_bytes: int,
        required_headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> httpx.Response:
        headers = {**required_headers, "Content-Length": str(size_bytes)}
        with httpx.Client(timeout=timeout_seconds) as client:
            return client.put(url, content=body, headers=headers)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Request-ID": f"uploadctl-{uuid.uuid4()}",
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        url = f"{self.api_url.rstrip('/')}{path}"
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.request(method, url, headers=headers, json=json, params=params)
        if response.is_error:
            raise _api_error(response)
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"API returned non-object JSON from {path}")
        return payload


def is_expired_presigned_response(response: httpx.Response) -> bool:
    if response.status_code != 403:
        return False
    body = response.text[:2048].lower()
    return (
        "expired" in body
        or "signaturedoesnotmatch" in body
        or "request has expired" in body
        or "accessdenied" in body
    )


def _api_error(response: httpx.Response) -> UploadApiError:
    try:
        payload = response.json()
    except ValueError:
        raise UploadApiError(
            status_code=response.status_code,
            code="http.error",
            message=f"HTTP {response.status_code} from {redact_url(str(response.url))}",
            details={},
        ) from None
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        raise UploadApiError(
            status_code=response.status_code,
            code="http.error",
            message=f"HTTP {response.status_code}",
            details={},
        )
    raw_details = error.get("details")
    details: Mapping[str, Any] = raw_details if isinstance(raw_details, dict) else {}
    return UploadApiError(
        status_code=response.status_code,
        code=str(error.get("code", "http.error")),
        message=str(error.get("message", "HTTP error")),
        details=details,
    )
