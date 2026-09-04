"""Display-only axis range helpers for Physical Lab physics scenarios."""
from __future__ import annotations

import math
from typing import Any


def _np():
    import numpy as np
    return np


def padded_range(
    values: Any,
    *,
    pad_fraction: float = 0.08,
    clamp: tuple[float | None, float | None] | None = None,
) -> list[float] | None:
    """Return a tight finite display range without changing stored values.

    Non-constant data are padded from their actual span, so a large common
    offset does not visually erase a small scientific difference. Constant
    traces use a separate scale-aware pad to avoid a zero-width axis.
    """
    np = _np()
    try:
        arr = np.asarray(values, dtype=float).ravel()
    except Exception:
        return None
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    lo = float(np.min(arr)); hi = float(np.max(arr))
    span = hi - lo
    scale = max(abs(lo), abs(hi), 1.0)
    constant_threshold = max(scale * 1e-12, 1e-15)
    if span <= constant_threshold:
        pad = max(scale * 0.04, 1e-9)
    else:
        pad = max(
            span * max(float(pad_fraction), 0.0),
            scale * 1e-12,
            1e-15,
        )
    lo -= pad; hi += pad
    if clamp is not None:
        lower, upper = clamp
        if lower is not None:
            lo = max(lo, float(lower))
        if upper is not None:
            hi = min(hi, float(upper))
    if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
        return None
    return [lo, hi]
