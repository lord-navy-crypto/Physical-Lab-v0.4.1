#!/usr/bin/env python3
"""Deterministic acceptance checks for Physical Lab Risk & Engineering Economics Layer v1."""
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
import physical_lab_risk_economics as re
from physical_lab_experiment_kernel import build_experiment_manifest, utc_now


def register_result(project_dir: Path, root: Path, manifest: dict, job_id: str, result: dict) -> None:
    job_dir = root / "compute-jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    result_path = job_dir / "result.json"
    log_path = job_dir / "worker.log"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    log_path.write_text("risk-economics validation\n", encoding="utf-8")
    record = {
        "id": job_id,
        "experiment_sha256": manifest["experiment_sha256"],
        "profile": manifest["profile"],
        "runner": "risk-economics-fixture",
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
    with tempfile.TemporaryDirectory(prefix="physical-lab-risk-economics-") as temp:
        root = Path(temp).resolve()
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)
        project_dir, _ = projects.create_project(
            "Risk Economics Validation",
            research_question="Can Physical Lab compute explicit risk and present-worth arithmetic without inventing safety or investment recommendations?",
        )
        manifest = build_experiment_manifest(
            "numerical-methods",
            parameters={"fixture": "risk-economics"},
            provenance={"source_commit": "abcdef0123456789abcdef0123456789abcdef01"},
        )
        projects.register_experiment(project_dir, manifest)
        register_result(project_dir, root, manifest, "job-risk-econ", {"revision": 1, "source": "fixture"})
        ref = [{"kind": "result", "id": "job-risk-econ"}]

        risk = re.register_risk_study(
            project_dir,
            name="Declared engineering risk fixture",
            cost_unit="kUSD",
            schedule_unit="day",
            performance_unit="fraction",
            scenarios=[
                {
                    "scenario_id": "r1",
                    "name": "Supplier delay",
                    "probability": 0.1,
                    "consequences": {"cost": 100.0, "schedule": 2.0},
                    "references": ref,
                },
                {
                    "scenario_id": "r2",
                    "name": "Test rerun",
                    "probability": 0.2,
                    "consequences": {"cost": 50.0, "schedule": 5.0},
                    "references": ref,
                },
                {
                    "scenario_id": "r3",
                    "name": "Performance uncertainty without elicited probability",
                    "probability": None,
                    "consequences": {"performance": 0.4},
                    "references": ref,
                },
            ],
            intended_use="deterministic risk arithmetic fixture",
        )
        risk_eval = re.evaluate_risk_study(project_dir, risk["study_id"])
        assert risk_eval["evidence_state"] == "CURRENT"
        assert risk_eval["scenario_count"] == 3
        assert risk_eval["probability_declared_count"] == 2
        approx(risk_eval["expected_consequence_totals"]["cost"], 20.0)
        approx(risk_eval["expected_consequence_totals"]["schedule"], 1.2)
        assert risk_eval["expected_consequence_totals"]["performance"] is None
        r3 = next(row for row in risk_eval["scenarios"] if row["scenario_id"] == "r3")
        assert r3["expected_consequence"]["performance"] is None

        economics = re.register_economics_study(
            project_dir,
            name="Present-worth fixture",
            discount_rate=0.10,
            currency_unit="kUSD",
            period_unit="year",
            cash_flows=[
                {"flow_id": "f0", "period": 0, "amount": -1000.0, "label": "Initial engineering cost", "references": ref},
                {"flow_id": "f1", "period": 1, "amount": 600.0, "label": "Year 1 benefit", "references": ref},
                {"flow_id": "f2", "period": 2, "amount": 600.0, "label": "Year 2 benefit", "references": ref},
            ],
            intended_use="deterministic present-worth arithmetic fixture",
        )
        econ_eval = re.evaluate_economics_study(project_dir, economics["study_id"])
        assert econ_eval["evidence_state"] == "CURRENT"
        approx(econ_eval["undiscounted_net_total"], 200.0)
        approx(econ_eval["cash_flows"][0]["discount_factor"], 1.0)
        approx(econ_eval["cash_flows"][1]["discount_factor"], 1.0 / 1.1)
        approx(econ_eval["cash_flows"][2]["discount_factor"], 1.0 / (1.1 ** 2))
        approx(econ_eval["present_worth"], -1000.0 + 600.0 / 1.1 + 600.0 / (1.1 ** 2))

        matrix = re.risk_economics_matrix(project_dir)
        assert len(matrix["risk_studies"]) == 1
        assert len(matrix["economics_studies"]) == 1
        assert len(matrix["matrix_sha256"]) == 64

        register_result(project_dir, root, manifest, "job-risk-econ", {"revision": 2, "source": "fixture"})
        stale_risk = re.evaluate_risk_study(project_dir, risk["study_id"])
        stale_econ = re.evaluate_economics_study(project_dir, economics["study_id"])
        assert stale_risk["evidence_state"] == "STALE"
        assert stale_econ["evidence_state"] == "STALE"
        assert len(stale_risk["stale_references"]) == 3
        assert len(stale_econ["stale_references"]) == 3

        for bad_probability in (-0.01, 1.01):
            try:
                re.register_risk_study(
                    project_dir,
                    name="Bad probability",
                    scenarios=[{"probability": bad_probability, "consequences": {"cost": 1.0}, "references": ref}],
                )
            except ValueError:
                pass
            else:
                raise AssertionError("probability outside [0,1] must be rejected")

        try:
            re.register_economics_study(
                project_dir,
                name="Bad discount rate",
                discount_rate=-1.0,
                cash_flows=[{"period": 0, "amount": -1.0, "references": ref}],
            )
        except ValueError:
            pass
        else:
            raise AssertionError("discount rate <= -1 must be rejected")

        encoded = json.dumps({"risk": risk_eval, "economics": econ_eval, "matrix": matrix}).lower()
        for forbidden in (
            '"risk_accepted"', '"safe": true', '"safety_approved": true', '"certified": true',
            '"recommended_investment"', '"recommended_alternative"', '"optimal_investment"',
            '"true_risk"', '"market_forecast"',
        ):
            assert forbidden not in encoded, forbidden

        print("Physical Lab Risk & Engineering Economics Layer v1 validation: PASS")
        print("- explicit probability × consequence arithmetic: PASS")
        print("- probability-absent scenario stays non-expected: PASS")
        print("- cost / schedule consequence totals: PASS")
        print("- signed cash-flow present-worth arithmetic: PASS")
        print("- explicit discount-rate semantics: PASS")
        print("- evidence fingerprint drift -> STALE: PASS")
        print("- probability / discount-rate guards: PASS")
        print("- risk acceptance / safety / investment recommendation verdicts: intentionally absent")
        print("Boundary: declared-assumption arithmetic only; no calibrated risk forecast, safety approval, investment advice, economic superiority, or certification claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
