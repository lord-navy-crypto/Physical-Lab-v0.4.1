#!/usr/bin/env python3
"""Deterministic acceptance checks for Physical Lab Engineering Decision Layer v1."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_engineering_decisions as decisions
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import build_experiment_manifest, utc_now


def register_result(project_dir: Path, root: Path, manifest: dict, job_id: str, result: dict) -> None:
    job_dir = root / "compute-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "result.json"
    log_path = job_dir / "worker.log"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    log_path.write_text("engineering-decision validation\n", encoding="utf-8")
    record = {
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
    assert projects.register_job_reference(project_dir, record, result=result)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="physical-lab-engineering-decision-") as temp:
        root = Path(temp).resolve()
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)
        project_dir, _ = projects.create_project(
            "Engineering Decision Validation",
            research_question="Can evidence-linked engineering alternatives be screened by constraints and Pareto dominance without a machine recommendation?",
        )
        manifest = build_experiment_manifest(
            "numerical-methods",
            parameters={"fixture": 1},
            provenance={"source_commit": "abcdef0123456789abcdef0123456789abcdef01"},
        )
        projects.register_experiment(project_dir, manifest)

        results = {
            "job-a": {"performance": 10.0, "cost": 100.0},
            "job-b": {"performance": 12.0, "cost": 120.0},
            "job-c": {"performance": 9.0, "cost": 90.0},
            "job-d": {"performance": 9.0, "cost": 110.0},
            "job-e": {"performance": 13.0, "cost": 150.0},
        }
        for job_id, result in results.items():
            register_result(project_dir, root, manifest, job_id, result)

        study = decisions.register_decision_study(
            project_dir,
            name="Fixture engineering trade study",
            decision_question="Which declared design alternatives remain reviewable under the cost constraint and stated performance/cost objectives?",
            metrics=[
                {"metric_id": "performance", "label": "Performance", "direction": "maximize", "unit": "1"},
                {"metric_id": "cost", "label": "Cost proxy", "direction": "minimize", "unit": "arb"},
            ],
            constraints=[{"metric_id": "cost", "operator": "<=", "threshold": 130.0}],
            alternatives=[
                {"alternative_id": "A", "label": "Balanced A", "values": results["job-a"], "references": [{"kind": "result", "id": "job-a"}]},
                {"alternative_id": "B", "label": "High performance B", "values": results["job-b"], "references": [{"kind": "result", "id": "job-b"}]},
                {"alternative_id": "C", "label": "Low cost C", "values": results["job-c"], "references": [{"kind": "result", "id": "job-c"}]},
                {"alternative_id": "D", "label": "Dominated D", "values": results["job-d"], "references": [{"kind": "result", "id": "job-d"}]},
                {"alternative_id": "E", "label": "Constraint fail E", "values": results["job-e"], "references": [{"kind": "result", "id": "job-e"}]},
            ],
            intended_use="deterministic CI trade-study semantics",
        )
        assert study["study_id"].startswith("trade-")
        assert len(study["study_sha256"]) == 64

        evaluation = decisions.evaluate_decision_study(project_dir, study["study_id"])
        by_id = {row["alternative_id"]: row for row in evaluation["alternatives"]}
        assert evaluation["pareto_frontier"] == ["A", "B", "C"], evaluation
        assert by_id["D"]["review_state"] == "FEASIBLE"
        assert by_id["D"]["pareto_nondominated"] is False
        assert by_id["D"]["dominated_by"] == ["A"]
        assert by_id["E"]["review_state"] == "INFEASIBLE"
        assert by_id["E"]["pareto_eligible"] is False
        assert evaluation["counts"]["FEASIBLE"] == 4
        assert evaluation["counts"]["INFEASIBLE"] == 1

        human = decisions.record_human_decision(
            project_dir,
            study["study_id"],
            selected_alternative_id="A",
            rationale="Fixture reviewer prefers the balanced alternative for this declared use; this is a human choice, not a tool recommendation.",
            reviewer="CI fixture reviewer",
        )
        assert human["selected_alternative_id"] == "A"
        assert human["evaluation_sha256"] == evaluation["evaluation_sha256"]
        assert len(human["decision_sha256"]) == 64

        changed = {"performance": 8.0, "cost": 100.0}
        register_result(project_dir, root, manifest, "job-a", changed)
        stale = decisions.evaluate_decision_study(project_dir, study["study_id"])
        stale_a = next(row for row in stale["alternatives"] if row["alternative_id"] == "A")
        assert stale_a["review_state"] == "STALE"
        assert stale_a["pareto_eligible"] is False
        assert any(item == "result:job-a" for item in stale_a["stale_references"])
        assert "A" not in stale["pareto_frontier"]

        matrix = decisions.decision_matrix(project_dir)
        assert matrix["studies"][0]["study_id"] == study["study_id"]
        assert len(matrix["matrix_sha256"]) == 64

        encoded = json.dumps({"study": study, "evaluation": evaluation, "human": human, "stale": stale}).lower()
        for forbidden in (
            '"recommended": true',
            '"best_alternative"',
            '"optimal_alternative"',
            '"truth_status"',
            '"certified": true',
        ):
            assert forbidden not in encoded, forbidden

        markdown = decisions.render_decision_markdown(evaluation)
        assert "Pareto frontier" in markdown
        assert "machine recommendation" in markdown

        print("Physical Lab Engineering Decision Layer v1 validation: PASS")
        print("- explicit constraints + feasibility: PASS")
        print("- multi-objective Pareto frontier: PASS")
        print("- dominated alternative detection: PASS")
        print("- evidence fingerprint drift -> STALE: PASS")
        print("- human decision record with rationale: PASS")
        print("- synthetic overall score / machine recommendation: intentionally absent")
        print("Boundary: decision analysis uses declared metrics, constraints and evidence only; it does not establish scientific truth, safety approval, certification, or unstated optimality.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
