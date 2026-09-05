#!/usr/bin/env python3
"""Deterministic acceptance checks for Physical Lab Evidence Review v1."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_cross_checks as cross_checks
import physical_lab_evidence_diff as evidence_diff
import physical_lab_measurement_registry as measurements
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import build_experiment_manifest, utc_now


def job_record(job_id: str, manifest: dict, root: Path) -> dict:
    job_dir = root / "compute-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "result.json"
    log_path = job_dir / "worker.log"
    log_path.write_text("evidence-review validation\n", encoding="utf-8")
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


def register_result(project_dir: Path, root: Path, manifest: dict, job_id: str, result: dict) -> None:
    record = job_record(job_id, manifest, root)
    Path(record["result_path"]).write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    assert projects.register_job_reference(project_dir, record, result=result)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="physical-lab-evidence-review-") as temp:
        root = Path(temp).resolve()
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)
        project_dir, _ = projects.create_project(
            "Evidence Review Validation",
            research_question="Can independent-path agreement and later evidence drift be detected without producing a truth verdict?",
        )

        measurement = measurements.ingest_measurement_bytes(
            project_dir,
            filename="reference.csv",
            data=b"x,value\n0,1.0\n1,0.9995\n",
            profile="numerical-methods",
            instrument="reference probe",
            quantity="fixture observable",
            unit="1",
            captured_at="fixture-run-001",
        )
        calibration = measurements.register_calibration(
            project_dir,
            instrument="reference probe",
            parameter="scale",
            nominal_value=1.0,
            unit="1",
            standard_uncertainty=0.001,
            uncertainty_unit="1",
            method="synthetic deterministic fixture",
            reference="fixture-calibration-v1",
            profile="numerical-methods",
            related_measurements=[measurement["measurement_id"]],
        )

        manifest = build_experiment_manifest(
            "numerical-methods",
            parameters={"grid": 401, "order": 6},
            inputs={
                "referent": {
                    "source": "measurement",
                    "measurement_id": measurement["measurement_id"],
                    "calibration_id": calibration["calibration_id"],
                    "sha256": measurement["sha256"],
                }
            },
            uncertainty={"input_standard_uncertainty": 0.001},
            provenance={
                "source_commit": "abcdef0123456789abcdef0123456789abcdef01",
                "solver_backend": "fixture-primary",
            },
        )
        projects.register_experiment(project_dir, manifest)

        primary_result = {
            "observable": {"value": 1.0},
            "verification": {"analytic_reference_relative_error": 2e-4, "convergence_order": 3.95},
            "validation": {"measurement_rmse": 4e-4},
            "uncertainty": {"propagated_standard_uncertainty": 8e-4},
            "robustness": {"timestep_relative_change": 2e-4},
        }
        comparison_result = {
            "observable": {"value": 1.0005},
            "verification": {"closed_form_reference": True},
            "validation": {"measurement_rmse": 5e-4},
            "uncertainty": {"propagated_standard_uncertainty": 8e-4},
            "robustness": {"parameter_sensitivity_spread": 3e-4},
        }
        register_result(project_dir, root, manifest, "job-primary", primary_result)
        register_result(project_dir, root, manifest, "job-comparison", comparison_result)

        agreement = cross_checks.register_cross_check(
            project_dir,
            name="Fixture observable dual-path check",
            observable="fixture observable",
            primary={
                "label": "Numerical path",
                "value": 1.0,
                "method_family": "numerical-rk4",
                "source_identity": "fixture-primary-solver",
                "references": [{"kind": "result", "id": "job-primary"}],
            },
            comparison={
                "label": "Analytic path",
                "value": 1.0005,
                "method_family": "analytic-closed-form",
                "source_identity": "fixture-analytic-formula",
                "references": [{"kind": "result", "id": "job-comparison"}],
            },
            tolerance=0.001,
            tolerance_mode="relative",
            unit="1",
            intended_use="deterministic CI only",
        )
        agree_eval = cross_checks.evaluate_cross_check(project_dir, agreement["cross_check_id"])
        assert agree_eval["status"] == "AGREES_WITHIN_TOLERANCE", agree_eval
        assert agree_eval["declared_distinct"] is True
        assert agree_eval["relative_difference"] <= 0.001

        not_distinct = cross_checks.register_cross_check(
            project_dir,
            name="Same-method control",
            observable="fixture observable",
            primary={
                "value": 1.0,
                "method_family": "numerical-rk4",
                "source_identity": "same-solver",
                "references": [{"kind": "result", "id": "job-primary"}],
            },
            comparison={
                "value": 1.0,
                "method_family": "numerical-rk4",
                "source_identity": "same-solver",
                "references": [{"kind": "result", "id": "job-comparison"}],
            },
            tolerance=0.001,
        )
        assert cross_checks.evaluate_cross_check(project_dir, not_distinct["cross_check_id"])["status"] == "NOT_DISTINCT"

        disagreement = cross_checks.register_cross_check(
            project_dir,
            name="Out-of-tolerance control",
            observable="fixture observable",
            primary={
                "value": 1.0,
                "method_family": "numerical-rk4",
                "source_identity": "solver-A",
                "references": [{"kind": "result", "id": "job-primary"}],
            },
            comparison={
                "value": 1.02,
                "method_family": "analytic-series",
                "source_identity": "formula-B",
                "references": [{"kind": "result", "id": "job-comparison"}],
            },
            tolerance=0.001,
        )
        assert cross_checks.evaluate_cross_check(project_dir, disagreement["cross_check_id"])["status"] == "DISAGREES"

        snapshot_a = evidence_diff.build_evidence_snapshot(
            project_dir,
            label="before-result-drift",
            generated_at="2026-01-01T00:00:00+00:00",
        )
        assert len(snapshot_a["snapshot_sha256"]) == 64
        assert snapshot_a["cross_check_status_counts"]["AGREES_WITHIN_TOLERANCE"] == 1
        assert snapshot_a["cross_check_status_counts"]["NOT_DISTINCT"] == 1
        assert snapshot_a["cross_check_status_counts"]["DISAGREES"] == 1

        changed_result = dict(comparison_result)
        changed_result["observable"] = {"value": 1.004}
        changed_result["validation"] = {"measurement_rmse": 0.004}
        register_result(project_dir, root, manifest, "job-comparison", changed_result)

        stale_eval = cross_checks.evaluate_cross_check(project_dir, agreement["cross_check_id"])
        assert stale_eval["status"] == "STALE", stale_eval
        assert any(item.startswith("comparison:result:job-comparison") for item in stale_eval["stale_references"])

        snapshot_b = evidence_diff.build_evidence_snapshot(
            project_dir,
            label="after-result-drift",
            generated_at="2026-01-01T00:01:00+00:00",
        )
        diff = evidence_diff.diff_evidence_snapshots(snapshot_a, snapshot_b)
        assert diff["graph_changed"] is True
        changed_checks = diff["cross_check_changes"]["changed"]
        agreement_change = next(row for row in changed_checks if row["cross_check_id"] == agreement["cross_check_id"])
        assert agreement_change["before_status"] == "AGREES_WITHIN_TOLERANCE"
        assert agreement_change["after_status"] == "STALE"
        assert diff["change_count"] >= 2
        assert len(diff["diff_sha256"]) == 64

        encoded = json.dumps({"agreement": agree_eval, "diff": diff}).lower()
        assert "truth_status" not in encoded
        assert '"status": "proven"' not in encoded
        assert '"status": "verified"' not in encoded

        markdown = evidence_diff.render_evidence_diff_markdown(diff)
        assert "Evidence Diff" in markdown
        assert "AGREES_WITHIN_TOLERANCE" in markdown
        assert "STALE" in markdown

        print("Physical Lab Evidence Review v1 validation: PASS")
        print("- declared-distinct agreement: PASS")
        print("- same-method NOT_DISTINCT guard: PASS")
        print("- out-of-tolerance disagreement: PASS")
        print("- result fingerprint drift -> STALE: PASS")
        print(f"- evidence diff changes: {diff['change_count']}")
        print("- machine truth/verification verdict: intentionally absent")
        print("Boundary: corroboration/readiness only; no scientific truth, independence, standards-compliance, or certification claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
