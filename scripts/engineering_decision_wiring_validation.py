#!/usr/bin/env python3
"""Static wiring checks for the shared Engineering Decision Center."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"


def main() -> int:
    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    for resource in (
        "resources/ui/physical_lab_engineering_decisions.py",
        "resources/ui/physical_lab_engineering_decision_ui.py",
        "resources/ui/physical_lab_evidence_center_patch.py",
        "resources/ui/physical_lab_evidence_center_ui.py",
    ):
        assert resource in resources, resource

    core = (UI / "physical_lab_engineering_decisions.py").read_text(encoding="utf-8")
    decision_ui = (UI / "physical_lab_engineering_decision_ui.py").read_text(encoding="utf-8")
    evidence_ui = (UI / "physical_lab_evidence_center_ui.py").read_text(encoding="utf-8")
    patch = (UI / "physical_lab_evidence_center_patch.py").read_text(encoding="utf-8")

    for needle in (
        "register_decision_study",
        "evaluate_decision_study",
        "record_human_decision",
        "pareto_frontier",
        "EVIDENCE_MISSING",
        "STALE",
        "INFEASIBLE",
        "FEASIBLE",
    ):
        assert needle in core, needle

    for needle in (
        "Register engineering trade study",
        "Review trade study",
        "Record human decision",
        "Pareto nondominated",
        "register_decision_study",
        "record_human_decision",
    ):
        assert needle in decision_ui, needle

    for needle in (
        '"Engineering Decisions"',
        "physical_lab_engineering_decision_ui",
        "render_engineering_decision_tab(st, path, profile, refs)",
        "_artifact_refs(path, doc)",
        "No aggregate credibility score or machine truth/design verdict",
    ):
        assert needle in evidence_ui, needle

    for needle in (
        "ACTIVE_PROJECT_SESSION_KEY",
        "Create new project",
        "render_evidence_center",
    ):
        assert needle in patch, needle
    assert "render_engineering_decision_tab" not in patch
    assert "physical_lab_engineering_decision_ui" not in patch
    assert "Selection remains a human engineering judgment" in decision_ui

    print("Physical Lab Engineering Decision Center wiring: PASS")
    print("- desktop bundle resources: PASS")
    print("- shared active Project surface: PASS")
    print("- Evidence Center fifth-tab integration: PASS")
    print("- evidence-reference bridge: PASS")
    print("- trade-study registration/review UI: PASS")
    print("- human decision rationale UI: PASS")
    print("Boundary: wiring adds decision support only; it does not create a second project state, credibility score, or machine engineering verdict.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
