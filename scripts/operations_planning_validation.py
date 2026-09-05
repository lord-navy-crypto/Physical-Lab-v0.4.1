#!/usr/bin/env python3
"""Deterministic acceptance checks for Physical Lab Operations Layer v1."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_operations_planning as operations
import physical_lab_project_kernel as projects


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="physical-lab-operations-") as temp:
        root = Path(temp).resolve()
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)
        project_dir, _ = projects.create_project(
            "Operations Planning Validation",
            research_question="How do explicit resource capacity, precedence and dispatch rules change queue and schedule metrics?",
        )

        plan = operations.register_operations_plan(
            project_dir,
            name="Single solver with downstream review",
            time_unit="h",
            resources=[
                {"resource_id": "solver", "label": "Compute / solver slot", "capacity": 1},
                {"resource_id": "reviewer", "label": "Engineering review slot", "capacity": 1},
            ],
            tasks=[
                {"task_id": "A", "label": "High-priority long solve", "duration": 4.0, "priority": 3, "resources": {"solver": 1}},
                {"task_id": "B", "label": "Short independent solve", "duration": 1.0, "priority": 1, "resources": {"solver": 1}},
                {"task_id": "C", "label": "Medium prerequisite solve", "duration": 2.0, "priority": 2, "resources": {"solver": 1}},
                {"task_id": "D", "label": "Human engineering review", "duration": 1.0, "priority": 2, "resources": {"reviewer": 1}, "dependencies": ["A", "C"]},
            ],
            intended_use="deterministic queue/resource fixture",
        )
        assert plan["plan_id"].startswith("ops-")
        assert len(plan["plan_sha256"]) == 64

        priority = operations.evaluate_operations_plan(project_dir, plan["plan_id"], policy="priority_fifo")
        fifo = operations.evaluate_operations_plan(project_dir, plan["plan_id"], policy="fifo")
        spt = operations.evaluate_operations_plan(project_dir, plan["plan_id"], policy="shortest_processing_time")

        priority_order = [row["task_id"] for row in priority["schedule"]]
        fifo_order = [row["task_id"] for row in fifo["schedule"]]
        spt_order = [row["task_id"] for row in spt["schedule"]]
        assert priority_order == ["A", "C", "B", "D"], priority_order
        assert fifo_order == ["A", "B", "C", "D"], fifo_order
        assert spt_order == ["B", "C", "A", "D"], spt_order

        assert priority["metrics"]["makespan"] == 7.0
        assert fifo["metrics"]["makespan"] == 8.0
        assert spt["metrics"]["makespan"] == 8.0
        assert abs(priority["metrics"]["average_waiting_time"] - 2.5) < 1e-12
        assert abs(fifo["metrics"]["average_waiting_time"] - 2.25) < 1e-12
        assert abs(spt["metrics"]["average_waiting_time"] - 1.0) < 1e-12
        assert abs(priority["metrics"]["resource_utilization"]["solver"] - 1.0) < 1e-12
        assert abs(spt["metrics"]["resource_utilization"]["solver"] - 0.875) < 1e-12

        review_priority = next(row for row in priority["schedule"] if row["task_id"] == "D")
        assert review_priority["eligible_time"] == 6.0
        assert review_priority["start_time"] == 6.0
        assert review_priority["waiting_time"] == 0.0

        comparison = operations.compare_dispatch_policies(project_dir, plan["plan_id"])
        rows = {row["policy"]: row for row in comparison["policies"]}
        assert rows["priority_fifo"]["makespan"] < rows["shortest_processing_time"]["makespan"]
        assert rows["shortest_processing_time"]["average_waiting_time"] < rows["priority_fifo"]["average_waiting_time"]
        assert len(comparison["comparison_sha256"]) == 64

        encoded = json.dumps({"plan": plan, "priority": priority, "fifo": fifo, "spt": spt, "comparison": comparison}).lower()
        for forbidden in (
            '"recommended_policy"',
            '"optimal_policy"',
            '"globally_optimal": true',
            '"certified": true',
            '"truth_status"',
        ):
            assert forbidden not in encoded, forbidden

        try:
            operations.register_operations_plan(
                project_dir,
                name="Cycle rejection",
                resources=[{"resource_id": "solver", "capacity": 1}],
                tasks=[
                    {"task_id": "X", "duration": 1, "resources": {"solver": 1}, "dependencies": ["Y"]},
                    {"task_id": "Y", "duration": 1, "resources": {"solver": 1}, "dependencies": ["X"]},
                ],
            )
        except ValueError as exc:
            assert "cycle" in str(exc).lower()
        else:
            raise AssertionError("cyclic task dependencies must be rejected")

        try:
            operations.register_operations_plan(
                project_dir,
                name="Capacity rejection",
                resources=[{"resource_id": "solver", "capacity": 1}],
                tasks=[{"task_id": "X", "duration": 1, "resources": {"solver": 2}}],
            )
        except ValueError as exc:
            assert "capacity" in str(exc).lower()
        else:
            raise AssertionError("resource requirements above capacity must be rejected")

        print("Physical Lab Operations Layer v1 validation: PASS")
        print("- finite resource capacity + non-preemptive scheduling: PASS")
        print("- precedence / eligible-time semantics: PASS")
        print("- priority FIFO / FIFO / SPT dispatch policies: PASS")
        print("- waiting, flow, utilization and makespan metrics: PASS")
        print("- policy trade-off with no auto-recommendation: PASS")
        print("- cyclic dependency and over-capacity guards: PASS")
        print("Boundary: dispatch results describe declared operational assumptions only; no global optimality, scientific validation, safety approval, or certification claim.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
