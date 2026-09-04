#!/usr/bin/env python3
"""Deterministic checks for the engineering decision layer on Physics Scenario mode."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

from physical_lab_application_modes import quantum_bound_state_verification  # noqa: E402
from physical_lab_engineering_scenarios import (  # noqa: E402
    SCENARIO_META,
    ising_engineering_review,
    quantum_engineering_review,
    transport_engineering_review,
)


def main() -> int:
    assert set(SCENARIO_META) == {
        "numerical-methods", "ising-monte-carlo", "random-walk-monte-carlo"
    }

    quantum = quantum_bound_state_verification(grid_points=160, width_nm=1.0, states=3)
    q_review = quantum_engineering_review(
        quantum,
        max_energy_error_pct=0.10,
        width_tolerance_pct=1.0,
        max_tolerance_energy_shift_pct=2.5,
    )
    assert q_review["schema"] == "physical-lab-engineering-scenario-review-v1"
    assert q_review["screening_status"] == "PASS"
    assert len(q_review["requirements"]) == 3
    assert q_review["responses"]["max_width_tolerance_energy_shift_pct"] > 1.9
    assert q_review["responses"]["max_width_tolerance_energy_shift_pct"] < 2.2
    assert q_review["responses"]["E1_tolerance_envelope_eV"][0] < q_review["responses"]["E1_exact_eV"]
    assert q_review["responses"]["E1_tolerance_envelope_eV"][1] > q_review["responses"]["E1_exact_eV"]

    q_review_strict = quantum_engineering_review(
        quantum,
        max_energy_error_pct=0.10,
        width_tolerance_pct=1.0,
        max_tolerance_energy_shift_pct=1.0,
    )
    assert q_review_strict["screening_status"] == "REVIEW"
    assert any(row["status"] == "REVIEW" for row in q_review_strict["requirements"])

    ising_result = {
        "rows": [
            {"T_over_JkB": 1.6, "abs_magnetization_per_spin": 0.94},
            {"T_over_JkB": 2.0, "abs_magnetization_per_spin": 0.84},
            {"T_over_JkB": 2.4, "abs_magnetization_per_spin": 0.55},
            {"T_over_JkB": 2.8, "abs_magnetization_per_spin": 0.22},
        ],
        "infinite_lattice_Tc_over_JkB": 2.269185314213022,
    }
    i_review = ising_engineering_review(
        ising_result,
        operating_temperature=2.0,
        minimum_abs_magnetization=0.70,
        minimum_critical_distance=0.20,
    )
    assert i_review["screening_status"] == "PASS"
    assert i_review["responses"]["thermal_margin_J_over_kB"] >= 0.0
    i_review_critical = ising_engineering_review(
        ising_result,
        operating_temperature=2.2,
        minimum_abs_magnetization=0.70,
        minimum_critical_distance=0.20,
    )
    assert i_review_critical["screening_status"] == "REVIEW"

    transport_result = {
        "inputs": {"diffusion_um2_s": 0.8, "drift_x_um_s": 0.25},
        "diffusion_relative_error": 0.025,
        "drift_absolute_error_um_s": 0.018,
    }
    t_review = transport_engineering_review(
        transport_result,
        max_diffusion_error_pct=5.0,
        max_drift_error_um_s=0.05,
        characteristic_length_um=10.0,
    )
    assert t_review["screening_status"] == "PASS"
    assert abs(t_review["responses"]["peclet_number"] - 3.125) < 1e-12
    assert abs(t_review["responses"]["diffusion_time_scale_s"] - 31.25) < 1e-12
    assert abs(t_review["responses"]["advection_time_scale_s"] - 40.0) < 1e-12

    t_review_bad = transport_engineering_review(
        {**transport_result, "diffusion_relative_error": 0.12},
        max_diffusion_error_pct=5.0,
        max_drift_error_um_s=0.05,
        characteristic_length_um=10.0,
    )
    assert t_review_bad["screening_status"] == "REVIEW"

    facade = (UI / "physical_lab_engineering.py").read_text(encoding="utf-8")
    config = (ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    assert "render_engineering_scenario_review" in facade
    assert "physical_lab_engineering_scenarios.py" in config

    print("PASS engineering scenario layer: requirements, signed margins, screening decisions and design-response metrics")
    print("Boundary: screening targets are editable engineering criteria, not standards, certification or experimental validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
