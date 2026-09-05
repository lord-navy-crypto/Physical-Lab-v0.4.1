#!/usr/bin/env python3
"""Deterministic acceptance checks for Physical Lab Requirements & Traceability Layer v1."""
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
import physical_lab_operations_planning as operations
import physical_lab_project_kernel as projects
import physical_lab_requirements as requirements
import physical_lab_risk_economics as risk_economics
from physical_lab_experiment_kernel import build_experiment_manifest, utc_now


def register_result(project_dir: Path, root: Path, manifest: dict, job_id: str, result: dict) -> None:
    job_dir = root / "compute-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "result.json"
    log_path = job_dir / "worker.log"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    log_path.write_text("requirements-traceability validation\n", encoding="utf-8")
    record = {
        "id": job_id,
        "experiment_sha256": manifest["experiment_sha256"],
        "profile": manifest["profile"],
        "runner": "requirements-fixture",
        "status": "succeeded",
        "stage": "complete",
        "attempt": 1,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "result_path": str(result_path),
        "log_path": str(log_path),
    }
    assert projects.register_job_reference(project_dir, record, result=result)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="physical-lab-requirements-") as temp:
        root = Path(temp).resolve()
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)
        project_dir, _ = projects.create_project(
            "Requirements Traceability Validation",
            research_question="Can Physical Lab preserve requirement flowdown and evidence freshness without issuing machine verification verdicts?",
        )
        manifest = build_experiment_manifest(
            "numerical-methods",
            parameters={"fixture": "requirements"},
            provenance={"source_commit": "abcdef0123456789abcdef0123456789abcdef01"},
        )
        projects.register_experiment(project_dir, manifest)
        register_result(project_dir, root, manifest, "job-req", {"metric": 1.0, "revision": 1})
        evidence = [{"kind": "result", "id": "job-req"}]

        claim = claims.register_claim(
            project_dir,
            statement="Fixture engineering result is available for requirements review.",
            intended_use="requirements traceability fixture",
            references=evidence,
        )
        risk = risk_economics.register_risk_study(
            project_dir,
            name="Requirement-linked risk fixture",
            scenarios=[{
                "scenario_id": "risk-a",
                "name": "Declared schedule risk",
                "probability": 0.1,
                "consequences": {"schedule": 2.0},
                "references": evidence,
            }],
            intended_use="requirements traceability fixture",
        )
        plan = operations.register_operations_plan(
            project_dir,
            name="Requirement-linked operations fixture",
            resources=[{"resource_id": "solver", "capacity": 1}],
            tasks=[{"task_id": "verify-task", "duration": 2.0, "resources": {"solver": 1}}],
            intended_use="requirements traceability fixture",
        )

        parent = requirements.register_requirement(
            project_dir,
            requirement_key="SYS-001",
            statement="The system shall produce a reviewable engineering result.",
            source="fixture stakeholder specification §1",
            level="system",
            verification_method="analysis",
            verification_criteria="Review the registered result against the declared engineering criterion.",
            evidence_references=evidence,
            engineering_links=[
                {"kind": "claim", "id": claim["claim_id"]},
                {"kind": "risk-study", "id": risk["study_id"]},
            ],
            intended_use="deterministic requirement-flowdown fixture",
        )
        parent_eval = requirements.evaluate_requirement(project_dir, parent["requirement_id"])
        assert parent_eval["status"] == "READY_FOR_REVIEW", parent_eval

        child = requirements.register_requirement(
            project_dir,
            requirement_key="SUB-001",
            statement="The subsystem shall complete the declared verification task.",
            source="fixture subsystem specification §2",
            level="subsystem",
            parent_requirement_ids=[parent["requirement_id"]],
            verification_method="test",
            verification_criteria="Execute the declared task and review the linked result evidence.",
            evidence_references=evidence,
            engineering_links=[{"kind": "operations-plan", "id": plan["plan_id"]}],
            intended_use="deterministic requirement-flowdown fixture",
        )
        child_eval = requirements.evaluate_requirement(project_dir, child["requirement_id"])
        assert child_eval["status"] == "READY_FOR_REVIEW", child_eval
        assert child_eval["parent_checks"][0]["state"] == "CURRENT"
        assert child_eval["engineering_checks"][0]["state"] == "CURRENT"

        unplanned = requirements.register_requirement(
            project_dir,
            requirement_key="PLAN-001",
            statement="The project shall later define a verification approach for this fixture requirement.",
            source="fixture planning note",
            evidence_references=evidence,
        )
        assert requirements.evaluate_requirement(project_dir, unplanned["requirement_id"])["status"] == "UNPLANNED"

        no_evidence = requirements.register_requirement(
            project_dir,
            requirement_key="EVID-001",
            statement="The project shall provide evidence for this fixture requirement.",
            source="fixture planning note",
            verification_method="inspection",
            verification_criteria="Inspect the future evidence package.",
        )
        assert requirements.evaluate_requirement(project_dir, no_evidence["requirement_id"])["status"] == "EVIDENCE_MISSING"

        matrix = requirements.traceability_matrix(project_dir)
        assert len(matrix["requirements"]) == 4
        rows = {row["requirement_key"]: row for row in matrix["requirements"]}
        assert rows["SYS-001"]["child_count"] == 1
        assert rows["SUB-001"]["parent_count"] == 1
        assert matrix["counts"]["READY_FOR_REVIEW"] == 2
        assert matrix["counts"]["UNPLANNED"] == 1
        assert matrix["counts"]["EVIDENCE_MISSING"] == 1
        assert len(matrix["matrix_sha256"]) == 64

        # Change an upstream engineering-record fingerprint in place. The child
        # requirement must become STALE rather than silently treating the link as current.
        plan_path = project_dir / "provenance" / "operations-plans" / f"{plan['plan_id']}.json"
        plan_doc = json.loads(plan_path.read_text(encoding="utf-8"))
        plan_doc["plan_sha256"] = "f" * 64
        plan_path.write_text(json.dumps(plan_doc, indent=2, sort_keys=True), encoding="utf-8")
        stale_link = requirements.evaluate_requirement(project_dir, child["requirement_id"])
        assert stale_link["status"] == "STALE"
        assert stale_link["engineering_checks"][0]["state"] == "STALE"

        plan_path.unlink()
        missing_link = requirements.evaluate_requirement(project_dir, child["requirement_id"])
        assert missing_link["status"] == "LINK_MISSING"
        assert missing_link["missing_links"] == [f"operations-plan:{plan['plan_id']}"]

        register_result(project_dir, root, manifest, "job-req", {"metric": 2.0, "revision": 2})
        stale_evidence = requirements.evaluate_requirement(project_dir, parent["requirement_id"])
        assert stale_evidence["status"] == "STALE"
        assert stale_evidence["stale_evidence"] == ["result:job-req"]

        try:
            requirements.register_requirement(
                project_dir,
                requirement_key="SYS-001",
                statement="Duplicate key",
                source="fixture",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("duplicate requirement_key must be rejected")

        try:
            requirements.register_requirement(
                project_dir,
                requirement_key="BAD-LINK",
                statement="Bad engineering link shall be rejected.",
                source="fixture",
                verification_method="analysis",
                verification_criteria="fixture",
                evidence_references=evidence,
                engineering_links=[{"kind": "decision-study", "id": "missing-study"}],
            )
        except ValueError:
            pass
        else:
            raise AssertionError("missing engineering links must be rejected at registration")

        encoded = json.dumps({"parent": parent_eval, "child": child_eval, "matrix": matrix}).lower()
        for forbidden in (
            '"verified": true', '"validated": true', '"compliant": true', '"accepted": true',
            '"safe": true', '"certified": true', '"verification_verdict"', '"validation_verdict"',
        ):
            assert forbidden not in encoded, forbidden

        print("Physical Lab Requirements & Traceability Layer v1 validation: PASS")
        print("- unique requirement key/source/flowdown: PASS")
        print("- declared verification method + criteria: PASS")
        print("- raw Project evidence freshness: PASS")
        print("- claim/risk/operations engineering links: PASS")
        print("- parent -> child bidirectional matrix counts: PASS")
        print("- upstream engineering fingerprint drift -> STALE: PASS")
        print("- missing engineering record -> LINK_MISSING: PASS")
        print("- missing evidence / unplanned verification states: PASS")
        print("- VERIFIED / VALIDATED / compliance / safety verdicts: intentionally absent")
        print("Boundary: readiness and traceability only; no machine verification, validation, compliance, acceptance, safety, or certification decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
