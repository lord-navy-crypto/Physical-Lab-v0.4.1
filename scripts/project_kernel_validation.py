#!/usr/bin/env python3
"""Deterministic validation for Physical Lab .physlab Project Kernel v1."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_compute_engine as compute  # noqa: E402
import physical_lab_experiment_kernel as experiments  # noqa: E402
import physical_lab_project_kernel as projects  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="physical-lab-project-kernel-") as temp:
        os.environ["PHYSICAL_LAB_DATA_DIR"] = temp
        os.environ["PHYSICAL_LAB_SOURCE_COMMIT"] = "project-kernel-validation"

        project_dir, project = projects.create_project(
            "Project Kernel Validation",
            description="Deterministic source-integrity fixture",
            research_question="Can project identity, experiment identity, jobs and reports round-trip without scientific reinterpretation?",
        )
        require(project_dir.suffix == ".physlab", "project directory must use .physlab suffix")
        require(projects.validate_project_document(project)["valid"], "new project must validate")
        for child in ("experiments", "jobs", "results", "measurements", "calibration", "reports", "provenance"):
            require((project_dir / child).is_dir(), f"missing project directory: {child}")

        manifest = experiments.build_experiment_manifest(
            "numerical-methods",
            parameters={"grid_points": 160, "well_width_nm": 1.0},
            execution={"mode": "validation-fixture"},
            provenance={"source_commit": "fixed", "engine_mode": "safe", "source_profile": "numerical-methods"},
            created_at="2026-09-04T00:00:00+00:00",
        )
        original_sha = manifest["experiment_sha256"]
        first = projects.register_experiment(project_dir, manifest)
        second = projects.register_experiment(project_dir, manifest)
        require(first["experiment_id"] == second["experiment_id"], "registration must be idempotent")
        loaded = projects.open_project(project_dir)
        require(len(loaded["experiments"]) == 1, "same scientific experiment must not duplicate")
        stored_manifest = json.loads((project_dir / first["manifest_path"]).read_text(encoding="utf-8"))
        require(stored_manifest["experiment_sha256"] == original_sha, "project must preserve experiment fingerprint")
        require(experiments.validate_manifest(stored_manifest)["valid"], "stored experiment manifest must validate")

        queued = compute.submit_job(manifest, runner="manifest-validate", priority=60)
        sync1 = projects.sync_compute_jobs(project_dir)
        require(sync1["matched"] == 1, "matching compute job must be indexed")
        loaded = projects.open_project(project_dir)
        require(queued["id"] in loaded["jobs"], "job index must contain queued job")
        require(loaded["jobs"][queued["id"]]["experiment_id"] == first["experiment_id"], "job must link to experiment")

        result_payload = {
            "schema": "physical-lab-worker-result-v1",
            "ok": True,
            "metric": 0.00125,
            "large_array_fixture": list(range(200)),
        }
        job_dir = Path(temp) / "compute-jobs" / queued["id"]
        result_path = job_dir / "result.json"
        result_path.write_text(json.dumps(result_payload, indent=2), encoding="utf-8")
        succeeded = compute.read_job(queued["id"]) or queued
        succeeded.update({
            "status": "succeeded",
            "stage": "result-persisted",
            "progress": 1.0,
            "result_path": str(result_path),
            "updated_at": "2026-09-04T00:01:00+00:00",
            "finished_at": "2026-09-04T00:01:00+00:00",
        })
        compute.write_job(succeeded)
        sync2 = projects.sync_compute_jobs(project_dir)
        require(sync2["results"] == 1, "completed result reference must be indexed")
        loaded = projects.open_project(project_dir)
        result_ref = loaded["results"][queued["id"]]
        require(result_ref["result_sha256"] == experiments.sha256_json(result_payload), "result fingerprint mismatch")
        require("large_array_fixture" not in result_ref["summary"], "project index must not duplicate large result arrays")
        require(Path(temp, result_ref["result_path"]).resolve() == result_path.resolve(), "result path must be portable to data root")

        report_path, report = projects.write_project_report(
            project_dir, generated_at="2026-09-04T00:02:00+00:00"
        )
        require(report_path.exists(), "project report must be persisted")
        for heading in (
            "## Research question",
            "## Experiments",
            "## Compute jobs",
            "## Result references",
            "## Reproducibility and V&V boundary",
        ):
            require(heading in report, f"report missing section: {heading}")
        require(first["experiment_id"] in report and queued["id"] in report, "report must cite experiment and job identities")

        legacy = {
            "schema": projects.LEGACY_PROJECT_SCHEMA,
            "project_id": "plproj-legacy-deterministic",
            "name": "Legacy Fixture",
            "description": "legacy",
            "research_question": "migration",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:00+00:00",
            "experiments": {"exp-legacy": {"profile": "oscillation-integration"}},
            "jobs": {},
        }
        migrated_a, notes_a = projects.migrate_project_document(legacy)
        migrated_b, notes_b = projects.migrate_project_document(legacy)
        require(migrated_a == migrated_b and notes_a == notes_b, "legacy migration must be deterministic")
        require(migrated_a["schema"] == projects.PROJECT_SCHEMA, "migration target schema mismatch")
        require(migrated_a["profiles"] == ["oscillation-integration"], "migration must rebuild profile index")

        listed = projects.list_projects()
        require(len(listed) == 1 and listed[0]["project_id"] == project["project_id"], "project discovery failed")
        summary = projects.project_summary(project_dir)
        require(summary["experiment_count"] == 1, "project summary experiment count mismatch")
        require(summary["job_count"] == 1 and summary["result_count"] == 1, "project summary job/result count mismatch")

    tauri = (ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    facade = (UI / "physical_lab_engineering.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "source-integrity.yml").read_text(encoding="utf-8")
    require("physical_lab_project_kernel.py" in tauri, "Project Kernel must be bundled in Tauri resources")
    require("render_project_workspace" in facade, "Engineering facade must render Project workspace")
    require("project_kernel_validation.py" in workflow, "Source Integrity must run Project Kernel validation")

    print("Physical Lab Project Kernel validation: PASS")
    print("- .physlab structure + schema: PASS")
    print("- idempotent experiment registration: PASS")
    print("- Compute Engine job/result indexing: PASS")
    print("- result-reference non-duplication: PASS")
    print("- deterministic legacy migration: PASS")
    print("- Markdown report generation: PASS")
    print("- Tauri/facade/CI integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
