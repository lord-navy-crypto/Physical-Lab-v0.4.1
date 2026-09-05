"""Unified refinement workspace for Physical Lab's newest model families."""
from __future__ import annotations

import hashlib
import json
import math
import os
import uuid
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from physical_lab_new_model_refinements import (
    KERR_VARIANT,
    LATTICE_VARIANT,
    SOLAR_VARIANT,
    build_model_evidence_contract,
    kerr_frequency_refinement,
    lattice_transport_refinement,
    render_refinement_report_markdown,
    solar_commensurability_refinement,
)


def _emit(severity: str, message: str, *, profile: str, run_id: str, code: str, detail: Any = None) -> None:
    try:
        from physical_lab_diagnostics import emit_event
        emit_event(severity, "new-model-refinement", message, kind="model-refinement", profile=profile, run_id=run_id, code=code, detail=detail)
    except Exception:
        pass


def _kerr_config(st: Any):
    from physical_lab_kerr_geodesics import KerrOrbitConfig
    particle = str(st.session_state.get("pl_kerr_particle") or "massive")
    lam_key = f"pl_kerr_lam_{particle}"
    return KerrOrbitConfig(
        spin=float(st.session_state.get("pl_kerr_spin", 0.60)),
        inclination_deg=float(st.session_state.get("pl_kerr_inclination", 60.0)),
        particle_type=particle,
        periapsis=float(st.session_state.get("pl_kerr_rp", 6.5)),
        apoapsis=float(st.session_state.get("pl_kerr_ra", 10.0)),
        lam_max=float(st.session_state.get(lam_key, 20.0 if particle == "massive" else 4.0)),
        samples=int(st.session_state.get("pl_kerr_samples", 2500)),
        rtol=10.0 ** int(st.session_state.get("pl_kerr_rtol_exp", -9)),
        atol=10.0 ** int(st.session_state.get("pl_kerr_atol_exp", -11)),
    )


def _solar_config(st: Any):
    from physical_lab_solar_system_dynamics import SolarSystemConfig
    modes = {"SHORT · 80 yr": 80.0, "LONG · 500 yr": 500.0, "ULTRA_LONG · 1000 yr": 1000.0}
    mode = str(st.session_state.get("pl_solar_mode") or "SHORT · 80 yr")
    return SolarSystemConfig(
        duration_years=float(modes.get(mode, 80.0)),
        samples=int(st.session_state.get("pl_solar_samples", 2400)),
        inclination_jupiter_deg=float(st.session_state.get("pl_solar_inclination_deg", 10.0)),
        saturn_backreaction=bool(st.session_state.get("pl_solar_saturn_backreaction", True)),
        solar_1pn=bool(st.session_state.get("pl_solar_1pn", False)),
        velocity_cross=bool(st.session_state.get("pl_solar_velocity_cross", False)),
        radial_drag=bool(st.session_state.get("pl_solar_radial_drag", False)),
        velocity_cross_strength=float(st.session_state.get("pl_solar_xi", 1e-4)),
        radial_drag_strength=float(st.session_state.get("pl_solar_sigma", 1e-8)),
        rtol=float(st.session_state.get("pl_solar_rtol", 1e-10)),
        atol=float(st.session_state.get("pl_solar_atol", 1e-12)),
        max_step_years=float(st.session_state.get("pl_solar_max_step", 0.03)),
    )


