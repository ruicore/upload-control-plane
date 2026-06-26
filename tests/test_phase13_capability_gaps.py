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
        "Phase 13 gap: KMS configuration fields exist, but there is no policy path that "
        "requires KMS and rejects initiation when KMS is unavailable."
    ),
    run=False,
)
def test_kms_unavailable_rejection_gap() -> None:
    raise AssertionError("KMS unavailable rejection path not implemented")
