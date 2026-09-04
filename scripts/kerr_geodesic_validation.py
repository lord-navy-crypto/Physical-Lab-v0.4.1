#!/usr/bin/env python3
"""Deterministic contract checks for the Physical Lab Kerr geodesic model."""
from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "src-tauri" / "resources" / "ui"
CORE_PATH = UI_DIR / "physical_lab_kerr_geodesics.py"
UI_PATH = UI_DIR / "physical_lab_kerr_ui.py"
TAURI_PATH = ROOT / "src-tauri" / "tauri.conf.json"
ENGINEERING_PATH = UI_DIR / "physical_lab_engineering.py"


def load_core():
    spec = importlib.util.spec_from_file_location("physical_lab_kerr_geodesics", CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Kerr core")
    module = importlib.util.module_from_spec(spec)
    sys.modules["physical_lab_kerr_geodesics"] = module
    spec.loader.exec_module(module)
    return module


def main() -> None:
    k = load_core()

    assert abs(k.horizon_radius(0.0) - 2.0) < 1e-12
    assert abs(k.horizon_radius(0.6) - 1.8) < 1e-12

    # Schwarzschild null benchmark: r_ph=3M and total impact parameter^2=27M^2.
    e, lz, q, r0 = k.solve_photon_spherical_constants(0.0, 60.0)
    assert abs(e - 1.0) < 1e-14
    assert abs(r0 - 3.0) < 1e-12
    assert abs((lz * lz + q) - 27.0) < 1e-10
    assert abs(float(k.radial_potential(r0, 0.0, e, lz, q, 0.0))) < 1e-9
    assert abs(float(k.radial_potential_dr(r0, 0.0, e, lz, q, 0.0))) < 1e-9

    # High-spin prograde spherical photon branch: this is where the old free
    # two-variable root was most likely to fail from a poor initial guess.
    e9, lz9, q9, r9 = k.solve_photon_spherical_constants(0.9, 60.0)
    assert r9 > k.horizon_radius(0.9)
    assert lz9 > 0.0 and q9 >= 0.0
    assert abs(float(k.radial_potential(r9, 0.9, e9, lz9, q9, 0.0))) < 1e-7
    assert abs(float(k.radial_potential_dr(r9, 0.9, e9, lz9, q9, 0.0))) < 1e-7

    # Bound massive orbit must satisfy both requested radial turning points.
    em, lm, qm = k.solve_massive_bound_constants(0.6, 60.0, 6.5, 10.0)
    assert 0.0 < em < 1.0
    assert qm >= 0.0
    assert abs(float(k.radial_potential(6.5, 0.6, em, lm, qm, 1.0))) < 1e-7
    assert abs(float(k.radial_potential(10.0, 0.6, em, lm, qm, 1.0))) < 1e-7

    massive = k.integrate_case(
        k.KerrOrbitConfig(
            spin=0.6,
            inclination_deg=60.0,
            particle_type="massive",
            lam_max=2.0,
            samples=400,
            rtol=1e-9,
            atol=1e-11,
        )
    )
    assert massive["status"] == "completed"
    assert massive["residuals"]["combined_max"] < 1e-6
    msummary = k.result_summary(massive)
    assert msummary["r_min"] > k.horizon_radius(0.6)
    assert msummary["r_max"] <= 10.00001

    photon = k.integrate_case(
        k.KerrOrbitConfig(
            spin=0.9,
            inclination_deg=60.0,
            particle_type="photon",
            lam_max=0.8,
            samples=300,
            rtol=1e-9,
            atol=1e-11,
        )
    )
    assert photon["status"] == "completed"
    psummary = k.result_summary(photon)
    assert psummary["first_integral_residual_max"] < 1e-6
    assert psummary["photon_radial_instability_mino"] > 0.0
    assert np.isfinite(psummary["photon_radial_instability_coordinate_time"])

    x, y, z = k.oblate_xyz(
        np.asarray([3.0]), np.asarray([math.pi / 2.0]), np.asarray([0.0]), 0.6
    )
    assert abs(float(z[0])) < 1e-12
    assert float(x[0]) > 3.0
    assert abs(float(y[0])) < 1e-12

    # UI module must be importable once the numerical core is loaded.
    ui_spec = importlib.util.spec_from_file_location("physical_lab_kerr_ui", UI_PATH)
    if ui_spec is None or ui_spec.loader is None:
        raise RuntimeError("unable to load Kerr UI")
    ui = importlib.util.module_from_spec(ui_spec)
    ui_spec.loader.exec_module(ui)
    assert callable(ui.render_kerr_geodesic_workspace)

    tauri = TAURI_PATH.read_text(encoding="utf-8")
    assert "physical_lab_kerr_geodesics.py" in tauri
    assert "physical_lab_kerr_ui.py" in tauri
    facade = ENGINEERING_PATH.read_text(encoding="utf-8")
    assert "render_kerr_geodesic_workspace" in facade

    print("Kerr geodesic model validation: PASS")


if __name__ == "__main__":
    main()
