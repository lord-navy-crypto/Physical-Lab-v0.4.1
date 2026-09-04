#!/usr/bin/env python3
"""Deterministic contract checks for Kerr Experiment/Compute/Project integration."""
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
DOC_PATH = ROOT / "docs" / "KERR_PLATFORM_WORKFLOW.md"

import sys
sys.path.insert(0, str(UI_DIR))

import physical_lab_kerr_geodesics as core
import physical_lab_kerr_workflow as workflow
import physical_lab_job_worker as worker
import physical_lab_project_kernel as project
import physical_lab_local_ai as local_ai


def main() -> None:
    scale = workflow.geometric_scale(1.0)
    assert 1.47 < scale["one_M_length_km"] < 1.49
    assert 4.9 < scale["one_M_time_us"] < 5.0

    config = core.KerrOrbitConfig(
        spin=0.6,
        inclination_deg=60.0,
        particle_type="photon",
        lam_max=0.25,
        samples=200,
        rtol=1e-9,
        atol=1e-11,
    )
    manifest_a = workflow.build_kerr_manifest(
        config,
        preset="compact",
        solar_masses=10.0,
        source_commit="validation-sha",
    )
    manifest_b = workflow.build_kerr_manifest(
        config,
        preset="compact",
        solar_masses=10.0,
        source_commit="validation-sha",
    )
    assert manifest_a["experiment_sha256"] == manifest_b["experiment_sha256"]
    assert manifest_a["model"]["variant"] == workflow.MODEL_VARIANT
    assert manifest_a["model"]["title"] == workflow.MODEL_TITLE
    assert manifest_a["execution"]["mode"] == "kerr-verification-campaign"
    assert manifest_a["uncertainty"]["probabilistic"] is False
    assert manifest_a["inputs"]["units"] == "geometric G=c=M=1"
    assert workflow.is_kerr_manifest(manifest_a)

    changed = core.KerrOrbitConfig(
        spin=0.61,
        inclination_deg=60.0,
        particle_type="photon",
        lam_max=0.25,
        samples=200,
        rtol=1e-9,
        atol=1e-11,
    )
    manifest_changed = workflow.build_kerr_manifest(changed, preset="compact", source_commit="validation-sha")
    assert manifest_changed["experiment_sha256"] != manifest_a["experiment_sha256"]

    pass_screen = workflow.evaluate_requirements(
        {
            "first_integral_residual_max": 1e-8,
            "constraint_residual_max": 1e-10,
            "refinement_relative_change_max": 1e-5,
            "minimum_horizon_margin_M": 1.0,
        },
        workflow.DEFAULT_REQUIREMENTS,
    )
    assert pass_screen["status"] == "PASS"
    review_screen = workflow.evaluate_requirements(
        {
            "first_integral_residual_max": 1e-2,
            "constraint_residual_max": 1e-10,
            "refinement_relative_change_max": 1e-5,
            "minimum_horizon_margin_M": 1.0,
        },
        workflow.DEFAULT_REQUIREMENTS,
    )
    assert review_screen["status"] == "REVIEW"

    old_data_dir = os.environ.get("PHYSICAL_LAB_DATA_DIR")
    try:
        # Exercise the actual worker specialization and Project Kernel registration.
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "physical-lab-data"
            data_root.mkdir(parents=True)
            os.environ["PHYSICAL_LAB_DATA_DIR"] = str(data_root)

            project_dir, project_doc = project.create_project(
                "Kerr CI Project",
                research_question="Can the selected Kerr geodesic satisfy its numerical verification contract?",
            )
            experiment_entry = project.register_experiment(project_dir, manifest_a)
            assert experiment_entry["experiment_sha256"] == manifest_a["experiment_sha256"]
            assert experiment_entry["model"] == workflow.MODEL_TITLE

            job_dir = Path(tmp) / "job-kerr-ci"
            job_dir.mkdir(parents=True)
            (job_dir / "manifest.json").write_text(json.dumps(manifest_a), encoding="utf-8")
            (job_dir / "job.json").write_text(
                json.dumps({
                    "schema": "physical-lab-job-v1",
                    "id": "job-kerr-ci",
                    "profile": core.PROFILE,
                    "experiment_sha256": manifest_a["experiment_sha256"],
                    "runner": "model-campaign",
                    "runner_config": {
                        "profile": core.PROFILE,
                        "preset": "compact",
                        "model_variant": workflow.MODEL_VARIANT,
                    },
                    "status": "queued",
                    "progress": 0.0,
                    "stage": "queued",
                    "created_at": "2026-09-04T00:00:00Z",
                    "updated_at": "2026-09-04T00:00:00Z",
                    "attempt": 0,
                    "result_path": None,
                    "log_path": str(job_dir / "worker.log"),
                }),
                encoding="utf-8",
            )
            output = worker.execute_job(job_dir)
            record = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
            persisted = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
            assert record["status"] == "succeeded"
            assert record["stage"] == "complete"
            assert output["model_variant"] == workflow.MODEL_VARIANT
            assert persisted["model_variant"] == workflow.MODEL_VARIANT
            campaign = persisted["result"]
            assert campaign["schema"] == workflow.CAMPAIGN_SCHEMA
            assert campaign["model_variant"] == workflow.MODEL_VARIANT
            assert len(campaign["spin_sweep"]) == 4
            assert len(campaign["sensitivity_cases"]) == 4
            assert campaign["kerr_metrics"]["first_integral_residual_max"] < 1e-5
            assert campaign["kerr_metrics"]["constraint_residual_max"] < 1e-6
            assert campaign["kerr_metrics"]["minimum_horizon_margin_M"] > 0.0
            assert campaign["screening"]["status"] in {"PASS", "REVIEW"}
            assert (job_dir / "checkpoint.json").exists()

            # Project Kernel indexes the experiment-bound job/result without duplicating arrays.
            assert project.register_job_reference(project_dir, record, result=persisted)
            project_state = project.project_summary(project_dir)
            assert project_state["experiment_count"] == 1
            assert project_state["job_count"] == 1
            assert project_state["result_count"] == 1
            project_report = project.render_project_report_markdown(
                project_dir,
                generated_at="2026-09-04T00:00:00Z",
            )
            assert workflow.MODEL_TITLE in project_report
            assert manifest_a["experiment_sha256"] in project_report
            assert "verification" in project_report.lower()

            report = workflow.render_kerr_report_markdown(manifest_a, campaign)
            assert manifest_a["experiment_sha256"] in report
            assert "integrable" in report.lower()
            assert "experimental validation" in report.lower()

            # Local AI receives the structured manifest/campaign as read-only session context.
            ai_context = local_ai.build_physics_context(
                core.PROFILE,
                {},
                {
                    "pl_kerr_spin": 0.6,
                    "pl_kerr_inclination": 60.0,
                    "pl_kerr_experiment_manifest": manifest_a,
                    "pl_kerr_campaign_result": campaign,
                },
            )
            selected = ai_context["selectedSessionState"]
            assert selected["pl_kerr_experiment_manifest"]["model"]["variant"] == workflow.MODEL_VARIANT
            assert selected["pl_kerr_experiment_manifest"]["inputs"]["units"] == "geometric G=c=M=1"
            assert selected["pl_kerr_campaign_result"]["screening"]["status"] in {"PASS", "REVIEW"}
    finally:
        if old_data_dir is None:
            os.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
        else:
            os.environ["PHYSICAL_LAB_DATA_DIR"] = old_data_dir

    tauri = TAURI_PATH.read_text(encoding="utf-8")
    assert "physical_lab_kerr_workflow.py" in tauri
    assert "physical_lab_kerr_platform_ui.py" in tauri
    facade = ENGINEERING_PATH.read_text(encoding="utf-8")
    assert "render_kerr_platform_workspace" in facade
    worker_source = WORKER_PATH.read_text(encoding="utf-8")
    assert "execute_kerr_manifest" in worker_source
    assert "kerr-{stage}" in worker_source
    documentation = DOC_PATH.read_text(encoding="utf-8")
    assert "deterministic local tolerance envelope" in documentation.lower()
    assert "not an inferred black-hole spin measurement" in documentation.lower()

    print("Kerr platform workflow validation: PASS")


if __name__ == "__main__":
    main()
