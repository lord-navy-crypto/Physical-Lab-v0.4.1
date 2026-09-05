#!/usr/bin/env python3
"""Deterministic acceptance checks for Physical Lab Credibility Passport v1."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_credibility as credibility
import physical_lab_measurement_registry as measurements
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import build_experiment_manifest, utc_now


def by_id(passport: dict) -> dict[str, dict]:
    return {row["factor_id"]: row for row in passport["factors"]}


def fake_job(job_id: str, manifest: dict, root: Path) -> dict:
    job_dir = root / "compute-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "result.json"
    log_path = job_dir / "worker.log"
    log_path.write_text("validated deterministic test run\n", encoding="utf-8")
    return {
        "id": job_id,
        "experiment_sha256": manifest["experiment_sha256"],
        "profile": manifest["profile"],
        "runner": "model-campaign",
        "status": "succeeded",
        "stage": "complete",
        "attempt": 1,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "result_path": str(result_path),
        "log_path": str(log_path),
    }


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="physical-lab-credibility-") as temp:
        data_root = Path(temp).resolve()
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(data_root)

        project_dir, _ = projects.create_project(
            "Credibility Passport Validation",
            description="Synthetic deterministic fixture for evidence-graph validation.",
            research_question="Can evidence provenance remain traceable without inventing an aggregate credibility score?",
        )

        empty = credibility.build_credibility_passport(project_dir, generated_at="2026-01-01T00:00:00+00:00")
        assert empty["schema"] == credibility.PASSPORT_SCHEMA
        assert len(empty["factors"]) == 8
        assert set(row["status"] for row in empty["factors"]) <= set(credibility.STATUSES)
        assert "aggregate_credibility_score" not in empty
        assert empty["coverage"]["missing"] >= 1

        measurement = measurements.ingest_measurement_bytes(
            project_dir,
            filename="reference-field.csv",
            data=b"z_m,field_T\n0.0,0.100\n0.1,0.095\n",
            profile="numerical-methods",
            instrument="reference field probe",
            quantity="magnetic field",
            unit="T",
            captured_at="fixture-run-001",
            notes="Synthetic CI fixture; not real laboratory evidence.",
        )
        calibration = measurements.register_calibration(
            project_dir,
            instrument="reference field probe",
            parameter="field scale",
            nominal_value=1.0,
            unit="T",
            standard_uncertainty=0.01,
            uncertainty_unit="T",
            method="synthetic CI calibration fixture",
            reference="fixture-reference-v1",
            profile="numerical-methods",
            calibrated_at="fixture-cal-001",
            related_measurements=[measurement["measurement_id"]],
        )

        manifest = build_experiment_manifest(
            "numerical-methods",
            parameters={"grid": 321, "order": 7},
            inputs={
                "reference_field": {
                    "source": "project measurement evidence",
                    "measurement_id": measurement["measurement_id"],
                    "calibration_id": calibration["calibration_id"],
                    "sha256": measurement["sha256"],
                }
            },
            execution={"preset": "standard", "solver": "deterministic-reference"},
            requirements=[{"metric": "measurement_rmse", "op": "<=", "target": 0.05}],
            uncertainty={
                "field_standard_uncertainty_T": 0.01,
                "method": "first-order propagation fixture",
            },
            provenance={
                "source_commit": "0123456789abcdef0123456789abcdef01234567",
                "solver_backend": "physical-lab-reference-solver",
                "engine_mode": "safe",
                "source_profile": "numerical-methods",
            },
            created_at="2026-01-01T00:00:01+00:00",
        )
        exp = projects.register_experiment(project_dir, manifest)

        result = {
            "schema": "physical-lab-job-result-v1",
            "verification": {
                "analytic_reference_relative_error": 1.0e-4,
                "convergence_order": 3.98,
            },
            "validation": {
                "measurement_rmse": 0.012,
                "measurement_residual_sigma": 0.6,
            },
            "uncertainty": {
                "propagated_standard_uncertainty": 0.018,
            },
            "robustness": {
                "sensitivity_spread": 0.025,
                "timestep_relative_change": 0.004,
                "replicate_cv": 0.011,
            },
            "boundary": "Synthetic CI evidence only; no experimental validation claim.",
        }

        job1 = fake_job("job-credibility-001", manifest, data_root)
        Path(job1["result_path"]).write_text(json.dumps(result), encoding="utf-8")
        assert projects.register_job_reference(project_dir, job1, result=result)

        result2 = dict(result)
        result2["robustness"] = {
            "sensitivity_spread": 0.021,
            "timestep_relative_change": 0.003,
            "replicate_cv": 0.010,
        }
        job2 = fake_job("job-credibility-002", manifest, data_root)
        Path(job2["result_path"]).write_text(json.dumps(result2), encoding="utf-8")
        assert projects.register_job_reference(project_dir, job2, result=result2)

        passport_a = credibility.build_credibility_passport(
            project_dir,
            experiment_id=exp["experiment_id"],
            generated_at="2026-01-01T00:00:02+00:00",
        )
        passport_b = credibility.build_credibility_passport(
            project_dir,
            experiment_id=exp["experiment_id"],
            generated_at="2026-01-02T00:00:02+00:00",
        )
        factors = by_id(passport_a)

        assert passport_a["passport_sha256"] == passport_b["passport_sha256"], "timestamp must not alter evidence identity"
        assert passport_a["evidence_graph"]["graph_sha256"] == passport_b["evidence_graph"]["graph_sha256"]
        assert passport_a["coverage"]["present"] >= 7, passport_a["coverage"]
        assert factors["data_pedigree"]["status"] == "PRESENT"
        assert factors["verification"]["status"] == "PRESENT"
        assert factors["validation"]["status"] == "PRESENT"
        assert factors["input_pedigree"]["status"] == "PRESENT"
        assert factors["uncertainty_characterization"]["status"] == "PRESENT"
        assert factors["results_robustness"]["status"] == "PRESENT"
        assert factors["ms_history"]["status"] == "PRESENT"
        assert factors["process_management"]["status"] == "PRESENT"

        graph = passport_a["evidence_graph"]
        node_types = {node["type"] for node in graph["nodes"]}
        edge_relations = {edge["relation"] for edge in graph["edges"]}
        assert {"project", "experiment", "job", "result", "measurement", "calibration"} <= node_types
        assert {"contains", "executed-as", "produced", "has-evidence", "has-calibration"} <= edge_relations

        summary = credibility.passport_summary(passport_a)
        assert summary["aggregate_credibility_score"] is None
        assert summary["factor_count"] == 8

        json_path, markdown_path, written = credibility.write_credibility_passport(
            project_dir,
            experiment_id=exp["experiment_id"],
            generated_at="2026-01-01T00:00:03+00:00",
        )
        assert json_path.exists() and markdown_path.exists()
        assert written["passport_sha256"] == passport_a["passport_sha256"]
        markdown = markdown_path.read_text(encoding="utf-8")
        assert "No aggregate credibility score" in markdown
        assert "not a NASA-STD-7009" in markdown

        print("Physical Lab Credibility Passport v1 validation: PASS")
        print(f"- factors: {passport_a['coverage']}")
        print(f"- evidence graph: nodes={len(graph['nodes'])}, edges={len(graph['edges'])}")
        print(f"- deterministic passport: {passport_a['passport_sha256'][:16]}…")
        print("- aggregate credibility score: intentionally absent")
        print("Boundary: evidence coverage/traceability only; no NASA/ASME compliance, certification, or experimental-validation claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
