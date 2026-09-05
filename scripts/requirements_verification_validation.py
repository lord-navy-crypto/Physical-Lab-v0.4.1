#!/usr/bin/env python3
"""Deterministic acceptance checks for Requirements & Verification Planning Layer v1."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_project_kernel as projects
import physical_lab_requirements_verification as rv
from physical_lab_experiment_kernel import build_experiment_manifest, utc_now


def register_result(project_dir: Path, root: Path, manifest: dict, job_id: str, result: dict) -> None:
    job_dir = root / "compute-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "result.json"
    log_path = job_dir / "worker.log"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    log_path.write_text("requirements verification validation\n", encoding="utf-8")
    record = {
        "id": job_id,
        "experiment_sha256": manifest["experiment_sha256"],
        "profile": manifest["profile"],
        "runner": "requirements-verification-fixture",
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
    with tempfile.TemporaryDirectory(prefix="physical-lab-requirements-verification-") as temp:
        root = Path(temp).resolve()
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)
        project_dir, _ = projects.create_project(
            "Requirements Verification Validation",
            research_question="Can Physical Lab plan requirement verification without fabricating compliance or certification?",
        )
        manifest = build_experiment_manifest(
            "numerical-methods",
            parameters={"fixture": "requirements-verification"},
            provenance={"source_commit": "abcdef0123456789abcdef0123456789abcdef01"},
        )
        projects.register_experiment(project_dir, manifest)
        register_result(project_dir, root, manifest, "job-req-v", {"revision": 1, "source": "fixture"})
        ref = [{"kind": "result", "id": "job-req-v"}]

        req = rv.register_requirement(
            project_dir,
            requirement_id="SYS-PERF-001",
            statement="The numerical workflow shall keep normalized error below the declared project threshold.",
            verification_method="analysis",
            verification_activity="Compare the deterministic result artifact with the declared threshold.",
            success_criteria="Normalized error is <= 0.001 for the declared fixture.",
            references=ref,
            source_document="System Requirements",
            source_locator="§3.2.1",
            rationale="Bound numerical error for the intended analysis workflow.",
            level="system",
            owner="project engineering",
            upstream_requirement_ids=["STAKEHOLDER-NEED-07", "MISSION-GOAL-02"],
            intended_use="verification planning fixture",
        )
        assert req["requirement_id"] == "SYS-PERF-001"
        assert req["verification_method"] == "analysis"
        assert req["upstream_requirement_ids"] == ["MISSION-GOAL-02", "STAKEHOLDER-NEED-07"]

        evaluation = rv.evaluate_requirement(project_dir, "SYS-PERF-001")
        assert evaluation["evidence_state"] == "READY_FOR_REVIEW"
        assert evaluation["reference_count"] == 1
        assert evaluation["normative_keyword"] == "shall"
        assert evaluation["verification_method"] == "analysis"

        review = rv.record_requirement_review(
            project_dir,
            "SYS-PERF-001",
            outcome="EVIDENCE_SUFFICIENT_FOR_PROJECT_REVIEW",
            rationale="The declared analysis artifact is present and current for project review.",
            reviewer="fixture-reviewer",
        )
        assert review["outcome"] == "EVIDENCE_SUFFICIENT_FOR_PROJECT_REVIEW"
        reviewed = rv.evaluate_requirement(project_dir, "SYS-PERF-001")
        assert reviewed["latest_human_review"]["reviewer"] == "fixture-reviewer"

        no_evidence = rv.register_requirement(
            project_dir,
            requirement_id="SYS-INSP-002",
            statement="The exported package shall contain a human-readable provenance manifest.",
            verification_method="inspection",
            verification_activity="Inspect the exported archive contents.",
            success_criteria="A provenance manifest is present and readable.",
            references=[],
            source_document="Packaging Requirements",
            upstream_requirement_ids=["SYS-PERF-001"],
        )
        assert no_evidence["verification_method"] == "inspection"
        missing_eval = rv.evaluate_requirement(project_dir, "SYS-INSP-002")
        assert missing_eval["evidence_state"] == "EVIDENCE_MISSING"
        assert missing_eval["missing_references"] == ["no-explicit-evidence-reference"]

        for method, req_id in (("test", "SYS-TEST-003"), ("demonstration", "SYS-DEMO-004")):
            rv.register_requirement(
                project_dir,
                requirement_id=req_id,
                statement=f"The fixture shall support the declared {method} verification plan.",
                verification_method=method,
                verification_activity=f"Execute the declared {method} activity.",
                success_criteria="The declared observable evidence is produced.",
                references=ref,
                source_document="Verification Fixture",
            )
            assert rv.evaluate_requirement(project_dir, req_id)["evidence_state"] == "READY_FOR_REVIEW"

        matrix = rv.requirements_verification_matrix(project_dir)
        assert matrix["requirement_count"] == 4
        assert matrix["verification_methods"] == ["test", "analysis", "inspection", "demonstration"]
        assert len(matrix["matrix_sha256"]) == 64
        row = next(item for item in matrix["requirements"] if item["requirement_id"] == "SYS-PERF-001")
        assert row["latest_review_outcome"] == "EVIDENCE_SUFFICIENT_FOR_PROJECT_REVIEW"

        register_result(project_dir, root, manifest, "job-req-v", {"revision": 2, "source": "fixture"})
        stale = rv.evaluate_requirement(project_dir, "SYS-PERF-001")
        assert stale["evidence_state"] == "STALE"
        assert stale["stale_references"] == ["result:job-req-v"]

        try:
            rv.record_requirement_review(
                project_dir,
                "SYS-PERF-001",
                outcome="EVIDENCE_SUFFICIENT_FOR_PROJECT_REVIEW",
                rationale="This should be rejected because evidence is stale.",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("stale evidence must not be marked sufficient for project review")

        try:
            rv.register_requirement(
                project_dir,
                requirement_id="BAD-NORMATIVE",
                statement="The workflow should be deterministic.",
                verification_method="test",
                verification_activity="Run the fixture.",
                success_criteria="Repeatable output.",
                references=ref,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("verification-matrix requirement without 'shall' must be rejected")

        try:
            rv.register_requirement(
                project_dir,
                requirement_id="BAD-METHOD",
                statement="The workflow shall support an unsupported verification method.",
                verification_method="simulation-only",
                verification_activity="Invalid fixture.",
                success_criteria="Invalid fixture.",
                references=ref,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("unsupported verification method must be rejected")

        encoded = json.dumps({"evaluation": evaluation, "review": review, "matrix": matrix}).lower()
        for forbidden in (
            '"verified": true',
            '"compliant": true',
            '"passed": true',
            '"accepted": true',
            '"qualified": true',
            '"certified": true',
            '"safe": true',
            '"validated": true',
            '"automatic_verdict"',
        ):
            assert forbidden not in encoded, forbidden

        print("Physical Lab Requirements & Verification Planning Layer v1 validation: PASS")
        print("- normative 'shall' requirement guard: PASS")
        print("- test / analysis / inspection / demonstration methods: PASS")
        print("- explicit source + upstream traceability IDs: PASS")
        print("- evidence ready / missing / stale semantics: PASS")
        print("- human evidence-review record + stale guard: PASS")
        print("- automatic verification/compliance/acceptance/certification verdicts: intentionally absent")
        print("Boundary: verification planning and evidence readiness only; no automatic product verification, stakeholder validation, safety approval, qualification, acceptance, standards compliance, or certification claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
