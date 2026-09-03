#!/usr/bin/env python3
"""Deterministic tests for RADIA → trajectory/radiation tolerance aggregation."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src-tauri" / "resources" / "ui"))

from physical_lab_radia_radiation_propagation import (
    summarize_propagation_records,
    assess_propagated_requirement,
)


def rec(seed, photon, power, excursion):
    return {
        "seed": seed,
        "observables": {
            "photon_energy_eV": photon,
            "P_larmor": power,
            "max_transverse_excursion_m": excursion,
        },
    }


def main() -> None:
    nominal = rec(None, 100.0, 4.0, 1.0e-4)
    members = [
        rec(10, 98.0, 3.8, 1.1e-4),
        rec(11, 101.0, 4.1, 1.4e-4),
        rec(12, 103.0, 4.2, 0.9e-4),
        rec(13, 99.0, 3.9, 1.2e-4),
    ]
    summary = summarize_propagation_records(nominal, members)
    assert summary["memberCount"] == 4
    photon = summary["metrics"]["photon_energy_eV"]
    assert photon["nominal"] == 100.0
    assert photon["min"] == 98.0 and photon["max"] == 103.0
    assert photon["maxAbsDeltaFromNominal"] == 3.0
    assert photon["count"] == 4

    passed = assess_propagated_requirement(members, "photon_energy_eV", lower=95.0, upper=105.0)
    assert passed["status"] == "PASS"
    assert passed["observedPassCount"] == 4

    reviewed = assess_propagated_requirement(members, "max_transverse_excursion_m", upper=1.2e-4)
    assert reviewed["status"] == "REVIEW"
    assert reviewed["observedPassCount"] == 3
    assert abs(reviewed["observedPassFraction"] - 0.75) < 1e-12

    try:
        assess_propagated_requirement(members, "P_larmor")
    except ValueError:
        pass
    else:
        raise AssertionError("missing engineering bound should be rejected")

    print("RADIA → Radiation propagation deterministic validation: PASS")


if __name__ == "__main__":
    main()
