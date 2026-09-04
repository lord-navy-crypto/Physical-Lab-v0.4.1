"""Streamlit workspace for the Physical Lab Kerr geodesic model."""
from __future__ import annotations

import uuid
from typing import Any

import numpy as np

from physical_lab_kerr_geodesics import (
    PROFILE,
    KerrOrbitConfig,
    integrate_case,
    oblate_xyz,
    result_summary,
    run_refinement_pair,
)


def _emit(severity: str, message: str, *, run_id: str, detail: Any = None, code: str | None = None) -> None:
    try:
        from physical_lab_diagnostics import emit_event
        emit_event(
            severity,
            "kerr-geodesic-model",
            message,
            kind="model-run",
            profile=PROFILE,
            run_id=run_id,
            code=code,
            detail=detail,
        )
    except Exception:
        pass


def _plotly():
    import plotly.graph_objects as go
    return go


def _single_orbit_tab(st: Any) -> None:
    c1, c2, c3, c4 = st.columns(4)
    particle = c1.selectbox(
        "Particle",
        ["massive", "photon"],
        format_func=lambda x: "Massive bound orbit" if x == "massive" else "Spherical photon orbit",
        key="pl_kerr_particle",
    )
    spin = c2.slider("Spin a/M", 0.0, 0.98, 0.60, 0.01, key="pl_kerr_spin")
    inclination = c3.slider(
        "Inclination from equator (deg)", 0.0, 85.0, 60.0, 1.0, key="pl_kerr_inclination"
    )
    lam_default = 20.0 if particle == "massive" else 4.0
    lam_max = c4.number_input(
        "Mino-time span",
        min_value=0.5,
        max_value=80.0,
        value=lam_default,
        step=0.5,
        key=f"pl_kerr_lam_{particle}",
    )

    rp, ra = 6.5, 10.0
    if particle == "massive":
        q1, q2 = st.columns(2)
        rp = q1.number_input(
            "Periapsis r_p / M", min_value=2.05, max_value=40.0, value=6.5, step=0.1, key="pl_kerr_rp"
        )
        ra = q2.number_input(
            "Apoapsis r_a / M",
            min_value=float(rp) + 0.1,
            max_value=80.0,
            value=max(10.0, float(rp) + 0.5),
            step=0.1,
            key="pl_kerr_ra",
        )

    n1, n2, n3 = st.columns(3)
    samples = n1.select_slider(
        "Display samples", options=[800, 1200, 1800, 2500, 4000], value=2500, key="pl_kerr_samples"
    )
    rtol_exp = n2.slider("log10(rtol)", -12, -6, -9, key="pl_kerr_rtol_exp")
    atol_exp = n3.slider("log10(atol)", -14, -8, -11, key="pl_kerr_atol_exp")

    config = KerrOrbitConfig(
        spin=float(spin),
        inclination_deg=float(inclination),
        particle_type=str(particle),
        periapsis=float(rp),
        apoapsis=float(ra),
        lam_max=float(lam_max),
        samples=int(samples),
        rtol=10.0 ** int(rtol_exp),
        atol=10.0 ** int(atol_exp),
    )

    if st.button("Run Kerr geodesic", type="primary", key="pl_kerr_run"):
        run_id = f"kerr-{uuid.uuid4().hex[:12]}"
        _emit(
            "INFO",
            "Kerr geodesic run started",
            run_id=run_id,
            detail={"particle_type": particle, "spin": float(spin), "inclination_deg": float(inclination)},
        )
        try:
            with st.spinner("Solving constants of motion and integrating the geodesic..."):
                result = integrate_case(config)
            summary = result_summary(result)
            st.session_state["pl_kerr_geodesic_result"] = result
            st.session_state["pl_kerr_geodesic_summary"] = summary
            st.session_state["pl_kerr_run_id"] = run_id
            severity = "WARNING" if (
                result["status"] != "completed"
                or summary["first_integral_residual_max"] > 1e-6
            ) else "INFO"
            _emit(
                severity,
                "Kerr geodesic run completed" if severity == "INFO" else "Kerr geodesic run completed with review flags",
                run_id=run_id,
                detail={
                    "particle_type": particle,
                    "spin": float(spin),
                    "status": result["status"],
                    "nfev": int(result["nfev"]),
                    "first_integral_residual_max": float(summary["first_integral_residual_max"]),
                },
                code="KERR_REVIEW" if severity == "WARNING" else "KERR_COMPLETE",
            )
        except Exception as exc:
            _emit("ERROR", f"{type(exc).__name__}: {exc}", run_id=run_id, code="KERR_RUN_FAILED")
            st.error(str(exc))

    result = st.session_state.get("pl_kerr_geodesic_result")
    if not result:
        return

    summary = result_summary(result)
    cols = st.columns(5)
    cols[0].metric("E", f"{summary['E']:.7g}")
    cols[1].metric("Lz", f"{summary['Lz']:.7g}")
    cols[2].metric("Q", f"{summary['Q']:.7g}")
    cols[3].metric("r range", f"{summary['r_min']:.4g}–{summary['r_max']:.4g} M")
    cols[4].metric("Invariant residual", f"{summary['first_integral_residual_max']:.2e}")

    if result["status"] != "completed":
        st.warning(f"Integrator status: {result['status']}")
    elif summary["first_integral_residual_max"] > 1e-6:
        st.warning("First-integral residual exceeds the default 1e-6 numerical review threshold.")
    else:
        st.success("Run completed with first-integral residual below the default numerical review threshold.")

    case = result["case"]
    lam = result["lambda"]
    y = result["state"]
    r, th, phi, pr, pth = y[1], y[2], y[3], y[4], y[5]
    x, yy, z = oblate_xyz(r, th, phi, case["a"])
    go = _plotly()

    fig3d = go.Figure()
    fig3d.add_scatter3d(x=x, y=yy, z=z, mode="lines", name=particle)
    fig3d.add_scatter3d(x=[x[0]], y=[yy[0]], z=[z[0]], mode="markers", name="start", marker={"size": 5})
    fig3d.update_layout(
        title="Kerr orbit coordinate view",
        scene={"xaxis_title": "x/M", "yaxis_title": "y/M", "zaxis_title": "z/M", "aspectmode": "data"},
        height=650,
    )
    st.plotly_chart(fig3d, width="stretch")

    f1 = go.Figure()
    f1.add_scatter(x=lam, y=r, mode="lines", name="r/M")
    f1.add_scatter(x=lam, y=th, mode="lines", name="theta [rad]", yaxis="y2")
    f1.update_layout(
        title="Radial and polar motion in Mino time",
        xaxis_title="Mino time λ",
        yaxis={"title": "r/M"},
        yaxis2={"title": "θ [rad]", "overlaying": "y", "side": "right"},
        height=520,
    )
    st.plotly_chart(f1, width="stretch")

    p1, p2 = st.columns(2)
    fr = go.Figure()
    fr.add_scatter(x=r, y=pr, mode="lines", name="radial phase curve")
    fr.update_layout(title="Radial phase portrait", xaxis_title="r/M", yaxis_title="dr/dλ", height=450)
    p1.plotly_chart(fr, width="stretch")
    ft = go.Figure()
    ft.add_scatter(x=th, y=pth, mode="lines", name="polar phase curve")
    ft.update_layout(title="Polar phase portrait", xaxis_title="θ [rad]", yaxis_title="dθ/dλ", height=450)
    p2.plotly_chart(ft, width="stretch")

    diag = result["diagnostics"]
    if len(diag["poincare_theta"]):
        fp = go.Figure()
        fp.add_scatter(
            x=diag["poincare_theta"], y=diag["poincare_ptheta"], mode="markers", name="periapsis section"
        )
        fp.update_layout(
            title="Poincaré-style section at radial periapsis",
            xaxis_title="θ [rad]",
            yaxis_title="pθ=dθ/dλ",
            height=450,
        )
        st.plotly_chart(fp, width="stretch")
        st.caption(
            "For the unperturbed Kerr geodesic problem, this is an invariant-torus diagnostic; "
            "it should not be interpreted as a chaos claim."
        )

    if particle == "photon":
        instability = diag["photon_instability"]
        i1, i2 = st.columns(2)
        i1.metric("Radial instability γλ", f"{instability['mino_exponent']:.5g} per λ")
        i2.metric(
            "Approx. coordinate-time γt",
            f"{instability['coordinate_time_exponent']:.5g} per t"
            if np.isfinite(instability["coordinate_time_exponent"]) else "n/a",
        )
        st.caption(
            "The spherical photon orbit is radially unstable. This local exponent comes from the "
            "curvature of the radial potential around r0, not from a generic phase-space MLE."
        )


