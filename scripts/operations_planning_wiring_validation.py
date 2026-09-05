#!/usr/bin/env python3
"""Static wiring checks for Physical Lab Operations Layer v1."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"


def main() -> int:
    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    for resource in (
        "resources/ui/physical_lab_operations_planning.py",
        "resources/ui/physical_lab_operations_ui.py",
        "resources/ui/physical_lab_evidence_center_ui.py",
    ):
        assert resource in resources, resource

    core = (UI / "physical_lab_operations_planning.py").read_text(encoding="utf-8")
    ops_ui = (UI / "physical_lab_operations_ui.py").read_text(encoding="utf-8")
    evidence_ui = (UI / "physical_lab_evidence_center_ui.py").read_text(encoding="utf-8")

    for needle in (
        "register_operations_plan",
        "evaluate_operations_plan",
        "compare_dispatch_policies",
        "priority_fifo",
        "shortest_processing_time",
        "resource_utilization",
        "average_waiting_time",
        "makespan",
        "task dependency graph contains a cycle",
    ):
        assert needle in core, needle

    for needle in (
        "Register operations plan",
        "Review operations plan",
        "Dispatch policy comparison",
        "Average queue wait",
        "globally optimal schedule",
    ):
        assert needle in ops_ui, needle

    for needle in (
        '"Operations"',
        "physical_lab_operations_ui",
        "render_operations_tab(st, path, profile)",
        "Engineering Decisions",
        "Snapshots & Diff",
    ):
        assert needle in evidence_ui, needle

    assert "globally optimal schedule" in evidence_ui
    assert "recommended_policy" not in core
    assert "optimal_policy" not in core

    print("Physical Lab Operations Layer wiring: PASS")
    print("- desktop bundle resources: PASS")
    print("- Evidence Center sixth-tab integration: PASS")
    print("- resource/task registration UI: PASS")
    print("- schedule/utilization/policy comparison UI: PASS")
    print("- machine dispatch recommendation: intentionally absent")
    print("Boundary: operations planning models declared resources and queue policies only; it does not establish global optimality, scientific validity, safety approval, or certification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
