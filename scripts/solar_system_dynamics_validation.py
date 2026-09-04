#!/usr/bin/env python3
"""Deterministic validation for the Physical Lab Sun-Jupiter-Saturn model."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = ROOT / "src-tauri" / "resources" / "ui"
TAURI_PATH = ROOT / "src-tauri" / "tauri.conf.json"
ENGINEERING_PATH = UI_DIR / "physical_lab_engineering.py"
WORKER_PATH = UI_DIR / "physical_lab_job_worker.py"

import sys
sys.path.insert(0, str(UI_DIR))

import numpy as np
import physical_lab_job_worker as worker
import physical_lab_project_kernel as project
import physical_lab_solar_system_dynamics as core
import physical_lab_solar_system_workflow as workflow


def main() -> None:
    cfg = core.SolarSystemConfig(
        duration_years=1.0,
        samples=240,
        inclination_jupiter_deg=10.0,
        rtol=1e-10,
        atol=1e-12,
        max_step_years=0.03,
    )
    state = core.initial_state(cfg)
    r0, v0 = core._unpack(state)
    m = core.masses(cfg)
    assert np.linalg.norm(np.sum(m[:, None] * r0, axis=0)) < 1e-12
    assert np.linalg.norm(np.sum(m[:, None] * v0, axis=0)) < 1e-12

    baseline = core.integrate_case(cfg)
    summary = core.result_summary(baseline)
    assert baseline["status"] == "completed"
    assert summary["invariants_expected"] is True
    assert summary["barycenter_position_drift_AU"] < 1e-8
    assert summary["absolute_linear_momentum_drift"] < 1e-10
    assert summary["relative_energy_drift"] < 2e-8
    assert summary["relative_angular_momentum_drift"] < 2e-8
    assert 2.0 < summary["final_period_ratio"] < 3.0
    assert summary["minimum_separation_AU"] > 0.1

    one_pn = core.integrate_case(core.SolarSystemConfig(
        duration_years=0.5,
        samples=160,
        inclination_jupiter_deg=10.0,
        solar_1pn=True,
        rtol=1e-10,
        atol=1e-12,
        max_step_years=0.03,
    ))
    assert core.result_summary(one_pn)["invariants_expected"] is False

    cross_cfg = core.SolarSystemConfig(
        duration_years=0.25,
        samples=120,
        velocity_cross=True,
        velocity_cross_strength=1e-4,
    )
    r, v = core._unpack(core.initial_state(cross_cfg))
    rel_v = v[1] - v[0]
    omega = np.asarray([0.0, 0.0, cross_cfg.omega_z_per_year])
    cross_acc = cross_cfg.velocity_cross_strength * np.cross(omega, rel_v)
    assert abs(float(np.dot(cross_acc, rel_v))) < 1e-12

    ftle = core.finite_time_lyapunov_indicator(cfg, d0=1e-8, segment_years=0.25, max_years=1.0)
    assert np.isfinite(ftle["finite_time_rate_per_year"])
    assert ftle["renormalizations"] == 4
    assert "not an asymptotic proof" in ftle["boundary"]

    refinement = core.run_refinement_pair(cfg)
    assert np.isfinite(refinement["max_relative_change"])

    manifest_a = workflow.build_solar_system_manifest(cfg, preset="compact", source_commit="validation-sha")
    manifest_b = workflow.build_solar_system_manifest(cfg, preset="compact", source_commit="validation-sha")
    assert manifest_a["experiment_sha256"] == manifest_b["experiment_sha256"]
    assert manifest_a["model"]["variant"] == core.MODEL_VARIANT
    assert workflow.is_solar_system_manifest(manifest_a)
    changed = workflow.build_solar_system_manifest(
        core.SolarSystemConfig(**{**cfg.__dict__, "inclination_jupiter_deg": 20.0}),
        preset="compact",
        source_commit="validation-sha",
    )
    assert changed["experiment_sha256"] != manifest_a["experiment_sha256"]

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PHYSICAL_LAB_DATA_DIR"] = tmp
        project_dir, _ = project.create_project("Solar System CI", research_question="Synthetic deterministic integration test")
        exp = project.register_experiment(project_dir, manifest_a)
        assert exp["experiment_sha256"] == manifest_a["experiment_sha256"]

        job_dir = Path(tmp) / "compute-jobs" / "job-solar-ci"
        job_dir.mkdir(parents=True)
        (job_dir / "manifest.json").write_text(json.dumps(manifest_a), encoding="utf-8")
        (job_dir / "job.json").write_text(json.dumps({
            "schema": "physical-lab-job-v1",
            "id": "job-solar-ci",
            "profile": core.PROFILE,
            "experiment_sha256": manifest_a["experiment_sha256"],
            "runner": "model-campaign",
            "runner_config": {
                "profile": core.PROFILE,
                "preset": "compact",
                "model_variant": core.MODEL_VARIANT,
            },
            "status": "queued",
            "progress": 0.0,
            "stage": "queued",
            "created_at": "2026-09-04T00:00:00Z",
            "updated_at": "2026-09-04T00:00:00Z",
            "attempt": 0,
        }), encoding="utf-8")
        output = worker.execute_job(job_dir)
        record = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        persisted = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
        assert record["status"] == "succeeded"
        assert persisted["model_variant"] == core.MODEL_VARIANT
        campaign = output["result"]
        assert campaign["schema"] == workflow.CAMPAIGN_SCHEMA
        assert campaign["model_variant"] == core.MODEL_VARIANT
        assert len(campaign["inclination_sweep"]) == 4
        assert len(campaign["model_effect_audit"]) == 4
        assert campaign["screening"]["status"] in {"PASS", "REVIEW"}
        assert np.isfinite(campaign["metrics"]["finite_time_divergence_rate_per_year"])
        assert (job_dir / "checkpoint.json").exists()

        assert project.register_job_reference(project_dir, record, result=output)
        pdoc = project.open_project(project_dir)
        assert "job-solar-ci" in pdoc["jobs"]
        assert "job-solar-ci" in pdoc["results"]
        report = workflow.render_report_markdown(manifest_a, campaign)
        assert manifest_a["experiment_sha256"] in report
        assert "phenomenological" in report.lower()
        assert "not experimental validation" in report.lower()

    tauri = TAURI_PATH.read_text(encoding="utf-8")
    assert "physical_lab_solar_system_dynamics.py" in tauri
    assert "physical_lab_solar_system_workflow.py" in tauri
    assert "physical_lab_solar_system_ui.py" in tauri
    facade = ENGINEERING_PATH.read_text(encoding="utf-8")
    assert "render_solar_system_workspace" in facade
    worker_source = WORKER_PATH.read_text(encoding="utf-8")
    assert "execute_solar_system_manifest" in worker_source
    assert "solar-system-" in worker_source

    print("Solar-system dynamics validation: PASS")


if __name__ == "__main__":
    main()