def _comparison_tab(st: Any) -> None:
    st.markdown("### Same spacetime, two geodesic classes")
    st.caption(
        "Runs a bound massive orbit and a prograde spherical photon orbit at the same Kerr spin and "
        "inclination. Their Mino-time spans are independent, so overlays compare geometry/phase structure "
        "rather than synchronized physical time."
    )
    c1, c2 = st.columns(2)
    spin = c1.slider("Comparison spin a/M", 0.0, 0.98, 0.60, 0.01, key="pl_kerr_cmp_spin")
    incl = c2.slider("Comparison inclination (deg)", 0.0, 80.0, 60.0, 1.0, key="pl_kerr_cmp_incl")

    if st.button("Run massive ↔ photon comparison", key="pl_kerr_cmp_run"):
        run_id = f"kerr-compare-{uuid.uuid4().hex[:10]}"
        try:
            _emit("INFO", "Kerr massive/photon comparison started", run_id=run_id, detail={"spin": float(spin), "inclination_deg": float(incl)})
            massive = integrate_case(
                KerrOrbitConfig(spin=float(spin), inclination_deg=float(incl), particle_type="massive", periapsis=6.5, apoapsis=10.0, lam_max=10.0, samples=1500)
            )
            photon = integrate_case(
                KerrOrbitConfig(spin=float(spin), inclination_deg=float(incl), particle_type="photon", lam_max=3.0, samples=1000)
            )
            st.session_state["pl_kerr_dual_compare"] = {"massive": massive, "photon": photon}
            _emit(
                "INFO",
                "Kerr massive/photon comparison completed",
                run_id=run_id,
                detail={
                    "massive_status": massive["status"],
                    "photon_status": photon["status"],
                    "massive_residual": massive["residuals"]["combined_max"],
                    "photon_residual": photon["residuals"]["combined_max"],
                },
            )
        except Exception as exc:
            _emit("ERROR", f"{type(exc).__name__}: {exc}", run_id=run_id, code="KERR_COMPARE_FAILED")
            st.error(str(exc))

    pair = st.session_state.get("pl_kerr_dual_compare")
    if not pair:
        return
    massive, photon = pair["massive"], pair["photon"]
    ms, ps = result_summary(massive), result_summary(photon)
    st.dataframe(
        [
            {"particle": "massive", "E": ms["E"], "Lz": ms["Lz"], "Q": ms["Q"], "r_min": ms["r_min"], "r_max": ms["r_max"], "invariant_residual": ms["first_integral_residual_max"]},
            {"particle": "photon", "E": ps["E"], "Lz": ps["Lz"], "Q": ps["Q"], "r_min": ps["r_min"], "r_max": ps["r_max"], "invariant_residual": ps["first_integral_residual_max"]},
        ],
        width="stretch",
        hide_index=True,
    )
    go = _plotly()
    fig = go.Figure()
    for name, result in (("massive", massive), ("photon", photon)):
        case = result["case"]
        state = result["state"]
        x, y, z = oblate_xyz(state[1], state[2], state[3], case["a"])
        fig.add_scatter3d(x=x, y=y, z=z, mode="lines", name=name)
    fig.update_layout(
        title="Massive and photon coordinate trajectories",
        scene={"xaxis_title": "x/M", "yaxis_title": "y/M", "zaxis_title": "z/M", "aspectmode": "data"},
        height=650,
    )
    st.plotly_chart(fig, width="stretch")


