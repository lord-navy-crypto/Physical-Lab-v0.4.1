#!/usr/bin/env python3
"""Deterministic acceptance checks for Physical Lab Quality & Reliability Layer v1."""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_project_kernel as projects
import physical_lab_quality_reliability as qr
from physical_lab_experiment_kernel import build_experiment_manifest, utc_now


def register_result(project_dir: Path, root: Path, manifest: dict, job_id: str, result: dict) -> None:
    job_dir = root / "compute-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "result.json"
    log_path = job_dir / "worker.log"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    log_path.write_text("quality-reliability validation\n", encoding="utf-8")
    record = {
        "id": job_id,
        "experiment_sha256": manifest["experiment_sha256"],
        "profile": manifest["profile"],
        "runner": "quality-reliability-fixture",
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
    with tempfile.TemporaryDirectory(prefix="physical-lab-quality-reliability-") as temp:
        root = Path(temp).resolve()
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)
        project_dir, _ = projects.create_project(
            "Quality Reliability Validation",
            research_question="Can Physical Lab summarize variation and observed reliability events without inventing qualification or certification claims?",
        )
        manifest = build_experiment_manifest(
            "numerical-methods",
            parameters={"fixture": "quality-reliability"},
            provenance={"source_commit": "abcdef0123456789abcdef0123456789abcdef01"},
        )
        projects.register_experiment(project_dir, manifest)
        result = {"source": "fixture", "revision": 1}
        register_result(project_dir, root, manifest, "job-quality", result)
        ref = [{"kind": "result", "id": "job-quality"}]

        observations = [
            {"observation_id": "o1", "value": 10.0, "replicate_group": "g1", "factors": {"temperature": "low"}, "references": ref},
            {"observation_id": "o2", "value": 10.2, "replicate_group": "g1", "factors": {"temperature": "low"}, "references": ref},
            {"observation_id": "o3", "value": 10.8, "replicate_group": "g2", "factors": {"temperature": "high"}, "references": ref},
            {"observation_id": "o4", "value": 11.0, "replicate_group": "g2", "factors": {"temperature": "high"}, "references": ref},
            {"observation_id": "o5", "value": 9.8, "replicate_group": "g3", "factors": {"temperature": "low"}, "references": ref},
            {"observation_id": "o6", "value": 10.0, "replicate_group": "g3", "factors": {"temperature": "low"}, "references": ref},
        ]
        quality = qr.register_quality_study(
            project_dir,
            name="Replicate quality fixture",
            measurement="response",
            unit="arb",
            observations=observations,
            specification={"lower": 9.9, "upper": 10.9},
            intended_use="deterministic descriptive quality evidence",
        )
        q_eval = qr.evaluate_quality_study(project_dir, quality["study_id"])
        assert q_eval["evidence_state"] == "CURRENT"
        assert q_eval["summary"]["count"] == 6
        approx(q_eval["summary"]["mean"], 10.3)
        assert q_eval["specification_summary"]["within_count"] == 4
        assert q_eval["specification_summary"]["outside_count"] == 2
        approx(q_eval["specification_summary"]["observed_within_fraction"], 4 / 6)
        approx(q_eval["pooled_repeatability_std"], math.sqrt(0.02))
        assert q_eval["repeatability_degrees_freedom"] == 3
        factor = q_eval["factor_summaries"][0]
        assert factor["factor"] == "temperature"
        assert factor["levels"] == ["high", "low"]
        contrast = factor["descriptive_two_level_contrast"]
        assert contrast["from_level"] == "high"
        assert contrast["to_level"] == "low"
        approx(contrast["difference_of_means"], -0.9)

        trials = [
            {"trial_id": "t1", "exposure": 10.0, "event_observed": False, "references": ref},
            {"trial_id": "t2", "exposure": 10.0, "event_observed": True, "event_category": "thermal", "references": ref},
            {"trial_id": "t3", "exposure": 10.0, "event_observed": False, "references": ref},
            {"trial_id": "t4", "exposure": 10.0, "event_observed": True, "event_category": "thermal", "references": ref},
        ]
        reliability = qr.register_reliability_study(
            project_dir,
            name="Observed event fixture",
            item="test article",
            trials=trials,
            exposure_unit="h",
            intended_use="deterministic descriptive reliability-event evidence",
        )
        r_eval = qr.evaluate_reliability_study(project_dir, reliability["study_id"])
        assert r_eval["evidence_state"] == "CURRENT"
        assert r_eval["trial_count"] == 4
        assert r_eval["event_count"] == 2
        approx(r_eval["observed_event_fraction"], 0.5)
        approx(r_eval["total_exposure"], 40.0)
        approx(r_eval["observed_event_rate_per_exposure"], 0.05)
        assert r_eval["event_categories"] == {"thermal": 2}

        matrix = qr.quality_reliability_matrix(project_dir)
        assert len(matrix["quality_studies"]) == 1
        assert len(matrix["reliability_studies"]) == 1
        assert len(matrix["matrix_sha256"]) == 64

        register_result(project_dir, root, manifest, "job-quality", {"source": "fixture", "revision": 2})
        q_stale = qr.evaluate_quality_study(project_dir, quality["study_id"])
        r_stale = qr.evaluate_reliability_study(project_dir, reliability["study_id"])
        assert q_stale["evidence_state"] == "STALE"
        assert r_stale["evidence_state"] == "STALE"
        assert len(q_stale["stale_references"]) == 6
        assert len(r_stale["stale_references"]) == 4

        encoded = json.dumps({"quality": q_eval, "reliability": r_eval, "matrix": matrix}).lower()
        for forbidden in (
            '"cp"', '"cpk"', '"process_capability"', '"mtbf"', '"reliability_function"',
            '"certified": true', '"safety_approved": true', '"production_qualified": true',
        ):
            assert forbidden not in encoded, forbidden

        try:
            qr.register_quality_study(
                project_dir,
                name="Bad specification",
                measurement="x",
                unit="1",
                observations=[{"value": 1.0, "references": ref}],
                specification={"lower": 2.0, "upper": 1.0},
            )
        except ValueError:
            pass
        else:
            raise AssertionError("inverted specification must be rejected")

        try:
            qr.register_reliability_study(
                project_dir,
                name="Bad exposure",
                item="x",
                trials=[{"exposure": -1.0, "event_observed": False, "references": ref}],
            )
        except ValueError:
            pass
        else:
            raise AssertionError("negative exposure must be rejected")

        print("Physical Lab Quality & Reliability Layer v1 validation: PASS")
        print("- descriptive variation/specification summary: PASS")
        print("- pooled repeatability across replicate groups: PASS")
        print("- two-level descriptive factor contrast: PASS")
        print("- observed reliability-event/exposure summary: PASS")
        print("- evidence fingerprint drift -> STALE: PASS")
        print("- inverted specifications / negative exposure guards: PASS")
        print("- Cp/Cpk, MTBF, reliability-function and qualification verdicts: intentionally absent")
        print("Boundary: descriptive engineering evidence only; no process stability/capability, causal, certification, safety, or field-reliability claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
