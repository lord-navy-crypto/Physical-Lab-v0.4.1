"""Experiment/Compute/Project workspace for the Kerr geodesic model."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

from physical_lab_kerr_geodesics import PROFILE, KerrOrbitConfig, horizon_radius
from physical_lab_kerr_workflow import (
    DEFAULT_REQUIREMENTS,
    MODEL_VARIANT,
    build_kerr_manifest,
    geometric_scale,
    render_kerr_report_markdown,
)


def _current_config(st: Any) -> KerrOrbitConfig:
    particle = str(st.session_state.get("pl_kerr_particle", "massive"))
    spin = float(st.session_state.get("pl_kerr_spin", 0.60))
    inclination = float(st.session_state.get("pl_kerr_inclination", 60.0))
    rp = float(st.session_state.get("pl_kerr_rp", 6.5))
    ra = float(st.session_state.get("pl_kerr_ra", max(10.0, rp + 0.5)))
    lam_key = f"pl_kerr_lam_{particle}"
    lam_default = 20.0 if particle == "massive" else 4.0
    lam_max = float(st.session_state.get(lam_key, lam_default))
    samples = int(st.session_state.get("pl_kerr_samples", 2500))
    rtol_exp = int(st.session_state.get("pl_kerr_rtol_exp", -9))
    atol_exp = int(st.session_state.get("pl_kerr_atol_exp", -11))
    return KerrOrbitConfig(
        spin=spin,
        inclination_deg=inclination,
        particle_type=particle,
        periapsis=rp,
        apoapsis=ra,
        lam_max=lam_max,
        samples=samples,
        rtol=10.0 ** rtol_exp,
        atol=10.0 ** atol_exp,
    )


def _load_compute():
    import physical_lab_compute_engine as compute
    return compute


def _load_project():
    import physical_lab_project_kernel as project
    return project


def _active_project(st: Any) -> str | None:
    try:
        project = _load_project()
        raw = st.session_state.get(project.ACTIVE_PROJECT_SESSION_KEY)
        if raw:
            return str(Path(str(raw)).expanduser().resolve())
    except Exception:
        pass
    return None


def _emit(severity: str, message: str, *, detail: Mapping[str, Any] | None = None, code: str | None = None) -> None:
    try:
        from physical_lab_diagnostics import emit_event
        emit_event(
            severity,
            "kerr-platform",
            message,
            kind="experiment-workflow",
            profile=PROFILE,
            code=code,
            detail=dict(detail or {}),
        )
    except Exception:
        pass


def _render_result(st: Any, manifest: Mapping[str, Any], campaign: Mapping[str, Any]) -> None:
    screening = campaign.get("screening") or {}
    metrics = campaign.get("kerr_metrics") or {}
    status = str(screening.get("status") or "REVIEW")
    if status == "PASS":
        st.success("Kerr verification campaign: PASS for the configured computational screening criteria.")
    else:
        st.warning("Kerr verification campaign: REVIEW. Inspect signed margins and numerical diagnostics.")

    cols = st.columns(5)
    keys = (
        ("First-integral residual", "first_integral_residual_max"),
        ("Constraint residual", "constraint_residual_max"),
        ("Refinement Δ", "refinement_relative_change_max"),
        ("Horizon margin", "minimum_horizon_margin_M"),
        ("Tolerance response", "local_tolerance_response_max"),
    )
    for col, (label, key) in zip(cols, keys):
        value = metrics.get(key)
        suffix = " M" if key == "minimum_horizon_margin_M" else ""
        col.metric(label, f"{float(value):.3e}{suffix}" if value is not None else "—")

    checks = screening.get("checks") or []
    if checks:
        st.dataframe(checks, width="stretch", hide_index=True)

    sweep = campaign.get("spin_sweep") or []
    if sweep:
        import pandas as pd
        import plotly.graph_objects as go

        frame = pd.DataFrame(sweep)
        st.markdown("#### Spin-response characterization")
        quantity_options = [key for key in (
            "r_min",
            "r_max",
            "mean_phi_rate_mino",
            "photon_radial_instability_mino",
            "photon_radial_instability_coordinate_time",
        ) if key in frame.columns]
        if quantity_options:
            quantity = st.selectbox(
                "Spin-sweep observable",
                quantity_options,
                key="pl_kerr_platform_sweep_quantity",
            )
            fig = go.Figure()
            fig.add_scatter(x=frame["spin"], y=frame[quantity], mode="lines+markers", name=quantity)
            fig.update_layout(
                title=f"Kerr spin sweep · {quantity}",
                xaxis_title="a/M",
                yaxis_title=quantity,
                height=470,
            )
            st.plotly_chart(fig, width="stretch")
        with st.expander("Spin-sweep table", expanded=False):
            st.dataframe(frame, width="stretch", hide_index=True)

    sensitivity = campaign.get("sensitivity_cases") or []
    if sensitivity:
        rows = []
        for item in sensitivity:
            row = {"case": item.get("label")}
            row.update(item.get("relative_changes") or {})
            rows.append(row)
        with st.expander("Deterministic tolerance envelope", expanded=False):
            st.caption(
                "These are bounded local perturbation responses, not probabilities, confidence intervals, "
                "population yield, or measurement-derived uncertainty."
            )
            st.dataframe(rows, width="stretch", hide_index=True)

    report = render_kerr_report_markdown(manifest, campaign)
    st.download_button(
        "Download Kerr verification report (.md)",
        data=report,
        file_name="physical-lab-kerr-verification.md",
        mime="text/markdown",
        key="pl_kerr_report_download",
    )


def render_kerr_platform_workspace(st: Any, profile: str) -> None:
    if profile != PROFILE:
        return

    st.markdown("---")
    st.markdown("## Physical Lab · Kerr Experiment / Compute")
    st.caption(
        "Promote the current interactive Kerr setup into an Experiment Kernel manifest, "
        "run a worker-native verification campaign, index it in the active .physlab project, "
        "and export a reproducible V&V report."
    )

    try:
        config = _current_config(st)
        config.validate()
    except Exception as exc:
        st.info(f"Configure a valid Kerr case in the workspace above before creating an experiment: {exc}")
        return

    a, b, c, d = st.columns(4)
    a.metric("Particle", "Massive" if config.particle_type == "massive" else "Photon")
    b.metric("Spin", f"{config.spin:.3f}")
    c.metric("Inclination", f"{config.inclination_deg:.1f}°")
    d.metric("Horizon r+/M", f"{horizon_radius(config.spin):.5g}")

    left, right = st.columns([1, 1])
    preset = left.selectbox(
        "Verification depth",
        ["compact", "standard"],
        index=0,
        key="pl_kerr_platform_preset",
        help="Both presets are bounded. Standard adds a denser spin sweep and larger local sensitivity envelope.",
    )
    use_scale = right.checkbox(
        "Attach physical mass scale",
        value=False,
        key="pl_kerr_platform_use_mass_scale",
        help="Display/provenance conversion only. The numerical solver remains G=c=M=1.",
    )
    solar_masses = None
    if use_scale:
        solar_masses = st.number_input(
            "Black-hole mass (solar masses; display/provenance only)",
            min_value=1e-6,
            max_value=1e12,
            value=10.0,
            format="%.6g",
            key="pl_kerr_platform_mass_solar",
        )
        scale = geometric_scale(float(solar_masses))
        sc1, sc2 = st.columns(2)
        sc1.metric("1 M length scale", f"{scale['one_M_length_km']:.6g} km")
        sc2.metric("1 M time scale", f"{scale['one_M_time_us']:.6g} µs")

    with st.expander("Computational screening requirements", expanded=False):
        st.caption(
            "Editable project screening thresholds. They are not GR standards, certification limits, "
            "or experimental-validation criteria."
        )
        r1, r2 = st.columns(2)
        residual_limit = r1.number_input(
            "First-integral residual ≤",
            min_value=1e-12,
            max_value=1e-2,
            value=float(DEFAULT_REQUIREMENTS["first_integral_residual_max"]),
            format="%.2e",
            key="pl_kerr_req_first_integral",
        )
        constraint_limit = r2.number_input(
            "Turning/spherical constraint residual ≤",
            min_value=1e-14,
            max_value=1e-2,
            value=float(DEFAULT_REQUIREMENTS["constraint_residual_max"]),
            format="%.2e",
            key="pl_kerr_req_constraint",
        )
        r3, r4 = st.columns(2)
        refinement_limit = r3.number_input(
            "Refinement relative change ≤",
            min_value=1e-10,
            max_value=1e-1,
            value=float(DEFAULT_REQUIREMENTS["refinement_relative_change_max"]),
            format="%.2e",
            key="pl_kerr_req_refinement",
        )
        horizon_margin = r4.number_input(
            "Minimum horizon margin ≥ (M)",
            min_value=0.0,
            max_value=20.0,
            value=float(DEFAULT_REQUIREMENTS["minimum_horizon_margin_M"]),
            format="%.3g",
            key="pl_kerr_req_horizon",
        )

    requirements = {
        "first_integral_residual_max": float(residual_limit),
        "constraint_residual_max": float(constraint_limit),
        "refinement_relative_change_max": float(refinement_limit),
        "minimum_horizon_margin_M": float(horizon_margin),
    }

    manifest = build_kerr_manifest(
        config,
        preset=str(preset),
        solar_masses=float(solar_masses) if solar_masses is not None else None,
        requirements=requirements,
        source_commit=os.environ.get("PHYSICAL_LAB_SOURCE_COMMIT") or None,
    )
    st.session_state["pl_kerr_experiment_manifest"] = manifest

    active_project = _active_project(st)
    m1, m2 = st.columns([2, 1])
    m1.write({
        "experiment_sha256": manifest["experiment_sha256"],
        "model": manifest["model"]["title"],
        "model_variant": manifest["model"]["variant"],
        "execution": manifest["execution"],
    })
    m2.metric("Project", Path(active_project).stem if active_project else "Not selected")

    b1, b2 = st.columns(2)
    if b1.button(
        "Register experiment in active project",
        width="stretch",
        disabled=not bool(active_project),
        key="pl_kerr_register_project",
    ):
        try:
            project = _load_project()
            entry = project.register_experiment(active_project, manifest)
            st.success(f"Registered {entry['experiment_id']} in {Path(active_project).name}.")
            _emit("INFO", "Kerr experiment registered in project", detail=entry, code="KERR_PROJECT_REGISTERED")
        except Exception as exc:
            st.error(f"Project registration failed: {exc}")
            _emit("ERROR", f"Project registration failed: {exc}", code="KERR_PROJECT_REGISTER_FAILED")

    if b2.button(
        "Queue Kerr verification",
        type="primary",
        width="stretch",
        key="pl_kerr_queue_verification",
    ):
        try:
            compute = _load_compute()
            if active_project:
                _load_project().register_experiment(active_project, manifest)
            job = compute.submit_job(
                manifest,
                runner="model-campaign",
                runner_config={
                    "profile": PROFILE,
                    "preset": str(preset),
                    "model_variant": MODEL_VARIANT,
                },
                priority=75,
            )
            compute.start_queued_jobs(max_parallel=1)
            st.session_state["pl_kerr_last_job_id"] = job["id"]
            _emit(
                "INFO",
                "Kerr verification queued",
                detail={"job_id": job["id"], "experiment_sha256": manifest["experiment_sha256"]},
                code="KERR_JOB_QUEUED",
            )
            st.success(f"Queued {job['id']}. The persistent worker owns the run lifecycle.")
            st.rerun()
        except Exception as exc:
            st.error(f"Could not queue Kerr verification: {exc}")
            _emit("ERROR", f"Kerr queue failed: {exc}", code="KERR_JOB_QUEUE_FAILED")

    try:
        compute = _load_compute()
        compute.reconcile_jobs()
        compute.start_queued_jobs(max_parallel=1)
        jobs = []
        for row in compute.list_jobs(limit=80, profile=PROFILE):
            cfg = row.get("runner_config") or {}
            if cfg.get("model_variant") == MODEL_VARIANT:
                jobs.append(row)
        if not jobs:
            st.caption("No worker-native Kerr verification jobs yet.")
            return

        import pandas as pd
        table = pd.DataFrame([
            {
                "id": row.get("id"),
                "status": row.get("status"),
                "progress": row.get("progress"),
                "stage": row.get("stage"),
                "attempt": row.get("attempt"),
                "experiment": str(row.get("experiment_sha256") or "")[:16],
            }
            for row in jobs[:20]
        ])
        st.dataframe(table, width="stretch", hide_index=True)

        ids = [str(row["id"]) for row in jobs[:20]]
        default_id = str(st.session_state.get("pl_kerr_last_job_id") or "")
        index = ids.index(default_id) if default_id in ids else 0
        selected = st.selectbox(
            "Inspect Kerr job",
            ids,
            index=index,
            key="pl_kerr_job_inspect",
        )
        record = compute.read_job(selected) or {}
        controls = st.columns(3)
        if controls[0].button("Refresh Kerr job", width="stretch", key="pl_kerr_job_refresh"):
            st.rerun()
        if controls[1].button(
            "Cancel Kerr job",
            width="stretch",
            disabled=str(record.get("status")) not in {"queued", "running"},
            key="pl_kerr_job_cancel",
        ):
            compute.cancel_job(selected)
            st.rerun()
        if controls[2].button(
            "Retry Kerr job",
            width="stretch",
            disabled=str(record.get("status")) not in {"failed", "interrupted", "cancelled"},
            key="pl_kerr_job_retry",
        ):
            compute.requeue_job(selected)
            compute.start_queued_jobs(max_parallel=1)
            st.rerun()

        result = compute.read_result(selected)
        if active_project:
            try:
                project = _load_project()
                project.sync_compute_jobs(active_project)
            except Exception:
                pass

        if result and result.get("model_variant") == MODEL_VARIANT:
            campaign = result.get("result") or {}
            st.session_state["pl_kerr_campaign_result"] = campaign
            _render_result(st, manifest, campaign)

        log = compute.tail_log(selected)
        if log:
            with st.expander("Kerr worker log", expanded=False):
                st.code(log, language="text")
    except Exception as exc:
        st.warning(f"Kerr Compute/Project integration could not load: {exc}")

    st.caption(
        "Scientific boundary: this workflow verifies the implemented Kerr geodesic model and explores "
        "bounded local sensitivity. It does not infer real black-hole parameters or constitute experimental validation."
    )
