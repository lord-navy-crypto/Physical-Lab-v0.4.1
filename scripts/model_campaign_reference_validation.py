#!/usr/bin/env python3
"""Deterministic acceptance checks for Physical Lab v0.9 model campaigns.

The checks exercise every non-accelerator automated campaign and feed the
resulting canonical metrics into the same model-specific engineering scorecards
used by the UI. They validate numerical/stochastic behavior only; they are not
experimental or product-certification evidence.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


campaigns = load("physical_lab_model_campaigns", UI / "physical_lab_model_campaigns.py")
sys.modules["physical_lab_model_campaigns"] = campaigns
campaign_ui = load("physical_lab_campaign_ui", UI / "physical_lab_campaign_ui.py")
engineering = load("physical_lab_model_engineering", UI / "physical_lab_model_engineering.py")


def assert_finite_metrics(profile: str, result: dict) -> None:
    metrics = result.get("metrics") or {}
    assert metrics, f"{profile}: campaign returned no metrics"
    for name, value in metrics.items():
        assert math.isfinite(float(value)), f"{profile}.{name}: metric is not finite"
    fingerprint = str(result.get("campaign_sha256", ""))
    assert len(fingerprint) == 64 and all(c in "0123456789abcdef" for c in fingerprint), f"{profile}: invalid campaign fingerprint"
    assert result.get("cases"), f"{profile}: campaign returned no cases"


def assert_scorecard_pass(profile: str, result: dict) -> dict:
    score = engineering.profile_scorecard(profile, result["metrics"])
    assert score["metric_completeness"] == 1.0, f"{profile}: incomplete scorecard"
    assert score["overall_status"] == "PASS", f"{profile}: scorecard {score['overall_status']} -> {score['requirements']}"
    return score


def assert_campaign_ui_contract() -> None:
    same = campaign_ui.campaign_result_state("compact", {"preset": "compact"})
    assert same == {
        "selected_preset": "compact",
        "result_preset": "compact",
        "has_result": True,
        "selection_matches_result": True,
    }
    stale = campaign_ui.campaign_result_state("standard", {"preset": "compact"})
    assert stale["has_result"] is True
    assert stale["selected_preset"] == "standard"
    assert stale["result_preset"] == "compact"
    assert stale["selection_matches_result"] is False
    empty = campaign_ui.campaign_result_state("standard", None)
    assert empty["has_result"] is False and empty["selection_matches_result"] is False

    ui_text = (UI / "physical_lab_campaign_ui.py").read_text(encoding="utf-8")
    assert 'st.tabs(["Summary", "Cases", "Provenance"])' in ui_text
    assert "The existing result is unchanged until you run the campaign again." in ui_text
    assert "pl_model_campaign_metrics_" in ui_text

    engineering_text = (UI / "physical_lab_engineering.py").read_text(encoding="utf-8")
    assert "from physical_lab_campaign_ui import render_model_campaign" in engineering_text

    tauri_text = (ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    assert '"resources/ui/physical_lab_campaign_ui.py": "ui/physical_lab_campaign_ui.py"' in tauri_text


def main() -> int:
    print("Physical Lab v0.9 automated model-campaign validation")
    assert_campaign_ui_contract()
    print("PASS campaign results UI state + bundle contract")
    observed = {}

    for profile in campaigns.SUPPORTED_PROFILES:
        result = campaigns.run_campaign(profile, "compact")
        assert_finite_metrics(profile, result)
        score = assert_scorecard_pass(profile, result)
        observed[profile] = result
        metrics = ", ".join(f"{k}={float(v):.6g}" for k, v in result["metrics"].items())
        print(f"PASS compact {profile}: {metrics}; requirements={len(score['requirements'])}")

    numerical = observed["numerical-methods"]
    p = float(numerical["metrics"]["convergence_order"])
    assert 1.8 <= p <= 2.2, f"numerical-methods: centered-difference order should be about 2, got {p}"
    numerical_cases = numerical["cases"]
    assert float(numerical_cases[0]["max_abs_error"]) > float(numerical_cases[-1]["max_abs_error"]), "numerical-methods: refinement did not reduce error"
    assert int(numerical_cases[0]["evaluations"]) < int(numerical_cases[-1]["evaluations"]), "numerical-methods: refinement cost proxy did not increase"

    ising = observed["ising-monte-carlo"]
    im = ising["metrics"]
    assert float(im["rhat_max"]) < 1.05
    assert float(im["effective_samples_min"]) >= 100.0
    assert float(im["exact_reference_relative_error"]) < 0.05
    exact_rows = [row for row in ising["cases"] if row.get("checkpoint") == "exact-4x4"]
    assert len(exact_rows) == 1, "ising-monte-carlo: missing exact 4x4 checkpoint"
    assert abs(float(exact_rows[0]["exact_energy_per_spin"])) > 0.1

    walk = observed["random-walk-monte-carlo"]
    wm = walk["metrics"]
    assert float(wm["msd_exponent_error"]) < 0.05
    assert float(wm["estimator_relative_error"]) < 0.05
    aggregate = [row for row in walk["cases"] if row.get("aggregate") == "MSD scaling"]
    assert len(aggregate) == 1
    assert 0.95 <= float(aggregate[0]["fitted_exponent"]) <= 1.05

    chaos = observed["nonlinear-chaos"]
    cm = chaos["metrics"]
    assert float(cm["indicator_timestep_relative_change"]) < 0.05
    assert float(cm["lyapunov_relative_spread"]) < 0.10
    assert float(cm["energy_balance_relative_error"]) < 0.01
    lyap_rows = [row for row in chaos["cases"] if "finite_time_lyapunov_estimates" in row]
    assert len(lyap_rows) == 1
    assert float(lyap_rows[0]["mean"]) > 0.01, "nonlinear-chaos: selected Duffing reference should show positive finite-time sensitivity"

    osc = observed["oscillation-integration"]
    om = osc["metrics"]
    assert float(om["frequency_relative_error"]) < 0.01
    assert float(om["amplitude_relative_error"]) < 0.02
    assert float(om["phase_error_rad"]) < 0.05
    assert float(om["energy_balance_relative_error"]) < 0.01
    coarse_error = float(osc["cases"][0]["final_state_error"])
    fine_error = float(osc["cases"][-1]["final_state_error"])
    assert fine_error < coarse_error, "oscillation-integration: RK4 timestep refinement did not reduce final-state error"

    # The standard chaos preset is explicitly checked because chaotic finite-time
    # diagnostics can change with the observation window even as the integrator
    # is behaving correctly. v0.9 keeps this preset in a tested screening window.
    standard_chaos = campaigns.run_campaign("nonlinear-chaos", "standard")
    assert_finite_metrics("nonlinear-chaos/standard", standard_chaos)
    assert_scorecard_pass("nonlinear-chaos", standard_chaos)
    print("PASS standard nonlinear-chaos:", ", ".join(f"{k}={float(v):.6g}" for k, v in standard_chaos["metrics"].items()))

    # Session-export helper must preserve exactly the canonical metrics.
    for profile, result in observed.items():
        exported = campaigns.canonical_session_metrics(result)
        assert exported == {k: float(v) for k, v in result["metrics"].items()}, f"{profile}: session metric export drift"

    print("PASS all v0.9 automated model campaigns and engineering scorecards")
    print("Boundary: deterministic numerical/stochastic acceptance only; no experimental-validation or certification claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