def _sweep_tab(st: Any) -> None:
    s1, s2, s3 = st.columns(3)
    particle = s1.selectbox("Sweep particle", ["massive", "photon"], key="pl_kerr_sweep_particle")
    spin_text = s2.text_input("a/M values", "0,0.15,0.30,0.45,0.60,0.75,0.90", key="pl_kerr_sweep_spins")
    incl = s3.slider("Sweep inclination (deg)", 0.0, 80.0, 60.0, 1.0, key="pl_kerr_sweep_incl")
    if st.button("Run spin sweep", key="pl_kerr_sweep_run"):
        run_id = f"kerr-sweep-{uuid.uuid4().hex[:10]}"
        try:
            spins = sorted({float(x.strip()) for x in spin_text.split(",") if x.strip()})
            if not spins or min(spins) < 0 or max(spins) >= 1:
                raise ValueError("spin list must contain values in [0,1)")
            rows = []
            bar = st.progress(0.0, text="Kerr spin sweep")
            _emit("INFO", "Kerr spin sweep started", run_id=run_id, detail={"count": len(spins), "particle_type": particle})
            for idx, aval in enumerate(spins):
                cfg = KerrOrbitConfig(
                    spin=aval,
                    inclination_deg=float(incl),
                    particle_type=str(particle),
                    periapsis=6.5,
                    apoapsis=10.0,
                    lam_max=8.0 if particle == "massive" else 2.5,
                    samples=900,
                )
                rows.append(result_summary(integrate_case(cfg)))
                bar.progress((idx + 1) / len(spins), text=f"Spin {idx + 1}/{len(spins)}")
            st.session_state["pl_kerr_spin_sweep"] = rows
            _emit("INFO", "Kerr spin sweep completed", run_id=run_id, detail={"count": len(rows), "particle_type": particle})
        except Exception as exc:
            _emit("ERROR", f"{type(exc).__name__}: {exc}", run_id=run_id, code="KERR_SWEEP_FAILED")
            st.error(str(exc))

    rows = st.session_state.get("pl_kerr_spin_sweep")
    if not rows:
        return
    st.dataframe(rows, width="stretch", hide_index=True)
    spins = [float(row["spin"]) for row in rows]
    go = _plotly()
    fig = go.Figure()
    fig.add_scatter(x=spins, y=[float(row["r_min"]) for row in rows], mode="lines+markers", name="r min")
    fig.add_scatter(x=spins, y=[float(row["r_max"]) for row in rows], mode="lines+markers", name="r max")
    fig.update_layout(title="Radial range vs Kerr spin", xaxis_title="a/M", yaxis_title="r/M", height=480)
    st.plotly_chart(fig, width="stretch")
    if particle == "photon":
        inst = go.Figure()
        inst.add_scatter(
            x=spins,
            y=[float(row["photon_radial_instability_mino"]) for row in rows],
            mode="lines+markers",
            name="γλ",
        )
        inst.update_layout(
            title="Spherical-photon radial instability vs spin",
            xaxis_title="a/M",
            yaxis_title="γλ [1/Mino-time]",
            height=480,
        )
        st.plotly_chart(inst, width="stretch")


