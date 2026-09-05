#!/usr/bin/env python3
"""Release-readiness contract for the Physical Lab v0.10 engineering-systems milestone.

This validator intentionally runs while the source version is still 0.9.0. A later
release PR may bump version metadata only after this contract and the full Source
Integrity suite are green.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"

ENGINEERING_LAYERS = (
    ("Engineering Decisions", "physical_lab_engineering_decisions.py", "physical_lab_engineering_decision_ui.py"),
    ("Operations", "physical_lab_operations_planning.py", "physical_lab_operations_ui.py"),
    ("Quality & Reliability", "physical_lab_quality_reliability.py", "physical_lab_quality_reliability_ui.py"),
    ("Risk & Economics", "physical_lab_risk_economics.py", "physical_lab_risk_economics_ui.py"),
    ("Requirements & Verification", "physical_lab_requirements_verification.py", "physical_lab_requirements_verification_ui.py"),
)


def main() -> int:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert version in {"0.9.0", "0.10.0"}, f"unexpected v0.10 milestone version: {version}"

    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    evidence_ui = (UI / "physical_lab_evidence_center_ui.py").read_text(encoding="utf-8")
    self_check = (ROOT / "scripts" / "self_check.py").read_text(encoding="utf-8")
    source_integrity = (ROOT / ".github" / "workflows" / "source-integrity.yml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    expected_tabs = (
        "Credibility Passport",
        "Claims",
        "Cross-Checks",
        "Engineering Decisions",
        "Operations",
        "Quality & Reliability",
        "Risk & Economics",
        "Requirements & Verification",
        "Snapshots & Diff",
    )
    for tab in expected_tabs:
        assert f'"{tab}"' in evidence_ui, tab

    for tab, core_name, ui_name in ENGINEERING_LAYERS:
        for filename in (core_name, ui_name):
            path = UI / filename
            assert path.is_file(), filename
            resource = f"resources/ui/{filename}"
            assert resource in resources, resource
            assert filename in self_check, f"self_check missing {filename}"
        assert tab in self_check, f"self_check missing tab {tab}"

    validation_scripts = (
        "engineering_decision_validation.py",
        "operations_planning_validation.py",
        "quality_reliability_validation.py",
        "risk_economics_validation.py",
        "requirements_verification_validation.py",
        "v010_release_readiness_validation.py",
    )
    for script in validation_scripts:
        assert script in source_integrity, f"Source Integrity missing {script}"

    forbidden_paths = (
        UI / "physical_lab_workspace_aliases.py",
        ROOT / "scripts" / "_integrate_risk_economics.py",
        ROOT / "scripts" / "_integrate_requirements_verification.py",
    )
    for path in forbidden_paths:
        assert not path.exists(), f"temporary/retired path must be absent: {path.relative_to(ROOT)}"
    assert not list((ROOT / ".github" / "workflows").glob("integrate-*.yml")), "temporary integration workflow remains tracked"

    research = (ROOT / "src-tauri" / "src" / "research.rs").read_text(encoding="utf-8")
    # Documentation/comments may name the frozen compatibility fixture. Runtime
    # separation is structural: the facade must not compile or call it.
    assert '#[path = "research_legacy_impl.rs"]' not in research
    assert 'mod legacy;' not in research
    assert 'legacy::' not in research
    assert 'ensure_alias_for_id' not in research

    for marker in (
        "Evidence-First Engineering Systems Workbench",
        "Engineering Decisions",
        "Operations",
        "Quality & Reliability",
        "Risk & Economics",
        "Requirements & Verification",
    ):
        assert marker in readme, f"README missing release architecture marker: {marker}"

    assert "## [Unreleased]" in changelog
    if version == "0.10.0":
        assert "## [0.10.0] - 2026-09-05" in changelog
        first_line = readme.splitlines()[0] if readme.splitlines() else ""
        assert "Physical Lab v0.10.0" in first_line
        assert "No unreleased changes." in changelog
    else:
        assert "## [0.10.0] - 2026-09-05" not in changelog
    for marker in (
        "Evidence-First Engineering Systems",
        "Engineering Decision Layer",
        "Operations Layer",
        "Quality & Reliability Layer",
        "Risk & Engineering Economics Layer",
        "Requirements & Verification Planning",
        "canonical `projects/*.physlab`",
    ):
        assert marker in changelog, f"CHANGELOG missing release marker: {marker}"

    print("Physical Lab v0.10 release-readiness contract: PASS")
    print(f"- v0.10 milestone release state ({version}): PASS")
    print("- nine Evidence Center tabs: PASS")
    print("- five engineering-systems layers packaged + self-checked: PASS")
    print("- canonical project store / alias retirement boundary: PASS")
    print("- frozen legacy fixture excluded from active Rust runtime: PASS")
    print("- temporary integration artifacts absent: PASS")
    print("- README / CHANGELOG reflect actual engineering architecture: PASS")
    print("Boundary: release readiness validates packaging/documentation/contracts; it does not create scientific, safety, standards-compliance, accreditation, or certification claims.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
