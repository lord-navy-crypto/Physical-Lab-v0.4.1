"""Project-local operations planning for Physical Lab.

The planner models declared tasks, precedence, release times, priorities, and
finite resource capacities. It simulates transparent dispatch policies and
reports queue/utilization metrics. It does not claim a globally optimal schedule.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import plain, utc_now

PLAN_SCHEMA = "physical-lab-operations-plan-v1"
INDEX_SCHEMA = "physical-lab-operations-plan-index-v1"
EVALUATION_SCHEMA = "physical-lab-operations-evaluation-v1"
PLAN_VERSION = 1
POLICIES = ("priority_fifo", "fifo", "shortest_processing_time")


def _sha(value: Any) -> str:
    raw = json.dumps(plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(plain(dict(value)), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _root(project_dir: Path) -> Path:
    path = project_dir / "provenance" / "operations-plans"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path(project_dir: Path) -> Path:
    return _root(project_dir) / "index.json"


def _load_index(project_dir: Path) -> dict[str, Any]:
    existing = _read_json(_index_path(project_dir))
    if existing and existing.get("schema") == INDEX_SCHEMA:
        return existing
    return {"schema": INDEX_SCHEMA, "plans": {}, "updated_at": None}


def _finite(value: Any, label: str, *, minimum: float | None = None) -> float:
    try:
        result = float(value)
    except Exception as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    if minimum is not None and result < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    return result


def _normalize_resources(resources: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in resources:
        resource_id = str(item.get("resource_id") or item.get("id") or "").strip()
        label = str(item.get("label") or resource_id).strip()
        if not resource_id or resource_id in seen:
            raise ValueError("resource ids must be non-empty and unique")
        try:
            capacity = int(item.get("capacity"))
        except Exception as exc:
            raise ValueError(f"{resource_id}.capacity must be an integer") from exc
        if capacity < 1:
            raise ValueError(f"{resource_id}.capacity must be >= 1")
        rows.append({"resource_id": resource_id, "label": label, "capacity": capacity})
        seen.add(resource_id)
    if not rows:
        raise ValueError("at least one resource is required")
    rows.sort(key=lambda row: row["resource_id"])
    return rows


def _normalize_tasks(tasks: list[Mapping[str, Any]], capacities: Mapping[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for order, item in enumerate(tasks):
        task_id = str(item.get("task_id") or item.get("id") or "").strip()
        label = str(item.get("label") or task_id).strip()
        if not task_id or task_id in seen:
            raise ValueError("task ids must be non-empty and unique")
        duration = _finite(item.get("duration"), f"{task_id}.duration", minimum=1e-12)
        release_time = _finite(item.get("release_time", 0.0), f"{task_id}.release_time", minimum=0.0)
        try:
            priority = int(item.get("priority", 0))
        except Exception as exc:
            raise ValueError(f"{task_id}.priority must be an integer") from exc
        raw_resources = item.get("resources") or {}
        if not isinstance(raw_resources, Mapping) or not raw_resources:
            raise ValueError(f"{task_id}.resources must contain at least one resource requirement")
        requirements: dict[str, int] = {}
        for resource_id, raw_units in raw_resources.items():
            resource_id = str(resource_id)
            if resource_id not in capacities:
                raise ValueError(f"{task_id} references unknown resource: {resource_id}")
            try:
                units = int(raw_units)
            except Exception as exc:
                raise ValueError(f"{task_id}.{resource_id} units must be an integer") from exc
            if units < 1 or units > capacities[resource_id]:
                raise ValueError(f"{task_id}.{resource_id} units must be between 1 and capacity {capacities[resource_id]}")
            requirements[resource_id] = units
        dependencies = sorted({str(value).strip() for value in item.get("dependencies") or [] if str(value).strip()})
        if task_id in dependencies:
            raise ValueError(f"{task_id} cannot depend on itself")
        rows.append({
            "task_id": task_id,
            "label": label,
            "duration": duration,
            "release_time": release_time,
            "priority": priority,
            "resources": dict(sorted(requirements.items())),
            "dependencies": dependencies,
            "input_order": order,
            "category": str(item.get("category") or "engineering-task").strip(),
        })
        seen.add(task_id)
    if not rows:
        raise ValueError("at least one task is required")
    ids = {row["task_id"] for row in rows}
    for row in rows:
        unknown = sorted(set(row["dependencies"]) - ids)
        if unknown:
            raise ValueError(f"{row['task_id']} has unknown dependencies: {', '.join(unknown)}")
    _assert_acyclic(rows)
    rows.sort(key=lambda row: row["task_id"])
    return rows


def _assert_acyclic(tasks: list[Mapping[str, Any]]) -> None:
    dependencies = {str(row["task_id"]): list(row.get("dependencies") or []) for row in tasks}
    state: dict[str, int] = {task_id: 0 for task_id in dependencies}

    def visit(task_id: str) -> None:
        if state[task_id] == 1:
            raise ValueError("task dependency graph contains a cycle")
        if state[task_id] == 2:
            return
        state[task_id] = 1
        for dependency in dependencies[task_id]:
            visit(str(dependency))
        state[task_id] = 2

    for task_id in sorted(dependencies):
        visit(task_id)


def register_operations_plan(
    project_dir: str | Path,
    *,
    name: str,
    resources: list[Mapping[str, Any]],
    tasks: list[Mapping[str, Any]],
    intended_use: str = "",
    time_unit: str = "h",
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    name = str(name).strip()
    if not name:
        raise ValueError("operations plan name is required")
    resource_rows = _normalize_resources(resources)
    capacities = {row["resource_id"]: int(row["capacity"]) for row in resource_rows}
    task_rows = _normalize_tasks(tasks, capacities)
    identity = {
        "project_id": project.get("project_id"),
        "name": name,
        "resources": resource_rows,
        "tasks": task_rows,
        "intended_use": str(intended_use).strip(),
        "time_unit": str(time_unit).strip() or "h",
    }
    plan_id = f"ops-{_sha(identity)[:20]}"
    now = utc_now()
    existing = _read_json(_root(path) / f"{plan_id}.json")
    stable = {
        "schema": PLAN_SCHEMA,
        "plan_version": PLAN_VERSION,
        "plan_id": plan_id,
        **identity,
    }
    record = {
        **stable,
        "plan_sha256": _sha(stable),
        "registered_at": str((existing or {}).get("registered_at") or now),
        "updated_at": now,
        "notes": str(notes),
        "boundary": (
            "This plan is a declared operational model. Durations, capacities, priorities and dependencies are user/project inputs. "
            "Dispatch simulations do not establish scientific validity or globally optimal scheduling."
        ),
    }
    _atomic_json(_root(path) / f"{plan_id}.json", record)
    index = _load_index(path)
    index.setdefault("plans", {})[plan_id] = {
        "plan_id": plan_id,
        "name": name,
        "plan_sha256": record["plan_sha256"],
        "path": f"provenance/operations-plans/{plan_id}.json",
        "updated_at": now,
    }
    index["updated_at"] = now
    _atomic_json(_index_path(path), index)
    return record


def get_operations_plan(project_dir: str | Path, plan_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    value = _read_json(_root(path) / f"{plan_id}.json")
    if not value or value.get("schema") != PLAN_SCHEMA:
        raise ValueError(f"unknown plan_id: {plan_id}")
    return value


def list_operations_plans(project_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    rows = [dict(value) for value in (_load_index(path).get("plans") or {}).values() if isinstance(value, Mapping)]
    rows.sort(key=lambda row: (str(row.get("updated_at") or ""), str(row.get("plan_id") or "")), reverse=True)
    return rows


def _policy_key(task: Mapping[str, Any], policy: str) -> tuple[Any, ...]:
    if policy == "priority_fifo":
        return (-int(task.get("priority") or 0), float(task.get("release_time") or 0.0), int(task.get("input_order") or 0), str(task.get("task_id")))
    if policy == "shortest_processing_time":
        return (float(task.get("duration") or 0.0), -int(task.get("priority") or 0), float(task.get("release_time") or 0.0), int(task.get("input_order") or 0), str(task.get("task_id")))
    return (float(task.get("release_time") or 0.0), int(task.get("input_order") or 0), str(task.get("task_id")))


def evaluate_operations_plan(project_dir: str | Path, plan_id: str, *, policy: str = "priority_fifo") -> dict[str, Any]:
    if policy not in POLICIES:
        raise ValueError(f"policy must be one of {POLICIES}")
    path = Path(project_dir).expanduser().resolve()
    plan = get_operations_plan(path, plan_id)
    tasks = {str(row["task_id"]): dict(row) for row in plan.get("tasks") or []}
    capacities = {str(row["resource_id"]): int(row["capacity"]) for row in plan.get("resources") or []}
    available = dict(capacities)
    unscheduled = set(tasks)
    active: list[dict[str, Any]] = []
    completed: dict[str, float] = {}
    schedule: list[dict[str, Any]] = []
    busy = {resource_id: 0.0 for resource_id in capacities}
    time = 0.0
    eps = 1e-12

    while unscheduled or active:
        finished = [row for row in active if float(row["finish_time"]) <= time + eps]
        if finished:
            for row in finished:
                task_id = str(row["task_id"])
                completed[task_id] = float(row["finish_time"])
                for resource_id, units in row["resources"].items():
                    available[resource_id] += int(units)
            active = [row for row in active if float(row["finish_time"]) > time + eps]

        candidates = []
        for task_id in unscheduled:
            task = tasks[task_id]
            if float(task["release_time"]) > time + eps:
                continue
            if not all(dep in completed for dep in task["dependencies"]):
                continue
            candidates.append(task)
        candidates.sort(key=lambda task: _policy_key(task, policy))

        started = False
        for task in candidates:
            if not all(available[resource_id] >= int(units) for resource_id, units in task["resources"].items()):
                continue
            task_id = str(task["task_id"])
            dependency_ready = max([completed[dep] for dep in task["dependencies"]] or [0.0])
            eligible_time = max(float(task["release_time"]), dependency_ready)
            start_time = time
            finish_time = start_time + float(task["duration"])
            for resource_id, units in task["resources"].items():
                available[resource_id] -= int(units)
                busy[resource_id] += int(units) * float(task["duration"])
            row = {
                "task_id": task_id,
                "label": task.get("label"),
                "category": task.get("category"),
                "priority": task.get("priority"),
                "release_time": task.get("release_time"),
                "eligible_time": eligible_time,
                "start_time": start_time,
                "finish_time": finish_time,
                "waiting_time": max(0.0, start_time - eligible_time),
                "flow_time": finish_time - float(task["release_time"]),
                "duration": task.get("duration"),
                "resources": plain(task.get("resources") or {}),
                "dependencies": list(task.get("dependencies") or []),
            }
            schedule.append(row)
            active.append({"task_id": task_id, "finish_time": finish_time, "resources": dict(task["resources"])})
            unscheduled.remove(task_id)
            started = True

        if not unscheduled and not active:
            break
        if started:
            continue

        events: list[float] = [float(row["finish_time"]) for row in active if float(row["finish_time"]) > time + eps]
        for task_id in unscheduled:
            task = tasks[task_id]
            if all(dep in completed for dep in task["dependencies"]):
                release_time = float(task["release_time"])
                if release_time > time + eps:
                    events.append(release_time)
        if not events:
            raise RuntimeError("operations simulation cannot advance; check task/resource declarations")
        time = min(events)

    schedule.sort(key=lambda row: (float(row["start_time"]), float(row["finish_time"]), str(row["task_id"])))
    makespan = max((float(row["finish_time"]) for row in schedule), default=0.0)
    total_wait = sum(float(row["waiting_time"]) for row in schedule)
    total_flow = sum(float(row["flow_time"]) for row in schedule)
    utilization = {
        resource_id: (busy[resource_id] / (makespan * capacity) if makespan > 0 else 0.0)
        for resource_id, capacity in capacities.items()
    }
    stable = {
        "schema": EVALUATION_SCHEMA,
        "plan_id": plan_id,
        "plan_sha256": plan.get("plan_sha256"),
        "policy": policy,
        "schedule": schedule,
        "metrics": {
            "task_count": len(schedule),
            "makespan": makespan,
            "total_waiting_time": total_wait,
            "average_waiting_time": total_wait / len(schedule) if schedule else 0.0,
            "average_flow_time": total_flow / len(schedule) if schedule else 0.0,
            "resource_utilization": utilization,
        },
    }
    return {
        **stable,
        "evaluation_sha256": _sha(stable),
        "time_unit": plan.get("time_unit"),
        "boundary": (
            "Metrics describe this declared non-preemptive dispatch simulation. A lower waiting time or makespan under one tested policy "
            "does not prove global optimality or superiority under unmodeled constraints, uncertainty, failures, or human factors."
        ),
    }


def compare_dispatch_policies(project_dir: str | Path, plan_id: str) -> dict[str, Any]:
    evaluations = [evaluate_operations_plan(project_dir, plan_id, policy=policy) for policy in POLICIES]
    rows = [
        {
            "policy": item["policy"],
            "makespan": item["metrics"]["makespan"],
            "average_waiting_time": item["metrics"]["average_waiting_time"],
            "average_flow_time": item["metrics"]["average_flow_time"],
            "resource_utilization": item["metrics"]["resource_utilization"],
            "evaluation_sha256": item["evaluation_sha256"],
        }
        for item in evaluations
    ]
    stable = {"schema": "physical-lab-dispatch-policy-comparison-v1", "plan_id": plan_id, "policies": rows}
    return {
        **stable,
        "comparison_sha256": _sha(stable),
        "boundary": "Policy comparison reports modeled outcomes only. Physical Lab does not automatically recommend or certify a dispatch policy.",
    }
