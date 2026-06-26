from __future__ import annotations

from upload_control_plane.application.storage_backpressure import evaluate_storage_backpressure
from upload_control_plane.config import get_settings


def test_backpressure_rejection_gate_gap_closed() -> None:
    settings = get_settings().model_copy(
        update={
            "storage_backpressure_observed_error_rate": 0.25,
            "backpressure_storage_error_rate_threshold": 0.05,
            "storage_backpressure_retry_after_seconds": 15,
        }
    )

    decision = evaluate_storage_backpressure(settings)

    assert decision.rejected is True
    assert decision.reason == "error_rate"
    assert decision.retry_after_seconds == 15
