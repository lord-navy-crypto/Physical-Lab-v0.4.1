#!/usr/bin/env python3
"""Static wiring checks for Physical Lab Risk & Engineering Economics Layer v1."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"


def main() -> int:
    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    for resource in (
        "resources/ui/physical_lab_risk_economics.py",
        "resources/ui/physical_lab_risk_economics_ui.py",
        "resources/ui/physical_lab_evidence_center_ui.py",
    ):
        assert resource in resources, resource

    core = (UI / "physical_lab_risk_economics.py").read_text(encoding="utf-8")
    risk_ui = (UI / "physical_lab_risk_economics_ui.py").read_text(encoding="utf-8")
    evidence_ui = (UI / "physical_lab_evidence_center_ui.py").read_text(encoding="utf-8")

    for needle in (
        "register_risk_study",
        "evaluate_risk_study",
        "register_economics_study",
        "evaluate_economics_study",
        "expected_consequence_totals",
        "present_worth",
        "discount_rate",
        "EVIDENCE_MISSING",
        "STALE",
    ):
        assert needle in core, needle

    for needle in (
        "Register risk study",
        "Register engineering-economics study",
        "probability",
        "Present worth",
        "No probability is inferred",
        "render_risk_economics_tab",
    ):
        assert needle in risk_ui, needle

    for needle in (
        '"Risk & Economics"',
        "physical_lab_risk_economics_ui",
        "render_risk_economics_tab(st, path, profile, refs)",
        "_artifact_refs(path, doc)",
        "risk acceptance",
        "investment recommendation",
    ):
        assert needle in evidence_ui, needle

    for forbidden in (
        '"risk_accepted"',
        '"safe": true',
        '"safety_approved": true',
        '"certified": true',
        '"recommended_investment"',
        '"recommended_alternative"',
        '"optimal_investment"',
        '"true_risk"',
    ):
        assert forbidden not in core.lower(), forbidden

    print("Physical Lab Risk & Engineering Economics Layer wiring: PASS")
    print("- desktop bundle resources: PASS")
    print("- Evidence Center eighth-tab integration: PASS")
    print("- shared Project evidence-reference bridge: PASS")
    print("- explicit risk probability/consequence UI: PASS")
    print("- explicit cash-flow/discount-rate UI: PASS")
    print("- risk acceptance / safety / investment recommendation verdicts: intentionally absent")
    print("Boundary: declared-assumption decision support only; no calibrated risk forecast, safety approval, investment advice, economic superiority, or certification claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
