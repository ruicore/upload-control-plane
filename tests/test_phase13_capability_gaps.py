from __future__ import annotations

import pytest


@pytest.mark.xfail(
    reason=(
        "Phase 13 gap: retention/legal-hold protected purge denial has storage capability "
        "metadata, but no purge policy workflow is implemented yet."
    ),
    run=False,
)
def test_retention_or_legal_hold_protected_purge_denial_gap() -> None:
    raise AssertionError("purge policy workflow not implemented")


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
        "Phase 13 gap: restore reconciliation is supported for in-progress multipart parts; "
        "completed dataset restore from DB/object-storage loss is not implemented yet."
    ),
    run=False,
)
def test_completed_dataset_restore_reconciliation_gap() -> None:
    raise AssertionError("completed dataset restore reconciliation not implemented")
