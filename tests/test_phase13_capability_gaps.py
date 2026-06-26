from __future__ import annotations

import pytest


@pytest.mark.xfail(
    reason=(
        "Phase 13 gap: backpressure settings and metrics exist, but no upload create or presign "
        "path rejects requests based on storage backpressure yet."
    ),
    run=False,
)
def test_backpressure_rejection_gate_gap() -> None:
    raise AssertionError("backpressure rejection gate not implemented")


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
