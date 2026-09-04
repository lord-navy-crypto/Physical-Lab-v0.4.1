#!/usr/bin/env python3
"""Deterministic regression checks for Physical Lab dual-mode physics scenarios."""
from __future__ import annotations

from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

from physical_lab_application_modes import (  # noqa: E402
    APPLICATION_PROFILES,
    ISING_TC_SQUARE_2D,
    brownian_transport_study,
    ising_criticality_study,
    padded_range,
    quantum_bound_state_verification,
)


def main() -> int:
    assert set(APPLICATION_PROFILES) == {
        "numerical-methods", "ising-monte-carlo", "random-walk-monte-carlo"
    }

    # Tight display range: large common offset must not force a misleading zero baseline.
    yrange = padded_range([1_000_000.001, 1_000_000.004, 1_000_000.007])
    assert yrange is not None
    assert yrange[0] > 999_999.0 and yrange[1] < 1_000_001.0
    assert yrange[0] < 1_000_000.001 < 1_000_000.007 < yrange[1]

    # Quantum verification: centered second-order finite difference should converge near p=2.
    quantum = quantum_bound_state_verification(grid_points=160, width_nm=1.0, states=3)
    assert quantum["profile"] == "numerical-methods"
    assert quantum["scenario"] == "quantum-bound-state-verification"
    assert len(quantum["energies"]) == 3
    errors = [row["relative_error_E1"] for row in quantum["convergence"]]
    assert all(math.isfinite(float(v)) and float(v) > 0 for v in errors)
    assert errors[-1] < errors[0]
    order = float(quantum["observed_convergence_order"])
    assert 1.7 <= order <= 2.3, order
    assert float(quantum["energies"][0]["relative_error"]) < 5e-4

    # Ising physics scene: basic observables and the exact infinite-lattice Tc reference remain bounded.
    ising = ising_criticality_study(
        lattice_size=8,
        temperature_min=1.7,
        temperature_max=3.5,
        temperature_points=5,
        burn_sweeps=100,
        sample_sweeps=180,
        seed=20260904,
    )
    rows = ising["rows"]
    assert len(rows) == 5
    assert abs(float(ising["infinite_lattice_Tc_over_JkB"]) - ISING_TC_SQUARE_2D) < 1e-12
    for row in rows:
        assert -2.1 <= float(row["energy_per_spin_J"]) <= 0.1
        assert 0.0 <= float(row["abs_magnetization_per_spin"]) <= 1.0
        assert float(row["heat_capacity_per_spin_kB"]) >= 0.0
        assert float(row["susceptibility_per_spin"]) >= 0.0
        assert math.isfinite(float(row["binder_cumulant"]))
    assert float(rows[0]["abs_magnetization_per_spin"]) > float(rows[-1]["abs_magnetization_per_spin"])

    # Brownian transport: recover imposed D and drift without counting mean drift as MSD diffusion.
    transport = brownian_transport_study(
        diffusion_um2_s=0.8,
        drift_x_um_s=0.25,
        dt_s=0.02,
        steps=220,
        particles=2600,
        seed=20260904,
        representative_trajectories=12,
    )
    assert transport["profile"] == "random-walk-monte-carlo"
    assert transport["scenario"] == "brownian-drift-diffusion"
    assert float(transport["diffusion_relative_error"]) < 0.08
    assert float(transport["drift_absolute_error_um_s"]) < 0.05
    assert len(transport["trajectories"]) == 12
    final_time = float(transport["time_s"][-1])
    expected_msd = 4.0 * 0.8 * final_time
    assert abs(float(transport["theoretical_msd_um2"][-1]) - expected_msd) < 1e-10

    print("PASS dual-mode physics applications: quantum numerical verification, Ising criticality, Brownian transport, tight display ranges")
    print("Boundary: mathematical tools remain standalone; physics scenarios add bounded model context rather than replacing the underlying methods")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
