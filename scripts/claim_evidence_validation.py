#!/usr/bin/env python3
"""Deterministic validation for Physical Lab Claim-to-Evidence Matrix v1."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_claims as claims
import physical_lab_measurement_registry as measurements
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import build_experiment_manifest, utc_now


def job_record(job_id: str, manifest: dict, root: Path) -> dict:
    job_dir = root / "compute-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "result.json"
    log_path = job_dir / "worker.log"
    log_path.write_text("claim-evidence validation\n", encoding="utf-8")
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


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="physical-lab-claims-") as temp:
        root = Path(temp).resolve()
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)
        project_dir, _ = projects.create_project(
            "Claim Evidence Validation",
            research_question="Can a scientific claim detect current, stale, and missing project evidence?",
        )

        measurement = measurements.ingest_measurement_bytes(
            project_dir,
            filename="reference.csv",
            data=b"x,value\n0,1.0\n1,0.9\n",
            profile="numerical-methods",
            instrument="reference probe",
            quantity="test quantity",
            unit="T",
            captured_at="fixture-001",
        )
        calibration = measurements.register_calibration(
            project_dir,
            instrument="reference probe",
            parameter="scale",
            nominal_value=1.0,
            unit="T",
            standard_uncertainty=0.01,
            uncertainty_unit="T",
            method="synthetic fixture",
            reference="fixture-calibration",
            profile="numerical-methods",
            related_measurements=[measurement["measurement_id"]],
        )

        manifest = build_experiment_manifest(
            "numerical-methods",
            parameters={"grid": 321},
            inputs={"referent": {"source": "measurement", "measurement_id": measurement["measurement_id"], "calibration_id": calibration["calibration_id"], "sha256": measurement["sha256"]}},
            uncertainty={"input_standard_uncertainty": 0.01},
            provenance={"source_commit": "1234567890abcdef1234567890abcdef12345678", "solver_backend": "fixture"},
        )
        exp = projects.register_experiment(project_dir, manifest)
        result = {
            "verification": {"analytic_reference_relative_error": 1e-4, "convergence_order": 3.9},
            "validation": {"measurement_rmse": 0.01},
            "uncertainty": {"propagated_standard_uncertainty": 0.02},
            "robustness": {"sensitivity_spread": 0.02, "timestep_relative_change": 0.003},
        }
        for number in (1, 2):
            job_id = f"job-claim-{number:03d}"
            record = job_record(job_id, manifest, root)
            Path(record["result_path"]).write_text(json.dumps(result), encoding="utf-8")
            assert projects.register_job_reference(project_dir, record, result=result)

        refs = [
            {"kind": "experiment", "id": exp["experiment_id"]},
            {"kind": "result", "id": "job-claim-001"},
            {"kind": "measurement", "id": measurement["measurement_id"]},
            {"kind": "calibration", "id": calibration["calibration_id"]},
        ]
        required = ["verification", "validation", "uncertainty_characterization", "results_robustness"]
        claim = claims.register_claim(
            project_dir,
            statement="The reference observable is reproduced within the declared fixture error bound for this experiment.",
            claim_type="validation",
            intended_use="deterministic CI demonstration only",
            required_factors=required,
            references=refs,
        )
        same = claims.register_claim(
            project_dir,
            statement=claim["statement"],
            claim_type="validation",
            intended_use="deterministic CI demonstration only",
            required_factors=required,
            references=refs,
        )
        assert same["claim_id"] == claim["claim_id"], "claim identity must be deterministic"

        ready = claims.evaluate_claim(project_dir, claim["claim_id"])
        assert ready["status"] == "READY_FOR_REVIEW", ready
        assert not ready["missing_references"]
        assert not ready["stale_references"]
        assert all(row["status"] == "PRESENT" for row in ready["factor_checks"])

        matrix = claims.claim_evidence_matrix(project_dir)
        assert matrix["status_counts"]["READY_FOR_REVIEW"] == 1
        assert len(matrix["matrix_sha256"]) == 64
        assert "truth" not in json.dumps(matrix).lower()

        calibration_index_path = project_dir / "calibration" / "index.json"
        calibration_index = json.loads(calibration_index_path.read_text(encoding="utf-8"))
        calibration_index["calibrations"][calibration["calibration_id"]]["notes"] = "changed after claim registration"
        write_json(calibration_index_path, calibration_index)
        stale = claims.evaluate_claim(project_dir, claim["claim_id"])
        assert stale["status"] == "STALE", stale
        assert any(item.startswith("calibration:") for item in stale["stale_references"])

        measurement_index_path = project_dir / "measurements" / "index.json"
        measurement_index = json.loads(measurement_index_path.read_text(encoding="utf-8"))
        measurement_index["measurements"].pop(measurement["measurement_id"])
        write_json(measurement_index_path, measurement_index)
        missing = claims.evaluate_claim(project_dir, claim["claim_id"])
        assert missing["status"] == "EVIDENCE_MISSING", missing
        assert any(item.startswith("measurement:") for item in missing["missing_references"])

        markdown = claims.render_matrix_markdown(matrix)
        assert "Claim-to-Evidence Matrix" in markdown
        assert "scientific truth" in markdown

        print("Physical Lab Claim-to-Evidence Matrix v1 validation: PASS")
        print(f"- deterministic claim id: {claim['claim_id']}")
        print(f"- ready evaluation: {ready['evaluation_sha256'][:16]}…")
        print("- stale evidence detection: PASS")
        print("- missing evidence detection: PASS")
        print("Boundary: evidence readiness/freshness only; no truth, standards-compliance, or certification decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