def _lattice_config(st: Any):
    from physical_lab_lattice_dynamics import LatticeConfig
    stochastic = bool(st.session_state.get("pl_lat_stochastic", False))
    duration = float(st.session_state.get("pl_lat_duration", 12.0))
    ldt = float(st.session_state.get("pl_lat_ldt", 0.005))
    samples = int(st.session_state.get("pl_lat_samples", 1000))
    if stochastic:
        samples = min(10000, max(128, int(round(duration / max(ldt, 1e-12))) + 1))
        ldt = duration / max(samples - 1, 1)
    return LatticeConfig(
        nx=int(st.session_state.get("pl_lat_nx", 4)),
        ny=int(st.session_state.get("pl_lat_ny", 4)),
        layers=int(st.session_state.get("pl_lat_layers", 3)),
        stacking=str(st.session_state.get("pl_lat_stacking") or "ABA"),
        strain_x=float(st.session_state.get("pl_lat_strain", 0.0)),
        k_in=float(st.session_state.get("pl_lat_k_in", 10.0)),
        alpha=float(st.session_state.get("pl_lat_alpha", 2.0)),
        k_inter=float(st.session_state.get("pl_lat_k_inter", 3.0)),
        damping=float(st.session_state.get("pl_lat_damping", 0.02)),
        interlayer_damping=float(st.session_state.get("pl_lat_inter_damping", 0.01)),
        defect_mode=str(st.session_state.get("pl_lat_defect") or "none"),
        drive_mode=str(st.session_state.get("pl_lat_drive") or "sin"),
        drive_amplitude=float(st.session_state.get("pl_lat_drive_amp", 0.08)),
        drive_frequency=float(st.session_state.get("pl_lat_drive_freq", 1.0)),
        stochastic_mode=stochastic,
        temperature_reduced=float(st.session_state.get("pl_lat_temp", 0.0)) if stochastic else 0.0,
        seed=int(st.session_state.get("pl_lat_seed", 12345)),
        duration=duration,
        samples=samples,
        langevin_dt=ldt,
    )


def _campaign(st: Any, variant: str) -> Mapping[str, Any] | None:
    keys = {
        KERR_VARIANT: "pl_kerr_campaign_result",
        SOLAR_VARIANT: "pl_solar_system_campaign_result",
        LATTICE_VARIANT: "pl_lattice_campaign_result",
    }
    value = st.session_state.get(keys[variant])
    return value if isinstance(value, Mapping) else None


def _manifest(st: Any, variant: str, config: Any) -> Mapping[str, Any]:
    source = os.environ.get("PHYSICAL_LAB_SOURCE_COMMIT") or None
    if variant == KERR_VARIANT:
        from physical_lab_kerr_workflow import build_kerr_manifest
        existing = st.session_state.get("pl_kerr_experiment_manifest")
        return existing if isinstance(existing, Mapping) else build_kerr_manifest(config, preset="compact", source_commit=source)
    if variant == SOLAR_VARIANT:
        from physical_lab_solar_system_workflow import build_solar_system_manifest
        return build_solar_system_manifest(config, preset="compact", source_commit=source)
    from physical_lab_lattice_workflow import build_lattice_manifest
    existing = st.session_state.get("pl_lattice_manifest")
    return existing if isinstance(existing, Mapping) else build_lattice_manifest(config, preset="compact", source_commit=source)


def _persist_project_report(st: Any, variant: str, text: str, evidence: Mapping[str, Any]) -> str | None:
    active = st.session_state.get("pl_active_project_path")
    if not active:
        return None
    try:
        import physical_lab_project_kernel as project
        root = Path(str(active)).expanduser().resolve()
        reports = root / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        filename = f"new-model-refinement-{variant}-{str(evidence.get('evidence_sha256') or '')[:12]}.md"
        path = reports / filename
        path.write_text(text, encoding="utf-8")
        doc = project.open_project(root)
        entry = {
            "path": path.relative_to(root).as_posix(),
            "generated_at": project.utc_now(),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "classification": "computational-refinement-evidence",
            "model_variant": variant,
            "evidence_sha256": evidence.get("evidence_sha256"),
        }
        rows = [r for r in (doc.get("reports") or []) if isinstance(r, Mapping) and r.get("path") != entry["path"]]
        rows.append(entry)
        doc["reports"] = rows[-100:]
        project.save_project(root, doc)
        return str(path)
    except Exception:
        return None


