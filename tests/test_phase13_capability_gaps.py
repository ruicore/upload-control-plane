from __future__ import annotations

import pytest


@pytest.mark.xfail(
    reason=(
        "Phase 13 gap: quota/backpressure settings and metrics exist, but upload or presign "
        "rejection gates are not implemented yet."
    ),
    run=False,
)
def test_quota_or_backpressure_rejection_gap() -> None:
    raise AssertionError("quota/backpressure rejection gate not implemented")


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
