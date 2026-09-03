#!/usr/bin/env python3
"""Deterministic checks for Physical Lab nonlinear tolerance post-processing."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

from physical_lab_radia_tolerance import summarize_component_ensemble, assess_observed_tolerance


def main() -> None:
    z = [-2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0]
    nominal = [0.0, 0.5, 1.0, 0.5, 0.0, -0.5, -1.0, -0.5, 0.0]
    e1 = [v + 0.01 for v in nominal]
    e2 = [v - 0.02 for v in nominal]
    e3 = [v + (0.03 if i == 2 else 0.0) for i, v in enumerate(nominal)]
    e4 = [v + (-0.04 if i == 6 else 0.0) for i, v in enumerate(nominal)]

    out = summarize_component_ensemble(z, nominal, [e1, e2, e3, e4], [10, 11, 12, 13])
    assert out["summary"]["memberCount"] == 4
    assert abs(out["summary"]["observedWorstMaxAbsDeviation_T"] - 0.04) < 1e-12
    assert len(out["p05_T"]) == len(z)
    assert len(out["p95_T"]) == len(z)
    assert all(lo <= hi for lo, hi in zip(out["p05_T"], out["p95_T"]))
    assert [m["seed"] for m in out["members"]] == [10, 11, 12, 13]

    passed = assess_observed_tolerance(out, 0.05)
    assert passed["status"] == "PASS"
    assert passed["observedPassCount"] == 4
    assert abs(passed["observedWorstMargin_T"] - 0.01) < 1e-12

    review = assess_observed_tolerance(out, 0.025)
    assert review["status"] == "REVIEW"
    assert review["observedPassCount"] == 2
    assert review["observedPassFraction"] == 0.5

    try:
        assess_observed_tolerance(out, 0.0)
    except ValueError:
        pass
    else:
        raise AssertionError("zero requirement limit must be rejected")

    print("Nonlinear tolerance deterministic validation: PASS")


if __name__ == "__main__":
    main()
