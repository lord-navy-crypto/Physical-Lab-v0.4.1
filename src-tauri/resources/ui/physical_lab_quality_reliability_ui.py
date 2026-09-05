"""Streamlit UI for Physical Lab Quality & Reliability Layer v1."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _csv_tokens(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _float_tokens(value: str) -> list[float]:
    return [float(item) for item in _csv_tokens(value)]


def _parse_optional_float(value: str) -> float | None:
    text = str(value).strip()
    return None if not text else float(text)


def render_quality_reliability_tab(st: Any, project_path: str | Path, profile: str, refs: list[str]) -> None:
    import physical_lab_quality_reliability as qr

    path = Path(project_path).expanduser().resolve()
    matrix = qr.quality_reliability_matrix(path)
    quality_rows = matrix.get("quality_studies") or []
    reliability_rows = matrix.get("reliability_studies") or []

    st.caption(
        "Describe observed variation, repeatability, declared specification context, factor contrasts and reliability events while preserving Project evidence freshness. "
        "No Cp/Cpk, MTBF, production qualification, safety approval, or certification verdict is generated."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Quality studies", len(quality_rows))
    c2.metric("Reliability studies", len(reliability_rows))
    c3.metric("Evidence refs available", len(refs))

    quality_tab, reliability_tab = st.tabs(["Quality / DOE evidence", "Reliability event evidence"])

    with quality_tab:
        if quality_rows:
            labels = {f"{row.get('name')} · {row.get('measurement')} · {row.get('study_id')}": str(row.get("study_id")) for row in quality_rows}
            selected = st.selectbox("Review quality study", [""] + list(labels), key=f"pl_quality_review_{profile}")
            if selected:
                evaluation = qr.evaluate_quality_study(path, labels[selected])
                s = evaluation.get("summary") or {}
                spec = evaluation.get("specification_summary") or {}
                a, b, c, d = st.columns(4)
                a.metric("Evidence", evaluation.get("evidence_state"))
                b.metric("n", s.get("count"))
                c.metric("Mean", s.get("mean"))
                d.metric("Sample std", s.get("sample_std"))
                if spec.get("declared"):
                    st.markdown(
                        f"**Declared specification context:** lower `{spec.get('lower')}` · upper `{spec.get('upper')}` · "
                        f"observed within fraction `{spec.get('observed_within_fraction')}`"
                    )
                st.markdown(f"**Pooled repeatability std:** `{evaluation.get('pooled_repeatability_std')}` · df `{evaluation.get('repeatability_degrees_freedom')}`")
                if evaluation.get("replicate_groups"):
                    st.dataframe(evaluation.get("replicate_groups"), width="stretch", hide_index=True)
                if evaluation.get("factor_summaries"):
                    st.markdown("#### Descriptive factor summaries")
                    st.json(evaluation.get("factor_summaries"))
                if evaluation.get("stale_references") or evaluation.get("missing_references"):
                    st.warning("Supporting Project evidence is stale or missing; review the evidence references before using this study.")
                st.caption(str(evaluation.get("boundary") or ""))
        else:
            st.info("No quality studies registered yet.")

        with st.expander("Register quality / DOE evidence study", expanded=False):
            name = st.text_input("Study name", key=f"pl_quality_name_{profile}")
            a, b = st.columns(2)
            measurement = a.text_input("Measurement / response", key=f"pl_quality_measurement_{profile}")
            unit = b.text_input("Unit", value="1", key=f"pl_quality_unit_{profile}")
            values_text = st.text_area(
                "Observed values (comma-separated)",
                value="10.0, 10.2, 10.8, 11.0",
                key=f"pl_quality_values_{profile}",
            )
            groups_text = st.text_input(
                "Replicate groups (optional, comma-separated; same length)",
                value="g1, g1, g2, g2",
                key=f"pl_quality_groups_{profile}",
            )
            a, b = st.columns(2)
            factor_name = a.text_input("Factor name (optional)", key=f"pl_quality_factor_name_{profile}")
            factor_levels_text = b.text_input("Factor levels (optional, comma-separated; same length)", key=f"pl_quality_factor_levels_{profile}")
            a, b = st.columns(2)
            lower_text = a.text_input("Declared lower specification (optional)", key=f"pl_quality_lower_{profile}")
            upper_text = b.text_input("Declared upper specification (optional)", key=f"pl_quality_upper_{profile}")
            evidence_ref = st.selectbox("Evidence reference applied to these observations", [""] + refs, key=f"pl_quality_ref_{profile}")
            intended_use = st.text_input("Intended use", key=f"pl_quality_use_{profile}")
            if st.button("Register quality study", type="primary", key=f"pl_quality_register_{profile}"):
                try:
                    values = _float_tokens(values_text)
                    groups = _csv_tokens(groups_text)
                    levels = _csv_tokens(factor_levels_text)
                    if not name.strip() or not measurement.strip() or not values or not evidence_ref:
                        raise ValueError("Study name, measurement, at least one value, and an evidence reference are required.")
                    if groups and len(groups) != len(values):
                        raise ValueError("Replicate-group count must match the number of observed values.")
                    if factor_name.strip() and levels and len(levels) != len(values):
                        raise ValueError("Factor-level count must match the number of observed values.")
                    kind, ref_id = evidence_ref.split(":", 1)
                    observations = []
                    for index, value in enumerate(values):
                        factors = {factor_name.strip(): levels[index]} if factor_name.strip() and levels else {}
                        observations.append({
                            "observation_id": f"obs-{index + 1:04d}",
                            "value": value,
                            "replicate_group": groups[index] if groups else "",
                            "factors": factors,
                            "references": [{"kind": kind, "id": ref_id}],
                        })
                    record = qr.register_quality_study(
                        path,
                        name=name,
                        measurement=measurement,
                        unit=unit,
                        observations=observations,
                        specification={"lower": _parse_optional_float(lower_text), "upper": _parse_optional_float(upper_text)},
                        intended_use=intended_use,
                    )
                    st.success(f"Registered {record['study_id']}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        st.caption("Two-level factor contrasts are descriptive differences of observed means; they are not causal-effect estimates or inferential DOE conclusions.")

    with reliability_tab:
        if reliability_rows:
            labels = {f"{row.get('name')} · {row.get('item')} · {row.get('study_id')}": str(row.get("study_id")) for row in reliability_rows}
            selected = st.selectbox("Review reliability study", [""] + list(labels), key=f"pl_reliability_review_{profile}")
            if selected:
                evaluation = qr.evaluate_reliability_study(path, labels[selected])
                a, b, c, d = st.columns(4)
                a.metric("Evidence", evaluation.get("evidence_state"))
                b.metric("Trials", evaluation.get("trial_count"))
                c.metric("Observed events", evaluation.get("event_count"))
                d.metric("Event fraction", evaluation.get("observed_event_fraction"))
                st.markdown(
                    f"**Total exposure:** `{evaluation.get('total_exposure')}` {evaluation.get('exposure_unit') or ''} · "
                    f"**observed event rate/exposure:** `{evaluation.get('observed_event_rate_per_exposure')}`"
                )
                if evaluation.get("event_categories"):
                    st.json(evaluation.get("event_categories"))
                if evaluation.get("stale_references") or evaluation.get("missing_references"):
                    st.warning("Supporting Project evidence is stale or missing; review the evidence references before using this study.")
                st.caption(str(evaluation.get("boundary") or ""))
        else:
            st.info("No reliability event studies registered yet.")

        with st.expander("Register reliability event study", expanded=False):
            name = st.text_input("Reliability study name", key=f"pl_reliability_name_{profile}")
            a, b = st.columns(2)
            item = a.text_input("Item / configuration", key=f"pl_reliability_item_{profile}")
            exposure_unit = b.text_input("Exposure unit", value="h", key=f"pl_reliability_unit_{profile}")
            exposures_text = st.text_input("Trial exposures (comma-separated)", value="10, 10, 10, 10", key=f"pl_reliability_exposure_{profile}")
            events_text = st.text_input("Event observed flags (0/1, comma-separated)", value="0, 1, 0, 1", key=f"pl_reliability_events_{profile}")
            categories_text = st.text_input("Event categories (optional, comma-separated; same length)", value=", thermal, , thermal", key=f"pl_reliability_categories_{profile}")
            evidence_ref = st.selectbox("Evidence reference applied to these trials", [""] + refs, key=f"pl_reliability_ref_{profile}")
            intended_use = st.text_input("Reliability intended use", key=f"pl_reliability_use_{profile}")
            if st.button("Register reliability study", type="primary", key=f"pl_reliability_register_{profile}"):
                try:
                    exposures = _float_tokens(exposures_text)
                    event_tokens = _csv_tokens(events_text)
                    categories = [item.strip() for item in str(categories_text).split(",")]
                    if not name.strip() or not item.strip() or not exposures or not evidence_ref:
                        raise ValueError("Study name, item, at least one exposure, and an evidence reference are required.")
                    if len(event_tokens) != len(exposures):
                        raise ValueError("Event-flag count must match exposure count.")
                    if any(token not in {"0", "1"} for token in event_tokens):
                        raise ValueError("Event flags must be 0 or 1.")
                    if categories and len(categories) not in {0, len(exposures)}:
                        raise ValueError("Event-category count must match exposure count.")
                    kind, ref_id = evidence_ref.split(":", 1)
                    trials = []
                    for index, exposure in enumerate(exposures):
                        trials.append({
                            "trial_id": f"trial-{index + 1:04d}",
                            "exposure": exposure,
                            "event_observed": event_tokens[index] == "1",
                            "event_category": categories[index] if len(categories) == len(exposures) else "",
                            "references": [{"kind": kind, "id": ref_id}],
                        })
                    record = qr.register_reliability_study(
                        path,
                        name=name,
                        item=item,
                        trials=trials,
                        exposure_unit=exposure_unit,
                        intended_use=intended_use,
                    )
                    st.success(f"Registered {record['study_id']}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        st.caption("Observed event summaries do not fit a lifetime distribution or infer MTBF, field reliability, safety, or certification status.")
