"""Shared Streamlit UI for evidence-linked engineering decision studies."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _parse_ref(value: str) -> dict[str, str]:
    kind, ref_id = str(value).split(":", 1)
    return {"kind": kind, "id": ref_id}


def render_engineering_decision_tab(st: Any, project_path: str | Path, profile: str, refs: list[str]) -> None:
    import physical_lab_engineering_decisions as decisions

    path = Path(project_path).expanduser().resolve()
    matrix = decisions.decision_matrix(path)
    rows = matrix.get("studies") or []
    if rows:
        st.dataframe([
            {
                "Trade study": row.get("name"),
                "Decision question": row.get("decision_question"),
                "Pareto frontier": ", ".join(row.get("pareto_frontier") or []),
                "Feasible": int((row.get("counts") or {}).get("FEASIBLE") or 0),
                "Infeasible": int((row.get("counts") or {}).get("INFEASIBLE") or 0),
                "Stale": int((row.get("counts") or {}).get("STALE") or 0),
                "Evidence missing": int((row.get("counts") or {}).get("EVIDENCE_MISSING") or 0),
            }
            for row in rows
        ], width="stretch", hide_index=True)
    else:
        st.info("No engineering trade studies registered yet.")

    with st.expander("Register engineering trade study", expanded=False):
        st.caption(
            "Define explicit objectives, constraints and evidence-linked alternatives. Physical Lab computes feasibility and Pareto dominance only; it does not assign an overall score or choose a best design."
        )
        name = st.text_input("Study name", key=f"pl_trade_name_{profile}")
        question = st.text_area("Decision question", key=f"pl_trade_question_{profile}")
        intended = st.text_input("Intended use", key=f"pl_trade_use_{profile}")

        st.markdown("#### Metrics")
        m1a, m1b, m1c, m1d = st.columns([1, 2, 1, 1])
        m1_id = m1a.text_input("Metric 1 id", value="performance", key=f"pl_trade_m1_id_{profile}")
        m1_label = m1b.text_input("Metric 1 label", value="Performance", key=f"pl_trade_m1_label_{profile}")
        m1_direction = m1c.selectbox("Metric 1 direction", ["maximize", "minimize"], key=f"pl_trade_m1_dir_{profile}")
        m1_unit = m1d.text_input("Metric 1 unit", value="1", key=f"pl_trade_m1_unit_{profile}")

        m2a, m2b, m2c, m2d = st.columns([1, 2, 1, 1])
        m2_id = m2a.text_input("Metric 2 id", value="cost", key=f"pl_trade_m2_id_{profile}")
        m2_label = m2b.text_input("Metric 2 label", value="Cost / resource proxy", key=f"pl_trade_m2_label_{profile}")
        m2_direction = m2c.selectbox("Metric 2 direction", ["minimize", "maximize"], key=f"pl_trade_m2_dir_{profile}")
        m2_unit = m2d.text_input("Metric 2 unit", value="arb", key=f"pl_trade_m2_unit_{profile}")

        metric_ids = [value.strip() for value in (m1_id, m2_id) if value.strip()]
        use_constraint = st.checkbox("Add hard constraint", value=True, key=f"pl_trade_constraint_enabled_{profile}")
        constraint_metric = None
        constraint_operator = "<="
        constraint_threshold = 0.0
        if use_constraint and metric_ids:
            ca, cb, cc = st.columns(3)
            constraint_metric = ca.selectbox("Constraint metric", metric_ids, index=min(1, len(metric_ids) - 1), key=f"pl_trade_constraint_metric_{profile}")
            constraint_operator = cb.selectbox("Operator", ["<=", ">="], key=f"pl_trade_constraint_operator_{profile}")
            constraint_threshold = cc.number_input("Threshold", value=100.0, format="%.12g", key=f"pl_trade_constraint_threshold_{profile}")

        st.markdown("#### Alternatives")
        alternatives = []
        for index, default_id in enumerate(("A", "B", "C"), start=1):
            st.markdown(f"**Alternative {default_id}**")
            a, b = st.columns([1, 2])
            alt_id = a.text_input("Alternative id", value=default_id, key=f"pl_trade_alt_id_{index}_{profile}")
            alt_label = b.text_input("Alternative label", value=f"Alternative {default_id}", key=f"pl_trade_alt_label_{index}_{profile}")
            va, vb = st.columns(2)
            value1 = va.number_input(f"{m1_label or m1_id} value", value=float(index), format="%.12g", key=f"pl_trade_alt_m1_{index}_{profile}")
            value2 = vb.number_input(f"{m2_label or m2_id} value", value=float(index * 10), format="%.12g", key=f"pl_trade_alt_m2_{index}_{profile}")
            alt_refs = st.multiselect(
                "Evidence references",
                refs,
                key=f"pl_trade_alt_refs_{index}_{profile}",
                help="Each alternative must be linked to at least one current project evidence record.",
            )
            alternatives.append((alt_id, alt_label, value1, value2, alt_refs))

        if st.button("Register trade study", type="primary", key=f"pl_trade_register_{profile}"):
            metrics = []
            if m1_id.strip():
                metrics.append({"metric_id": m1_id.strip(), "label": m1_label, "direction": m1_direction, "unit": m1_unit})
            if m2_id.strip():
                metrics.append({"metric_id": m2_id.strip(), "label": m2_label, "direction": m2_direction, "unit": m2_unit})
            constraints = []
            if use_constraint and constraint_metric:
                constraints.append({"metric_id": constraint_metric, "operator": constraint_operator, "threshold": constraint_threshold})
            alt_rows = []
            for alt_id, alt_label, value1, value2, alt_refs in alternatives:
                if not str(alt_id).strip() or not str(alt_label).strip():
                    continue
                values = {}
                if m1_id.strip():
                    values[m1_id.strip()] = value1
                if m2_id.strip():
                    values[m2_id.strip()] = value2
                alt_rows.append({
                    "alternative_id": str(alt_id).strip(),
                    "label": str(alt_label).strip(),
                    "values": values,
                    "references": [_parse_ref(value) for value in alt_refs],
                })
            if not name.strip() or not question.strip():
                st.error("Study name and decision question are required.")
            elif len(metrics) < 1:
                st.error("At least one metric is required.")
            elif len(alt_rows) < 2:
                st.error("At least two alternatives are required.")
            elif any(not row["references"] for row in alt_rows):
                st.error("Every alternative must have at least one explicit evidence reference.")
            else:
                try:
                    record = decisions.register_decision_study(
                        path,
                        name=name,
                        decision_question=question,
                        metrics=metrics,
                        constraints=constraints,
                        alternatives=alt_rows,
                        intended_use=intended,
                    )
                    evaluation = decisions.evaluate_decision_study(path, record["study_id"])
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.success(
                        f"Registered {record['study_id']} · Pareto frontier: "
                        f"{', '.join(evaluation['pareto_frontier']) or 'none under current evidence/constraints'}"
                    )
                    st.rerun()

    study_rows = decisions.list_decision_studies(path)
    if study_rows:
        st.markdown("#### Review trade study")
        options = {f"{row.get('name')} · {row.get('study_id')}": str(row.get("study_id")) for row in study_rows}
        label = st.selectbox("Study", list(options), key=f"pl_trade_review_select_{profile}")
        study_id = options[label]
        evaluation = decisions.evaluate_decision_study(path, study_id)
        table = []
        for row in evaluation.get("alternatives") or []:
            display = {
                "Alternative": row.get("alternative_id"),
                "Label": row.get("label"),
                "Review state": row.get("review_state"),
                "Pareto nondominated": row.get("pareto_nondominated"),
                "Dominated by": ", ".join(row.get("dominated_by") or []),
            }
            for metric_id, value in (row.get("values") or {}).items():
                display[str(metric_id)] = value
            table.append(display)
        st.dataframe(table, width="stretch", hide_index=True)
        st.caption(f"Evaluation `{str(evaluation.get('evaluation_sha256') or '')[:16]}…` · Pareto frontier: {', '.join(evaluation.get('pareto_frontier') or []) or 'none'}")
        with st.expander("Engineering decision evaluation", expanded=False):
            st.json(evaluation)

        st.markdown("#### Record human decision")
        alternatives_for_selection = [str(row.get("alternative_id")) for row in evaluation.get("alternatives") or []]
        selected = st.selectbox("Selected alternative", alternatives_for_selection, key=f"pl_trade_human_selected_{profile}")
        reviewer = st.text_input("Reviewer / decision owner", key=f"pl_trade_human_reviewer_{profile}")
        rationale = st.text_area("Human rationale", key=f"pl_trade_human_rationale_{profile}")
        if st.button("Record human decision", key=f"pl_trade_human_record_{profile}"):
            if not rationale.strip():
                st.error("A human-authored rationale is required.")
            else:
                record = decisions.record_human_decision(
                    path,
                    study_id,
                    selected_alternative_id=selected,
                    rationale=rationale,
                    reviewer=reviewer,
                )
                st.success(f"Recorded human decision `{str(record['decision_sha256'])[:16]}…`")

    st.caption(
        "Engineering Decision Layer boundary: feasibility and Pareto dominance use only declared metrics, constraints and current evidence. Selection remains a human engineering judgment."
    )