def _finalize(st: Any, profile: str, variant: str, config: Any, refinement: Mapping[str, Any]) -> tuple[Mapping[str, Any], str]:
    manifest = _manifest(st, variant, config)
    evidence = build_model_evidence_contract(variant, manifest=manifest, campaign=_campaign(st, variant), refinement=refinement)
    st.session_state[f"pl_refinement_result_{variant}"] = refinement
    st.session_state[f"pl_refinement_evidence_{variant}"] = evidence
    report = render_refinement_report_markdown(evidence, refinement)
    st.session_state[f"pl_refinement_report_{variant}"] = report
    return evidence, report


def _render_evidence(st: Any, variant: str) -> None:
    evidence = st.session_state.get(f"pl_refinement_evidence_{variant}")
    refinement = st.session_state.get(f"pl_refinement_result_{variant}")
    if not isinstance(evidence, Mapping) or not isinstance(refinement, Mapping):
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Evidence contract", str(evidence.get("schema") or "—"))
    c2.metric("Campaign screening", str(evidence.get("computational_screening") or "NOT-RUN"))
    c3.metric("Evidence hash", str(evidence.get("evidence_sha256") or "")[:12])
    st.caption(str(evidence.get("fidelity_level") or ""))
    with st.expander("Supported / unsupported claim boundary", expanded=False):
        st.markdown("**Supported by this model/evidence layer**")
        for item in evidence.get("supported_claims") or []:
            st.write(f"• {item}")
        st.markdown("**Not supported**")
        for item in evidence.get("unsupported_claims") or []:
            st.write(f"• {item}")
    report = st.session_state.get(f"pl_refinement_report_{variant}")
    if isinstance(report, str):
        a, b = st.columns(2)
        a.download_button("Download refinement evidence", report, file_name=f"physical-lab-{variant}-refinement.md", mime="text/markdown", key=f"pl_refinement_download_{variant}", width="stretch")
        if b.button("Save evidence into active .physlab", key=f"pl_refinement_save_{variant}", width="stretch", disabled=not bool(st.session_state.get("pl_active_project_path"))):
            path = _persist_project_report(st, variant, report, evidence)
            if path:
                st.success(f"Saved {Path(path).name} and indexed it in the project report list.")
            else:
                st.warning("Could not save the refinement report into the active project.")


def _render_kerr(st: Any) -> None:
    cfg = _kerr_config(st)
    st.caption("Adds Mino-time fundamental-frequency ratios and low-order rational proximity. This remains an integrable Kerr geodesic diagnostic, not a chaos detector.")
    c1, c2, c3 = st.columns(3)
    c1.metric("a/M", f"{cfg.spin:.3f}")
    c2.metric("Inclination", f"{cfg.inclination_deg:.1f}°")
    c3.metric("Particle", cfg.particle_type)
    if st.button("Run Kerr frequency refinement", type="primary", key="pl_refinement_run_kerr", width="stretch"):
        run_id = f"refine-kerr-{uuid.uuid4().hex[:10]}"
        _emit("INFO", "Kerr frequency refinement started", profile="nonlinear-chaos", run_id=run_id, code="REFINE_KERR_START")
        try:
            existing = st.session_state.get("pl_kerr_geodesic_result")
            with st.spinner("Computing fundamental-frequency and local commensurability diagnostics..."):
                refinement = kerr_frequency_refinement(cfg, result=existing if isinstance(existing, Mapping) else None, scan=True)
            evidence, _ = _finalize(st, "nonlinear-chaos", KERR_VARIANT, cfg, refinement)
            _emit("INFO", "Kerr frequency refinement completed", profile="nonlinear-chaos", run_id=run_id, code="REFINE_KERR_COMPLETE", detail={"evidence_sha256": evidence["evidence_sha256"]})
        except Exception as exc:
            _emit("ERROR", f"{type(exc).__name__}: {exc}", profile="nonlinear-chaos", run_id=run_id, code="REFINE_KERR_FAILED")
            st.error(str(exc))
    refinement = st.session_state.get(f"pl_refinement_result_{KERR_VARIANT}")
    if isinstance(refinement, Mapping):
        ratios = refinement.get("ratios") or {}
        cols = st.columns(3)
        for col, key, label in zip(cols, ("omega_r_over_omega_theta", "omega_phi_over_omega_theta", "omega_phi_over_omega_r"), ("Ωr/Ωθ", "Ωφ/Ωθ", "Ωφ/Ωr")):
            row = ratios.get(key)
            col.metric(label, f"{float(row['ratio']):.5g} ≈ {row['nearest_low_order']}" if isinstance(row, Mapping) else "n/a")
        rows = [r for r in refinement.get("local_frequency_scan") or [] if isinstance(r, Mapping) and "error" not in r]
        if rows:
            try:
                import pandas as pd
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            except Exception:
                st.json(rows)
        st.info(str(refinement.get("boundary") or ""))
    _render_evidence(st, KERR_VARIANT)


