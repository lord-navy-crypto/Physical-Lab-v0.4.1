#!/usr/bin/env python3
"""Static wiring checks for Physical Lab Requirements & Traceability Layer v1."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"


def main() -> int:
    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    for resource in (
        "resources/ui/physical_lab_requirements.py",
        "resources/ui/physical_lab_requirements_ui.py",
        "resources/ui/physical_lab_evidence_center_ui.py",
    ):
        assert resource in resources, resource

    core = (UI / "physical_lab_requirements.py").read_text(encoding="utf-8")
    req_ui = (UI / "physical_lab_requirements_ui.py").read_text(encoding="utf-8")
    evidence_ui = (UI / "physical_lab_evidence_center_ui.py").read_text(encoding="utf-8")

    for needle in (
        "register_requirement",
        "evaluate_requirement",
        "traceability_matrix",
        "requirement_key",
        "verification_method",
        "verification_criteria",
        "engineering_links",
        "parent_requirement_ids",
        "READY_FOR_REVIEW",
        "UNPLANNED",
        "EVIDENCE_MISSING",
        "LINK_MISSING",
        "STALE",
    ):
        assert needle in core, needle

    for link_kind in (
        "claim",
        "cross-check",
        "decision-study",
        "operations-plan",
        "quality-study",
        "reliability-study",
        "risk-study",
        "economics-study",
    ):
        assert f'"{link_kind}"' in core, link_kind

    for needle in (
        "Register requirement",
        "Parent requirements",
        "Planned verification method",
        "Explicit Project evidence",
        "Engineering-record links",
        "READY_FOR_REVIEW",
        "does not automatically mark requirements VERIFIED",
    ):
        assert needle in req_ui, needle

    for needle in (
        '"Requirements"',
        "physical_lab_requirements_ui",
        "render_requirements_tab(st, path, profile, refs)",
        "_artifact_refs(path, doc)",
        "machine requirement verification",
    ):
        assert needle in evidence_ui, needle

    forbidden_phrases = (
        '"verified": true',
        '"validated": true',
        '"compliant": true',
        '"accepted": true',
        '"safe": true',
        '"certified": true',
        '"verification_verdict"',
        '"validation_verdict"',
    )
    lower = core.lower()
    for forbidden in forbidden_phrases:
        assert forbidden not in lower, forbidden

    print("Physical Lab Requirements & Traceability Layer wiring: PASS")
    print("- desktop bundle resources: PASS")
    print("- Evidence Center ninth-tab integration: PASS")
    print("- parent/child flowdown surface: PASS")
    print("- raw evidence + eight engineering-link kinds: PASS")
    print("- verification method/criteria planning UI: PASS")
    print("- VERIFIED / VALIDATED / compliance / safety verdicts: intentionally absent")
    print("Boundary: requirements readiness/traceability only; no machine verification, validation, compliance, acceptance, safety, or certification decision.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
