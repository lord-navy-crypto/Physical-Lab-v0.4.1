#!/usr/bin/env python3
"""Deterministic checks for Physical Lab's model-specific engineering profiles."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src-tauri" / "resources" / "ui" / "physical_lab_model_engineering.py"
REFERENCE_PATH = ROOT / "docs" / "model-engineering-reference-validation.json"

spec = importlib.util.spec_from_file_location("physical_lab_model_engineering", MODULE_PATH)
eng = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(eng)


def build_payload() -> dict:
    scorecards = {}
    for profile, metrics in eng.profile_reference_cases().items():
        result = eng.profile_scorecard(profile, metrics)
        scorecards[profile] = {
            "overall_status": result["overall_status"],
            "metric_completeness": result["metric_completeness"],
            "requirement_count": len(result["requirements"]),
            "statuses": [row["status"] for row in result["requirements"]],
        }

    convergence_order = eng.estimate_convergence_order(0.04, 0.01, 2.0)
    stability = eng.replicate_stability([0.99, 1.0, 1.01, 1.0])
    frontier = eng.cost_accuracy_front([
        {"design": "cheap", "cost": 1.0, "error": 0.10},
        {"design": "balanced", "cost": 2.0, "error": 0.05},
        {"design": "dominated", "cost": 3.0, "error": 0.08},
    ])
    return {
        "schema": "physical-lab-model-engineering-reference-v1",
        "scorecards": scorecards,
        "convergence_order": convergence_order,
        "relative_change": eng.relative_change(10.0, 10.5),
        "replicate_stability": {
            "n": stability["n"],
            "mean": stability["mean"],
            "sample_std": stability["sample_std"],
            "coefficient_of_variation": stability["coefficient_of_variation"],
            "p05": stability["p05"],
            "median": stability["median"],
            "p95": stability["p95"],
            "range": stability["range"],
        },
        "cost_accuracy_front_indices": frontier["indices"],
        "boundary": "Synthetic deterministic math validation only; not experimental or product certification evidence.",
    }


def compare(expected, actual, path="root") -> None:
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"{path}: expected mapping"
        assert set(expected) == set(actual), f"{path}: key mismatch"
        for key in expected:
            compare(expected[key], actual[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        assert isinstance(actual, list) and len(expected) == len(actual), f"{path}: list mismatch"
        for i, (e, a) in enumerate(zip(expected, actual)):
            compare(e, a, f"{path}[{i}]")
        return
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        assert isinstance(actual, (int, float)) and not isinstance(actual, bool), f"{path}: numeric mismatch"
        assert math.isclose(float(expected), float(actual), rel_tol=1e-12, abs_tol=1e-12), f"{path}: {expected} != {actual}"
        return
    assert expected == actual, f"{path}: {expected!r} != {actual!r}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    payload = build_payload()

    # Hard invariants independent of the committed snapshot.
    assert set(payload["scorecards"]) == set(eng.SUPPORTED_PROFILES)
    assert all(item["overall_status"] == "PASS" for item in payload["scorecards"].values())
    assert all(item["metric_completeness"] == 1.0 for item in payload["scorecards"].values())
    assert math.isclose(payload["convergence_order"], 2.0, abs_tol=1e-12)
    assert payload["cost_accuracy_front_indices"] == [0, 1]

    if args.write:
        REFERENCE_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"WROTE {REFERENCE_PATH}")
        return 0
    if args.check:
        expected = json.loads(REFERENCE_PATH.read_text())
        compare(expected, payload)
        print("PASS model-specific engineering reference validation")
        return 0
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
