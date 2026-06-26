from __future__ import annotations

import pytest


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
