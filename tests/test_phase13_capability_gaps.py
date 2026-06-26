from __future__ import annotations

import pytest

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


@pytest.mark.xfail(
    reason=(
        "Phase 13 gap: KMS configuration fields exist, but there is no policy path that "
        "requires KMS and rejects initiation when KMS is unavailable."
    ),
    run=False,
)
def test_kms_unavailable_rejection_gap() -> None:
    raise AssertionError("KMS unavailable rejection path not implemented")


@pytest.mark.xfail(
    reason=(
        "Phase 13 gap: completed dataset reconciliation classifies missing-object, "
        "metadata-only, verified, and object-only cases in the lifecycle worker, but no "
        "product path rebuilds dataset DB metadata from an object-only reference or restores "
        "a missing final object."
    ),
    run=False,
)
def test_completed_dataset_automated_restore_or_rebuild_gap() -> None:
    raise AssertionError("completed dataset automated restore or rebuild not implemented")
