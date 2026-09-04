#!/usr/bin/env python3
"""Deterministic validation for the shared new-model refinement evidence layer."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_kerr_geodesics as kerr
import physical_lab_kerr_workflow as kerr_workflow
import physical_lab_lattice_dynamics as lattice
import physical_lab_lattice_workflow as lattice_workflow
import physical_lab_new_model_refinements as refine
import physical_lab_solar_system_dynamics as solar
import physical_lab_solar_system_workflow as solar_workflow


def main() -> None:
    # Kerr: frequency structure must remain explicitly an integrable diagnostic.
    kcfg = kerr.KerrOrbitConfig(
        spin=0.6,
        inclination_deg=55.0,
        particle_type="massive",
        periapsis=6.5,
        apoapsis=10.0,
        lam_max=24.0,
        samples=1400,
        rtol=1e-9,
        atol=1e-11,
    )
    kres = kerr.integrate_case(kcfg)
    kref = refine.kerr_frequency_refinement(kcfg, result=kres, scan=False)
    assert kref["schema"] == refine.REFINEMENT_SCHEMA
    assert kref["model_variant"] == refine.KERR_VARIANT
    assert "integrable" in kref["boundary"].lower()
    assert kref["omega_phi_mino"] is not None
    phi_theta = kref["ratios"]["omega_phi_over_omega_theta"]
    if kref["omega_theta_mino"] is not None:
        assert phi_theta is not None
        assert phi_theta["denominator"] <= 12
        assert phi_theta["absolute_detuning"] >= 0.0

    kmanifest = kerr_workflow.build_kerr_manifest(kcfg, preset="compact", source_commit="refinement-validation")
    kevidence = refine.build_model_evidence_contract(refine.KERR_VARIANT, manifest=kmanifest, refinement=kref)
    assert kevidence["experiment_sha256"] == kmanifest["experiment_sha256"]
    assert kevidence["computational_screening"] == "NOT-RUN"
    assert len(kevidence["evidence_sha256"]) == 64
    assert "generic chaos" in " ".join(kevidence["unsupported_claims"]).lower()

    # Solar System: use the rebuilt barycentric solver and a finite-window 5:2
    # projected-longitude phase proxy; never label it a canonical resonant angle.
    scfg = solar.SolarSystemConfig(
        duration_years=12.0,
        samples=500,
        inclination_jupiter_deg=10.0,
        rtol=1e-10,
        atol=1e-12,
        max_step_years=0.03,
    )
    sres = solar.integrate_case(scfg)
    sref = refine.solar_commensurability_refinement(sres)
    assert sref["model_variant"] == refine.SOLAR_VARIANT
    assert len(sref["phase_wrapped_rad"]) == len(sres["time_years"])
    assert np.all(np.isfinite(np.asarray(sref["phase_wrapped_rad"], dtype=float)))
    assert 0.0 <= float(sref["finite_window_circular_concentration"]) <= 1.0 + 1e-12
    assert np.isfinite(float(sref["phase_drift_rad_per_year"]))
    assert "not a canonical" in sref["boundary"].lower()
    assert len(sref["jupiter_eccentricity_spectrum"]) > 0

    smanifest = solar_workflow.build_solar_system_manifest(scfg, preset="compact", source_commit="refinement-validation")
    sevidence = refine.build_model_evidence_contract(refine.SOLAR_VARIANT, manifest=smanifest, refinement=sref)
    assert "full einstein" in " ".join(sevidence["unsupported_claims"]).lower()

    # Honeycomb: group velocity is a path derivative of the verified harmonic
    # Bloch reference, with corner values excluded from the global max.
    lcfg = lattice.LatticeConfig(
        nx=3,
        ny=3,
        layers=2,
        stacking="ABA",
        strain_x=0.0,
        k_in=10.0,
        k_inter=3.0,
        duration=0.6,
        samples=128,
    )
    lref = refine.lattice_transport_refinement(lcfg, points_per_segment=12, strain_sweep=False)
    assert lref["model_variant"] == refine.LATTICE_VARIANT
    assert lref["max_abs_path_group_velocity"] is not None
    assert float(lref["max_abs_path_group_velocity"]) >= 0.0
    assert len(lref["max_abs_path_group_velocity_by_branch"]) == 4 * lcfg.layers
    assert lref["dispersion_summary"]["gamma_zero_mode_count"] == 2
    assert lref["dispersion_summary"]["negative_eigenvalue_magnitude_max"] < 1e-8
    assert "path" in lref["boundary"].lower() and "reduced" in lref["boundary"].lower()

    lmanifest = lattice_workflow.build_lattice_manifest(lcfg, preset="compact", source_commit="refinement-validation")
    levidence = refine.build_model_evidence_contract(refine.LATTICE_VARIANT, manifest=lmanifest, refinement=lref)
    assert "ab-initio" in " ".join(levidence["unsupported_claims"]).lower()

    # Evidence hash is deterministic and changes when scientific identity changes.
    levidence2 = refine.build_model_evidence_contract(refine.LATTICE_VARIANT, manifest=lmanifest, refinement=lref)
    assert levidence2["evidence_sha256"] == levidence["evidence_sha256"]
    lchanged = lattice_workflow.build_lattice_manifest(
        lattice.LatticeConfig(**{**lcfg.__dict__, "strain_x": 0.02}),
        preset="compact",
        source_commit="refinement-validation",
    )
    changed_evidence = refine.build_model_evidence_contract(refine.LATTICE_VARIANT, manifest=lchanged, refinement=lref)
    assert changed_evidence["evidence_sha256"] != levidence["evidence_sha256"]

    report = refine.render_refinement_report_markdown(levidence, lref)
    assert levidence["evidence_sha256"] in report
    assert "Unsupported claims" in report
    assert "experimental validation" in report

    tauri = (ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    assert "physical_lab_new_model_refinements.py" in tauri
    assert "physical_lab_new_model_refinement_ui.py" in tauri
    facade = (UI / "physical_lab_engineering.py").read_text(encoding="utf-8")
    assert "render_new_model_refinement_workspace" in facade

    print("New model refinement validation: PASS")


if __name__ == "__main__":
    main()
