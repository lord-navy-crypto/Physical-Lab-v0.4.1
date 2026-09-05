"""Streamlit UI for Physical Lab Risk & Engineering Economics Layer v1."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _optional_float(text: str) -> float | None:
    value = str(text).strip()
    return None if not value else float(value)


def _parse_risk_rows(text: str, reference: str) -> list[dict[str, Any]]:
    kind, ref_id = reference.split(":", 1)
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(str(text).splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 5:
            raise ValueError(f"Risk row {index} must have 5 pipe-separated fields: name | probability | cost | schedule | performance")
        name, probability, cost, schedule, performance = parts
        consequences = {
            "cost": _optional_float(cost),
            "schedule": _optional_float(schedule),
            "performance": _optional_float(performance),
        }
        rows.append({
            "scenario_id": f"scenario-{index:04d}",
            "name": name or f"Scenario {index}",
            "probability": _optional_float(probability),
            "consequences": consequences,
            "references": [{"kind": kind, "id": ref_id}],
        })
    if not rows:
        raise ValueError("At least one risk scenario row is required.")
    return rows


def _parse_cash_flow_rows(text: str, reference: str) -> list[dict[str, Any]]:
    kind, ref_id = reference.split(":", 1)
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(str(text).splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            raise ValueError(f"Cash-flow row {index} must have 3 pipe-separated fields: period | amount | label")
        period, amount, label = parts
        rows.append({
            "flow_id": f"flow-{index:04d}",
            "period": float(period),
            "amount": float(amount),
            "label": label or f"Flow {index}",
            "references": [{"kind": kind, "id": ref_id}],
        })
    if not rows:
        raise ValueError("At least one cash-flow row is required.")
    return rows


def render_risk_economics_tab(st: Any, project_path: str | Path, profile: str, refs: list[str]) -> None:
    import physical_lab_risk_economics as re

    path = Path(project_path).expanduser().resolve()
    matrix = re.risk_economics_matrix(path)
    risk_rows = matrix.get("risk_studies") or []
    economics_rows = matrix.get("economics_studies") or []

    st.caption(
        "Analyze explicitly declared engineering risk scenarios and time-valued cash flows while preserving Project evidence freshness. "
        "No probability is inferred, no risk is automatically accepted, and no investment/design alternative is automatically recommended."
    )
    a, b, c = st.columns(3)
    a.metric("Risk studies", len(risk_rows))
    b.metric("Economics studies", len(economics_rows))
    c.metric("Evidence refs available", len(refs))

    risk_tab, economics_tab = st.tabs(["Risk analysis", "Engineering economics"])

    with risk_tab:
        if risk_rows:
            labels = {f"{row.get('name')} · {row.get('study_id')}": str(row.get("study_id")) for row in risk_rows}
            selected = st.selectbox("Review risk study", [""] + list(labels), key=f"pl_risk_review_{profile}")
            if selected:
                evaluation = re.evaluate_risk_study(path, labels[selected])
                a, b, c = st.columns(3)
                a.metric("Evidence", evaluation.get("evidence_state"))
                b.metric("Scenarios", evaluation.get("scenario_count"))
                c.metric("Probabilities declared", evaluation.get("probability_declared_count"))
                display = []
                units = evaluation.get("consequence_units") or {}
                for row in evaluation.get("scenarios") or []:
                    expected = row.get("expected_consequence") or {}
                    consequences = row.get("consequences") or {}
                    display.append({
                        "Scenario": row.get("name"),
                        "Probability": row.get("probability"),
                        f"Cost consequence [{units.get('cost')}]": consequences.get("cost"),
                        f"Expected cost [{units.get('cost')}]": expected.get("cost"),
                        f"Schedule consequence [{units.get('schedule')}]": consequences.get("schedule"),
                        f"Expected schedule [{units.get('schedule')}]": expected.get("schedule"),
                        f"Performance consequence [{units.get('performance')}]": consequences.get("performance"),
                        f"Expected performance [{units.get('performance')}]": expected.get("performance"),
                    })
                st.dataframe(display, width="stretch", hide_index=True)
                st.markdown("#### Arithmetic totals from declared probabilities")
                st.json(evaluation.get("expected_consequence_totals") or {})
                if evaluation.get("stale_references") or evaluation.get("missing_references"):
                    st.warning("Supporting Project evidence is stale or missing; review the evidence references before using this study.")
                st.caption(str(evaluation.get("boundary") or ""))
        else:
            st.info("No risk studies registered yet.")

        with st.expander("Register risk study", expanded=False):
            name = st.text_input("Risk study name", key=f"pl_risk_name_{profile}")
            a, b, c = st.columns(3)
            cost_unit = a.text_input("Cost consequence unit", value="currency", key=f"pl_risk_cost_unit_{profile}")
            schedule_unit = b.text_input("Schedule consequence unit", value="day", key=f"pl_risk_schedule_unit_{profile}")
            performance_unit = c.text_input("Performance consequence unit", value="1", key=f"pl_risk_performance_unit_{profile}")
            scenario_text = st.text_area(
                "Scenarios — one per line: name | probability | cost | schedule | performance",
                value="Supplier delay | 0.10 | 100 | 2 |\nTest rerun | 0.20 | 50 | 5 |\nUnelicited performance uncertainty |  |  |  | 0.4",
                key=f"pl_risk_rows_{profile}",
                help="Leave probability blank when it has not been explicitly elicited. Blank consequence dimensions are allowed, but every scenario must declare at least one consequence.",
            )
            evidence_ref = st.selectbox("Evidence reference applied to these scenarios", [""] + refs, key=f"pl_risk_ref_{profile}")
            intended_use = st.text_input("Risk-study intended use", key=f"pl_risk_use_{profile}")
            if st.button("Register risk study", type="primary", key=f"pl_risk_register_{profile}"):
                try:
                    if not name.strip() or not evidence_ref:
                        raise ValueError("Risk study name and an evidence reference are required.")
                    scenarios = _parse_risk_rows(scenario_text, evidence_ref)
                    record = re.register_risk_study(
                        path,
                        name=name,
                        scenarios=scenarios,
                        cost_unit=cost_unit,
                        schedule_unit=schedule_unit,
                        performance_unit=performance_unit,
                        intended_use=intended_use,
                    )
                    st.success(f"Registered {record['study_id']}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        st.caption("Expected consequence is computed only when both a probability and that consequence magnitude are explicitly declared. It is not a risk-acceptance or safety verdict.")

    with economics_tab:
        if economics_rows:
            labels = {f"{row.get('name')} · {row.get('study_id')}": str(row.get("study_id")) for row in economics_rows}
            selected = st.selectbox("Review economics study", [""] + list(labels), key=f"pl_economics_review_{profile}")
            if selected:
                evaluation = re.evaluate_economics_study(path, labels[selected])
                a, b, c = st.columns(3)
                a.metric("Evidence", evaluation.get("evidence_state"))
                b.metric("Undiscounted net total", evaluation.get("undiscounted_net_total"))
                c.metric("Present worth", evaluation.get("present_worth"))
                st.markdown(
                    f"**Declared discount rate:** `{evaluation.get('discount_rate')}` · "
                    f"**currency:** `{evaluation.get('currency_unit')}` · **period:** `{evaluation.get('period_unit')}`"
                )
                st.caption(str(evaluation.get("sign_convention") or ""))
                st.dataframe(evaluation.get("cash_flows") or [], width="stretch", hide_index=True)
                if evaluation.get("stale_references") or evaluation.get("missing_references"):
                    st.warning("Supporting Project evidence is stale or missing; review the evidence references before using this study.")
                st.caption(str(evaluation.get("boundary") or ""))
        else:
            st.info("No engineering-economics studies registered yet.")

        with st.expander("Register engineering-economics study", expanded=False):
            name = st.text_input("Economics study name", key=f"pl_economics_name_{profile}")
            a, b, c = st.columns(3)
            rate = a.number_input("Discount rate", value=0.10, min_value=-0.99, format="%.8g", key=f"pl_economics_rate_{profile}")
            currency = b.text_input("Currency / value unit", value="currency", key=f"pl_economics_currency_{profile}")
            period_unit = c.text_input("Period unit", value="year", key=f"pl_economics_period_unit_{profile}")
            flow_text = st.text_area(
                "Cash flows — one per line: period | signed amount | label",
                value="0 | -1000 | Initial engineering cost\n1 | 600 | Year 1 benefit\n2 | 600 | Year 2 benefit",
                key=f"pl_economics_flows_{profile}",
                help="Sign convention: positive = inflow/benefit; negative = outflow/cost.",
            )
            evidence_ref = st.selectbox("Evidence reference applied to these cash flows", [""] + refs, key=f"pl_economics_ref_{profile}")
            intended_use = st.text_input("Economics intended use", key=f"pl_economics_use_{profile}")
            if st.button("Register economics study", type="primary", key=f"pl_economics_register_{profile}"):
                try:
                    if not name.strip() or not evidence_ref:
                        raise ValueError("Economics study name and an evidence reference are required.")
                    flows = _parse_cash_flow_rows(flow_text, evidence_ref)
                    record = re.register_economics_study(
                        path,
                        name=name,
                        cash_flows=flows,
                        discount_rate=rate,
                        currency_unit=currency,
                        period_unit=period_unit,
                        intended_use=intended_use,
                    )
                    st.success(f"Registered {record['study_id']}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        st.caption("Present worth is arithmetic under the declared cash flows and discount rate. It is not financial advice, a market forecast, or an automatic engineering-selection rule.")
