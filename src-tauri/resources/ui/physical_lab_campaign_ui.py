"""Presentation layer for Physical Lab automated model campaigns.

This module intentionally owns only Streamlit session/presentation behavior. The
numerical and stochastic campaign solvers remain in ``physical_lab_model_campaigns``.
Changing a depth selector does not mutate or relabel an already-computed result.
"""
from __future__ import annotations

import json
import time
from typing import Any

from physical_lab_model_campaigns import (
    SUPPORTED_PROFILES,
    canonical_session_metrics,
    run_campaign,
)


TITLES = {
    "numerical-methods": "Numerical Accuracy / Cost Campaign",
    "ising-monte-carlo": "Multi-Chain Sampling Campaign",
    "random-walk-monte-carlo": "Multi-Seed Estimator Campaign",
    "nonlinear-chaos": "Nonlinear Robustness Campaign",
    "oscillation-integration": "Dynamic-System Convergence Campaign",
}


def campaign_result_state(selected_preset: str, result: dict[str, Any] | None) -> dict[str, Any]:
    """Return explicit selected-vs-displayed state for deterministic UI tests."""
    selected = str(selected_preset or "").strip().lower()
    result_preset = str((result or {}).get("preset") or "").strip().lower()
    has_result = bool(result_preset)
    return {
        "selected_preset": selected,
        "result_preset": result_preset,
        "has_result": has_result,
        "selection_matches_result": bool(has_result and selected == result_preset),
    }


def _display_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, sort_keys=True, ensure_ascii=True)
        except Exception:
            return str(value)
    return value


def render_model_campaign(st: Any, profile: str, namespace: dict[str, Any] | None = None) -> None:
    """Render a one-click campaign and publish canonical scorecard metrics."""
    if profile not in SUPPORTED_PROFILES:
        return
    import pandas as pd

    title = TITLES[profile]
    st.markdown("---")
    st.markdown(f"## Physical Lab · {title}")
    st.caption(
        "Run a bounded refinement/replicate study and publish canonical metrics to the existing Engineering scorecard. "
        "Changing Campaign depth changes only the next run; it never relabels a result already in this session."
    )

    left, right = st.columns([2, 1])
    preset = left.selectbox(
        "Campaign depth",
        ["compact", "standard"],
        index=0,
        key=f"pl_campaign_preset_{profile}",
    )
    should_run = right.button(
        "Run engineering campaign",
        type="primary",
        width="stretch",
        key=f"pl_campaign_run_{profile}",
    )

    result_key = f"pl_model_campaign_result_{profile}"
    if should_run:
        started = time.perf_counter()
        try:
            with st.spinner(f"Running {title}..."):
                result = run_campaign(profile, preset)
            result["observed_runtime_s"] = time.perf_counter() - started
            st.session_state[result_key] = result
            st.success("Campaign complete. Engineering scorecard metrics were refreshed.")
        except Exception as exc:
            st.error(f"Campaign failed: {exc}")

    result = st.session_state.get(result_key)
    if not isinstance(result, dict):
        st.info(f"No campaign result is displayed yet. The next run will use the {preset.upper()} preset.")
        return

    state = campaign_result_state(preset, result)
    if state["selection_matches_result"]:
        st.caption(
            f"Displayed result: {state['result_preset'].upper()} · "
            f"next run: {state['selected_preset'].upper()}"
        )
    else:
        st.warning(
            f"Displayed result is {state['result_preset'].upper()}, while the next run is set to "
            f"{state['selected_preset'].upper()}. The existing result is unchanged until you run the campaign again."
        )

    metrics = canonical_session_metrics(result)
    st.session_state[f"pl_model_campaign_metrics_{profile}"] = metrics
    cases = result.get("cases") or []
    summary_tab, cases_tab, provenance_tab = st.tabs(["Summary", "Cases", "Provenance"])

    with summary_tab:
        metric_columns = st.columns(min(4, max(1, len(metrics))))
        for index, (name, value) in enumerate(metrics.items()):
            metric_columns[index % len(metric_columns)].metric(name.replace("_", " "), f"{value:.6g}")

        a, b, c = st.columns(3)
        a.metric("Result preset", str(result.get("preset", "—")).upper())
        b.metric("Campaign cases", str(len(cases)))
        c.metric("Observed runtime", f"{float(result.get('observed_runtime_s', 0.0)):.3f} s")
        st.caption(
            "These canonical metrics are the values published to the model-specific Engineering scorecard for this displayed result."
        )

    with cases_tab:
        if not cases:
            st.info("This campaign result contains no case rows.")
        else:
            try:
                case_frame = pd.json_normalize(cases)
                st.caption(
                    f"{len(case_frame)} recorded campaign case row(s). Nested values are display-expanded where possible."
                )
                st.dataframe(case_frame, width="stretch", hide_index=True)
            except Exception:
                st.json(cases)

    with provenance_tab:
        st.markdown("#### Run identity")
        identity = pd.DataFrame([
            {"field": "Preset used for displayed result", "value": str(result.get("preset", "—"))},
            {"field": "Observed runtime (s)", "value": float(result.get("observed_runtime_s", 0.0))},
            {"field": "Schema", "value": str(result.get("schema", "—"))},
        ])
        st.dataframe(identity, width="stretch", hide_index=True)
        fingerprint = str(result.get("campaign_sha256", ""))
        if fingerprint:
            st.caption("Campaign fingerprint")
            st.code(fingerprint, language=None)

        st.markdown("#### Resolved configuration")
        config = result.get("config") or {}
        if isinstance(config, dict) and config:
            config_rows = [
                {"parameter": str(key), "value": _display_value(value)}
                for key, value in config.items()
            ]
            st.dataframe(pd.DataFrame(config_rows), width="stretch", hide_index=True)
        else:
            st.caption("No resolved configuration was recorded.")

        notes = result.get("notes") or []
        if notes:
            st.markdown("#### Scientific notes")
            for note in notes:
                st.markdown(f"- {note}")

        boundary = str(result.get("boundary", "") or "")
        if boundary:
            st.info(boundary)

        st.download_button(
            "Export campaign JSON",
            data=json.dumps(result, indent=2, allow_nan=False).encode("utf-8"),
            file_name=f"physical-lab-{profile}-{result.get('preset', 'campaign')}.json",
            mime="application/json",
            key=f"pl_campaign_export_{profile}",
        )