def _verification_tab(st: Any) -> None:
    st.markdown("### Solver-refinement / invariant audit")
    st.caption(
        "Runs the same physical case with looser and tighter RK45 tolerances. Agreement plus first-integral "
        "residuals are numerical verification evidence, not experimental validation."
    )
    if st.button("Run refinement audit", key="pl_kerr_refine"):
        particle = str(st.session_state.get("pl_kerr_particle", "massive"))
        base = KerrOrbitConfig(
            spin=float(st.session_state.get("pl_kerr_spin", 0.6)),
            inclination_deg=float(st.session_state.get("pl_kerr_inclination", 60.0)),
            particle_type=particle,
            periapsis=float(st.session_state.get("pl_kerr_rp", 6.5)),
            apoapsis=float(st.session_state.get("pl_kerr_ra", 10.0)),
            lam_max=float(st.session_state.get(f"pl_kerr_lam_{particle}", 8.0)),
            samples=1200,
        )
        run_id = f"kerr-verify-{uuid.uuid4().hex[:10]}"
        try:
            _emit("INFO", "Kerr refinement audit started", run_id=run_id)
            audit = run_refinement_pair(base)
            st.session_state["pl_kerr_refinement"] = audit
            severity = "WARNING" if audit["tight_residual"] > 1e-6 else "INFO"
            _emit(
                severity,
                "Kerr refinement audit completed",
                run_id=run_id,
                detail={"tight_residual": audit["tight_residual"], "absolute_deltas": audit["absolute_deltas"]},
            )
        except Exception as exc:
            _emit("ERROR", f"{type(exc).__name__}: {exc}", run_id=run_id, code="KERR_VERIFY_FAILED")
            st.error(str(exc))
    audit = st.session_state.get("pl_kerr_refinement")
    if audit:
        v1, v2 = st.columns(2)
        v1.metric("Loose invariant residual", f"{audit['loose']['first_integral_residual_max']:.2e}")
        v2.metric("Tight invariant residual", f"{audit['tight']['first_integral_residual_max']:.2e}")
        st.json(audit["absolute_deltas"])
        st.caption(
            "Default numerical screening target: tight first-integral residual ≤ 1e-6. This is a project "
            "screening criterion, not a GR code-certification standard."
        )


def render_kerr_geodesic_workspace(st: Any, profile: str) -> None:
    if profile != PROFILE:
        return
    st.markdown("---")
    st.markdown("## Physical Lab · Kerr Geodesic Dynamics")
    st.caption(
        "Relativistic dynamics in geometric units G=c=M=1. Standard Kerr geodesics are integrable; "
        "phase-space and stability views here are numerical/V&V tools, not a claim of generic chaos."
    )
    with st.expander("Scientific boundary & assumptions", expanded=False):
        st.markdown(
            "- Boyer–Lindquist coordinates and Carter–Mino time.\n"
            "- Test particles/photons only: no self-force, radiation reaction, accretion flow, plasma refraction, or spacetime perturbations.\n"
            "- The 3D view is an oblate-coordinate visualization, not a Euclidean embedding of Kerr spatial geometry.\n"
            "- Photon instability is obtained from local radial-potential curvature; it is not reported as a generic maximal Lyapunov exponent."
        )
    tab_run, tab_compare, tab_sweep, tab_verify = st.tabs(
        ["Single orbit", "Massive ↔ photon", "Spin sweep", "Numerical verification"]
    )
    with tab_run:
        _single_orbit_tab(st)
    with tab_compare:
        _comparison_tab(st)
    with tab_sweep:
        _sweep_tab(st)
    with tab_verify:
        _verification_tab(st)
