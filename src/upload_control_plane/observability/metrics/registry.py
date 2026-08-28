from __future__ import annotations

import math
import time
from collections import defaultdict
from collections.abc import Mapping

from sqlalchemy.orm import Session

from ..request_timing import monotonic_time
from .formatting import label_key, render_counter, render_histogram
from .operational import render_operational_metrics


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._histograms: dict[
            tuple[str, tuple[tuple[str, str], ...]],
            list[float],
        ] = defaultdict(list)

    def increment(
        self, name: str, labels: Mapping[str, str] | None = None, amount: float = 1
    ) -> None:
        self._counters[(name, label_key(labels))] += amount

    def observe(self, name: str, value: float, labels: Mapping[str, str] | None = None) -> None:
        self._histograms[(name, label_key(labels))].append(value)

    def storage_backpressure_reason(
        self,
        *,
        error_rate_threshold: float,
        p95_latency_ms: int,
    ) -> str | None:
        observations = [
            value
            for (name, _labels), values in self._histograms.items()
            if name == "storage_operation_duration_seconds"
            for value in values
        ]
        if not observations:
            return None

        error_count = sum(
            value
            for (name, _labels), value in self._counters.items()
            if name == "storage_operation_errors_total"
        )
        error_rate = error_count / len(observations)
        if error_rate_threshold > 0 and error_rate >= error_rate_threshold:
            return "storage_error_rate"

        if p95_latency_ms > 0:
            sorted_observations = sorted(observations)
            p95_index = max(math.ceil(len(sorted_observations) * 0.95) - 1, 0)
            p95_latency_seconds = sorted_observations[p95_index]
            if p95_latency_seconds * 1000 >= p95_latency_ms:
                return "storage_p95_latency"
        return None

    def reset_for_tests(self) -> None:
        self._counters.clear()
        self._histograms.clear()

    def render(self, session: Session | None = None) -> str:
        lines: list[str] = []
        render_counter(
            lines,
            "api_requests_total",
            "Total HTTP API requests.",
            self._counters,
            {"method": "unknown", "path": "unknown", "status_code": "unknown"},
        )
        render_histogram(
            lines,
            "api_request_duration_seconds",
            "HTTP API request duration in seconds.",
            self._histograms,
            {"method": "unknown", "path": "unknown", "status_code": "unknown"},
        )
        render_histogram(
            lines,
            "storage_operation_duration_seconds",
            "Object storage operation duration in seconds.",
            self._histograms,
            {"operation": "unknown"},
        )
        render_counter(
            lines,
            "storage_operation_errors_total",
            "Object storage operation errors.",
            self._counters,
            {"operation": "unknown", "error_code": "unknown"},
        )
        render_counter(
            lines,
            "storage_backpressure_rejects_total",
            "Storage backpressure rejects.",
            self._counters,
            {"reason": "unknown"},
        )
        render_counter(
            lines,
            "quota_rejects_total",
            "Quota rejects.",
            self._counters,
            {"tenant_id": "unknown", "scope": "unknown"},
        )
        render_counter(
            lines,
            "rate_limit_rejects_total",
            "Rate limit rejects.",
            self._counters,
            {"tenant_id": "unknown", "scope": "unknown"},
        )
        if session is not None:
            render_operational_metrics(lines, session)
        return "\n".join(lines) + "\n"


metrics_registry = MetricsRegistry()


def storage_backpressure_reason(
    *,
    error_rate_threshold: float,
    p95_latency_ms: int,
) -> str | None:
    return metrics_registry.storage_backpressure_reason(
        error_rate_threshold=error_rate_threshold,
        p95_latency_ms=p95_latency_ms,
    )


def record_storage_backpressure_reject(reason: str) -> None:
    metrics_registry.increment("storage_backpressure_rejects_total", {"reason": reason})


def storage_operation_started() -> float:
    return monotonic_time()


def record_storage_operation(
    operation: str, started_at: float, error_code: str | None = None
) -> None:
    metrics_registry.observe(
        "storage_operation_duration_seconds",
        (time.perf_counter() - started_at),
        {"operation": operation},
    )
    if error_code is not None:
        metrics_registry.increment(
            "storage_operation_errors_total",
            {"operation": operation, "error_code": error_code},
        )
