#!/usr/bin/env python3
"""Static wiring checks for Physical Lab Requirements & Verification Planning v1."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"


def main() -> int:
    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    for resource in (
        "resources/ui/physical_lab_requirements_verification.py",
        "resources/ui/physical_lab_requirements_verification_ui.py",
        "resources/ui/physical_lab_evidence_center_ui.py",
    ):
        assert resource in resources, resource

    core = (UI / "physical_lab_requirements_verification.py").read_text(encoding="utf-8")
    req_ui = (UI / "physical_lab_requirements_verification_ui.py").read_text(encoding="utf-8")
    evidence_ui = (UI / "physical_lab_evidence_center_ui.py").read_text(encoding="utf-8")

    for needle in (
        "register_requirement",
        "evaluate_requirement",
        "record_requirement_review",
        "requirements_verification_matrix",
        'VERIFICATION_METHODS = ("test", "analysis", "inspection", "demonstration")',
        "READY_FOR_REVIEW",
        "STALE",
        "EVIDENCE_MISSING",
        "upstream_requirement_ids",
        "success_criteria",
    ):
        assert needle in core, needle

    for needle in (
        "Register requirement / verification plan",
        "Review requirement / verification plan",
        "Record human requirement review",
        "Normative requirement statement",
        "Verification method",
        "Declared upstream trace IDs",
        "READY_FOR_REVIEW means evidence is present and current",
    ):
        assert needle in req_ui, needle

    for needle in (
        '"Requirements & Verification"',
        "physical_lab_requirements_verification_ui",
        "render_requirements_verification_tab(st, path, profile, refs)",
        '"Risk & Economics"',
        '"Quality & Reliability"',
        '"Engineering Decisions"',
    ):
        assert needle in evidence_ui, needle

    encoded = (core + "\n" + req_ui + "\n" + evidence_ui).lower()
    for forbidden in (
        '"verified": true',
        '"compliant": true',
        '"certified": true',
        '"safe": true',
        '"validation_passed": true',
        '"requirement_pass": true',
        '"automatic_acceptance": true',
    ):
        assert forbidden not in encoded, forbidden

    print("Physical Lab Requirements & Verification Planning wiring: PASS")
    print("- desktop bundle resources: PASS")
    print("- Evidence Center ninth-tab integration: PASS")
    print("- shared Project evidence-reference bridge: PASS")
    print("- shall/source/upstream trace planning UI: PASS")
    print("- test/analysis/inspection/demonstration method UI: PASS")
    print("- human evidence-sufficiency review UI: PASS")
    print("- automatic verification/compliance/certification verdicts: intentionally absent")
    print("Boundary: verification planning and evidence readiness only; no formal verification, validation, acceptance, safety approval, standards compliance, qualification, or certification claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
