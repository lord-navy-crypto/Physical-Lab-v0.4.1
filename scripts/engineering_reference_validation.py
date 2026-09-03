#!/usr/bin/env python3
"""Deterministic checks for Physical Lab engineering uncertainty math."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "src-tauri" / "resources" / "ui" / "physical_lab_engineering.py"
spec = importlib.util.spec_from_file_location("physical_lab_engineering", MOD)
eng = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(eng)

rows = [
    {"component": "a", "category": "measurement", "standard_uncertainty": 3.0, "sensitivity": 2.0, "tolerance_half_width": 4.0},
    {"component": "b", "category": "manufacturing", "standard_uncertainty": 4.0, "sensitivity": 1.0, "tolerance_half_width": 3.0},
]

budget = eng.linear_uncertainty_budget(rows)
# standard effects are 6 and 4 -> sqrt(52)
assert math.isclose(budget["combined_standard_uncertainty"], math.sqrt(52.0), rel_tol=0, abs_tol=1e-12)
assert math.isclose(budget["expanded_uncertainty_k2"], 2.0 * math.sqrt(52.0), rel_tol=0, abs_tol=1e-12)
assert math.isclose(sum(x["independent_variance_share"] for x in budget["contributions"]), 1.0, abs_tol=1e-12)

stack = eng.tolerance_stack(rows)
# tolerance effects are 8 and 3
assert math.isclose(stack["rss_half_width"], math.sqrt(73.0), abs_tol=1e-12)
assert math.isclose(stack["worst_case_half_width"], 11.0, abs_tol=1e-12)

assert eng.requirement_assessment(5.0, 0.0, 10.0, 1.0)["status"] == "PASS"
assert eng.requirement_assessment(9.5, 0.0, 10.0, 1.0)["status"] == "REVIEW"
assert eng.requirement_assessment(10.5, 0.0, 10.0, 0.1)["status"] == "FAIL"

val = eng.validation_comparison(10.0, 9.0, 0.6, 0.8, 0.0)
assert math.isclose(val["combined_standard_uncertainty"], 1.0, abs_tol=1e-12)
assert math.isclose(val["normalized_discrepancy"], 1.0, abs_tol=1e-12)

corr = [[1.0, 1.0], [1.0, 1.0]]
fully = eng.linear_uncertainty_budget(rows, corr)
assert math.isclose(fully["combined_standard_uncertainty"], 10.0, abs_tol=1e-12)

for profile in eng.PROFILE_COMPONENTS:
    template = eng.default_budget(profile)
    assert template
    assert all(float(r["standard_uncertainty"]) == 0.0 for r in template)
    assert all(float(r["sensitivity"]) == 0.0 for r in template)

try:
    import numpy as np  # noqa: F401
except Exception:
    print("PASS engineering VVUQ core (Monte Carlo skipped: numpy unavailable)")
else:
    mc = eng.linearized_monte_carlo([
        {"component": "x", "standard_uncertainty": 2.0, "sensitivity": 3.0}
    ], nominal=10.0, samples=50000, seed=123)
    assert abs(mc["mean"] - 10.0) < 0.08
    assert abs(mc["std"] - 6.0) < 0.08
    print("PASS engineering VVUQ core + linearized Monte Carlo")
