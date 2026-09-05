"""Shared Streamlit UI for Physical Lab Operations Layer v1."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _deps(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item.strip()]


def render_operations_tab(st: Any, project_path: str | Path, profile: str) -> None:
    import physical_lab_operations_planning as operations

    path = Path(project_path).expanduser().resolve()
    plans = operations.list_operations_plans(path)
    if plans:
        st.dataframe([
            {
                "Plan": row.get("name"),
                "Plan id": row.get("plan_id"),
                "Updated": row.get("updated_at"),
            }
            for row in plans
        ], width="stretch", hide_index=True)
    else:
        st.info("No operations plans registered yet.")

    with st.expander("Register operations plan", expanded=False):
        st.caption(
            "Model declared engineering work as non-preemptive tasks competing for finite solver, instrument, review, or other resources. "
            "The planner simulates transparent dispatch rules; it does not claim a globally optimal schedule."
        )
        name = st.text_input("Plan name", value=f"{profile} operations plan", key=f"pl_ops_name_{profile}")
        intended = st.text_input("Intended use", key=f"pl_ops_use_{profile}")
        time_unit = st.text_input("Time unit", value="h", key=f"pl_ops_unit_{profile}")

        st.markdown("#### Resources")
        r1a, r1b, r1c = st.columns([1, 2, 1])
        r1_id = r1a.text_input("Resource 1 id", value="solver", key=f"pl_ops_r1_id_{profile}")
        r1_label = r1b.text_input("Resource 1 label", value="Solver / compute slot", key=f"pl_ops_r1_label_{profile}")
        r1_capacity = r1c.number_input("Resource 1 capacity", min_value=1, value=1, step=1, key=f"pl_ops_r1_capacity_{profile}")
        r2a, r2b, r2c = st.columns([1, 2, 1])
        r2_id = r2a.text_input("Resource 2 id", value="reviewer", key=f"pl_ops_r2_id_{profile}")
        r2_label = r2b.text_input("Resource 2 label", value="Engineering review slot", key=f"pl_ops_r2_label_{profile}")
        r2_capacity = r2c.number_input("Resource 2 capacity", min_value=1, value=1, step=1, key=f"pl_ops_r2_capacity_{profile}")

        resource_ids = [value.strip() for value in (r1_id, r2_id) if value.strip()]
        st.markdown("#### Tasks")
        task_rows = []
        defaults = (
            ("A", "Primary simulation", 4.0, 3, "solver", ""),
            ("B", "Independent simulation", 1.0, 1, "solver", ""),
            ("C", "Supporting simulation", 2.0, 2, "solver", ""),
            ("D", "Engineering review", 1.0, 2, "reviewer", "A,C"),
        )
        for index, (default_id, default_label, default_duration, default_priority, default_resource, default_deps) in enumerate(defaults, start=1):
            st.markdown(f"**Task {index}**")
            a, b, c, d = st.columns([1, 2, 1, 1])
            task_id = a.text_input("Task id", value=default_id, key=f"pl_ops_task_id_{index}_{profile}")
            label = b.text_input("Task label", value=default_label, key=f"pl_ops_task_label_{index}_{profile}")
            duration = c.number_input("Duration", min_value=0.000001, value=default_duration, format="%.6g", key=f"pl_ops_task_duration_{index}_{profile}")
            priority = d.number_input("Priority", value=default_priority, step=1, key=f"pl_ops_task_priority_{index}_{profile}")
            a, b, c = st.columns([1, 1, 2])
            default_index = resource_ids.index(default_resource) if default_resource in resource_ids else 0
            resource_id = a.selectbox("Resource", resource_ids or ["resource"], index=default_index, key=f"pl_ops_task_resource_{index}_{profile}")
            release = b.number_input("Release time", min_value=0.0, value=0.0, format="%.6g", key=f"pl_ops_task_release_{index}_{profile}")
            dependencies = c.text_input("Dependencies (comma-separated task ids)", value=default_deps, key=f"pl_ops_task_deps_{index}_{profile}")
            task_rows.append({
                "task_id": task_id.strip(),
                "label": label.strip(),
                "duration": duration,
                "priority": int(priority),
                "release_time": release,
                "resources": {resource_id: 1},
                "dependencies": _deps(dependencies),
            })

        if st.button("Register operations plan", type="primary", key=f"pl_ops_register_{profile}"):
            resources = []
            if r1_id.strip():
                resources.append({"resource_id": r1_id.strip(), "label": r1_label, "capacity": int(r1_capacity)})
            if r2_id.strip():
                resources.append({"resource_id": r2_id.strip(), "label": r2_label, "capacity": int(r2_capacity)})
            tasks = [row for row in task_rows if row["task_id"]]
            try:
                record = operations.register_operations_plan(
                    path,
                    name=name,
                    resources=resources,
                    tasks=tasks,
                    intended_use=intended,
                    time_unit=time_unit,
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success(f"Registered operations plan `{record['plan_id']}`")
                st.rerun()

    plans = operations.list_operations_plans(path)
    if plans:
        st.markdown("#### Review operations plan")
        options = {f"{row.get('name')} · {row.get('plan_id')}": str(row.get("plan_id")) for row in plans}
        selected_label = st.selectbox("Operations plan", list(options), key=f"pl_ops_select_{profile}")
        plan_id = options[selected_label]
        policy = st.selectbox(
            "Dispatch policy",
            list(operations.POLICIES),
            format_func=lambda value: {
                "priority_fifo": "Priority → FIFO",
                "fifo": "FIFO",
                "shortest_processing_time": "Shortest processing time",
            }.get(value, value),
            key=f"pl_ops_policy_{profile}",
        )
        evaluation = operations.evaluate_operations_plan(path, plan_id, policy=policy)
        metrics = evaluation.get("metrics") or {}
        a, b, c = st.columns(3)
        a.metric("Makespan", f"{float(metrics.get('makespan') or 0):.6g} {evaluation.get('time_unit') or ''}")
        b.metric("Average queue wait", f"{float(metrics.get('average_waiting_time') or 0):.6g}")
        c.metric("Average flow time", f"{float(metrics.get('average_flow_time') or 0):.6g}")
        st.dataframe([
            {
                "Task": row.get("task_id"),
                "Label": row.get("label"),
                "Start": row.get("start_time"),
                "Finish": row.get("finish_time"),
                "Wait": row.get("waiting_time"),
                "Flow": row.get("flow_time"),
                "Resources": ", ".join(f"{k}:{v}" for k, v in (row.get("resources") or {}).items()),
                "Dependencies": ", ".join(row.get("dependencies") or []),
            }
            for row in evaluation.get("schedule") or []
        ], width="stretch", hide_index=True)
        utilization = metrics.get("resource_utilization") or {}
        st.dataframe([
            {"Resource": resource_id, "Utilization": value}
            for resource_id, value in utilization.items()
        ], width="stretch", hide_index=True)

        comparison = operations.compare_dispatch_policies(path, plan_id)
        st.markdown("#### Dispatch policy comparison")
        st.dataframe([
            {
                "Policy": row.get("policy"),
                "Makespan": row.get("makespan"),
                "Average waiting": row.get("average_waiting_time"),
                "Average flow": row.get("average_flow_time"),
                "Utilization": row.get("resource_utilization"),
            }
            for row in comparison.get("policies") or []
        ], width="stretch", hide_index=True)
        st.caption(
            "Different policies may trade off queue delay, downstream completion and utilization. Physical Lab reports the modeled outcomes and does not select a globally optimal policy."
        )
        with st.expander("Operations evaluation JSON", expanded=False):
            st.json(evaluation)

    st.caption(
        "Operations Layer boundary: durations, capacities, priorities and dependencies are declared planning assumptions. Schedule metrics do not establish scientific validity, safety approval, or certification."
    )
