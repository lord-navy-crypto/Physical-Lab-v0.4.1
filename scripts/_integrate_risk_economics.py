#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one integration anchor in {path}: found {count}\nANCHOR:\n{old}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    evidence = ROOT / "src-tauri/resources/ui/physical_lab_evidence_center_ui.py"
    replace_once(
        evidence,
        "    import physical_lab_quality_reliability_ui as quality_reliability_ui\n",
        "    import physical_lab_quality_reliability_ui as quality_reliability_ui\n    import physical_lab_risk_economics_ui as risk_economics_ui\n",
    )
    replace_once(
        evidence,
        '            "Evidence-first review across the active .physlab project. Passport, claims, cross-checks, engineering decisions, operations plans, quality/reliability studies, snapshots and diffs "\n            "use the same deterministic project state. No aggregate credibility score, machine truth verdict, design verdict, globally optimal schedule, process qualification, or certification verdict is produced."\n',
        '            "Evidence-first review across the active .physlab project. Passport, claims, cross-checks, engineering decisions, operations plans, quality/reliability studies, risk/economics studies, snapshots and diffs "\n            "use the same deterministic project state. No aggregate credibility score, machine truth verdict, design verdict, globally optimal schedule, process qualification, risk acceptance, investment recommendation, or certification verdict is produced."\n',
    )
    replace_once(
        evidence,
        '        passport_tab, claims_tab, cross_tab, decision_tab, operations_tab, quality_tab, diff_tab = st.tabs([\n            "Credibility Passport", "Claims", "Cross-Checks", "Engineering Decisions", "Operations", "Quality & Reliability", "Snapshots & Diff"\n        ])\n',
        '        passport_tab, claims_tab, cross_tab, decision_tab, operations_tab, quality_tab, risk_economics_tab, diff_tab = st.tabs([\n            "Credibility Passport", "Claims", "Cross-Checks", "Engineering Decisions", "Operations", "Quality & Reliability", "Risk & Economics", "Snapshots & Diff"\n        ])\n',
    )
    replace_once(
        evidence,
        '        with quality_tab:\n            quality_reliability_ui.render_quality_reliability_tab(st, path, profile, refs)\n\n        with diff_tab:\n',
        '        with quality_tab:\n            quality_reliability_ui.render_quality_reliability_tab(st, path, profile, refs)\n\n        with risk_economics_tab:\n            risk_economics_ui.render_risk_economics_tab(st, path, profile, refs)\n\n        with diff_tab:\n',
    )

    tauri = ROOT / "src-tauri/tauri.conf.json"
    replace_once(
        tauri,
        '      "resources/ui/physical_lab_quality_reliability_ui.py": "ui/physical_lab_quality_reliability_ui.py",\n      "resources/ui/physical_lab_units.py": "ui/physical_lab_units.py",\n',
        '      "resources/ui/physical_lab_quality_reliability_ui.py": "ui/physical_lab_quality_reliability_ui.py",\n      "resources/ui/physical_lab_risk_economics.py": "ui/physical_lab_risk_economics.py",\n      "resources/ui/physical_lab_risk_economics_ui.py": "ui/physical_lab_risk_economics_ui.py",\n      "resources/ui/physical_lab_units.py": "ui/physical_lab_units.py",\n',
    )

    print("Risk & Economics guarded integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
