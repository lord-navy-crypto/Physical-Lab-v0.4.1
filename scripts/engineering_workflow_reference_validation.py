#!/usr/bin/env python3
"""Deterministic validation for Physical Lab v0.8 engineering workflow."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "src-tauri" / "resources" / "ui" / "physical_lab_engineering_workflow.py"
SNAPSHOT = ROOT / "docs" / "engineering-workflow-reference-validation.json"

spec = importlib.util.spec_from_file_location("physical_lab_engineering_workflow", MOD)
eng = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(eng)


def build_results() -> dict:
    requirements = [
        {"id": "R-PERF", "metric": "performance", "lower": 9.5},
        {"id": "R-STEER", "metric": "steering", "upper": 0.25},
    ]
    req = eng.evaluate_requirements(
        {"performance": 10.0, "steering": 0.20},
        requirements,
        {"performance": 0.2, "steering": 0.02},
    )

    x = [0.0, 0.5, 1.0, 1.5, 2.0]
    model = [0.0, 1.0, 0.0, -1.0, 0.0]
    measured = [0.01, 0.98, 0.02, -1.03, -0.01]
    sigma = [0.02] * len(x)
    field = eng.measured_field_residual(x, model, measured, sigma)

    sens = eng.local_sensitivity_screening([
        {"parameter": "gap", "delta_parameter": 0.1, "delta_response": -0.4},
        {"parameter": "period", "delta_parameter": 0.2, "delta_response": 0.1},
    ])

    designs = [
        {"design": "A", "performance": 10.0, "cost": 8.0},
        {"design": "B", "performance": 12.0, "cost": 11.0},
        {"design": "C", "performance": 9.0, "cost": 6.0},
        {"design": "D", "performance": 9.5, "cost": 9.0},
    ]
    pareto = eng.pareto_front(designs, {"performance": "max", "cost": "min"})

    robust = eng.robust_design_summary(
        {
            "A": [
                {"performance": 9.8, "steering": 0.18},
                {"performance": 10.1, "steering": 0.22},
                {"performance": 9.7, "steering": 0.20},
            ],
            "B": [
                {"performance": 10.2, "steering": 0.19},
                {"performance": 9.2, "steering": 0.21},
                {"performance": 10.0, "steering": 0.28},
            ],
        },
        requirements,
    )

    control = eng.bounded_calibration_update(1.0, 0.9, 1.0, 2.0, gain=0.5, lower_bound=0.0, upper_bound=2.0)
    thermal = eng.undulator_thermal_coupling(0.020, 0.05, 80.0, 12e-6, 10.0)
    batch = eng.build_batch_plan([{"gap": 4.0}, {"gap": 4.1}, {"gap": 4.2}, {"gap": 4.3}, {"gap": 4.4}], workers=2, chunk_size=2)

    checks = {
        "requirements": {
            "overall_status": req["overall_status"],
            "pass": req["overall_status"] == "PASS",
        },
        "measured_field": {
            "rmse": field["rmse"],
            "integral_difference": field["integral_difference"],
            "uncertainty_normalized_rms": field["uncertainty_normalized_rms"],
            "pass": field["rmse"] > 0 and field["uncertainty_normalized_rms"] is not None,
        },
        "sensitivity": {
            "ranked_parameters": [row["parameter"] for row in sens],
            "pass": [row["parameter"] for row in sens] == ["gap", "period"],
        },
        "pareto": {
            "designs": [row["design"] for row in pareto["designs"]],
            "pass": [row["design"] for row in pareto["designs"]] == ["A", "B", "C"],
        },
        "robust_design": {
            "A_pass_fraction": robust["designs"][0]["pass_fraction"],
            "B_pass_fraction": robust["designs"][1]["pass_fraction"],
            "pass": robust["designs"][0]["design"] == "A" and math.isclose(robust["designs"][0]["pass_fraction"], 1.0),
        },
        "bounded_update": {
            "next_parameter": control["next_parameter"],
            "pass": math.isclose(control["next_parameter"], 1.025, rel_tol=0, abs_tol=1e-12),
        },
        "thermal_coupling": {
            "period_relative": thermal["changes"]["period_relative"],
            "photon_energy_relative": thermal["changes"]["photon_energy_relative"],
            "pass": thermal["changes"]["period_relative"] > 0 and thermal["changes"]["photon_energy_relative"] < 0,
        },
        "batch_plan": {
            "chunk_count": batch["chunk_count"],
            "minimum_scheduling_waves": batch["minimum_scheduling_waves"],
            "unique_fingerprints": len({job["fingerprint"] for job in batch["jobs"]}),
            "pass": batch["chunk_count"] == 3 and batch["minimum_scheduling_waves"] == 2 and len({job["fingerprint"] for job in batch["jobs"]}) == 5,
        },
    }
    return {
        "schema": "physical-lab-engineering-workflow-reference-v1",
        "purpose": "Deterministic verification of requirement, measured-field, sensitivity, Pareto, robust-design, thermal/control and batch-planning definitions.",
        "checks": checks,
        "boundary": "These checks validate software definitions and deterministic synthetic cases, not a physical device or certified engineering process.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = build_results()
    failed = [name for name, item in result["checks"].items() if item.get("pass") is False]
    if failed:
        raise SystemExit("engineering workflow validation failed: " + ", ".join(failed))
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write:
        SNAPSHOT.write_text(text, encoding="utf-8")
        print(f"wrote {SNAPSHOT.relative_to(ROOT)}")
    if args.check:
        if not SNAPSHOT.exists():
            raise SystemExit("engineering workflow snapshot missing; run --write")
        if SNAPSHOT.read_text(encoding="utf-8") != text:
            raise SystemExit("engineering workflow snapshot is stale; run --write")
        print("engineering workflow reference validation: PASS")
    if not args.write and not args.check:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