def _render_solar(st: Any) -> None:
    cfg = _solar_config(st)
    st.caption("Adds a finite-window 5:2 projected-longitude commensurability phase and eccentricity spectral diagnostics. It deliberately does not call the proxy a canonical resonant argument.")
    if st.button("Run Solar-System resonance refinement", type="primary", key="pl_refinement_run_solar", width="stretch"):
        run_id = f"refine-solar-{uuid.uuid4().hex[:10]}"
        _emit("INFO", "Solar-system commensurability refinement started", profile="nonlinear-chaos", run_id=run_id, code="REFINE_SOLAR_START")
        try:
            from physical_lab_solar_system_dynamics import integrate_case
            existing = st.session_state.get("pl_solar_system_result")
            with st.spinner("Computing 5:2 commensurability phase and secular spectra..."):
                result = existing if isinstance(existing, Mapping) else integrate_case(cfg)
                refinement = solar_commensurability_refinement(result)
            evidence, _ = _finalize(st, "nonlinear-chaos", SOLAR_VARIANT, cfg, refinement)
            _emit("INFO", "Solar-system commensurability refinement completed", profile="nonlinear-chaos", run_id=run_id, code="REFINE_SOLAR_COMPLETE", detail={"evidence_sha256": evidence["evidence_sha256"]})
        except Exception as exc:
            _emit("ERROR", f"{type(exc).__name__}: {exc}", profile="nonlinear-chaos", run_id=run_id, code="REFINE_SOLAR_FAILED")
            st.error(str(exc))
    refinement = st.session_state.get(f"pl_refinement_result_{SOLAR_VARIANT}")
    if isinstance(refinement, Mapping):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("ψ drift", f"{float(refinement['phase_drift_rad_per_year']):+.3e} rad/yr")
        c2.metric("Phase concentration", f"{float(refinement['finite_window_circular_concentration']):.4f}")
        c3.metric("Mean Ts/Tj", f"{float(refinement['period_ratio_mean']):.6f}")
        beat = refinement.get("beat_period_years_from_phase_drift")
        c4.metric("Beat period proxy", f"{float(beat):.3g} yr" if beat is not None else "very long / unresolved")
        try:
            import plotly.graph_objects as go
            fig = go.Figure(go.Scatter(x=np.asarray(refinement["time_years"], dtype=float), y=np.asarray(refinement["phase_wrapped_rad"], dtype=float), mode="lines"))
            fig.update_layout(title="5:2 projected-longitude commensurability phase proxy", xaxis_title="time (yr)", yaxis_title="wrapped ψ (rad)")
            st.plotly_chart(fig, width="stretch")
        except Exception:
            pass
        with st.expander("Secular eccentricity spectra", expanded=False):
            st.json({"Jupiter": refinement.get("jupiter_eccentricity_spectrum"), "Saturn": refinement.get("saturn_eccentricity_spectrum")})
        st.info(str(refinement.get("boundary") or ""))
    _render_evidence(st, SOLAR_VARIANT)


