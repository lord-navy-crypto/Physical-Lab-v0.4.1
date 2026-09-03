#!/usr/bin/env python3
"""Deterministic validation for the Physical Lab digital-twin scientific core."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(CORE_DIR))

from physical_lab_digital_twin import (
    analyze_beam_phase_space,
    compare_field_series,
    fit_linear_calibration,
    fit_model_affine,
    suggest_residual_measurement_points,
)

SNAPSHOT = ROOT / "docs" / "digital-twin-reference-validation.json"


def build_results() -> dict:
    calibration = fit_linear_calibration([0, 1, 2, 3, 4], [1, 3, 5, 7, 9])
    field = compare_field_series(
        [-2, -1, 0, 1, 2],
        [-0.9, -0.45, 0.0, 0.48, 0.94],
        [-1.0, -0.5, 0.0, 0.5, 1.0],
    )
    inverse = fit_model_affine([1, 3, 5, 7, 9], [0, 1, 2, 3, 4])
    beam = analyze_beam_phase_space(
        [-1.0, -0.25, 0.5, 1.25, 2.0],
        [-0.20, -0.05, 0.10, 0.28, 0.42],
        [-1.5, -0.7, 0.0, 0.8, 1.6],
        [-0.25, -0.12, 0.02, 0.15, 0.31],
        beta_gamma=500.0,
    )
    suggestions = suggest_residual_measurement_points(
        [0, 1, 2, 3, 4, 5],
        [0, 0.9, 2.4, 1.2, 0.3, 0],
        [0, 0.8, 1.5, 1.0, 0.2, 0],
        count=3,
    )
    checks = {
        "linear_sensor_calibration": {
            "slope": calibration.slope,
            "offset": calibration.offset,
            "rmse": calibration.rmse,
            "pass": abs(calibration.slope - 2.0) < 1e-12 and abs(calibration.offset - 1.0) < 1e-12 and calibration.rmse < 1e-12,
        },
        "field_comparison": {
            "rmse": field.rmse,
            "measured_integral": field.measured_integral,
            "model_integral": field.model_integral,
            "pass": field.n == 5 and field.rmse > 0 and math.isfinite(field.integral_difference),
        },
        "affine_inverse_fit": {
            "scale": inverse.scale,
            "offset": inverse.offset,
            "rmse_after": inverse.rmse_after,
            "pass": abs(inverse.scale - 2.0) < 1e-12 and abs(inverse.offset - 1.0) < 1e-12 and inverse.rmse_after < 1e-12,
        },
        "beam_phase_space": {
            "x_emittance": beam.x_plane.rms_emittance,
            "y_emittance": beam.y_plane.rms_emittance,
            "normalized_x_emittance": beam.normalized_x_emittance,
            "pass": beam.x_plane.rms_emittance > 0 and beam.y_plane.rms_emittance > 0 and beam.normalized_x_emittance is not None,
        },
        "residual_guided_sampling": {
            "suggestions": suggestions,
            "pass": len(suggestions) == 3 and suggestions[0]["position"] == 2.0,
            "boundary": "Heuristic residual-guided sampling; not Bayesian information gain or optimal experimental design.",
        },
    }
    return {
        "schema": "physical-lab-digital-twin-reference-v1",
        "purpose": "Deterministic verification of shared calibration, comparison, inverse-fit, beam phase-space, and residual-guided sampling definitions.",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    results = build_results()
    failed = [name for name, item in results["checks"].items() if item.get("pass") is False]
    if failed:
        raise SystemExit("Digital-twin reference validation failed: " + ", ".join(failed))
    text = json.dumps(results, indent=2, sort_keys=True) + "\n"
    if args.write:
        SNAPSHOT.write_text(text, encoding="utf-8")
        print(f"wrote {SNAPSHOT.relative_to(ROOT)}")
    if args.check:
        if not SNAPSHOT.exists():
            raise SystemExit("Digital-twin snapshot missing; run --write")
        if SNAPSHOT.read_text(encoding="utf-8") != text:
            raise SystemExit("Digital-twin snapshot is stale; run --write")
        print("digital-twin reference validation: PASS")
    if not args.write and not args.check:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
