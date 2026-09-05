#!/usr/bin/env python3
"""Deterministic acceptance for Physical Lab Reproducibility Capsule v1."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_claims as claims
import physical_lab_cross_checks as cross_checks
import physical_lab_measurement_registry as measurements
import physical_lab_project_kernel as projects
import physical_lab_reproducibility_capsule as capsule
from physical_lab_experiment_kernel import build_experiment_manifest


def main() -> int:
    old_data = os.environ.get("PHYSICAL_LAB_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="physical-lab-capsule-") as td:
            data_root = Path(td).resolve()
            os.environ["PHYSICAL_LAB_DATA_DIR"] = str(data_root)
            project_dir, _ = projects.create_project(
                "Reproducibility Capsule Validation",
                description="Synthetic deterministic fixture for portable evidence packaging.",
                research_question="Can Physical Lab export a bounded evidence package without inflating provenance into scientific truth?",
            )

            measurement = measurements.ingest_measurement_bytes(
                project_dir,
                filename="reference-field.csv",
                data=b"z_m,field_T\n0.0,0.100\n0.1,0.095\n",
                profile="numerical-methods",
                instrument="synthetic reference field probe",
                quantity="magnetic field",
                unit="T",
                captured_at="fixture-run-001",
                notes="Synthetic CI fixture; not laboratory validation evidence.",
            )
            calibration = measurements.register_calibration(
                project_dir,
                instrument="synthetic reference field probe",
                parameter="field scale",
                nominal_value=1.0,
                unit="T",
                standard_uncertainty=0.01,
                uncertainty_unit="T",
                method="synthetic deterministic fixture",
                reference="capsule-fixture-reference-v1",
                profile="numerical-methods",
                calibrated_at="fixture-cal-001",
                related_measurements=[measurement["measurement_id"]],
            )

            manifest = build_experiment_manifest(
                "numerical-methods",
                parameters={"grid": 257, "order": 6},
                inputs={
                    "reference_field": {
                        "measurement_id": measurement["measurement_id"],
                        "calibration_id": calibration["calibration_id"],
                        "sha256": measurement["sha256"],
                    }
                },
                execution={"preset": "standard", "solver": "capsule-fixture-solver"},
                requirements=[{"metric": "measurement_rmse", "op": "<=", "target": 0.05}],
                uncertainty={"field_standard_uncertainty_T": 0.01, "method": "fixture propagation"},
                provenance={
                    "source_commit": "0123456789abcdef0123456789abcdef01234567",
                    "solver_backend": "physical-lab-capsule-fixture",
                    "engine_mode": "safe",
                    "source_profile": "numerical-methods",
                },
                created_at="2026-01-01T00:00:01+00:00",
            )
            exp = projects.register_experiment(project_dir, manifest)

            job_id = "job-capsule-001"
            job_dir = data_root / "compute-jobs" / job_id
            job_dir.mkdir(parents=True)
            result = {
                "schema": "physical-lab-job-result-v1",
                "verification": {"analytic_reference_relative_error": 1.0e-4, "convergence_order": 3.99},
                "validation": {"measurement_rmse": 0.012},
                "uncertainty": {"propagated_standard_uncertainty": 0.018},
                "robustness": {"timestep_relative_change": 0.004, "sensitivity_spread": 0.02},
                "boundary": "Synthetic CI result only.",
            }
            result_path = job_dir / "result.json"
            result_path.write_text(json.dumps(result, sort_keys=True), encoding="utf-8")
            log_path = job_dir / "worker.log"
            log_path.write_text("synthetic deterministic worker log\n", encoding="utf-8")
            job = {
                "id": job_id,
                "experiment_sha256": manifest["experiment_sha256"],
                "profile": manifest["profile"],
                "runner": "model-campaign",
                "status": "succeeded",
                "stage": "complete",
                "attempt": 1,
                "created_at": "2026-01-01T00:00:02+00:00",
                "updated_at": "2026-01-01T00:00:03+00:00",
                "result_path": str(result_path),
                "log_path": str(log_path),
            }
            assert projects.register_job_reference(project_dir, job, result=result)

            claim = claims.register_claim(
                project_dir,
                statement="The fixture result remains within the registered comparison requirement.",
                intended_use="deterministic capsule CI fixture",
                required_factors=["verification", "validation", "uncertainty_characterization", "results_robustness"],
                references=[
                    {"kind": "experiment", "id": exp["experiment_id"]},
                    {"kind": "result", "id": job_id},
                    {"kind": "measurement", "id": measurement["measurement_id"]},
                    {"kind": "calibration", "id": calibration["calibration_id"]},
                ],
            )
            assert claims.evaluate_claim(project_dir, claim["claim_id"])["status"] in {"READY_FOR_REVIEW", "PARTIAL"}

            check = cross_checks.register_cross_check(
                project_dir,
                name="fixture numerical vs analytic check",
                observable="normalized response",
                primary={
                    "value": 1.0000,
                    "method_family": "numerical-rk4",
                    "source_identity": "capsule-fixture-result",
                    "references": [{"kind": "result", "id": job_id}],
                },
                comparison={
                    "value": 0.9995,
                    "method_family": "analytic-closed-form",
                    "source_identity": "capsule-fixture-reference",
                    "references": [{"kind": "measurement", "id": measurement["measurement_id"]}],
                },
                tolerance=0.001,
                tolerance_mode="relative",
                unit="1",
                intended_use="capsule CI corroboration fixture",
            )
            assert cross_checks.evaluate_cross_check(project_dir, check["cross_check_id"])["status"] == "AGREES_WITHIN_TOLERANCE"

            # Workflow provenance should travel, but never be relabeled as a canonical scientific result.
            (project_dir / "runs/desktop-run-001").mkdir(parents=True)
            (project_dir / "runs/desktop-run-001/run.json").write_text(
                json.dumps({"schema": "physical-lab-run-v1", "id": "desktop-run-001", "results": {"preview": 1.0}}),
                encoding="utf-8",
            )
            (project_dir / "campaigns").mkdir(exist_ok=True)
            (project_dir / "campaigns/gap-scan.json").write_text(
                json.dumps({"schema": "physical-lab-campaign-v1", "parameter": "gap_mm"}), encoding="utf-8"
            )

            # Add a deliberately oversized provenance artifact. It must be fingerprinted and explicitly omitted.
            large_path = project_dir / "reports/oversized-fixture.txt"
            large_path.parent.mkdir(exist_ok=True)
            large_path.write_bytes(b"X" * 4096)

            max_file = 2048
            max_total = 2 * 1024 * 1024
            first_path, first_manifest, first_archive_sha = capsule.write_reproducibility_capsule(
                project_dir, max_file_bytes=max_file, max_total_bytes=max_total
            )
            first_bytes = first_path.read_bytes()
            verify = capsule.verify_reproducibility_capsule(first_path)
            assert verify["valid"], verify
            assert first_manifest["schema"] == capsule.CAPSULE_SCHEMA
            assert first_manifest["project_id"] == projects.open_project(project_dir)["project_id"]
            assert first_manifest["included_file_count"] > 8
            assert first_manifest["omitted_file_count"] >= 1
            assert first_archive_sha == verify["archive_sha256"]

            inventory = {row["archive_path"]: row for row in first_manifest["inventory"]}
            required_members = {
                "project/project.json",
                f"experiments/{exp['experiment_id']}/manifest.json",
                f"results/{job_id}/result.json",
                f"measurements/{measurement['measurement_id']}/measurement.json",
                f"measurements/{measurement['measurement_id']}/assets/reference-field.csv",
                f"calibration/{calibration['calibration_id']}.json",
                "evidence/credibility-passport.json",
                "evidence/claim-matrix.json",
                "evidence/cross-check-matrix.json",
                "evidence/current-evidence-snapshot.json",
                "workflow/runs/desktop-run-001/run.json",
            }
            assert required_members <= set(inventory), sorted(required_members - set(inventory))
            assert all(inventory[name]["included"] for name in required_members)
            assert inventory["reports/oversized-fixture.txt"]["included"] is False
            assert "exceeds max_file_bytes" in str(inventory["reports/oversized-fixture.txt"]["omission_reason"])
            assert len(str(inventory["reports/oversized-fixture.txt"]["sha256"])) == 64
            assert inventory["workflow/runs/desktop-run-001/run.json"]["scientific_role"] == "workflow-provenance"
            assert first_manifest["policy"]["workflow_artifacts_are_scientific_results"] is False

            with zipfile.ZipFile(first_path, "r") as archive:
                names = set(archive.namelist())
                assert "capsule.json" in names
                assert required_members <= names
                assert "reports/oversized-fixture.txt" not in names
                capsule_json = json.loads(archive.read("capsule.json"))
                assert capsule_json["capsule_sha256"] == first_manifest["capsule_sha256"]
                assert "aggregate_credibility_score" not in json.loads(archive.read("evidence/credibility-passport.json"))

            # Export is not project state: same state/policy must produce exactly the same manifest and ZIP bytes.
            second_path = project_dir / "exports/second-capsule.zip"
            second_path, second_manifest, second_archive_sha = capsule.write_reproducibility_capsule(
                project_dir,
                output_path=second_path,
                max_file_bytes=max_file,
                max_total_bytes=max_total,
            )
            assert second_manifest["capsule_sha256"] == first_manifest["capsule_sha256"]
            assert second_archive_sha == first_archive_sha
            assert second_path.read_bytes() == first_bytes
            assert capsule.verify_reproducibility_capsule(second_path)["valid"]

            # Tampering with a member must invalidate verification while leaving capsule.json unchanged.
            tampered = project_dir / "exports/tampered-capsule.zip"
            with zipfile.ZipFile(first_path, "r") as source, zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as target:
                for name in source.namelist():
                    data = source.read(name)
                    if name == "project/project.json":
                        data += b"\nTAMPERED\n"
                    target.writestr(name, data)
            bad = capsule.verify_reproducibility_capsule(tampered)
            assert not bad["valid"]
            assert "project/project.json" in bad["corrupt_members"]

            # Changing scientific evidence must change capsule identity, and an existing claim/cross-check must become stale.
            changed_result = dict(result)
            changed_result["verification"] = {"analytic_reference_relative_error": 2.0e-4, "convergence_order": 3.98}
            result_path.write_text(json.dumps(changed_result, sort_keys=True), encoding="utf-8")
            assert projects.register_job_reference(project_dir, {**job, "updated_at": "2026-01-02T00:00:00+00:00"}, result=changed_result)
            third_manifest, _payloads = capsule.build_capsule_manifest(
                project_dir, max_file_bytes=max_file, max_total_bytes=max_total
            )
            assert third_manifest["capsule_sha256"] != first_manifest["capsule_sha256"]
            assert claims.evaluate_claim(project_dir, claim["claim_id"])["status"] == "STALE"
            assert cross_checks.evaluate_cross_check(project_dir, check["cross_check_id"])["status"] == "STALE"

            print("Physical Lab Reproducibility Capsule v1 validation: PASS")
            print(f"- capsule fingerprint: {first_manifest['capsule_sha256'][:16]}…")
            print(f"- deterministic archive SHA-256: {first_archive_sha[:16]}…")
            print(f"- included: {first_manifest['included_file_count']} · omitted explicitly: {first_manifest['omitted_file_count']}")
            print("- complete evidence chain packaging: PASS")
            print("- workflow provenance remains non-scientific-role: PASS")
            print("- oversized artifact fingerprint + explicit omission: PASS")
            print("- byte-for-byte deterministic re-export: PASS")
            print("- archive/member tamper detection: PASS")
            print("- evidence drift -> new capsule identity + stale review state: PASS")
            print("Boundary: capsule integrity/portability only; no truth, verification, validation, standards-compliance, accreditation or certification verdict.")
    finally:
        if old_data is None:
            os.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
        else:
            os.environ["PHYSICAL_LAB_DATA_DIR"] = old_data
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
