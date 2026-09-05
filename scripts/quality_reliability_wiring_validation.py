#!/usr/bin/env python3
"""Static wiring checks for Physical Lab Quality & Reliability Layer v1."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"


def main() -> int:
    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    for resource in (
        "resources/ui/physical_lab_quality_reliability.py",
        "resources/ui/physical_lab_quality_reliability_ui.py",
        "resources/ui/physical_lab_evidence_center_ui.py",
    ):
        assert resource in resources, resource

    core = (UI / "physical_lab_quality_reliability.py").read_text(encoding="utf-8")
    qr_ui = (UI / "physical_lab_quality_reliability_ui.py").read_text(encoding="utf-8")
    evidence_ui = (UI / "physical_lab_evidence_center_ui.py").read_text(encoding="utf-8")

    for needle in (
        "register_quality_study",
        "evaluate_quality_study",
        "register_reliability_study",
        "evaluate_reliability_study",
        "pooled_repeatability_std",
        "descriptive_two_level_contrast",
        "observed_event_fraction",
        "observed_event_rate_per_exposure",
        "EVIDENCE_MISSING",
        "STALE",
    ):
        assert needle in core, needle

    for needle in (
        "Register quality / DOE evidence study",
        "Register reliability event study",
        "Pooled repeatability std",
        "observed event rate/exposure",
        "No Cp/Cpk, MTBF",
        "render_quality_reliability_tab",
    ):
        assert needle in qr_ui, needle

    for needle in (
        '"Quality & Reliability"',
        "physical_lab_quality_reliability_ui",
        "render_quality_reliability_tab(st, path, profile, refs)",
        "_artifact_refs(path, doc)",
        "process qualification",
        "certification verdict",
    ):
        assert needle in evidence_ui, needle

    for forbidden in (
        '"process_capability"',
        '"mtbf"',
        '"reliability_function"',
        '"certified": true',
        '"safety_approved": true',
        '"production_qualified": true',
    ):
        assert forbidden not in core.lower(), forbidden

    print("Physical Lab Quality & Reliability Layer wiring: PASS")
    print("- desktop bundle resources: PASS")
    print("- Evidence Center seventh-tab integration: PASS")
    print("- shared Project evidence-reference bridge: PASS")
    print("- quality/DOE registration and review UI: PASS")
    print("- reliability event/exposure registration and review UI: PASS")
    print("- Cp/Cpk, MTBF and qualification verdicts: intentionally absent")
    print("Boundary: descriptive quality/reliability evidence only; no process capability, field reliability, safety approval, certification, or production qualification claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
