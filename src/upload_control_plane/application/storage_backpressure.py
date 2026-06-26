from __future__ import annotations

from dataclasses import dataclass

from upload_control_plane.api.errors import ApiError
from upload_control_plane.config import Settings
from upload_control_plane.observability import (
    record_storage_backpressure_reject,
    storage_backpressure_reason,
)

_BOUNDED_REASONS = {
    "error_rate",
    "latency",
    "manual",
}


@dataclass(frozen=True, slots=True)
class StorageBackpressureDecision:
    rejected: bool
    reason: str
    retry_after_seconds: int | None


def evaluate_storage_backpressure(settings: Settings) -> StorageBackpressureDecision:
    forced_reason = settings.storage_backpressure_forced_reason.strip().lower()
    if forced_reason:
        return StorageBackpressureDecision(
            rejected=True,
            reason=_bounded_reason(forced_reason),
            retry_after_seconds=_retry_after(settings),
        )

    observed_error_rate = settings.storage_backpressure_observed_error_rate
    if (
        observed_error_rate is not None
        and observed_error_rate >= settings.backpressure_storage_error_rate_threshold
    ):
        return StorageBackpressureDecision(
            rejected=True,
            reason="error_rate",
            retry_after_seconds=_retry_after(settings),
        )

    observed_p95_latency_ms = settings.storage_backpressure_observed_p95_latency_ms
    if (
        observed_p95_latency_ms is not None
        and observed_p95_latency_ms >= settings.backpressure_storage_p95_latency_ms
    ):
        return StorageBackpressureDecision(
            rejected=True,
            reason="latency",
            retry_after_seconds=_retry_after(settings),
        )

    metric_reason = storage_backpressure_reason(
        error_rate_threshold=settings.backpressure_storage_error_rate_threshold,
        p95_latency_ms=settings.backpressure_storage_p95_latency_ms,
    )
    if metric_reason is not None:
        return StorageBackpressureDecision(
            rejected=True,
            reason=metric_reason,
            retry_after_seconds=_retry_after(settings, default=30),
        )

    return StorageBackpressureDecision(rejected=False, reason="", retry_after_seconds=None)


def reject_if_storage_backpressure(settings: Settings) -> None:
    decision = evaluate_storage_backpressure(settings)
    if not decision.rejected:
        return
    record_storage_backpressure_reject(decision.reason)
    headers = {}
    details: dict[str, str | int] = {
        "source": "storage_health",
        "reason": decision.reason,
    }
    if decision.retry_after_seconds is not None:
        headers["Retry-After"] = str(decision.retry_after_seconds)
        details["retry_after_seconds"] = decision.retry_after_seconds
    raise ApiError(
        status_code=503,
        code="storage.backpressure",
        message="Storage health is currently applying backpressure.",
        details=details,
        headers=headers,
    )


def _bounded_reason(reason: str) -> str:
    if reason in _BOUNDED_REASONS:
        return reason
    return "manual"


def _retry_after(settings: Settings, *, default: int | None = None) -> int | None:
    retry_after = settings.storage_backpressure_retry_after_seconds
    if retry_after is None or retry_after <= 0:
        return default
    return retry_after
