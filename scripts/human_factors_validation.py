#!/usr/bin/env python3
"""Deterministic acceptance checks for Physical Lab Human Factors Layer v1."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_human_factors as hf
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import build_experiment_manifest, utc_now


def register_result(project_dir: Path, root: Path, manifest: dict, job_id: str, result: dict) -> None:
    job_dir = root / "compute-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "result.json"
    log_path = job_dir / "worker.log"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    log_path.write_text("human-factors validation\n", encoding="utf-8")
    record = {
        "id": job_id,
        "experiment_sha256": manifest["experiment_sha256"],
        "profile": manifest["profile"],
        "runner": "human-factors-fixture",
        "status": "succeeded",
        "stage": "complete",
        "attempt": 1,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "result_path": str(result_path),
        "log_path": str(log_path),
    }
    assert projects.register_job_reference(project_dir, record, result=result)


def approx(value: float | None, expected: float, tol: float = 1e-12) -> None:
    assert value is not None
    assert abs(float(value) - expected) <= tol, (value, expected)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="physical-lab-human-factors-") as temp:
        root = Path(temp).resolve()
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)
        project_dir, _ = projects.create_project(
            "Human Factors Validation",
            research_question="Can Physical Lab summarize operator-task evidence without creating a synthetic usability or safety verdict?",
        )
        manifest = build_experiment_manifest(
            "numerical-methods",
            parameters={"fixture": "human-factors"},
            provenance={"source_commit": "abcdef0123456789abcdef0123456789abcdef01"},
        )
        projects.register_experiment(project_dir, manifest)
        register_result(project_dir, root, manifest, "job-human-factors", {"revision": 1, "source": "fixture"})
        ref = [{"kind": "result", "id": "job-human-factors"}]

        record = hf.register_human_factors_study(
            project_dir,
            name="Operator workflow fixture",
            system_context="Physical Lab evidence review workflow",
            observations=[
                {
                    "observation_id": "o1",
                    "session_label": "session-a",
                    "task_id": "task-review",
                    "task_name": "Review evidence",
                    "completion_state": "COMPLETED",
                    "completion_time_s": 10.0,
                    "error_count": 0,
                    "assistance_count": 0,
                    "ease_rating_1_to_7": 6,
                    "references": ref,
                },
                {
                    "observation_id": "o2",
                    "session_label": "session-b",
                    "task_id": "task-review",
                    "task_name": "Review evidence",
                    "completion_state": "COMPLETED",
                    "completion_time_s": 14.0,
                    "error_count": 1,
                    "assistance_count": 0,
                    "ease_rating_1_to_7": 5,
                    "references": ref,
                },
                {
                    "observation_id": "o3",
                    "session_label": "session-c",
                    "task_id": "task-export",
                    "task_name": "Export evidence snapshot",
                    "completion_state": "COMPLETED",
                    "completion_time_s": 20.0,
                    "error_count": 0,
                    "assistance_count": 1,
                    "ease_rating_1_to_7": 4,
                    "references": ref,
                },
                {
                    "observation_id": "o4",
                    "session_label": "session-d",
                    "task_id": "task-export",
                    "task_name": "Export evidence snapshot",
                    "completion_state": "NOT_COMPLETED",
                    "completion_time_s": None,
                    "error_count": 2,
                    "assistance_count": 2,
                    "ease_rating_1_to_7": 2,
                    "references": ref,
                },
            ],
            intended_use="deterministic descriptive human-factors fixture",
        )
        evaluation = hf.evaluate_human_factors_study(project_dir, record["study_id"])
        assert evaluation["evidence_state"] == "CURRENT"
        assert evaluation["observation_count"] == 4
        assert evaluation["task_count"] == 2
        assert evaluation["completed_count"] == 3
        approx(evaluation["completion_fraction"], 0.75)
        approx(evaluation["completion_time_s"]["mean"], 44.0 / 3.0)
        approx(evaluation["completion_time_s"]["median"], 14.0)
        assert evaluation["total_errors"] == 3
        approx(evaluation["errors_per_observation"], 0.75)
        assert evaluation["total_assistance"] == 3
        approx(evaluation["assistance_per_observation"], 0.75)
        approx(evaluation["ease_rating_1_to_7"]["mean"], 4.25)

        tasks = {row["task_id"]: row for row in evaluation["task_summaries"]}
        assert set(tasks) == {"task-review", "task-export"}
        approx(tasks["task-review"]["completion_fraction"], 1.0)
        approx(tasks["task-review"]["completion_time_s"]["mean"], 12.0)
        approx(tasks["task-review"]["errors_per_observation"], 0.5)
        approx(tasks["task-export"]["completion_fraction"], 0.5)
        approx(tasks["task-export"]["completion_time_s"]["mean"], 20.0)
        approx(tasks["task-export"]["errors_per_observation"], 1.0)
        approx(tasks["task-export"]["assistance_per_observation"], 1.5)

        matrix = hf.human_factors_matrix(project_dir)
        assert len(matrix["studies"]) == 1
        assert len(matrix["matrix_sha256"]) == 64

        register_result(project_dir, root, manifest, "job-human-factors", {"revision": 2, "source": "fixture"})
        stale = hf.evaluate_human_factors_study(project_dir, record["study_id"])
        assert stale["evidence_state"] == "STALE"
        assert len(stale["stale_references"]) == 4

        bad_cases = [
            {"error_count": -1},
            {"assistance_count": -1},
            {"completion_time_s": -0.1},
            {"ease_rating_1_to_7": 8},
        ]
        for patch in bad_cases:
            row = {
                "task_id": "bad-task",
                "task_name": "Bad task",
                "completion_state": "COMPLETED",
                "completion_time_s": 1.0,
                "error_count": 0,
                "assistance_count": 0,
                "ease_rating_1_to_7": 4,
                "references": ref,
            }
            row.update(patch)
            try:
                hf.register_human_factors_study(
                    project_dir,
                    name="Bad fixture",
                    system_context="validation",
                    observations=[row],
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid human-factors observation accepted: {patch}")

        try:
            hf.register_human_factors_study(
                project_dir,
                name="PII guard",
                system_context="validation",
                observations=[{
                    "session_label": "email:test@example.com",
                    "task_id": "task",
                    "task_name": "task",
                    "completion_state": "COMPLETED",
                    "completion_time_s": 1.0,
                    "references": ref,
                }],
            )
        except ValueError:
            pass
        else:
            raise AssertionError("contact-information session label must be rejected")

        encoded = json.dumps({"evaluation": evaluation, "matrix": matrix}).lower()
        for forbidden in (
            '"usability_score"', '"operator_score"', '"fitness"', '"safe": true',
            '"ergonomic_pass"', '"accessibility_compliant"', '"certified": true',
            '"recommended_operator"', '"health_status"',
        ):
            assert forbidden not in encoded, forbidden

        print("Physical Lab Human Factors Layer v1 validation: PASS")
        print("- task completion + timing summaries: PASS")
        print("- error / assistance descriptive rates: PASS")
        print("- 1–7 declared ease-rating summaries: PASS")
        print("- task-level workflow summaries: PASS")
        print("- evidence fingerprint drift -> STALE: PASS")
        print("- invalid metric / direct-contact-info guards: PASS")
        print("- usability/operator/safety/certification score or verdict: intentionally absent")
        print("Boundary: descriptive anonymous/pseudonymous operator-workflow evidence only; no health diagnosis, person ranking, ergonomic certification, safety approval, accessibility compliance, or causal human-performance claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
