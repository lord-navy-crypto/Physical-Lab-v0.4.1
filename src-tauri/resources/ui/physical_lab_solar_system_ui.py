"""Streamlit UI for Physical Lab Sun-Jupiter-Saturn orbital dynamics."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from physical_lab_solar_system_dynamics import (
    MODEL_TITLE,
    MODEL_VARIANT,
    SolarSystemConfig,
    finite_time_lyapunov_indicator,
    integrate_case,
    result_summary,
)
from physical_lab_solar_system_workflow import (
    build_solar_system_manifest,
    render_report_markdown,
)

_DURATION_MODES = {"SHORT · 80 yr": 80.0, "LONG · 500 yr": 500.0, "ULTRA_LONG · 1000 yr": 1000.0}


def _config_from_ui(st: Any) -> SolarSystemConfig:
    mode = st.selectbox(
        "Simulation horizon",
        list(_DURATION_MODES),
        index=0,
        key="pl_solar_mode",
        help="Preserves the original SHORT/LONG/ULTRA_LONG idea. Long horizons may require substantial local CPU time.",
    )
    c1, c2, c3 = st.columns(3)
    inc = c1.selectbox("Jupiter inclination", [0.0, 10.0, 20.0, 30.0], index=1, key="pl_solar_inclination_deg")
    samples = c2.number_input("Output samples", 400, 12000, 2400, 200, key="pl_solar_samples")
    max_step = c3.number_input("Max solver step (yr)", 0.002, 0.20, 0.03, 0.002, format="%.3f", key="pl_solar_max_step")

    p1, p2 = st.columns(2)
    saturn_backreaction = p1.toggle(
        "Saturn gravitational backreaction",
        value=True,
        key="pl_solar_saturn_backreaction",
        help="Off keeps Saturn as a massless tracer instead of removing its displayed trajectory.",
    )
    solar_1pn = p2.toggle(
        "Approximate central-Sun 1PN correction",
        value=False,
        key="pl_solar_1pn",
        help="Controlled test-particle-like central-Sun 1PN term; not complete N-body post-Newtonian dynamics.",
    )

    velocity_cross = False
    radial_drag = False
    xi = 1e-4
    sigma = 1e-8
    with st.expander("Legacy phenomenological perturbations", expanded=False):
        st.warning(
            "These preserve the experimental intent of the original spin/GW switches but are deliberately not labelled as physical spin-orbit coupling or gravitational-wave reaction."
        )
        q1, q2 = st.columns(2)
        velocity_cross = q1.toggle("Velocity-cross toy perturbation", value=False, key="pl_solar_velocity_cross")
        radial_drag = q2.toggle("Radial-drag toy perturbation", value=False, key="pl_solar_radial_drag")
        q3, q4 = st.columns(2)
        xi = q3.number_input("Velocity-cross strength", 0.0, 1e-2, 1e-4, 1e-5, format="%.6g", key="pl_solar_xi")
        sigma = q4.number_input("Radial-drag strength", 0.0, 1e-5, 1e-8, 1e-8, format="%.6g", key="pl_solar_sigma")
        st.caption(
            "Original mutable gravitational-delay deque is not promoted into this solver. A correct retarded interaction study would require a dedicated delay-differential formulation rather than adaptive ODE history side effects."
        )

    with st.expander("Numerical controls", expanded=False):
        n1, n2 = st.columns(2)
        rtol = n1.number_input("Relative tolerance", 1e-13, 1e-5, 1e-10, format="%.1e", key="pl_solar_rtol")
        atol = n2.number_input("Absolute tolerance", 1e-15, 1e-7, 1e-12, format="%.1e", key="pl_solar_atol")

    return SolarSystemConfig(
        duration_years=_DURATION_MODES[mode],
        samples=int(samples),
        inclination_jupiter_deg=float(inc),
        saturn_backreaction=bool(saturn_backreaction),
        solar_1pn=bool(solar_1pn),
        velocity_cross=bool(velocity_cross),
        radial_drag=bool(radial_drag),
        velocity_cross_strength=float(xi),
        radial_drag_strength=float(sigma),
        rtol=float(rtol),
        atol=float(atol),
        max_step_years=float(max_step),
    )


def _render_result(st: Any, result: Mapping[str, Any]) -> None:
    summary = result_summary(dict(result))
    d = result["diagnostics"]
    t = np.asarray(result["time_years"], dtype=float)
    r = np.asarray(result["positions_AU"], dtype=float)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Period ratio Ts/Tj", f"{summary['final_period_ratio']:.6f}")
    m2.metric("5:2 deviation", f"{summary['final_resonance_deviation_5_2']:+.3e}")
    m3.metric("Min J–S separation", f"{summary['minimum_separation_AU']:.3f} AU")
    m4.metric("Barycenter drift", f"{summary['barycenter_position_drift_AU']:.2e} AU")

    try:
        import plotly.graph_objects as go

        fig3 = go.Figure()
        for idx, name in ((0, "Sun"), (1, "Jupiter"), (2, "Saturn")):
            fig3.add_trace(go.Scatter3d(
                x=r[:, idx, 0], y=r[:, idx, 1], z=r[:, idx, 2],
                mode="lines", name=name,
            ))
        fig3.update_layout(
            title="Barycentric 3-D trajectories",
            scene=dict(xaxis_title="x (AU)", yaxis_title="y (AU)", zaxis_title="z (AU)", aspectmode="data"),
            height=520,
        )
        st.plotly_chart(fig3, width="stretch")

        j = d["jupiter"]
        s = d["saturn"]
        fig_a = go.Figure()
        fig_a.add_trace(go.Scatter(x=t, y=j["a_AU"], mode="lines", name="Jupiter a"))
        fig_a.add_trace(go.Scatter(x=t, y=s["a_AU"], mode="lines", name="Saturn a"))
        fig_a.update_layout(title="Osculating semi-major axis", xaxis_title="Time (yr)", yaxis_title="a (AU)")
        st.plotly_chart(fig_a, width="stretch")

        fig_e = go.Figure()
        fig_e.add_trace(go.Scatter(x=t, y=j["e"], mode="lines", name="Jupiter e"))
        fig_e.add_trace(go.Scatter(x=t, y=s["e"], mode="lines", name="Saturn e"))
        fig_e.update_layout(title="Osculating eccentricity", xaxis_title="Time (yr)", yaxis_title="e")
        st.plotly_chart(fig_e, width="stretch")

        fig_r = go.Figure()
        fig_r.add_trace(go.Scatter(x=t, y=d["period_ratio_saturn_over_jupiter"], mode="lines", name="Ts/Tj"))
        fig_r.add_hline(y=2.5, line_dash="dash", annotation_text="5:2")
        fig_r.update_layout(title="Mean-motion period-ratio diagnostic", xaxis_title="Time (yr)", yaxis_title="Ts/Tj")
        st.plotly_chart(fig_r, width="stretch")

        fig_inv = go.Figure()
        e0 = float(d["newtonian_energy"][0])
        l = np.linalg.norm(np.asarray(d["angular_momentum"], dtype=float), axis=1)
        l0 = float(l[0])
        fig_inv.add_trace(go.Scatter(x=t, y=(np.asarray(d["newtonian_energy"]) - e0) / max(abs(e0), 1e-30), mode="lines", name="ΔE/|E0|"))
        fig_inv.add_trace(go.Scatter(x=t, y=(l - l0) / max(abs(l0), 1e-30), mode="lines", name="Δ|L|/|L0|"))
        fig_inv.update_layout(title="Numerical / model invariant audit", xaxis_title="Time (yr)", yaxis_title="Relative change")
        st.plotly_chart(fig_inv, width="stretch")
    except Exception as exc:
        st.caption(f"Interactive Plotly rendering unavailable: {exc}")

    st.caption(
        "Energy/angular-momentum conservation is a strict invariant check only for the pure Newtonian baseline. With approximate 1PN or phenomenological perturbations enabled, those quantities are displayed diagnostically rather than treated as conserved requirements."
    )
    with st.expander("Structured result summary", expanded=False):
        st.json(summary)


def _active_project_path(st: Any) -> str | None:
    value = st.session_state.get("pl_active_project_path")
    return str(value) if value else None


def _matching_jobs(compute: Any) -> list[dict[str, Any]]:
    rows = []
    for row in compute.list_jobs(limit=100, profile="nonlinear-chaos"):
        cfg = row.get("runner_config") or {}
        if str(cfg.get("model_variant") or "") == MODEL_VARIANT:
            rows.append(row)
    return rows


def _render_platform(st: Any, config: SolarSystemConfig) -> None:
    with st.expander("Experiment / Compute / Project workflow", expanded=False):
        try:
            import physical_lab_compute_engine as compute
            import physical_lab_project_kernel as project
        except Exception as exc:
            st.warning(f"Platform modules unavailable: {exc}")
            return

        preset = st.selectbox("Verification campaign", ["compact", "standard"], index=0, key="pl_solar_campaign_preset")
        manifest = build_solar_system_manifest(
            config,
            preset=preset,
            source_commit=os.environ.get("PHYSICAL_LAB_SOURCE_COMMIT") or None,
        )
        st.write({
            "model": MODEL_TITLE,
            "variant": MODEL_VARIANT,
            "experiment_sha256": manifest["experiment_sha256"],
            "campaign": preset,
        })

        active_project = _active_project_path(st)
        p1, p2, p3 = st.columns(3)
        if p1.button("Register experiment", width="stretch", disabled=not active_project, key="pl_solar_register"):
            project.register_experiment(active_project, manifest)
            st.success("Solar-system experiment registered in active .physlab project.")
        if p2.button("Queue verification", type="primary", width="stretch", key="pl_solar_queue"):
            compute.submit_job(
                manifest,
                runner="model-campaign",
                runner_config={"profile": "nonlinear-chaos", "preset": preset, "model_variant": MODEL_VARIANT},
                priority=70,
            )
            st.success("Persistent solar-system verification campaign queued.")
            st.rerun()
        if p3.button("Sync project jobs", width="stretch", disabled=not active_project, key="pl_solar_sync"):
            sync = project.sync_compute_jobs(active_project)
            st.success(f"Project sync: {sync}")

        compute.start_queued_jobs(max_parallel=1)
        jobs = _matching_jobs(compute)
        if not jobs:
            st.caption("No solar-system Compute Engine jobs yet.")
            return

        import pandas as pd
        st.dataframe(pd.DataFrame([
            {"id": row.get("id"), "status": row.get("status"), "progress": row.get("progress"), "stage": row.get("stage"), "attempt": row.get("attempt")}
            for row in jobs[:12]
        ]), hide_index=True, width="stretch")
        selected = st.selectbox("Inspect solar-system job", [str(row["id"]) for row in jobs], key="pl_solar_job")
        record = compute.read_job(selected) or {}
        a, b, c = st.columns(3)
        if a.button("Refresh", width="stretch", key="pl_solar_refresh"):
            st.rerun()
        if b.button("Cancel", width="stretch", disabled=record.get("status") not in {"queued", "running"}, key="pl_solar_cancel"):
            compute.cancel_job(selected)
            st.rerun()
        if c.button("Requeue", width="stretch", disabled=record.get("status") not in {"failed", "interrupted", "cancelled"}, key="pl_solar_requeue"):
            compute.requeue_job(selected)
            st.rerun()

        result = compute.read_result(selected)
        if result and isinstance(result.get("result"), Mapping):
            campaign = result["result"]
            st.metric("Campaign screening", str((campaign.get("screening") or {}).get("status") or "REVIEW"))
            st.json(campaign.get("metrics") or {})
            report = render_report_markdown(manifest, campaign)
            st.download_button(
                "Download solar-system V&V report",
                report,
                file_name="physical-lab-sun-jupiter-saturn-report.md",
                mime="text/markdown",
                key="pl_solar_report_download",
            )
            if st.button("Publish campaign to current Lab", type="primary", key="pl_solar_publish"):
                st.session_state["pl_solar_system_campaign_result"] = campaign
                st.success("Solar-system campaign published to Lab session state.")


def render_solar_system_workspace(st: Any, profile: str) -> None:
    if profile != "nonlinear-chaos":
        return
    st.markdown("---")
    st.markdown(f"## Physical Lab · {MODEL_TITLE}")
    st.caption(
        "Barycentric Sun–Jupiter–Saturn nonlinear orbital dynamics rebuilt from the standalone long-duration study. "
        "Newtonian point-mass gravity is the authoritative baseline; optional 1PN and legacy toy perturbations are separated by provenance."
    )
    config = _config_from_ui(st)

    b1, b2 = st.columns([2, 1])
    if b1.button("Run interactive orbital model", type="primary", width="stretch", key="pl_solar_run"):
        with st.spinner("Integrating barycentric orbital dynamics..."):
            result = integrate_case(config)
        st.session_state["pl_solar_system_result"] = result
        st.session_state["pl_solar_system_result_summary"] = result_summary(result)
        st.success("Orbital integration completed.")

    if b2.button("Finite-time divergence audit", width="stretch", key="pl_solar_ftle"):
        with st.spinner("Running renormalized finite-time sensitivity audit..."):
            ftle = finite_time_lyapunov_indicator(config, max_years=min(config.duration_years, 30.0))
        st.session_state["pl_solar_system_ftle"] = ftle
        st.success("Finite-time divergence audit completed.")

    result = st.session_state.get("pl_solar_system_result")
    if isinstance(result, Mapping):
        _render_result(st, result)
    ftle = st.session_state.get("pl_solar_system_ftle")
    if isinstance(ftle, Mapping):
        st.write({
            "finite_time_divergence_rate_per_year": ftle.get("finite_time_rate_per_year"),
            "elapsed_years": ftle.get("elapsed_years"),
            "renormalizations": ftle.get("renormalizations"),
            "interpretation": ftle.get("boundary"),
        })

    _render_platform(st, config)