def _render_lattice(st: Any) -> None:
    cfg = _lattice_config(st)
    st.caption("Adds path-projected dω/dq, adjacent-branch gap diagnostics and a bounded affine-strain dispersion sweep to the harmonic Bloch reference.")
    if st.button("Run phonon transport refinement", type="primary", key="pl_refinement_run_lattice", width="stretch"):
        run_id = f"refine-lattice-{uuid.uuid4().hex[:10]}"
        _emit("INFO", "Lattice transport refinement started", profile="oscillation-integration", run_id=run_id, code="REFINE_LATTICE_START")
        try:
            with st.spinner("Computing group velocity, branch gaps and strain dispersion sweep..."):
                refinement = lattice_transport_refinement(cfg, points_per_segment=36, strain_sweep=True)
            evidence, _ = _finalize(st, "oscillation-integration", LATTICE_VARIANT, cfg, refinement)
            _emit("INFO", "Lattice transport refinement completed", profile="oscillation-integration", run_id=run_id, code="REFINE_LATTICE_COMPLETE", detail={"evidence_sha256": evidence["evidence_sha256"]})
        except Exception as exc:
            _emit("ERROR", f"{type(exc).__name__}: {exc}", profile="oscillation-integration", run_id=run_id, code="REFINE_LATTICE_FAILED")
            st.error(str(exc))
    refinement = st.session_state.get(f"pl_refinement_result_{LATTICE_VARIANT}")
    if isinstance(refinement, Mapping):
        gap = refinement.get("gap_diagnostics") or {}
        c1, c2, c3 = st.columns(3)
        vmax = refinement.get("max_abs_path_group_velocity")
        c1.metric("Max |dω/dq|", f"{float(vmax):.5g}" if vmax is not None else "n/a")
        c2.metric("Min positive branch gap", f"{float(gap['minimum_positive_adjacent_gap']):.5g}" if gap.get("minimum_positive_adjacent_gap") is not None else "n/a")
        c3.metric("Γ zero modes", int((refinement.get("dispersion_summary") or {}).get("gamma_zero_mode_count", -1)))
        rows = refinement.get("strain_sweep") or []
        if rows:
            try:
                import plotly.graph_objects as go
                x = [row["strain_x"] for row in rows]
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=x, y=[row["frequency_max"] for row in rows], mode="lines+markers", name="max frequency"))
                fig.add_trace(go.Scatter(x=x, y=[row["max_abs_path_group_velocity"] for row in rows], mode="lines+markers", name="max |dω/dq|", yaxis="y2"))
                fig.update_layout(title="Bounded strain response of harmonic dispersion", xaxis_title="affine x strain", yaxis_title="frequency", yaxis2={"title":"reduced path group velocity","overlaying":"y","side":"right"})
                st.plotly_chart(fig, width="stretch")
            except Exception:
                st.json(rows)
        st.info(str(refinement.get("boundary") or ""))
    _render_evidence(st, LATTICE_VARIANT)


def render_new_model_refinement_for_variant(st: Any, variant: str) -> None:
    """Render only one strengthened model's refinement/evidence workspace."""
    st.markdown("---")
    st.markdown("## Physical Lab · Model Refinement Evidence")
    if variant == KERR_VARIANT:
        _render_kerr(st)
    elif variant == SOLAR_VARIANT:
        _render_solar(st)
    elif variant == LATTICE_VARIANT:
        _render_lattice(st)
    else:
        raise ValueError(f"unsupported refinement model variant: {variant}")


def render_new_model_refinement_workspace(st: Any, profile: str) -> None:
    if profile not in {"nonlinear-chaos", "oscillation-integration"}:
        return
    st.markdown("---")
    st.markdown("## Physical Lab · New Model Refinement Studio")
    st.caption(
        "Shared evidence layer for recently promoted models. It deepens diagnostics without silently changing solver equations. "
        "Each refinement produces a Model Evidence Contract with a scientific claim boundary and reproducibility hash."
    )
    if profile == "nonlinear-chaos":
        tab1, tab2 = st.tabs(["Kerr frequency structure", "Sun–Jupiter–Saturn 5:2 structure"])
        with tab1:
            _render_kerr(st)
        with tab2:
            _render_solar(st)
    else:
        _render_lattice(st)
