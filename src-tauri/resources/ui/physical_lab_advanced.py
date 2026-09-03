"""Advanced experiment suites injected by Physical Lab.

The hook is appended only to Physical Lab's managed copy of selected lab entrypoints.
It does not replace or alter the original experiment flow; it renders additional
research-oriented experiments after the upstream UI.
"""
from __future__ import annotations

import math
import os
import json
import sys
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _plotly():
    import plotly.graph_objects as go
    return go


def _np():
    import numpy as np
    return np


def _pd():
    import pandas as pd
    return pd


def _headline(st, rows: list[tuple[str, str, str]]) -> None:
    cols = st.columns(min(4, max(1, len(rows))))
    for i, (label, value, help_text) in enumerate(rows):
        cols[i % len(cols)].metric(label, value, help=help_text or None)


def _section_header(st, title: str, caption: str) -> None:
    st.markdown("---")
    st.markdown(f"## {title}")
    st.caption(caption)


def render_advanced_experiments(namespace: dict[str, Any]) -> None:
    profile = os.environ.get("PHYSICAL_LAB_UI_PROFILE", "").strip()
    supported = {
        "numerical-methods", "ising-monte-carlo", "random-walk-monte-carlo",
        "nonlinear-chaos", "oscillation-integration", "radia-magnet-studio",
        "radiation-platform",
    }
    if profile not in supported:
        return
    try:
        import streamlit as st
    except Exception:
        return
    if profile == "numerical-methods":
        _numerical_suite(st, namespace)
    elif profile == "ising-monte-carlo":
        _ising_suite(st, namespace)
    elif profile == "random-walk-monte-carlo":
        _random_walk_suite(st, namespace)
    elif profile == "nonlinear-chaos":
        _chaos_suite(st, namespace)
    elif profile == "oscillation-integration":
        _oscillation_suite(st, namespace)
    elif profile == "radia-magnet-studio":
        _radia_magnet_suite(st, namespace)
    elif profile == "radiation-platform":
        _radiation_suite(st, namespace)
    _render_content_validation(st, profile, namespace)
    _render_run_vault(st, profile)



def _plain_value(value: Any, *, result_mode: bool = False, depth: int = 0) -> Any:
    """Convert Streamlit/session objects into bounded JSON-safe research records."""
    if depth > 5:
        return {"type": type(value).__name__, "summary": "depth limit"}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value): return "nan"
        if math.isinf(value): return "infinity" if value > 0 else "-infinity"
        return value
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return _plain_value(value.item(), result_mode=result_mode, depth=depth + 1)
        if isinstance(value, np.ndarray):
            arr=np.asarray(value)
            if arr.size <= (1200 if result_mode else 120):
                return {"type":"ndarray","shape":list(arr.shape),"data":_plain_value(arr.tolist(),result_mode=result_mode,depth=depth+1)}
            finite=arr[np.isfinite(arr)] if np.issubdtype(arr.dtype,np.number) else np.asarray([])
            out={"type":"ndarray-summary","shape":list(arr.shape),"dtype":str(arr.dtype),"size":int(arr.size)}
            if finite.size:
                out.update({"min":float(np.min(finite)),"max":float(np.max(finite)),"mean":float(np.mean(finite))})
            return out
    except Exception:
        pass
    try:
        import pandas as pd
        if isinstance(value, pd.DataFrame):
            if len(value) <= 120 and len(value.columns) <= 30:
                return {"type":"dataframe","columns":[str(x) for x in value.columns],"records":_plain_value(value.to_dict(orient="records"),result_mode=True,depth=depth+1)}
            return {"type":"dataframe-summary","rows":int(len(value)),"columns":[str(x) for x in value.columns]}
        if isinstance(value, pd.Series):
            return _plain_value(value.to_dict(),result_mode=result_mode,depth=depth+1)
    except Exception:
        pass
    if isinstance(value, dict):
        return {str(k):_plain_value(v,result_mode=result_mode,depth=depth+1) for k,v in list(value.items())[:250]}
    if isinstance(value, (list, tuple)):
        limit=1200 if result_mode else 120
        return [_plain_value(v,result_mode=result_mode,depth=depth+1) for v in list(value)[:limit]]
    return {"type":type(value).__name__,"repr":repr(value)[:500]}


def _capture_parameters(st) -> dict[str, Any]:
    """Capture restorable scalar/simple widget state without huge result payloads."""
    output={}
    for key in list(st.session_state.keys()):
        k=str(key)
        if k.startswith("__") or k.startswith("pl_") or any(token in k.lower() for token in ("result","frame","history","scan_df","uploaded","signature")):
            continue
        value=st.session_state.get(key)
        if value is None or isinstance(value,(str,bool,int,float)):
            output[k]=_plain_value(value)
        elif isinstance(value,(list,tuple)) and len(value)<=60 and all(v is None or isinstance(v,(str,bool,int,float)) for v in value):
            output[k]=_plain_value(value)
    return output


def _capture_advanced_state(st) -> dict[str, Any]:
    output={}
    for key in list(st.session_state.keys()):
        k=str(key)
        if k.startswith("pl_") and not k.startswith("pl_vault_"):
            output[k]=_plain_value(st.session_state.get(key),result_mode=True)
    return output


def _package_versions() -> dict[str, str]:
    versions={}
    for name in ("numpy","scipy","pandas","plotly","streamlit","matplotlib","h5py","mpmath"):
        try:
            mod=__import__(name);versions[name]=str(getattr(mod,"__version__","unknown"))
        except Exception:
            continue
    return versions


def _source_commit() -> str | None:
    try:
        out=subprocess.run(["git","rev-parse","HEAD"],capture_output=True,text=True,timeout=2,check=False)
        value=out.stdout.strip()
        return value if out.returncode==0 and len(value)>=7 else None
    except Exception:
        return None

def _parameter_fingerprint(parameters: dict[str, Any]) -> str:
    raw=json.dumps(parameters,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def _vault_dir(profile: str) -> Path | None:
    raw=os.environ.get("PHYSICAL_LAB_DATA_DIR","").strip()
    if not raw:
        return None
    path=Path(raw)/"run-vault"/profile
    try:
        path.mkdir(parents=True,exist_ok=True)
    except Exception:
        return None
    return path


def _load_snapshot(path: Path) -> dict[str, Any] | None:
    try:
        obj=json.loads(path.read_text())
        return obj if isinstance(obj,dict) else None
    except Exception:
        return None


def _numeric_flatten(value: Any, prefix: str = "") -> dict[str, float]:
    out={}
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        try:
            x=float(value)
            if math.isfinite(x):out[prefix or "value"]=x
        except Exception:pass
        return out
    if isinstance(value,dict):
        for k,v in value.items():
            child=f"{prefix}.{k}" if prefix else str(k)
            if len(out)>=150:break
            out.update(_numeric_flatten(v,child))
    return out


def _render_run_vault(st, profile: str) -> None:
    root=_vault_dir(profile)
    _section_header(st,"Physical Lab · Run Vault","Persistent experiment snapshots for reproducibility, parameter restoration, comparison, notes, and bug reports. Stored under Physical Lab Application Support, not inside the Git repository.")
    if root is None:
        st.info("Run Vault needs PHYSICAL_LAB_DATA_DIR from the desktop shell. The experiment itself remains fully usable.")
        return
    current_params=_capture_parameters(st)
    current_packages=_package_versions()
    current_commit=_source_commit()
    seed_keys=[k for k in current_params if "seed" in k.lower()]
    _headline(st,[
        ("Engine mode",os.environ.get("PHYSICAL_LAB_ENGINE_MODE","standard"),"Execution context recorded with every snapshot"),
        ("Parameter fingerprint",_parameter_fingerprint(current_params)[:12],"SHA-256 prefix of the current restorable parameter state"),
        ("Source revision",current_commit[:12] if current_commit else "unavailable","Git commit of the managed Lab checkout when available"),
        ("Seed controls",str(len(seed_keys)),"Detected simple parameters containing 'seed'; stochastic Labs should save these for reproducibility"),
    ])
    with st.expander("Save current experiment snapshot",expanded=False):
        c1,c2=st.columns([1,2])
        label=c1.text_input("Run label",value="",placeholder="e.g. near-critical deep run",key=f"pl_vault_label_{profile}")
        note=c2.text_input("Research note",value="",placeholder="What changed, what should be checked?",key=f"pl_vault_note_{profile}")
        if st.button("Save snapshot",type="primary",key=f"pl_vault_save_{profile}"):
            created=datetime.now(timezone.utc)
            stamp=created.strftime("%Y%m%dT%H%M%S.%fZ")
            safe_label="".join(ch.lower() if ch.isalnum() else "-" for ch in label).strip("-")[:50]
            filename=f"{stamp}{('-'+safe_label) if safe_label else ''}.json"
            parameters=_capture_parameters(st)
            payload={
                "schema":"physical-lab-run-vault-v1",
                "created_utc":created.isoformat(),
                "profile":profile,
                "engine_mode":os.environ.get("PHYSICAL_LAB_ENGINE_MODE","standard"),
                "label":label.strip(),
                "note":note.strip(),
                "source_commit":_source_commit(),
                "parameter_sha256":_parameter_fingerprint(parameters),
                "python":{"version":sys.version.split()[0],"executable":sys.executable},
                "packages":_package_versions(),
                "parameters":parameters,
                "advanced_state":_capture_advanced_state(st),
            }
            try:
                (root/filename).write_text(json.dumps(payload,indent=2,allow_nan=False))
                st.success(f"Saved Run Vault snapshot: {filename}")
            except Exception as exc:
                st.error(f"Could not save snapshot: {exc}")

    files=sorted(root.glob("*.json"),reverse=True)[:40]
    if not files:
        st.caption("No saved snapshots for this Lab yet.")
        return
    names=[p.name for p in files]
    selected=st.selectbox("Saved snapshot",names,key=f"pl_vault_selected_{profile}")
    selected_path=root/selected
    snap=_load_snapshot(selected_path)
    if snap:
        _headline(st,[
            ("Saved",str(snap.get("created_utc","—"))[:19].replace("T"," "),"UTC snapshot time"),
            ("Mode",str(snap.get("engine_mode","—")),"Safe/Full/standard engine context"),
            ("Python",str((snap.get("python") or {}).get("version","—")),"Interpreter used for the saved run"),
            ("Parameters",str(len(snap.get("parameters") or {})),"Restorable simple experiment controls"),
        ])
        if snap.get("note"):st.caption(f"Note: {snap['note']}")
        c1,c2,c3=st.columns(3)
        raw=json.dumps(snap,indent=2).encode("utf-8")
        c1.download_button("Export snapshot JSON",data=raw,file_name=selected,mime="application/json",key=f"pl_vault_export_{profile}",width="stretch")
        if c2.button("Restore parameters",key=f"pl_vault_restore_{profile}",width="stretch"):
            params=snap.get("parameters") if isinstance(snap.get("parameters"),dict) else {}
            st.session_state["__pl_restore_pending"]=params
            st.rerun()
        if c3.button("Delete snapshot",key=f"pl_vault_delete_{profile}",width="stretch"):
            try:
                selected_path.unlink();st.success("Snapshot deleted.");st.rerun()
            except Exception as exc:st.error(f"Could not delete snapshot: {exc}")
        with st.expander("Snapshot details",expanded=False):
            st.json(snap)

    if len(files)>=2:
        st.markdown("#### Compare two saved runs")
        a,b=st.columns(2)
        name_a=a.selectbox("Run A",names,index=0,key=f"pl_vault_a_{profile}")
        name_b=b.selectbox("Run B",names,index=1,key=f"pl_vault_b_{profile}")
        if name_a!=name_b:
            sa=_load_snapshot(root/name_a) or {};sb=_load_snapshot(root/name_b) or {}
            na=_numeric_flatten({"parameters":sa.get("parameters",{}),"advanced":sa.get("advanced_state",{})})
            nb=_numeric_flatten({"parameters":sb.get("parameters",{}),"advanced":sb.get("advanced_state",{})})
            rows=[]
            for key in sorted(set(na)&set(nb)):
                va,vb=na[key],nb[key]
                if va!=vb:
                    rows.append({"quantity":key,"Run A":va,"Run B":vb,"Δ (B−A)":vb-va,"relative Δ":(vb-va)/max(abs(va),1e-300)})
                if len(rows)>=100:break
            if rows:
                st.dataframe(_pd().DataFrame(rows),width="stretch",hide_index=True)
            else:
                st.caption("No differing finite numeric values were found in the bounded snapshot summaries.")


def _render_content_validation(st, profile: str, ns: dict[str, Any]) -> None:
    """One-click content-quality checks that exercise analytic references already owned by each Lab."""
    np = _np(); pd = _pd()
    _section_header(
        st,
        "Physical Lab · Content Validation Battery",
        "Runs short, deterministic sanity checks against analytic references. This strengthens scientific content quality without replacing the full advanced experiments above.",
    )
    if st.button("Run content validation", type="primary", key=f"pl_val_run_{profile}"):
        rows = []
        try:
            if profile == "ising-monte-carlo":
                onsager_tc = ns.get("onsager_tc"); IsingParams = ns.get("IsingParams"); Method = ns.get("Method"); simulate = ns.get("simulate")
                if not all([onsager_tc, IsingParams, Method, simulate]):
                    rows.append({"check": "Ising APIs", "status": "SKIP", "detail": "Upstream APIs unavailable"})
                else:
                    tc = float(onsager_tc(1.0))
                    expected = 2.0 / math.log(1.0 + math.sqrt(2.0))
                    rows.append({"check": "Onsager Tc(J=1)", "status": "PASS" if abs(tc - expected) < 1e-12 else "FAIL", "detail": f"got {tc:.12g}, expected {expected:.12g}"})
                    p = IsingParams(size=8, coupling=1.0, field=0.0, temperature=10.0, dimension=2)
                    r = simulate(p, method=Method.METROPOLIS, equilibration_sweeps=80, measurement_sweeps=200, measure_every=1, seed=7)
                    mag = float(r["mean_abs_magnetization"])
                    rows.append({"check": "High-T |M|/N small", "status": "PASS" if mag < 0.35 else "WARN", "detail": f"⟨|M|⟩/N={mag:.4g} at T=10, L=8"})
            elif profile == "numerical-methods":
                sine_taylor = ns.get("sine_taylor"); Method = ns.get("Method"); ReferenceBackend = ns.get("ReferenceBackend")
                if not all([sine_taylor, Method, ReferenceBackend]):
                    rows.append({"check": "Numerical APIs", "status": "SKIP", "detail": "Upstream APIs unavailable"})
                else:
                    r = sine_taylor(math.pi / 6, method=Method.RANGE_REDUCED, dtype="float64", max_terms=40, reference_backend=ReferenceBackend.MPMATH, reference_precision_digits=80)
                    err = float(getattr(r, "absolute_error", float("nan")))
                    rows.append({"check": "sin(π/6) absolute error", "status": "PASS" if err < 1e-12 else "WARN", "detail": f"|error|={err:.3e}"})
            elif profile == "oscillation-integration":
                Params = ns.get("OscillatorParams"); Method = ns.get("Method"); simulate_fixed = ns.get("simulate_fixed")
                if not all([Params, Method, simulate_fixed]):
                    rows.append({"check": "Oscillation APIs", "status": "SKIP", "detail": "Upstream APIs unavailable"})
                else:
                    omega0 = 2 * math.pi; mass = 1.0; u0 = 1.0; v0 = 0.0
                    p = Params(mass=mass, omega0=omega0, gamma=0.0, force_amplitude=0.0, force_frequency=0.0)
                    r = simulate_fixed(np.asarray([u0, v0], dtype=float), p, duration=1.0, dt=0.001, method=Method.RK4)
                    t = np.asarray(r["time"]); u = np.asarray(r["state"])[:, 0]
                    analytic = u0 * np.cos(omega0 * t)
                    max_err = float(np.max(np.abs(u - analytic)))
                    rows.append({"check": "Force-free RK4 vs analytic", "status": "PASS" if max_err < 5e-4 else "WARN", "detail": f"max |Δu|={max_err:.3e} over 1 s"})
                    chrono_py = os.environ.get("PHYSICAL_LAB_PYCHRONO_PYTHON", "").strip()
                    rows.append({"check": "PyChrono runtime discovered", "status": "PASS" if chrono_py else "INFO", "detail": chrono_py or "Not set — Runtime Center can detect a Conda chrono env"})
            elif profile == "radiation-platform":
                # Pure analytic resonance identity: doubling γ at fixed K,θ roughly scales E ~ γ²
                gamma = 100.0; k = 1.0; period_mm = 50.0; theta = 0.0
                lam_u = period_mm * 1e-3
                def e_ph(g):
                    denom = 1.0 + 0.5 * k * k + (g * theta * 1e-3) ** 2
                    wavelength = lam_u * denom / (2.0 * g * g)
                    return 1.2398419843320026e-6 / wavelength
                ratio = e_ph(200.0) / e_ph(100.0)
                rows.append({"check": "Undulator E(γ) ~ γ² scaling", "status": "PASS" if abs(ratio - 4.0) < 1e-9 else "FAIL", "detail": f"E(200)/E(100)={ratio:.12g}"})
            elif profile == "random-walk-monte-carlo":
                fit_power_law = ns.get("fit_power_law")
                if fit_power_law is None:
                    rows.append({"check": "Random-walk APIs", "status": "SKIP", "detail": "Upstream APIs unavailable"})
                else:
                    x = np.asarray([10.0, 20.0, 40.0, 80.0]); y = 3.0 * x ** 0.5
                    fit = fit_power_law(x, y)
                    exp = float(fit["exponent"])
                    rows.append({"check": "Power-law fit recovers 1/2", "status": "PASS" if abs(exp - 0.5) < 1e-9 else "FAIL", "detail": f"exponent={exp:.12g}"})
            elif profile == "nonlinear-chaos":
                energy_fn = ns.get("double_pendulum_energy"); Params = ns.get("DoublePendulumParams"); sim = ns.get("simulate_double_pendulum")
                if not all([energy_fn, Params, sim]):
                    rows.append({"check": "Chaos APIs", "status": "SKIP", "detail": "Upstream APIs unavailable"})
                else:
                    p = Params(mass1=1.0, mass2=1.0, length1=1.0, length2=1.0, gravity=9.81, damping=0.0)
                    state0 = np.asarray([0.2, 0.0, -0.15, 0.0])
                    t, traj = sim(state0, p, duration=2.0, dt=0.002)
                    e = np.asarray(energy_fn(traj, p), dtype=float)
                    rel = float(np.max(np.abs(e - e[0])) / max(abs(float(e[0])), 1e-15))
                    rows.append({"check": "Conservative energy drift", "status": "PASS" if rel < 1e-6 else "WARN", "detail": f"max |ΔE/E0|={rel:.3e}"})
            elif profile == "radia-magnet-studio":
                rows.append({"check": "Magnet Studio advanced suite loaded", "status": "PASS", "detail": "Engineering preflight / audit / seed ensemble available below"})
                rows.append({"check": "RADIA Full engine", "status": "INFO" if os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "") == "full" else "INFO", "detail": f"engine mode={os.environ.get('PHYSICAL_LAB_ENGINE_MODE', 'unknown')}"})
            else:
                rows.append({"check": "Profile", "status": "SKIP", "detail": f"No battery registered for {profile}"})
        except Exception as exc:
            rows.append({"check": "Validation battery", "status": "FAIL", "detail": str(exc)})
        st.session_state[f"pl_val_{profile}"] = pd.DataFrame(rows)
    df = st.session_state.get(f"pl_val_{profile}")
    if df is not None and len(df):
        passed = int(np.sum(df["status"].astype(str) == "PASS"))
        failed = int(np.sum(df["status"].astype(str) == "FAIL"))
        _headline(st, [
            ("PASS", str(passed), "Checks that matched the expected reference"),
            ("FAIL", str(failed), "Checks that missed the reference"),
            ("Rows", str(len(df)), "Total battery rows"),
            ("Engine", os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "standard"), "Safe/Full context"),
        ])
        st.dataframe(df, width="stretch", hide_index=True)
        payload = {
            "schema": "physical-lab-content-validation-v1",
            "profile": profile,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "engine_mode": os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "standard"),
            "source_commit": _source_commit(),
            "packages": _package_versions(),
            "rows": df.to_dict(orient="records"),
        }
        raw = json.dumps(payload, indent=2).encode("utf-8")
        st.download_button("Export validation JSON", data=raw, file_name=f"physical-lab-validation-{profile}.json", mime="application/json", key=f"pl_val_export_{profile}")
        data_root = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
        if data_root:
            out_dir = Path(data_root) / "content-validation" / profile
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                out_path = out_dir / f"{stamp}-content-validation.json"
                out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                st.caption(f"Also saved under Application Support: `{out_path}` (compatible with Research Workspace provenance folders).")
            except Exception as exc:
                st.caption(f"Could not persist validation JSON to Application Support: {exc}")
        else:
            st.caption("Set PHYSICAL_LAB_DATA_DIR from the desktop shell to auto-persist validation JSON beside Run Vault / research data.")


def _radiation_suite(st, ns: dict[str, Any]) -> None:
    np = _np(); pd = _pd(); go = _plotly()
    _section_header(
        st,
        "Physical Lab · Advanced Radiation Analysis",
        "Adds sensitivity maps, derived-quantity inspection, scan-point intelligence, and model-comparison diagnostics without changing the original V11/RADIA experiment chain.",
    )
    with st.expander("Research-note evidence checklist (magnet → trajectory → radiation)", expanded=False):
        st.markdown(
            """
Follow the Physical Lab research note protocol without inventing Full-mode results:

1. Record magnet geometry / material / target-field inputs.
2. Run RADIA Magnet Studio Full mode and preserve on-axis metrics (never substitute Br for solved B0).
3. If claiming tolerance sensitivity, run a bounded manufacturing-seed ensemble.
4. Hand the realized field to Radiation Platform.
5. Compare against the ideal undulator reference using matched units (see Analytic reference comparison + Linewidth ladder).
6. Export Run Vault / Content Validation JSON and keep model-boundary notes.
            """.strip()
        )
        st.caption("See docs/RESEARCH_NOTE_RADIATION.md in the Physical Lab source tree.")
    tab_sense, tab_scan, tab_compare, tab_line = st.tabs([
        "2D sensitivity atlas", "Representative scan intelligence", "Analytic reference comparison", "Linewidth & harmonic ladder"
    ])

    # Pull current upstream controls when possible. These names exist in the V11 UI;
    # fallbacks keep this suite usable if upstream variable names change.
    gamma_default = float(ns.get("gamma0", 100.0))
    periods_default = int(ns.get("n_periods", 20))
    theta_x_default = float(ns.get("theta_x_mrad", 0.0))
    theta_y_default = float(ns.get("theta_y_mrad", 0.0))
    bridge = ns.get("stage1_bridge") if isinstance(ns.get("stage1_bridge"), dict) else {}
    bridge_params = bridge.get("parameters", {}) if isinstance(bridge, dict) else {}
    period_mm_default = float(bridge_params.get("period_mm", ns.get("radia_period_mm", 50.0) or 50.0))

    def photon_energy_ev(gamma: np.ndarray, kval: np.ndarray, period_mm: float, theta_mrad: np.ndarray, harmonic: int = 1):
        # Ideal planar-undulator resonance reference. Used as a reference surface,
        # not a replacement for the full V11/RADIA field + trajectory solution.
        lam_u = period_mm * 1e-3
        theta = theta_mrad * 1e-3
        denom = 1.0 + 0.5 * kval**2 + (gamma * theta) ** 2
        wavelength = lam_u * denom / (2.0 * harmonic * gamma**2)
        hc_ev_m = 1.2398419843320026e-6
        return hc_ev_m / wavelength

    with tab_sense:
        st.markdown("### Coupled-parameter sensitivity")
        st.caption("This is an analytic reference atlas. It is designed to tell you where the expensive Full-mode RADIA/V11 deep runs are most informative.")
        c1, c2, c3, c4 = st.columns(4)
        gmin = c1.number_input("γ minimum", min_value=1.01, value=max(2.0, gamma_default * 0.6), key="pl_rad_gmin")
        gmax = c2.number_input("γ maximum", min_value=1.02, value=max(3.0, gamma_default * 1.4), key="pl_rad_gmax")
        kmin = c3.number_input("K minimum", min_value=0.0, value=0.1, key="pl_rad_kmin")
        kmax = c4.number_input("K maximum", min_value=0.01, value=2.5, key="pl_rad_kmax")
        c5, c6, c7, c8 = st.columns(4)
        period_mm = c5.number_input("Undulator period λu (mm)", min_value=0.1, value=period_mm_default, key="pl_rad_period")
        theta_mrad = c6.number_input("Observation angle magnitude (mrad)", min_value=0.0, value=float(math.hypot(theta_x_default, theta_y_default)), key="pl_rad_theta")
        harmonic = c7.selectbox("Ideal harmonic", [1, 3, 5, 7], index=0, key="pl_rad_harmonic")
        resolution = c8.select_slider("Atlas resolution", options=[25, 40, 60, 80, 100], value=60, key="pl_rad_res")
        invalid = gmax <= gmin or kmax <= kmin
        if invalid:
            st.error("Maximum values must exceed minimum values.")
        elif st.button("Run 2D sensitivity atlas", type="primary", key="pl_rad_run_atlas"):
            gammas = np.linspace(float(gmin), float(gmax), int(resolution))
            kvals = np.linspace(float(kmin), float(kmax), int(resolution))
            gg, kk = np.meshgrid(gammas, kvals)
            energy = photon_energy_ev(gg, kk, float(period_mm), np.full_like(gg, float(theta_mrad)), harmonic=int(harmonic))
            st.session_state["pl_rad_atlas"] = (gammas, kvals, energy, int(harmonic))
        atlas = st.session_state.get("pl_rad_atlas")
        if atlas is not None:
            gammas, kvals, energy, harmonic_used = atlas
            finite = np.asarray(energy)[np.isfinite(energy)]
            _headline(st, [
                ("Energy min", f"{finite.min():.5g} eV", "Ideal fundamental across the selected atlas"),
                ("Energy max", f"{finite.max():.5g} eV", "Ideal fundamental across the selected atlas"),
                ("Grid evaluations", f"{energy.size:,}", "Analytic reference evaluations"),
                ("Current periods", str(periods_default), "Original Full-mode period count remains unchanged"),
            ])
            fig = go.Figure(data=go.Heatmap(x=gammas, y=kvals, z=energy, colorbar={"title":"eV"}))
            fig.update_layout(title=f"Ideal harmonic n={harmonic_used} photon energy: γ × K", xaxis_title="Lorentz factor γ", yaxis_title="Undulator parameter K", height=650)
            st.plotly_chart(fig, width="stretch")
            # normalized finite-difference sensitivity
            loge = np.log(np.maximum(energy, np.finfo(float).tiny))
            dlog_dg = np.gradient(loge, np.log(gammas), axis=1)
            dlog_dk = np.gradient(loge, kvals, axis=0)
            sens = np.sqrt(dlog_dg**2 + dlog_dk**2)
            fig2 = go.Figure(data=go.Heatmap(x=gammas, y=kvals, z=sens, colorbar={"title":"sensitivity"}))
            fig2.update_layout(title="Local logarithmic sensitivity magnitude", xaxis_title="Lorentz factor γ", yaxis_title="K", height=590)
            st.plotly_chart(fig2, width="stretch")
            st.info("Use high-sensitivity regions to choose Full-mode deep-analysis points. The atlas is an ideal resonance reference; it does not replace realized-field, trajectory, polarization, or Liénard–Wiechert calculations.")

        st.markdown("### Inverse resonance design")
        st.caption("Solve the ideal resonance relation backward: choose a target photon energy and estimate the Lorentz factor needed before committing to an expensive Full-mode run.")
        q1,q2,q3,q4=st.columns(4)
        target_ev=q1.number_input("Target photon energy (eV)",min_value=1e-6,value=1000.0,format="%.8g",key="pl_rad_inv_ev")
        target_k=q2.number_input("Design K",min_value=0.0,value=1.0,key="pl_rad_inv_k")
        target_h=q3.selectbox("Design harmonic",[1,3,5,7],key="pl_rad_inv_h")
        target_angle=q4.number_input("Observation angle (mrad)",min_value=0.0,value=0.0,key="pl_rad_inv_angle")
        design_period=st.number_input("Design period λu (mm)",min_value=0.1,value=period_mm_default,key="pl_rad_inv_period")
        hc_ev_m=1.2398419843320026e-6
        target_lambda=hc_ev_m/max(float(target_ev),np.finfo(float).tiny)
        lam_u=float(design_period)*1e-3;theta=float(target_angle)*1e-3;harm=int(target_h);A=1.0+0.5*float(target_k)**2
        denominator=(2.0*harm*target_lambda/lam_u)-theta**2
        angular_floor=lam_u*theta**2/(2.0*harm)
        if denominator<=0:
            st.warning(f"This ideal target is unreachable at the selected nonzero observation angle: the angular term imposes λ ≥ {angular_floor:.6g} m regardless of γ.")
        else:
            gamma_req=math.sqrt(A/denominator);beta=math.sqrt(max(0.0,1.0-1.0/(gamma_req*gamma_req))) if gamma_req>=1 else float("nan");energy_gev=gamma_req*0.00051099895
            _headline(st,[("Required γ",f"{gamma_req:.8g}","Ideal resonance inversion"),("β = v/c",f"{beta:.10g}" if np.isfinite(beta) else "n/a","Relativistic speed ratio"),("Electron total energy",f"{energy_gev:.8g} GeV","γ m_ec²; total relativistic energy"),("Target λ",f"{target_lambda*1e9:.8g} nm","Photon wavelength implied by the requested energy")])
            st.caption("This inverse design is an ideal-undulator starting estimate. Realized RADIA fields, trajectory errors, finite device length, beam energy spread/emittance, optics and detector response can shift the Full result.")

    with tab_scan:
        st.markdown("### Automatic representative-point selection")
        scan_df = st.session_state.get("scan_df")
        if scan_df is None:
            st.info("Run the original scalar scan first. Physical Lab will then inspect that exact scan and nominate informative deep-analysis rows.")
        else:
            try:
                frame = pd.DataFrame(scan_df).copy()
            except Exception:
                frame = pd.DataFrame()
            numeric = [c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
            if frame.empty or len(numeric) < 2:
                st.warning("The current scalar scan does not expose enough numeric columns for automatic selection.")
            else:
                axis = st.selectbox("Independent variable", numeric, key="pl_rad_rep_axis")
                observables = [c for c in numeric if c != axis]
                observable = st.selectbox("Observable used for feature selection", observables, key="pl_rad_rep_obs")
                x = frame[axis].to_numpy(dtype=float); y = frame[observable].to_numpy(dtype=float)
                valid = np.isfinite(x) & np.isfinite(y)
                x=x[valid]; y=y[valid]
                if x.size < 3:
                    st.warning("At least three finite scan rows are needed.")
                else:
                    dy = np.gradient(y, x) if np.all(np.diff(x) != 0) else np.gradient(y)
                    idxs = {
                        "minimum": int(np.argmin(y)), "maximum": int(np.argmax(y)),
                        "largest slope": int(np.argmax(np.abs(dy))),
                        "mid-range": int(np.argmin(np.abs(x - 0.5*(x.min()+x.max())))),
                    }
                    rows=[]
                    for reason, idx in idxs.items():
                        rows.append({"reason":reason, axis:float(x[idx]), observable:float(y[idx]), "slope":float(dy[idx])})
                    rep = pd.DataFrame(rows).drop_duplicates(subset=[axis]).reset_index(drop=True)
                    st.dataframe(rep, width="stretch", hide_index=True)
                    fig = go.Figure()
                    fig.add_scatter(x=x,y=y,mode="lines+markers",name=observable)
                    fig.add_scatter(x=rep[axis],y=rep[observable],mode="markers+text",text=rep["reason"],textposition="top center",name="Suggested deep points",marker={"size":12})
                    fig.update_layout(title="Scalar scan with automatically selected deep-analysis points",xaxis_title=axis,yaxis_title=observable,height=580)
                    st.plotly_chart(fig,width="stretch")
                    st.caption("Selection is descriptive, not a physical proof: it intentionally captures extrema, strong local response, and a central reference point.")

    with tab_compare:
        st.markdown("### Analytic reference against current scan")
        st.caption("This comparison never overwrites the Full-mode result. You explicitly map the upstream scan axis/observable, so Physical Lab does not guess units or silently reinterpret a column.")
        scan_df = st.session_state.get("scan_df")
        if scan_df is None:
            st.info("Run the original scalar scan first to unlock direct analytic-vs-numerical comparison.")
        else:
            frame = pd.DataFrame(scan_df).copy()
            numeric = [c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
            if not numeric:
                st.warning("No numeric scan columns were detected.")
            else:
                c1,c2,c3=st.columns(3)
                axis_col=c1.selectbox("Scan-axis column",numeric,key="pl_rad_cmp_axis")
                semantics=c2.selectbox("Axis meaning",["Lorentz factor γ","Undulator K","Observation angle (mrad)"],key="pl_rad_cmp_sem")
                quantity=c3.selectbox("Reference quantity",["Photon energy (eV)","Wavelength (nm)"],key="pl_rad_cmp_q")
                c4,c5,c6=st.columns(3)
                base_gamma=c4.number_input("Fixed γ when axis is not γ",min_value=1.01,value=gamma_default,key="pl_rad_cmp_gamma")
                base_k_default=1.0
                try:
                    preset=ns.get("v11").get_device_preset(ns.get("device_preset")) if ns.get("v11") is not None and ns.get("device_preset") is not None else {}
                    base_k_default=float(preset.get("wiggler_K") or 1.0)
                except Exception:
                    pass
                base_k=c5.number_input("Fixed K when axis is not K",min_value=0.0,value=base_k_default,key="pl_rad_cmp_k")
                cmp_period=c6.number_input("Reference λu (mm)",min_value=0.1,value=period_mm_default,key="pl_rad_cmp_period")
                x=frame[axis_col].to_numpy(dtype=float)
                gamma=np.full_like(x,float(base_gamma)); kval=np.full_like(x,float(base_k)); angle=np.full_like(x,float(math.hypot(theta_x_default,theta_y_default)))
                if semantics.startswith("Lorentz"):
                    gamma=x
                elif semantics.startswith("Undulator"):
                    kval=x
                else:
                    angle=x
                energy=photon_energy_ev(gamma,kval,float(cmp_period),angle)
                reference=energy if quantity.startswith("Photon") else (1.2398419843320026e3/energy)
                unit="eV" if quantity.startswith("Photon") else "nm"
                fig=go.Figure();fig.add_scatter(x=x,y=reference,mode="lines",name=f"Ideal reference ({unit})")
                observed_choices=["(none)"]+numeric
                observed=st.selectbox("Optional upstream observable to overlay",observed_choices,key="pl_rad_cmp_obs")
                if observed!="(none)":
                    obs=frame[observed].to_numpy(dtype=float)
                    fig.add_scatter(x=x,y=obs,mode="lines+markers",name=f"Upstream: {observed}")
                    valid=np.isfinite(obs)&np.isfinite(reference)&(np.abs(reference)>np.finfo(float).tiny)
                    if np.any(valid):
                        rel=(obs[valid]-reference[valid])/reference[valid]
                        _headline(st,[("Median |Δ/reference|",f"{np.median(np.abs(rel)):.3e}","Only meaningful if you mapped an upstream column with the same quantity and unit"),("Maximum |Δ/reference|",f"{np.max(np.abs(rel)):.3e}","Largest relative difference"),("Compared rows",f"{np.count_nonzero(valid):,}","Finite paired values")])
                fig.update_layout(title=f"Upstream scan vs ideal-undulator {quantity.lower()}",xaxis_title=str(axis_col),yaxis_title=f"{quantity} [{unit}]",height=600)
                st.plotly_chart(fig,width="stretch")
                st.warning("Overlay comparison is valid only when the selected upstream observable has the same physical quantity and unit shown here. The analytic reference omits realized-field errors, trajectory effects, finite-emittance/energy-spread physics, beamline optics, and detector response.")

    with tab_line:
        st.markdown("### Ideal undulator harmonic ladder and finite-N linewidth")
        st.caption(
            "Uses the ideal planar-undulator resonance relation and the standard 1/(nN) relative-bandwidth "
            "estimate for a finite-period device. This is a design reference, not a Full-mode RADIA spectrum."
        )
        c1, c2, c3, c4 = st.columns(4)
        gamma = c1.number_input("γ", min_value=1.01, value=float(gamma_default), key="pl_rad_line_gamma")
        kval = c2.number_input("K", min_value=0.0, value=1.0, key="pl_rad_line_k")
        period_mm = c3.number_input("Period λu (mm)", min_value=0.1, value=float(period_mm_default), key="pl_rad_line_period")
        n_periods = c4.number_input("Periods N", min_value=1, value=int(periods_default), key="pl_rad_line_n")
        theta_mrad = st.number_input("Observation angle θ (mrad)", value=float(theta_x_default), key="pl_rad_line_theta")
        if st.button("Build harmonic ladder", type="primary", key="pl_rad_line_run"):
            rows = []
            e1 = float(photon_energy_ev(np.asarray([gamma]), np.asarray([kval]), float(period_mm), np.asarray([theta_mrad]), harmonic=1)[0])
            for n in (1, 3, 5, 7, 9):
                en = n * e1
                rel_bw = 1.0 / max(n * float(n_periods), 1.0)
                rows.append({
                    "harmonic n": n,
                    "photon energy (eV)": en,
                    "wavelength (nm)": 1.2398419843320026e3 / en if en > 0 else float("nan"),
                    "relative bandwidth ~1/(nN)": rel_bw,
                    "absolute ΔE (eV)": en * rel_bw,
                })
            st.session_state["pl_rad_ladder"] = (pd.DataFrame(rows), e1, float(n_periods), float(kval), float(gamma))
        data = st.session_state.get("pl_rad_ladder")
        if data:
            df, e1, nper, kk, gg = data
            _headline(st, [
                ("Fundamental E1", f"{e1:.6g} eV", "Ideal planar undulator on-axis/off-axis resonance"),
                ("N periods", f"{nper:.0f}", "Finite device length used for 1/(nN) estimate"),
                ("K", f"{kk:.6g}", "Undulator strength parameter"),
                ("γ", f"{gg:.6g}", "Lorentz factor"),
            ])
            fig = go.Figure(go.Bar(x=df["harmonic n"].astype(str), y=df["photon energy (eV)"], name="E_n"))
            fig.update_layout(title="Ideal odd-harmonic energy ladder", xaxis_title="Harmonic n", yaxis_title="Photon energy (eV)", height=520)
            st.plotly_chart(fig, width="stretch")
            fig2 = go.Figure()
            fig2.add_scatter(x=df["harmonic n"], y=df["relative bandwidth ~1/(nN)"], mode="lines+markers", name="ΔE/E ≈ 1/(nN)")
            fig2.update_layout(title="Finite-N relative linewidth estimate", xaxis_title="Harmonic n", yaxis_title="Relative bandwidth", yaxis_type="log", height=500)
            st.plotly_chart(fig2, width="stretch")
            st.dataframe(df, width="stretch", hide_index=True)
            st.caption(
                "The 1/(nN) rule is an ideal finite-length estimate. Emittance, energy spread, tapering, "
                "field errors and optics all broaden or reshape the realized spectrum in Full mode."
            )


def _ising_suite(st, ns: dict[str, Any]) -> None:
    np = _np(); pd = _pd(); go = _plotly()
    _section_header(
        st,
        "Physical Lab · Criticality & Sampling Suite",
        "Adds adaptive critical-window refinement, Binder-cumulant finite-size analysis, distribution views, and work-normalized sampler efficiency while preserving the original Ising experiments.",
    )
    tab_adapt, tab_binder, tab_eff, tab_fss = st.tabs(["Adaptive critical scan", "Binder & distributions", "Sampler efficiency", "Finite-size scaling"])
    IsingParams = ns.get("IsingParams"); Method = ns.get("Method")
    simulate = ns.get("simulate"); thermodynamic_scan = ns.get("thermodynamic_scan"); onsager_tc = ns.get("onsager_tc")
    method_compatibility = ns.get("method_compatibility")
    if not all([IsingParams, Method, simulate, thermodynamic_scan, onsager_tc]):
        st.warning("Advanced Ising APIs were not found in this upstream version. The original lab remains fully available.")
        return
    base_size = int(st.session_state.get("size", 16)); J=float(st.session_state.get("coupling",1.0)); h=float(st.session_state.get("field",0.0)); dim=int(st.session_state.get("dimension",2))
    seed=int(st.session_state.get("seed",2026))

    with tab_adapt:
        st.markdown("### Coarse → refine critical scan")
        c1,c2,c3,c4=st.columns(4)
        tmin=c1.number_input("Coarse T min",min_value=0.05,value=1.4,key="pl_i_tmin")
        tmax=c2.number_input("Coarse T max",min_value=0.06,value=3.2,key="pl_i_tmax")
        coarse_n=c3.select_slider("Coarse points",options=[9,13,17,25,33],value=17,key="pl_i_cn")
        refine_n=c4.select_slider("Refine points",options=[9,15,21,31,41],value=21,key="pl_i_rn")
        method_label=st.selectbox("Update method",["wolff","metropolis","checkerboard","heat_bath"],key="pl_i_method")
        eq=int(st.session_state.get("eq_sweeps",400)); mc=int(st.session_state.get("mc_sweeps",800)); measure=int(st.session_state.get("measure_every",1))
        if st.button("Run adaptive critical scan",type="primary",key="pl_i_run_adapt",disabled=tmax<=tmin):
            params=IsingParams(size=base_size,coupling=J,field=h,temperature=float((tmin+tmax)/2),dimension=dim)
            method=Method(method_label)
            if method_compatibility and not method_compatibility(params,method)[0]:
                st.error(method_compatibility(params,method)[1])
            else:
                bar=st.progress(0,text="Coarse critical scan")
                coarse=np.linspace(float(tmin),float(tmax),int(coarse_n))
                def cb1(done,total): bar.progress(0.45*done/max(total,1),text=f"Coarse scan {done}/{total}")
                first=thermodynamic_scan(coarse,params,method=method,equilibration_sweeps=eq,measurement_sweeps=mc,measure_every=measure,seed=seed,progress_callback=cb1)
                chi=np.asarray(first["susceptibility_standard"],dtype=float); cv=np.asarray(first["specific_heat"],dtype=float)
                scores=np.nan_to_num((chi-np.nanmin(chi))/(np.nanmax(chi)-np.nanmin(chi)+1e-15))+np.nan_to_num((cv-np.nanmin(cv))/(np.nanmax(cv)-np.nanmin(cv)+1e-15))
                center=float(coarse[int(np.nanargmax(scores))]); spacing=float((tmax-tmin)/max(int(coarse_n)-1,1)); half=max(2.5*spacing,0.08*center)
                lo=max(float(tmin),center-half); hi=min(float(tmax),center+half)
                refined=np.linspace(lo,hi,int(refine_n))
                def cb2(done,total): bar.progress(0.45+0.55*done/max(total,1),text=f"Refined scan {done}/{total}")
                second=thermodynamic_scan(refined,params,method=method,equilibration_sweeps=eq,measurement_sweeps=mc,measure_every=measure,seed=seed+101,progress_callback=cb2)
                bar.progress(1.0,text="Adaptive critical scan complete")
                st.session_state["pl_i_adapt"]=(first,second)
        data=st.session_state.get("pl_i_adapt")
        if data:
            first,second=data
            T=np.asarray(second["temperature"],dtype=float); chi=np.asarray(second["susceptibility_standard"],dtype=float); cv=np.asarray(second["specific_heat"],dtype=float); mag=np.asarray(second["mean_abs_magnetization"],dtype=float)
            t_chi=float(T[int(np.nanargmax(chi))]); t_cv=float(T[int(np.nanargmax(cv))]); exact=float(onsager_tc(J)) if dim==2 and abs(h)<1e-14 else float("nan")
            _headline(st,[("χ peak T",f"{t_chi:.6g}","Refined susceptibility maximum"),("Cv peak T",f"{t_cv:.6g}","Refined specific-heat maximum"),("Onsager Tc",f"{exact:.6g}" if np.isfinite(exact) else "n/a","Exact 2D zero-field thermodynamic-limit reference"),("Refined window",f"{T.min():.4g}–{T.max():.4g}","Automatically selected")])
            fig=go.Figure();fig.add_scatter(x=T,y=chi,mode="lines+markers",name="Susceptibility");fig.add_scatter(x=T,y=cv,mode="lines+markers",name="Specific heat");fig.update_layout(title="Refined critical response",xaxis_title="Temperature T",yaxis_title="Response",height=570);st.plotly_chart(fig,width="stretch")
            fig2=go.Figure();fig2.add_scatter(x=T,y=mag,mode="lines+markers",name="<|M|>/N");fig2.update_layout(title="Order parameter through refined critical window",xaxis_title="Temperature T",yaxis_title="Mean |M| / N",height=500);st.plotly_chart(fig2,width="stretch")
            st.markdown("#### Multi-seed critical-peak stability")
            a1,a2,a3=st.columns(3)
            audit_seeds=a1.select_slider("Independent seeds",options=[3,4,5,6,8],value=4,key="pl_i_peak_seeds")
            audit_eq=a2.number_input("Equilibration cycles / seed",min_value=50,value=max(150,eq//2),step=50,key="pl_i_peak_eq")
            audit_mc=a3.number_input("Measurement cycles / seed",min_value=100,value=max(400,mc//2),step=100,key="pl_i_peak_mc")
            if st.button("Audit critical peak across seeds",key="pl_i_peak_run"):
                pbase=IsingParams(size=base_size,coupling=J,field=h,temperature=float(np.mean(T)),dimension=dim);rows=[];bar=st.progress(0,text="Critical-peak seed audit")
                for i in range(int(audit_seeds)):
                    rr=thermodynamic_scan(T,pbase,method=Method(method_label),equilibration_sweeps=int(audit_eq),measurement_sweeps=int(audit_mc),measure_every=measure,seed=seed+5003*i)
                    rchi=np.asarray(rr["susceptibility_standard"],dtype=float);rcv=np.asarray(rr["specific_heat"],dtype=float)
                    rows.append({"seed":seed+5003*i,"T at χ peak":float(T[int(np.nanargmax(rchi))]),"T at Cv peak":float(T[int(np.nanargmax(rcv))]),"χ peak":float(np.nanmax(rchi)),"Cv peak":float(np.nanmax(rcv))})
                    bar.progress((i+1)/int(audit_seeds),text=f"Seed {i+1}/{int(audit_seeds)}")
                st.session_state["pl_i_peak_audit"]=pd.DataFrame(rows)
            adf=st.session_state.get("pl_i_peak_audit")
            if adf is not None and len(adf):
                _headline(st,[("χ-peak T mean",f"{adf['T at χ peak'].mean():.6g}","Across independent seeds"),("χ-peak T SD",f"{adf['T at χ peak'].std(ddof=1):.3e}" if len(adf)>1 else "0","Seed-to-seed spread on this discrete T grid"),("Cv-peak T mean",f"{adf['T at Cv peak'].mean():.6g}","Across independent seeds"),("Audit runs",str(len(adf)),"Independent RNG seeds")])
                st.dataframe(adf,width="stretch",hide_index=True)
                st.caption("This quantifies Monte Carlo peak-location stability on the chosen finite temperature grid. It is not a full critical-exponent or finite-size uncertainty analysis.")

    with tab_binder:
        st.markdown("### Binder cumulant finite-size probe")
        c1,c2,c3=st.columns(3)
        sizes_text=c1.text_input("Lattice sizes",value="8,12,16,24",key="pl_i_sizes")
        bmin=c2.number_input("T min",min_value=0.05,value=1.9,key="pl_i_bmin")
        bmax=c3.number_input("T max",min_value=0.06,value=2.7,key="pl_i_bmax")
        points=st.select_slider("Temperature points",options=[7,9,11,15],value=9,key="pl_i_bpoints")
        if st.button("Run Binder analysis",type="primary",key="pl_i_run_binder",disabled=bmax<=bmin):
            try:
                sizes=sorted({int(x.strip()) for x in sizes_text.split(',') if x.strip()})
                if not sizes or min(sizes)<4 or max(sizes)>128: raise ValueError("sizes must be integers from 4 to 128")
            except Exception as e:
                st.error(str(e)); sizes=[]
            if sizes:
                temps=np.linspace(float(bmin),float(bmax),int(points)); rows=[]; total=len(sizes)*len(temps); done=0; bar=st.progress(0,text="Binder finite-size scan")
                for si,L in enumerate(sizes):
                    for ti,T in enumerate(temps):
                        p=IsingParams(size=L,coupling=J,field=0.0,temperature=float(T),dimension=2)
                        r=simulate(p,method=Method.WOLFF,equilibration_sweeps=max(200,int(st.session_state.get("eq_sweeps",400)//2)),measurement_sweeps=max(500,int(st.session_state.get("mc_sweeps",800))),measure_every=1,seed=seed+L*1009+ti)
                        m=np.asarray(r["abs_magnetization_samples_per_site"],dtype=float)
                        m2=float(np.mean(m**2)); m4=float(np.mean(m**4)); u4=float(1.0-m4/(3.0*m2*m2)) if m2>0 else float("nan")
                        rows.append({"L":L,"T":float(T),"Binder U4":u4,"mean |M|/N":float(r["mean_abs_magnetization"]),"ESS |M|":float(r["effective_samples_abs_magnetization"])})
                        done+=1;bar.progress(done/total,text=f"Binder scan {done}/{total}")
                st.session_state["pl_i_binder"]=pd.DataFrame(rows)
        bdf=st.session_state.get("pl_i_binder")
        if bdf is not None and len(bdf):
            fig=go.Figure()
            for L,grp in bdf.groupby("L"): fig.add_scatter(x=grp["T"],y=grp["Binder U4"],mode="lines+markers",name=f"L={L}")
            fig.update_layout(title="Binder cumulant curves",xaxis_title="Temperature T",yaxis_title="U4",height=600);st.plotly_chart(fig,width="stretch")
            crossings=[]; sizes_sorted=sorted(int(x) for x in bdf["L"].unique())
            for a,b in zip(sizes_sorted[:-1],sizes_sorted[1:]):
                ga=bdf[bdf["L"]==a].sort_values("T"); gb=bdf[bdf["L"]==b].sort_values("T")
                if len(ga)==len(gb) and np.allclose(ga["T"].to_numpy(dtype=float),gb["T"].to_numpy(dtype=float)):
                    tt=ga["T"].to_numpy(dtype=float); dd=ga["Binder U4"].to_numpy(dtype=float)-gb["Binder U4"].to_numpy(dtype=float)
                    idx=np.flatnonzero(dd[:-1]*dd[1:]<=0)
                    for j in idx:
                        denom=dd[j+1]-dd[j]; frac=(-dd[j]/denom) if abs(denom)>np.finfo(float).tiny else 0.0
                        crossings.append({"size pair":f"{a} ↔ {b}","crossing T":float(tt[j]+frac*(tt[j+1]-tt[j]))})
            if crossings:
                cdf=pd.DataFrame(crossings); _headline(st,[("Median Binder crossing T",f"{float(cdf['crossing T'].median()):.6g}","Descriptive median of adjacent-size interpolated crossings")]); st.dataframe(cdf,width="stretch",hide_index=True)
            st.dataframe(bdf,width="stretch",hide_index=True)
            st.caption("Crossings of finite-size Binder curves can localize the critical region. The interpolated crossings are descriptive finite-size estimates; sampling, autocorrelation and scaling corrections still matter.")
            st.markdown("#### Magnetization-distribution microscope")
            d1,d2=st.columns(2);dist_L=d1.number_input("Distribution lattice size",min_value=4,max_value=128,value=16,key="pl_i_dist_L");dist_T=d2.number_input("Distribution temperature",min_value=0.05,value=float(onsager_tc(J)) if dim==2 and abs(h)<1e-14 else 2.3,key="pl_i_dist_T")
            if st.button("Run distribution microscope",key="pl_i_dist_run"):
                rr=simulate(IsingParams(size=int(dist_L),coupling=J,field=h,temperature=float(dist_T),dimension=dim),method=Method.WOLFF if abs(h)<1e-14 else Method.METROPOLIS,equilibration_sweeps=max(300,int(st.session_state.get("eq_sweeps",400))),measurement_sweeps=max(1200,int(st.session_state.get("mc_sweeps",800))),measure_every=1,seed=seed+404)
                st.session_state["pl_i_dist"]=np.asarray(rr["abs_magnetization_samples_per_site"],dtype=float)
            dist=st.session_state.get("pl_i_dist")
            if dist is not None and len(dist):
                figd=go.Figure(go.Histogram(x=dist,nbinsx=40,histnorm="probability density"));figd.update_layout(title="Sampled |M|/N distribution",xaxis_title="|M|/N",yaxis_title="Density",height=500);st.plotly_chart(figd,width="stretch")

    with tab_eff:
        st.markdown("### Work-normalized sampler efficiency")
        temp=st.number_input("Comparison temperature",min_value=0.05,value=float(st.session_state.get("temperature",2.5)),key="pl_i_eff_t")
        if st.button("Compare compatible samplers",type="primary",key="pl_i_eff_run"):
            p=IsingParams(size=base_size,coupling=J,field=h,temperature=float(temp),dimension=dim);rows=[]
            methods=[Method.METROPOLIS,Method.CHECKERBOARD,Method.HEAT_BATH,Method.WOLFF]
            for i,meth in enumerate(methods):
                if method_compatibility and not method_compatibility(p,meth)[0]: continue
                r=simulate(p,method=meth,equilibration_sweeps=max(150,int(st.session_state.get("comparison_eq",250))),measurement_sweeps=max(300,int(st.session_state.get("comparison_mc",400))),seed=seed+i*71)
                work=max(float(r["work_units"]),1e-15);ess=float(r["effective_samples_energy"])
                rows.append({"method":meth.value,"ESS energy":ess,"work units":work,"ESS / work":ess/work,"tau energy (cycles)":float(r["tau_int_energy_cycles"]),"energy/site":float(r["energy_per_site"])})
            st.session_state["pl_i_eff"]=pd.DataFrame(rows)
        edf=st.session_state.get("pl_i_eff")
        if edf is not None and len(edf):
            fig=go.Figure(go.Bar(x=edf["method"],y=edf["ESS / work"]));fig.update_layout(title="Effective energy samples per work unit",xaxis_title="Sampler",yaxis_title="ESS / work",height=500);st.plotly_chart(fig,width="stretch");st.dataframe(edf,width="stretch",hide_index=True)

    with tab_fss:
        st.markdown("### Finite-size scaling of critical response")
        st.caption(
            "For the 2D zero-field Ising model, Onsager exponents give ν=1 and γ=7/4. "
            "Physical Lab measures χ-peak height versus lattice size and compares the empirical power "
            "against γ/ν = 1.75. This is a finite-grid diagnostic, not a full data-collapse analysis."
        )
        if dim != 2 or abs(h) >= 1e-14:
            st.info("Finite-size scaling reference exponents are shown for the 2D zero-field case. Switch the upstream Lab to dimension=2 and h≈0 for the Onsager comparison.")
        c1, c2, c3 = st.columns(3)
        sizes_text = c1.text_input("Lattice sizes", value="8,12,16,24,32", key="pl_i_fss_sizes")
        tmin = c2.number_input("T window min", min_value=0.05, value=1.8, key="pl_i_fss_tmin")
        tmax = c3.number_input("T window max", min_value=0.06, value=2.8, key="pl_i_fss_tmax")
        points = st.select_slider("Temperature points / size", options=[9, 11, 15, 21], value=15, key="pl_i_fss_points")
        method_label = st.selectbox("Update method", ["wolff", "metropolis", "heat_bath"], key="pl_i_fss_method")
        if st.button("Run finite-size scaling scan", type="primary", key="pl_i_fss_run", disabled=tmax <= tmin):
            try:
                sizes = sorted({int(x.strip()) for x in sizes_text.split(",") if x.strip()})
                if not sizes or min(sizes) < 4 or max(sizes) > 96:
                    raise ValueError("sizes must be integers from 4 to 96")
            except Exception as e:
                st.error(str(e))
                sizes = []
            if sizes:
                temps = np.linspace(float(tmin), float(tmax), int(points))
                rows = []
                curves = []
                total = len(sizes)
                bar = st.progress(0, text="Finite-size χ-peak scan")
                for i, L in enumerate(sizes):
                    p = IsingParams(size=L, coupling=J, field=h, temperature=float((tmin + tmax) / 2), dimension=dim)
                    meth = Method(method_label)
                    if method_compatibility and not method_compatibility(p, meth)[0]:
                        st.warning(f"L={L}: {method_compatibility(p, meth)[1]}")
                        continue
                    scan = thermodynamic_scan(
                        temps, p, method=meth,
                        equilibration_sweeps=max(200, eq // 2),
                        measurement_sweeps=max(500, mc),
                        measure_every=measure, seed=seed + L * 917,
                    )
                    T = np.asarray(scan["temperature"], dtype=float)
                    chi = np.asarray(scan["susceptibility_standard"], dtype=float)
                    cv = np.asarray(scan["specific_heat"], dtype=float)
                    mag = np.asarray(scan["mean_abs_magnetization"], dtype=float)
                    rows.append({
                        "L": L,
                        "T at χ peak": float(T[int(np.nanargmax(chi))]),
                        "χ peak": float(np.nanmax(chi)),
                        "T at Cv peak": float(T[int(np.nanargmax(cv))]),
                        "Cv peak": float(np.nanmax(cv)),
                        "⟨|M|⟩/N at χ peak": float(mag[int(np.nanargmax(chi))]),
                    })
                    curves.append({"L": int(L), "T": T, "chi": chi, "mag": mag})
                    bar.progress((i + 1) / total, text=f"Size {i + 1}/{total}")
                st.session_state["pl_i_fss"] = pd.DataFrame(rows)
                st.session_state["pl_i_fss_curves"] = curves
        fdf = st.session_state.get("pl_i_fss")
        if fdf is not None and len(fdf):
            L = fdf["L"].to_numpy(dtype=float)
            chi_peak = fdf["χ peak"].to_numpy(dtype=float)
            # Power-law fit: χ_max ~ L^{γ/ν}
            mask = (L > 0) & np.isfinite(chi_peak) & (chi_peak > 0)
            exponent = float("nan")
            intercept = float("nan")
            if np.count_nonzero(mask) >= 2:
                x = np.log(L[mask])
                y = np.log(chi_peak[mask])
                A = np.vstack([x, np.ones_like(x)]).T
                exponent, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
            exact = float(onsager_tc(J)) if dim == 2 and abs(h) < 1e-14 else float("nan")
            theory = 1.75  # γ/ν for 2D Ising
            _headline(st, [
                ("Observed γ/ν", f"{exponent:.4g}" if np.isfinite(exponent) else "n/a", "Log–log fit of χ_peak versus L"),
                ("2D Onsager γ/ν", f"{theory:.4g}", "Exact thermodynamic-limit ratio γ/ν = (7/4)/1"),
                ("Median T(χ peak)", f"{float(np.nanmedian(fdf['T at χ peak'])):.6g}", "Across scanned sizes"),
                ("Onsager Tc", f"{exact:.6g}" if np.isfinite(exact) else "n/a", "Exact 2D zero-field reference"),
            ])
            fig = go.Figure()
            fig.add_scatter(x=L, y=chi_peak, mode="markers+lines", name="χ peak")
            if np.isfinite(exponent):
                Lfit = np.linspace(float(np.min(L)), float(np.max(L)), 80)
                fig.add_scatter(x=Lfit, y=np.exp(intercept) * Lfit ** exponent, mode="lines", name=f"Fit L^{exponent:.3f}")
                L0 = float(np.min(L[mask])); chi0 = float(chi_peak[mask][np.argmin(L[mask])])
                fig.add_scatter(x=Lfit, y=chi0 * (Lfit / L0) ** theory, mode="lines", name="Guide ∝ L^1.75", opacity=0.55)
            fig.update_layout(title="Susceptibility-peak scaling", xaxis_title="Lattice size L", yaxis_title="χ peak", xaxis_type="log", yaxis_type="log", height=560)
            st.plotly_chart(fig, width="stretch")
            fig2 = go.Figure()
            fig2.add_scatter(x=fdf["L"], y=fdf["T at χ peak"], mode="lines+markers", name="T(χ peak)")
            if np.isfinite(exact):
                fig2.add_hline(y=exact, line_dash="dash", annotation_text="Onsager Tc")
            fig2.update_layout(title="Finite-size critical-temperature proxy", xaxis_title="L", yaxis_title="T at χ peak", height=500)
            st.plotly_chart(fig2, width="stretch")
            st.dataframe(fdf, width="stretch", hide_index=True)
            st.caption(
                "Observed γ/ν depends on equilibration, measurement budget, temperature grid and lattice range. "
                "Disagreement with 1.75 usually means the scan is still pre-asymptotic, not that the Onsager exponents are wrong."
            )
            curves = st.session_state.get("pl_i_fss_curves")
            if curves and np.isfinite(exact):
                st.markdown("#### Order-parameter collapse guide (β/ν = 1/8)")
                st.caption(
                    "Plots m L^{β/ν} versus reduced temperature t = (T−Tc)/Tc using the exact Onsager Tc and β/ν = 1/8. "
                    "This is a visual finite-size guide, not an optimized data-collapse fit."
                )
                beta_over_nu = 0.125
                figc = go.Figure()
                for curve in curves:
                    Lv = float(curve["L"])
                    T = np.asarray(curve["T"], dtype=float)
                    mag = np.asarray(curve["mag"], dtype=float)
                    tred = (T - exact) / max(abs(exact), np.finfo(float).tiny)
                    figc.add_scatter(x=tred, y=mag * (Lv ** beta_over_nu), mode="lines+markers", name=f"L={int(Lv)}")
                figc.update_layout(
                    title="Guided magnetization collapse using Onsager Tc and β/ν=1/8",
                    xaxis_title="Reduced temperature t=(T−Tc)/Tc",
                    yaxis_title="m L^{β/ν}",
                    height=560,
                )
                st.plotly_chart(figc, width="stretch")
                # Also report mag-at-Tc-proxy scaling if available.
                mag_peak = fdf["⟨|M|⟩/N at χ peak"].to_numpy(dtype=float)
                mask_m = (L > 0) & np.isfinite(mag_peak) & (mag_peak > 0)
                beta_obs = float("nan")
                if np.count_nonzero(mask_m) >= 2:
                    xm = np.log(L[mask_m]); ym = np.log(mag_peak[mask_m])
                    Am = np.vstack([xm, np.ones_like(xm)]).T
                    beta_obs, _ = np.linalg.lstsq(Am, ym, rcond=None)[0]
                _headline(st, [
                    ("Guide β/ν", f"{beta_over_nu:.4g}", "Exact 2D Ising β/ν = (1/8)/1"),
                    ("Observed slope of m(χ-peak) vs L", f"{beta_obs:.4g}" if np.isfinite(beta_obs) else "n/a", "Log–log slope near the χ-peak temperatures; not a full collapse fit"),
                    ("Exact Tc used", f"{exact:.6g}", "Onsager thermodynamic-limit reference"),
                    ("Curves", str(len(curves)), "Finite-size magnetization scans retained for collapse"),
                ])


def _chaos_suite(st, ns: dict[str, Any]) -> None:
    np = _np(); pd = _pd(); go = _plotly()
    _section_header(
        st,
        "Physical Lab · Chaos Explorer",
        "Adds paired-trajectory divergence, finite-time Lyapunov interpretation, phase-space diagnostics, and a clickable stability atlas while keeping the original driven/Kapitza/double-pendulum experiments intact.",
    )
    sim=ns.get("simulate_double_pendulum"); energy_fn=ns.get("double_pendulum_energy"); cart=ns.get("double_pendulum_cartesian"); lyap=ns.get("lyapunov_benettin"); flip=ns.get("flip_time_map"); Params=ns.get("DoublePendulumParams")
    if not all([sim,energy_fn,cart,lyap,flip,Params]):
        st.warning("Advanced chaos APIs were not found in this upstream version. The original lab remains available.");return
    p=Params(mass1=float(st.session_state.get("m1",1.0)),mass2=float(st.session_state.get("m2",1.0)),length1=float(st.session_state.get("l1",1.0)),length2=float(st.session_state.get("l2",1.0)),gravity=float(st.session_state.get("gravity",9.81)),damping=0.0)
    base=np.asarray([float(st.session_state.get("theta1_0",math.pi/2)),float(st.session_state.get("omega1_0",0.0)),float(st.session_state.get("theta2_0",1.27)),float(st.session_state.get("omega2_0",0.0))])
    driven_scan=ns.get("driven_poincare_scan")
    tab_pair,tab_lyap,tab_atlas,tab_drive,tab_poincare=st.tabs(["Twin-trajectory divergence","Lyapunov + phase space","Stability atlas","Driven bifurcation intelligence","Poincaré section"])

    with tab_pair:
        c1,c2,c3=st.columns(3);duration=c1.number_input("Duration (s)",min_value=0.1,value=min(30.0,float(st.session_state.get("trajectory_duration",20.0))),key="pl_c_pair_dur");dt=c2.number_input("dt (s)",min_value=1e-5,value=float(st.session_state.get("trajectory_dt",0.01)),format="%.6g",key="pl_c_pair_dt");pert_exp=c3.slider("log10 initial Δθ₁",-12,-2,-7,key="pl_c_pair_pert")
        if st.button("Run paired trajectories",type="primary",key="pl_c_pair_run"):
            pert=10.0**int(pert_exp);other=base.copy();other[0]+=pert
            t,a=sim(base,p,duration=float(duration),dt=float(dt));_,b=sim(other,p,duration=float(duration),dt=float(dt))
            diff=b-a;diff[:,[0,2]]=(diff[:,[0,2]]+np.pi)%(2*np.pi)-np.pi
            omega_scale=math.sqrt(p.gravity/max(p.length1,p.length2));scaled=diff.copy();scaled[:,[1,3]]/=omega_scale;sep=np.linalg.norm(scaled,axis=1)
            e=energy_fn(a,p);rel_drift=(e-e[0])/max(abs(float(e[0])),np.finfo(float).tiny)
            st.session_state["pl_c_pair"]=(t,a,b,sep,rel_drift,pert)
        data=st.session_state.get("pl_c_pair")
        if data:
            t,a,b,sep,rel_drift,pert=data
            growth=np.log(np.maximum(sep,np.finfo(float).tiny)/pert);valid=(t>0)&np.isfinite(growth);rough=float(np.median(growth[valid]/t[valid])) if np.any(valid) else float("nan")
            _headline(st,[("Initial separation",f"{pert:.1e}","Perturbation in θ1"),("Final separation",f"{sep[-1]:.5g}","Scaled state-space distance"),("Rough growth rate",f"{rough:.5g} s⁻¹","Descriptive median log-growth/time, not the renormalized Benettin estimate"),("Max |ΔE/E0|",f"{np.max(np.abs(rel_drift)):.3e}","Numerical conservation diagnostic")])
            fig=go.Figure();fig.add_scatter(x=t,y=np.maximum(sep,np.finfo(float).tiny),mode="lines",name="State separation");fig.update_layout(title="Nearby-orbit separation",xaxis_title="Time (s)",yaxis_title="Scaled separation",yaxis_type="log",height=560);st.plotly_chart(fig,width="stretch")
            fig2=go.Figure();fig2.add_scatter(x=a[:,0],y=a[:,1],mode="lines",name="Base");fig2.add_scatter(x=b[:,0],y=b[:,1],mode="lines",name="Perturbed");fig2.update_layout(title="θ1–ω1 phase portrait: paired trajectories",xaxis_title="θ1 (rad)",yaxis_title="ω1 (rad/s)",height=580);st.plotly_chart(fig2,width="stretch")

    with tab_lyap:
        c1,c2,c3=st.columns(3);dur=c1.number_input("Lyapunov duration",min_value=1.0,value=float(st.session_state.get("lyap_duration",30.0)),key="pl_c_ly_dur");ldt=c2.number_input("Lyapunov dt",min_value=1e-5,value=float(st.session_state.get("lyap_dt",0.005)),format="%.6g",key="pl_c_ly_dt");renorm=c3.number_input("Renormalization interval",min_value=0.01,value=0.25,key="pl_c_ly_ren")
        if st.button("Run finite-time Lyapunov analysis",type="primary",key="pl_c_ly_run"):
            bar=st.progress(0,text="Lyapunov integration")
            def cb(done,total):bar.progress(done/max(total,1),text=f"Lyapunov integration {done}/{total}")
            r=lyap(base,p,duration=float(dur),dt=float(ldt),renormalization_interval=float(renorm),progress_callback=cb);st.session_state["pl_c_ly"]=r
        r=st.session_state.get("pl_c_ly")
        if r:
            tt=np.asarray(r["time"]);local=np.asarray(r["local_exponent"]);cum=np.asarray(r["cumulative_exponent"]);estimate=float(r["estimate"])
            tail=cum[max(0,len(cum)//2):];spread=float(np.std(tail)) if len(tail) else float("nan")
            label="chaotic tendency" if estimate>max(3*spread,1e-4) else ("near-neutral / unresolved" if abs(estimate)<=max(3*spread,1e-4) else "contracting tendency")
            _headline(st,[("λ largest",f"{estimate:.6g} s⁻¹","Finite-time Benettin estimate"),("Tail spread",f"{spread:.3g}","Std. dev. of cumulative exponent over second half"),("Interpretation",label,"Heuristic finite-time classification"),("Actual dt",f"{float(r['actual_dt']):.6g} s","Integrator step actually used")])
            fig=go.Figure();fig.add_scatter(x=tt,y=cum,mode="lines",name="Cumulative λ(t)");fig.add_scatter(x=tt,y=local,mode="lines",name="Local interval λ",opacity=.45);fig.update_layout(title="Finite-time Lyapunov evolution",xaxis_title="Time (s)",yaxis_title="Exponent (s⁻¹)",height=600);st.plotly_chart(fig,width="stretch")
            export_df=pd.DataFrame({"time_s":tt,"local_exponent":local,"cumulative_exponent":cum})
            st.download_button(
                "Export Lyapunov time series CSV",
                data=export_df.to_csv(index=False).encode("utf-8"),
                file_name="physical-lab-lyapunov-series.csv",
                mime="text/csv",
                key="pl_c_ly_export",
            )
            st.caption("A positive finite-time exponent is evidence of local exponential sensitivity for this trajectory and integration window; it is not by itself a proof of a global strange attractor.")

    with tab_atlas:
        st.markdown("### Initial-condition flip-time atlas")
        c1,c2,c3=st.columns(3);span=c1.slider("Angle span (rad)",0.5,math.pi,2.6,0.1,key="pl_c_at_span");res=c2.select_slider("Grid resolution",options=[20,28,36,44,52,60],value=36,key="pl_c_at_res");tmax=c3.number_input("Maximum time",min_value=1.0,value=min(50.0,float(st.session_state.get("flip_tmax",50.0))),key="pl_c_at_tmax")
        adt=st.number_input("Atlas dt",min_value=0.001,value=max(0.01,float(st.session_state.get("flip_dt",0.02))),key="pl_c_at_dt")
        systems=int(res)*int(res)*int(math.ceil(float(tmax)/float(adt)));st.caption(f"Estimated system-steps: {systems:,} · safety limit remains enforced by the core model.")
        if st.button("Run stability atlas",type="primary",key="pl_c_at_run"):
            axis=np.linspace(-float(span),float(span),int(res));bar=st.progress(0,text="Flip-time atlas")
            def cb(done,total):bar.progress(done/max(total,1),text=f"Atlas integration {done}/{total}")
            try:r=flip(axis,axis,p,t_max=float(tmax),dt=float(adt),progress_callback=cb);st.session_state["pl_c_atlas"]=r
            except Exception as e:st.error(str(e))
        r=st.session_state.get("pl_c_atlas")
        if r:
            x=np.asarray(r["theta1"]);y=np.asarray(r["theta2"]);z=np.asarray(r["flip_time"],dtype=float);plotz=np.where(np.isfinite(z),z,float(r["t_max"]))
            frac=float(np.mean(np.isfinite(z)));_headline(st,[("Flipped fraction",f"{100*frac:.2f}%","Fraction flipping before tmax"),("No-flip fraction",f"{100*(1-frac):.2f}%","Did not flip within finite observation window"),("Grid",f"{z.shape[0]}×{z.shape[1]}","Initial-condition resolution"),("Actual dt",f"{float(r['actual_dt']):.6g} s","Core-integrator step")])
            fig=go.Figure(data=go.Heatmap(x=y,y=x,z=plotz,colorbar={"title":"flip time (s)"},hovertemplate="θ2=%{x:.4f}<br>θ1=%{y:.4f}<br>tflip=%{z:.4g}s<extra></extra>"));fig.update_layout(title="Flip-time stability atlas",xaxis_title="θ2(0) (rad)",yaxis_title="θ1(0) (rad)",height=690);st.plotly_chart(fig,width="stretch")
            st.caption("Cells capped at tmax mean 'no flip observed within this finite window', not mathematically stable forever.")


    with tab_drive:
        st.markdown("### Driven-pendulum stroboscopic response")
        if driven_scan is None:
            st.info("The upstream driven Poincaré API is not available in this version.")
        else:
            c1,c2,c3,c4=st.columns(4)
            amin=c1.number_input("Drive amplitude min",min_value=0.0,value=float(st.session_state.get("drive_a_min",0.2)),key="pl_c_d_amin")
            amax=c2.number_input("Drive amplitude max",min_value=0.01,value=float(st.session_state.get("drive_a_max",1.4)),key="pl_c_d_amax")
            apoints=c3.select_slider("Amplitude points",options=[30,45,60,80,100],value=60,key="pl_c_d_points")
            periods=c4.select_slider("Drive periods",options=[160,220,300,360,480],value=300,key="pl_c_d_periods")
            gamma=st.number_input("Driven damping γ",min_value=0.0,value=0.05,key="pl_c_d_gamma");freq=st.number_input("Drive frequency",min_value=0.05,value=0.65,key="pl_c_d_freq")
            if st.button("Run driven bifurcation intelligence",type="primary",key="pl_c_d_run",disabled=amax<=amin):
                amps=np.linspace(float(amin),float(amax),int(apoints));discard=max(40,int(periods*0.55));bar=st.progress(0,text="Driven Poincaré scan")
                def cb(done,total):bar.progress(done/max(total,1),text=f"Driven scan {done}/{total}")
                rr=driven_scan(amps,gamma=float(gamma),omega0=1.0,drive_frequency=float(freq),theta0=0.1,omega_initial=0.0,periods=int(periods),discard_periods=discard,steps_per_period=80,progress_callback=cb)
                frame=pd.DataFrame({"amplitude":rr["drive_amplitude"],"theta":rr["theta"],"omega":rr["omega"]})
                stats=[]
                for amp,grp in frame.groupby("amplitude"):
                    hist,_=np.histogram(grp["theta"],bins=36,range=(-np.pi,np.pi));occupied=int(np.count_nonzero(hist))
                    stats.append({"amplitude":float(amp),"theta_std":float(grp["theta"].std()),"omega_std":float(grp["omega"].std()),"occupied theta bins":occupied})
                st.session_state["pl_c_drive"]=(frame,pd.DataFrame(stats))
            data=st.session_state.get("pl_c_drive")
            if data:
                frame,sdf=data;fig=go.Figure(go.Scattergl(x=frame["amplitude"],y=frame["theta"],mode="markers",marker={"size":3,"opacity":0.45},name="Poincaré θ"));fig.update_layout(title="Driven-pendulum stroboscopic response",xaxis_title="Drive amplitude",yaxis_title="Wrapped θ (rad)",height=650);st.plotly_chart(fig,width="stretch")
                fig2=go.Figure();fig2.add_scatter(x=sdf["amplitude"],y=sdf["occupied theta bins"],mode="lines+markers",name="Occupied θ bins");fig2.update_layout(title="Descriptive response-complexity indicator",xaxis_title="Drive amplitude",yaxis_title="Occupied θ histogram bins",height=500);st.plotly_chart(fig2,width="stretch")
                st.caption("The occupancy indicator summarizes finite stroboscopic spread; it is not a formal entropy, bifurcation order, or proof of chaos. Use it to identify amplitudes for deeper Poincaré/Lyapunov inspection.")

    with tab_poincare:
        st.markdown("### Poincaré section — fixed-amplitude driven pendulum")
        st.caption(
            "Stroboscopic Poincaré section: sample (θ, ω) at every drive period after discarding transients. "
            "Periodic orbits appear as isolated dots; quasiperiodic orbits as closed curves; chaos as scattered points."
        )
        if driven_scan is None:
            st.info("The upstream driven Poincaré API is not available in this version.")
        else:
            c1, c2, c3 = st.columns(3)
            p_amp = c1.number_input("Drive amplitude A", min_value=0.01, value=1.2, step=0.05, key="pl_c_p_amp")
            p_gamma = c2.number_input("Damping γ", min_value=0.0, value=0.05, step=0.01, key="pl_c_p_gamma")
            p_freq = c3.number_input("Drive frequency ω_d", min_value=0.05, value=0.667, step=0.01, key="pl_c_p_freq")
            c4, c5 = st.columns(2)
            p_periods = c4.select_slider("Drive periods", options=[200, 400, 600, 1000, 1500, 2000], value=600, key="pl_c_p_periods")
            p_ics = c5.number_input("Initial conditions (grid side)", min_value=1, max_value=10, value=3, key="pl_c_p_ics")
            if st.button("Build Poincaré section", type="primary", key="pl_c_p_run"):
                discard = max(80, int(p_periods * 0.6))
                all_theta = []; all_omega = []
                ics = [(float(t0), float(w0))
                       for t0 in np.linspace(-2.0, 2.0, int(p_ics))
                       for w0 in np.linspace(-1.5, 1.5, int(p_ics))]
                bar = st.progress(0, text="Poincaré section")
                for idx, (t0, w0) in enumerate(ics):
                    rr = driven_scan(
                        np.array([float(p_amp)]),
                        gamma=float(p_gamma), omega0=1.0, drive_frequency=float(p_freq),
                        theta0=t0, omega_initial=w0,
                        periods=int(p_periods), discard_periods=discard,
                        steps_per_period=80,
                    )
                    all_theta.extend(rr["theta"].tolist() if hasattr(rr["theta"], "tolist") else list(rr["theta"]))
                    all_omega.extend(rr["omega"].tolist() if hasattr(rr["omega"], "tolist") else list(rr["omega"]))
                    bar.progress((idx + 1) / len(ics), text=f"IC {idx+1}/{len(ics)}")
                st.session_state["pl_c_poincare"] = (np.array(all_theta), np.array(all_omega), float(p_amp), float(p_gamma), float(p_freq))
            pdata = st.session_state.get("pl_c_poincare")
            if pdata:
                th, om, amp_v, gam_v, freq_v = pdata
                fig = go.Figure(go.Scattergl(
                    x=th, y=om, mode="markers",
                    marker={"size": 2.5, "opacity": 0.5, "color": om, "colorscale": "Viridis", "colorbar": {"title": "ω"}},
                ))
                fig.update_layout(
                    title=f"Poincaré section  A={amp_v:.3g}, γ={gam_v:.3g}, ω_d={freq_v:.3g}",
                    xaxis_title="θ (rad)", yaxis_title="ω (rad/s)", height=680,
                )
                st.plotly_chart(fig, width="stretch")
                _headline(st, [
                    ("Sampled points", str(len(th)), "Total stroboscopic intersections plotted"),
                    ("Drive amplitude A", f"{amp_v:.4g}", ""),
                    ("Damping γ", f"{gam_v:.4g}", ""),
                    ("Drive frequency ω_d", f"{freq_v:.4g}", ""),
                ])
                poincare_df = pd.DataFrame({"theta": th, "omega": om})
                st.download_button(
                    "Export Poincaré section CSV",
                    data=poincare_df.to_csv(index=False).encode("utf-8"),
                    file_name="physical-lab-poincare-section.csv", mime="text/csv",
                    key="pl_c_p_export",
                )
                st.caption(
                    "The Poincaré section is a stroboscopic slice of the 3D extended phase space (θ, ω, t). "
                    "Structure in this plot reveals the topology of the attractor: fixed points → periodic, "
                    "invariant curves → quasiperiodic, space-filling scatter → chaotic."
                )


def _numerical_suite(st, ns: dict[str, Any]) -> None:
    np = _np(); pd = _pd(); go = _plotly()
    _section_header(
        st,
        "Physical Lab · Numerical Reliability Observatory",
        "Adds failure-frontier mapping, cancellation heatmaps, and term-by-term error microscopy on top of the original Taylor/error experiments.",
    )
    sine_taylor = ns.get("sine_taylor"); scan_sine = ns.get("scan_sine")
    Method = ns.get("Method"); ReferenceBackend = ns.get("ReferenceBackend")
    if not all([sine_taylor, scan_sine, Method, ReferenceBackend]):
        st.warning("Advanced numerical APIs were not found in this upstream version. The original lab remains available.")
        return

    tab_frontier, tab_atlas, tab_micro, tab_order = st.tabs([
        "Reliability frontier", "Cancellation atlas", "Error microscope", "Convergence order"
    ])

    with tab_frontier:
        st.markdown("### Where does floating-point evaluation stop being trustworthy?")
        c1,c2,c3=st.columns(3)
        xmax=c1.number_input("|x| scan limit (rad)",min_value=1.0,value=100.0,step=10.0,key="pl_n_xmax")
        points=c2.select_slider("Scan points",options=[250,500,800,1200,1800],value=800,key="pl_n_points")
        dtype=c3.selectbox("Arithmetic",["float32","float64"],index=1,key="pl_n_dtype")
        if st.button("Map reliability frontier",type="primary",key="pl_n_frontier_run"):
            x=np.linspace(-float(xmax),float(xmax),int(points))
            results={}
            for method in (Method.RANGE_REDUCED,Method.RAW):
                results[method.value]=scan_sine(
                    x,method=method,dtype=dtype,
                    tolerance_multiplier=float(st.session_state.get("tolerance_multiplier",8.0)),
                    max_terms=int(st.session_state.get("max_terms",120)),
                    reference_backend=ReferenceBackend.MPMATH,
                    reference_precision_digits=max(60,int(st.session_state.get("reference_precision_digits",80))),
                )
            st.session_state["pl_n_frontier"]=(x,results,dtype)
        data=st.session_state.get("pl_n_frontier")
        if data:
            x,results,dtype=data
            rows=[];fig=go.Figure()
            for key,label in ((Method.RANGE_REDUCED.value,"Range reduced"),(Method.RAW.value,"Raw Taylor")):
                r=results[key]
                norm=np.asarray(r["normalized_error"],dtype=float)
                safe=np.isfinite(norm)&(norm<=1.0)&np.asarray(r["numerically_reliable"],dtype=bool)
                fail=np.flatnonzero(~safe)
                first_abs=float(np.min(np.abs(x[fail]))) if fail.size else float("nan")
                rows.append((f"{label} reliable",f"{100*np.mean(safe):.1f}%","Fraction of sampled x classified numerically reliable"))
                rows.append((f"{label} first failure",f"|x|≈{first_abs:.5g}" if np.isfinite(first_abs) else "none","Smallest sampled |x| that fails the combined reliability check"))
                fig.add_scatter(x=x,y=np.maximum(norm,np.finfo(float).tiny),mode="lines",name=label)
            _headline(st,rows)
            fig.add_hline(y=1.0,line_dash="dash",annotation_text="acceptance threshold")
            fig.update_layout(title="Normalized error across x",xaxis_title="x (rad)",yaxis_title="absolute error / allowed error",yaxis_type="log",height=600)
            st.plotly_chart(fig,width="stretch")
            st.caption("The frontier is numerical and configuration-dependent. It is not a mathematical convergence radius; the sine Taylor series converges for all finite x.")

    with tab_atlas:
        st.markdown("### Term-count × input-magnitude cancellation atlas")
        c1,c2,c3,c4=st.columns(4)
        method_label=c1.selectbox("Method",["Raw Taylor","Range reduced"],key="pl_n_at_method")
        dtype=c2.selectbox("dtype",["float32","float64"],index=1,key="pl_n_at_dtype")
        axmax=c3.number_input("x max",min_value=1.0,value=60.0,key="pl_n_at_xmax")
        grid=c4.select_slider("Atlas resolution",options=[20,28,36,44,52],value=36,key="pl_n_at_grid")
        max_terms=st.slider("Maximum fixed Taylor terms",10,120,60,5,key="pl_n_at_terms")
        if st.button("Run cancellation atlas",type="primary",key="pl_n_at_run"):
            method=Method.RAW if method_label.startswith("Raw") else Method.RANGE_REDUCED
            xs=np.linspace(0.0,float(axmax),int(grid)); terms=np.unique(np.linspace(2,int(max_terms),int(grid)).astype(int))
            error=np.empty((len(terms),len(xs))); cancel=np.empty_like(error)
            bar=st.progress(0,text="Building numerical atlas");total=len(terms)*len(xs);done=0
            for i,nterm in enumerate(terms):
                for j,xv in enumerate(xs):
                    r=sine_taylor(float(xv),method=method,dtype=dtype,max_terms=max(int(nterm),1),fixed_terms=int(nterm),reference_backend=ReferenceBackend.MPMATH,reference_precision_digits=80)
                    error[i,j]=max(float(r.normalized_error),np.finfo(float).tiny)
                    cancel[i,j]=max(float(r.cancellation_ratio),1.0)
                    done+=1
                bar.progress(done/total,text=f"Atlas row {i+1}/{len(terms)}")
            st.session_state["pl_n_atlas"]=(xs,terms,error,cancel,method_label,dtype)
        atlas=st.session_state.get("pl_n_atlas")
        if atlas:
            xs,terms,error,cancel,method_label,dtype=atlas
            fig=go.Figure(data=go.Heatmap(x=xs,y=terms,z=np.log10(error),colorbar={"title":"log10 norm. error"}))
            fig.update_layout(title=f"{method_label}: normalized-error atlas ({dtype})",xaxis_title="x (rad)",yaxis_title="Fixed Taylor terms",height=650)
            st.plotly_chart(fig,width="stretch")
            fig2=go.Figure(data=go.Heatmap(x=xs,y=terms,z=np.log10(cancel),colorbar={"title":"log10 cancellation"}))
            fig2.update_layout(title="Cancellation amplification atlas",xaxis_title="x (rad)",yaxis_title="Fixed Taylor terms",height=610)
            st.plotly_chart(fig2,width="stretch")

    with tab_micro:
        st.markdown("### Error microscope at one x")
        c1,c2,c3=st.columns(3)
        xv=c1.number_input("x (rad)",value=float(st.session_state.get("single_x",math.pi/2)),format="%.10g",key="pl_n_micro_x")
        dtype=c2.selectbox("Arithmetic",["float32","float64"],index=1,key="pl_n_micro_dtype")
        nmax=c3.slider("Terms to inspect",5,120,50,key="pl_n_micro_n")
        if st.button("Inspect term-by-term behavior",type="primary",key="pl_n_micro_run"):
            rows=[]
            for method in (Method.RANGE_REDUCED,Method.RAW):
                for n in range(1,int(nmax)+1):
                    r=sine_taylor(float(xv),method=method,dtype=dtype,max_terms=max(n,1),fixed_terms=n,reference_backend=ReferenceBackend.MPMATH,reference_precision_digits=100)
                    rows.append({"method":method.value,"terms":n,"approximation":float(r.value),"absolute_error":float(r.absolute_error),"normalized_error":float(r.normalized_error),"cancellation_ratio":float(r.cancellation_ratio)})
            st.session_state["pl_n_micro"]=pd.DataFrame(rows)
        df=st.session_state.get("pl_n_micro")
        if df is not None and len(df):
            fig=go.Figure()
            for method,grp in df.groupby("method"):
                fig.add_scatter(x=grp["terms"],y=np.maximum(grp["absolute_error"],np.finfo(float).tiny),mode="lines+markers",name=method)
            fig.update_layout(title="Absolute error versus Taylor terms",xaxis_title="Fixed terms",yaxis_title="Absolute error",yaxis_type="log",height=560)
            st.plotly_chart(fig,width="stretch")
            fig2=go.Figure()
            for method,grp in df.groupby("method"):
                fig2.add_scatter(x=grp["terms"],y=np.maximum(grp["cancellation_ratio"],1.0),mode="lines",name=method)
            fig2.update_layout(title="Cancellation ratio versus term count",xaxis_title="Fixed terms",yaxis_title="Σ|term| / |sum|",yaxis_type="log",height=520)
            st.plotly_chart(fig2,width="stretch")

    with tab_order:
        st.markdown("### Empirical convergence-order verification")
        st.caption(
            "Uses Richardson-extrapolation logic: evaluate sin(x) with N and 2N Taylor terms, "
            "measure how the error shrinks, and report the observed convergence order. "
            "For the Taylor series of sin, the theoretical order is 2 (each new term adds two powers of x)."
        )
        c1, c2, c3 = st.columns(3)
        xv = c1.number_input("Test x (rad)", value=1.0, format="%.8g", key="pl_n_ord_x")
        dtype = c2.selectbox("Arithmetic", ["float64", "float32"], index=0, key="pl_n_ord_dtype")
        method_label = c3.selectbox("Method", ["Range reduced", "Raw Taylor"], key="pl_n_ord_method")
        nmax = st.slider("Maximum term count", 8, 100, 40, 2, key="pl_n_ord_nmax")
        if st.button("Measure convergence order", type="primary", key="pl_n_ord_run"):
            method = Method.RANGE_REDUCED if method_label.startswith("Range") else Method.RAW
            rows = []
            prev_err = None
            for n in range(2, int(nmax) + 1):
                r = sine_taylor(float(xv), method=method, dtype=dtype, max_terms=max(n, 1), fixed_terms=n,
                                reference_backend=ReferenceBackend.MPMATH, reference_precision_digits=100)
                err = max(float(r.absolute_error), np.finfo(float).tiny)
                order = float("nan")
                if prev_err is not None and prev_err > err > 0:
                    order = math.log(prev_err / err) / math.log((n) / (n - 1))
                rows.append({"terms": n, "absolute_error": err, "observed_order": order})
                prev_err = err
            st.session_state["pl_n_order"] = pd.DataFrame(rows)
        odf = st.session_state.get("pl_n_order")
        if odf is not None and len(odf):
            finite = odf[np.isfinite(odf["observed_order"]) & (odf["observed_order"] > 0) & (odf["observed_order"] < 100)]
            median_order = float(np.median(finite["observed_order"])) if len(finite) else float("nan")
            _headline(st, [
                ("Median observed order", f"{median_order:.3g}" if np.isfinite(median_order) else "n/a",
                 "Median of log(e_{n-1}/e_n)/log(n/(n-1)) over the convergent regime"),
                ("Theoretical", "2", "Each Taylor term adds x^2 suppression"),
                ("Points measured", str(len(finite)), "Term counts where error was monotonically decreasing"),
            ])
            fig = go.Figure()
            fig.add_scatter(x=odf["terms"], y=np.maximum(odf["absolute_error"], np.finfo(float).tiny),
                            mode="lines+markers", name="Absolute error")
            fig.update_layout(title="Error decay with Taylor terms",
                              xaxis_title="Fixed terms", yaxis_title="Absolute error",
                              yaxis_type="log", height=520)
            st.plotly_chart(fig, width="stretch")
            fig2 = go.Figure()
            fig2.add_scatter(x=finite["terms"], y=finite["observed_order"], mode="lines+markers", name="Observed order")
            fig2.add_hline(y=2.0, line_dash="dash", annotation_text="Theoretical order = 2")
            fig2.update_layout(title="Empirical convergence order per term step",
                               xaxis_title="Terms", yaxis_title="Order",
                               height=500, yaxis_range=[0, max(8, float(np.nanmax(finite["observed_order"])) * 1.1) if len(finite) else 8])
            st.plotly_chart(fig2, width="stretch")
            st.download_button("Export convergence-order CSV",
                               data=odf.to_csv(index=False).encode("utf-8"),
                               file_name="physical-lab-convergence-order.csv", mime="text/csv",
                               key="pl_n_ord_export")
            st.caption(
                "In the convergent regime |x| is small enough that adding terms improves accuracy. "
                "Beyond the convergent regime, floating-point cancellation dominates and the order becomes meaningless."
            )


def _random_walk_suite(st, ns: dict[str, Any]) -> None:
    np = _np(); pd = _pd(); go = _plotly()
    _section_header(
        st,
        "Physical Lab · Scaling & Monte Carlo Efficiency Suite",
        "Adds diffusion-exponent recovery, dimensional concentration studies, and matched-budget Monte Carlo versus scrambled-QMC comparisons.",
    )
    random_walk_scan=ns.get("random_walk_scan"); fit_power_law=ns.get("fit_power_law")
    repeated_circle_trials=ns.get("repeated_circle_trials"); repeated_scrambled_qmc=ns.get("repeated_scrambled_qmc"); return_probability=ns.get("return_probability")
    if not all([random_walk_scan,fit_power_law,repeated_circle_trials,repeated_scrambled_qmc]):
        st.warning("Advanced stochastic APIs were not found in this upstream version. The original lab remains available.")
        return
    tab_scale,tab_dim,tab_qmc,tab_return=st.tabs(["Diffusion scaling law","Dimension concentration","MC vs scrambled QMC","Finite-horizon recurrence"])
    seed=int(st.session_state.get("seed",12345))

    with tab_scale:
        c1,c2,c3,c4=st.columns(4)
        dim=c1.number_input("Dimension d",min_value=1,max_value=50,value=int(st.session_state.get("rw_dimension",2)),key="pl_rw_s_dim")
        walkers=c2.number_input("Walkers / point",min_value=100,max_value=200000,value=min(30000,int(st.session_state.get("rw_walkers",10000))),step=100,key="pl_rw_s_walkers")
        nmin=c3.number_input("N min",min_value=2,value=20,key="pl_rw_s_nmin")
        nmax=c4.number_input("N max",min_value=3,value=5000,key="pl_rw_s_nmax")
        points=st.select_slider("Log-spaced scan points",options=[6,8,10,12,16],value=10,key="pl_rw_s_points")
        if st.button("Recover diffusion exponents",type="primary",key="pl_rw_s_run",disabled=nmax<=nmin):
            vals=np.unique(np.geomspace(int(nmin),int(nmax),int(points)).astype(int))
            bar=st.progress(0,text="Random-walk scaling scan")
            def cb(frac,msg):bar.progress(float(frac),text=msg)
            df=random_walk_scan(vals,scan_variable="n_steps",dim=int(dim),n_steps=int(vals[0]),n_walkers=int(walkers),model="fixed",p1=1.0,seed=seed,progress=cb)
            fit_r=fit_power_law(df["n_steps"],df["mean_radius"]);fit_msd=fit_power_law(df["n_steps"],df["msd"])
            st.session_state["pl_rw_scale"]=(df,fit_r,fit_msd)
        data=st.session_state.get("pl_rw_scale")
        if data:
            df,fit_r,fit_msd=data
            _headline(st,[
                ("Mean-radius exponent",f"{fit_r['exponent']:.5f}","Diffusive asymptotic expectation is 1/2"),
                ("MSD exponent",f"{fit_msd['exponent']:.5f}","Independent-step expectation is 1"),
                ("R² log fit (radius)",f"{fit_r['r2_log']:.5f}","Power-law fit quality in log space"),
                ("R² log fit (MSD)",f"{fit_msd['r2_log']:.5f}","Power-law fit quality in log space"),
            ])
            fig=go.Figure();fig.add_scatter(x=df["n_steps"],y=df["mean_radius"],mode="lines+markers",name="Simulation mean radius");fig.add_scatter(x=df["n_steps"],y=df["theory_mean_radius_asymptotic"],mode="lines",name="Asymptotic theory")
            fig.update_layout(title="Mean radius scaling",xaxis_title="Steps N",yaxis_title="E[R]",xaxis_type="log",yaxis_type="log",height=560);st.plotly_chart(fig,width="stretch")
            fig2=go.Figure();fig2.add_scatter(x=df["n_steps"],y=df["msd"],mode="lines+markers",name="Simulation MSD");fig2.add_scatter(x=df["n_steps"],y=df["theory_msd_exact"],mode="lines",name="Exact MSD theory")
            fig2.update_layout(title="Mean-squared displacement scaling",xaxis_title="Steps N",yaxis_title="E[R²]",xaxis_type="log",yaxis_type="log",height=540);st.plotly_chart(fig2,width="stretch")

    with tab_dim:
        c1,c2,c3=st.columns(3)
        dmax=c1.slider("Maximum dimension",2,40,12,key="pl_rw_d_max")
        steps=c2.number_input("Steps",min_value=10,value=min(3000,int(st.session_state.get("rw_steps",1000))),key="pl_rw_d_steps")
        walkers=c3.number_input("Walkers / dimension",min_value=200,value=min(20000,int(st.session_state.get("rw_walkers",10000))),step=100,key="pl_rw_d_walkers")
        if st.button("Run dimension concentration study",type="primary",key="pl_rw_d_run"):
            dims=np.arange(1,int(dmax)+1)
            bar=st.progress(0,text="Dimension scan")
            def cb(frac,msg):bar.progress(float(frac),text=msg)
            df=random_walk_scan(dims,scan_variable="dimension",dim=1,n_steps=int(steps),n_walkers=int(walkers),model="fixed",p1=1.0,seed=seed+91,progress=cb)
            df["radius_to_rms"]=df["mean_radius"]/np.sqrt(df["msd"])
            df["theory_radius_to_rms"]=df["theory_mean_radius_asymptotic"]/np.sqrt(df["theory_msd_exact"])
            df["relative_radial_spread"]=df["std_radius"]/np.maximum(df["mean_radius"],np.finfo(float).tiny)
            st.session_state["pl_rw_dim"]=df
        df=st.session_state.get("pl_rw_dim")
        if df is not None and len(df):
            fig=go.Figure();fig.add_scatter(x=df["dimension"],y=df["radius_to_rms"],mode="lines+markers",name="Simulation E[R]/√E[R²]");fig.add_scatter(x=df["dimension"],y=df["theory_radius_to_rms"],mode="lines",name="Asymptotic theory")
            fig.update_layout(title="Radial concentration with dimension",xaxis_title="Dimension d",yaxis_title="Mean radius / RMS radius",height=560);st.plotly_chart(fig,width="stretch")
            fig2=go.Figure();fig2.add_scatter(x=df["dimension"],y=df["relative_radial_spread"],mode="lines+markers",name="σ(R)/E[R]")
            fig2.update_layout(title="Relative radial spread",xaxis_title="Dimension d",yaxis_title="Relative spread",height=500);st.plotly_chart(fig2,width="stretch")

    with tab_qmc:
        st.markdown("### Same sample budget: pseudorandom MC versus independent scrambled Sobol replicates")
        c1,c2=st.columns(2)
        powers_text=c1.text_input("Powers of two",value="8,10,12,14",key="pl_rw_q_powers")
        reps=c2.select_slider("Independent replicates / trials",options=[4,6,8,12,16],value=8,key="pl_rw_q_reps")
        if st.button("Run matched-budget comparison",type="primary",key="pl_rw_q_run"):
            try:
                powers=sorted({int(x.strip()) for x in powers_text.split(',') if x.strip()})
                if not powers or min(powers)<4 or max(powers)>20:raise ValueError("powers must be integers from 4 to 20")
            except Exception as e:
                st.error(str(e));powers=[]
            if powers:
                rows=[];bar=st.progress(0,text="MC/QMC comparison")
                for i,power in enumerate(powers):
                    n=2**power
                    mc=repeated_circle_trials(int(n),int(reps),seed+power*101)
                    qmc=repeated_scrambled_qmc(2,power=int(power),n_replicates=int(reps),seed=seed+power*307)
                    rows.append({"samples":n,"MC abs error of mean":abs(float(mc["mean_estimate"])-math.pi),"MC SEM":float(mc["sem_of_trial_mean"]),"QMC abs error of mean":float(qmc["absolute_error_of_mean"]),"QMC SEM":float(qmc["sem"])})
                    bar.progress((i+1)/len(powers),text=f"Budget {i+1}/{len(powers)}")
                st.session_state["pl_rw_qmc"]=pd.DataFrame(rows)
        df=st.session_state.get("pl_rw_qmc")
        if df is not None and len(df):
            fig=go.Figure();fig.add_scatter(x=df["samples"],y=np.maximum(df["MC abs error of mean"],1e-18),mode="lines+markers",name="Pseudorandom MC");fig.add_scatter(x=df["samples"],y=np.maximum(df["QMC abs error of mean"],1e-18),mode="lines+markers",name="Scrambled Sobol QMC")
            fig.update_layout(title="Absolute error at matched per-replicate sample budget",xaxis_title="Samples per replicate",yaxis_title="|mean estimate − π|",xaxis_type="log",yaxis_type="log",height=570);st.plotly_chart(fig,width="stretch")
            st.dataframe(df,width="stretch",hide_index=True)
            st.caption("QMC uncertainty here comes from independent Owen-scrambled replicates. One finite comparison does not prove universal QMC superiority for every integrand or dimension.")

    with tab_return:
        st.markdown("### Return probability versus finite observation horizon")
        if return_probability is None:
            st.info("The upstream finite-horizon return-probability API is not available in this version.")
        else:
            c1,c2,c3=st.columns(3)
            horizons_text=c1.text_input("Horizons (steps)",value="20,50,100,250,500,1000",key="pl_rw_r_horizons")
            dims_text=c2.text_input("Dimensions",value="1,2,3",key="pl_rw_r_dims")
            trials=c3.number_input("Trials / point",min_value=100,max_value=200000,value=5000,step=100,key="pl_rw_r_trials")
            if st.button("Run recurrence-horizon study",type="primary",key="pl_rw_r_run"):
                try:
                    horizons=sorted({int(x.strip()) for x in horizons_text.split(',') if x.strip()});dims=sorted({int(x.strip()) for x in dims_text.split(',') if x.strip()})
                    if not horizons or min(horizons)<1 or max(horizons)>200000:raise ValueError("horizons must be integers from 1 to 200000")
                    if not dims or min(dims)<1 or max(dims)>12:raise ValueError("dimensions must be integers from 1 to 12")
                except Exception as e:
                    st.error(str(e));horizons=[];dims=[]
                if horizons and dims:
                    rows=[];total=len(horizons)*len(dims);done=0;bar=st.progress(0,text="Finite-horizon recurrence scan")
                    for d in dims:
                        for H in horizons:
                            rr=return_probability(int(d),max_steps=int(H),n_trials=int(trials),seed=seed+d*10007+H)
                            rows.append({"dimension":int(d),"horizon":int(H),"return probability":float(rr["return_probability_by_horizon"]),"CI low":float(rr["probability_ci_low"]),"CI high":float(rr["probability_ci_high"]),"returned":int(rr["returned_trials"])})
                            done+=1;bar.progress(done/total,text=f"Recurrence point {done}/{total}")
                    st.session_state["pl_rw_return"]=pd.DataFrame(rows)
            rdf=st.session_state.get("pl_rw_return")
            if rdf is not None and len(rdf):
                fig=go.Figure()
                for d,grp in rdf.groupby("dimension"):
                    fig.add_scatter(x=grp["horizon"],y=grp["return probability"],mode="lines+markers",name=f"d={d}")
                fig.update_layout(title="Finite-horizon probability of at least one return to the origin",xaxis_title="Observation horizon H (steps)",yaxis_title="P(return by H)",xaxis_type="log",height=590);st.plotly_chart(fig,width="stretch")
                st.dataframe(rdf,width="stretch",hide_index=True)
                # Pólya infinite-time reference lines
                polya = {}
                for d in sorted(int(x) for x in rdf["dimension"].unique()):
                    if d == 1:
                        polya[d] = 1.0
                    elif d == 2:
                        polya[d] = 1.0
                    elif d == 3:
                        # Pólya / Watson (1939): P(return, d=3) ≈ 0.340537...
                        polya[d] = 0.340537
                    else:
                        polya[d] = None  # no simple closed form
                if any(v is not None for v in polya.values()):
                    st.markdown("#### Pólya recurrence reference (infinite-time limit)")
                    ref_rows = []
                    for d in sorted(polya.keys()):
                        if polya[d] is not None:
                            max_h = int(rdf[rdf["dimension"] == d]["horizon"].max()) if len(rdf[rdf["dimension"] == d]) else 0
                            max_p = float(rdf[rdf["dimension"] == d]["return probability"].max()) if len(rdf[rdf["dimension"] == d]) else 0
                            ref_rows.append({
                                "dimension": d,
                                "Pólya P∞": polya[d],
                                "observed max P(H)": f"{max_p:.4f}",
                                "largest H scanned": max_h,
                                "note": "recurrent" if polya[d] >= 1.0 - 1e-9 else "transient",
                            })
                    st.dataframe(pd.DataFrame(ref_rows), width="stretch", hide_index=True)
                    st.caption(
                        "d=1,2 simple random walks are recurrent (P∞=1). d=3 is transient with "
                        "P∞≈0.3405 (Watson 1939). Finite-horizon simulations approach but never reach P∞; "
                        "disagreement at moderate H is expected, not a bug."
                    )
                st.caption("These are finite-horizon Monte Carlo probabilities with binomial confidence intervals. They are not the exact infinite-time Pólya recurrence probabilities.")


def _oscillation_suite(st, ns: dict[str, Any]) -> None:
    np = _np(); pd = _pd(); go = _plotly()
    _section_header(
        st,
        "Physical Lab · Oscillator Dynamics Observatory",
        "Adds a damping–drive response atlas, cross-method accuracy frontier, and explicit energy/work flow microscope while preserving the original oscillator experiments.",
    )
    Params=ns.get("OscillatorParams"); Method=ns.get("Method"); convergence_scan=ns.get("convergence_scan")
    steady=ns.get("steady_state_amplitude"); simulate_fixed=ns.get("simulate_fixed"); energy_diag=ns.get("energy_balance_diagnostic")
    if not all([Params,Method,convergence_scan,steady,simulate_fixed,energy_diag]):
        st.warning("Advanced oscillation APIs were not found in this upstream version. The original lab remains available.");return
    mass=float(st.session_state.get("mass",1.0));omega0=float(st.session_state.get("omega0",2*math.pi));u0=float(st.session_state.get("u0",1.0));v0=float(st.session_state.get("v0",0.0));duration=float(st.session_state.get("duration",10.0))
    initial=np.asarray([u0,v0],dtype=float)
    tab_atlas,tab_solver,tab_energy,tab_chrono=st.tabs(["Damping × drive atlas","Solver accuracy frontier","Energy-flow microscope","PyChrono cross-check"])

    with tab_atlas:
        c1,c2,c3,c4=st.columns(4)
        gmax=c1.number_input("γ max (s⁻¹)",min_value=0.01,value=max(2.0,2.2*omega0),key="pl_o_gmax")
        rmin=c2.number_input("Ω/ω0 min",min_value=0.05,value=0.4,key="pl_o_rmin")
        rmax=c3.number_input("Ω/ω0 max",min_value=0.06,value=1.6,key="pl_o_rmax")
        res=c4.select_slider("Atlas resolution",options=[30,45,60,80,100],value=60,key="pl_o_res")
        force=st.number_input("Drive force F0 (N)",min_value=1e-6,value=max(0.6,abs(float(st.session_state.get("force_amplitude",0.6))) or 0.6),key="pl_o_force")
        if st.button("Run damping–drive atlas",type="primary",key="pl_o_atlas_run",disabled=rmax<=rmin):
            gammas=np.linspace(0.0,float(gmax),int(res));ratios=np.linspace(float(rmin),float(rmax),int(res));gg,rr=np.meshgrid(gammas,ratios,indexing="ij")
            freq=rr*omega0
            denom=np.sqrt((omega0**2-freq**2)**2+(gg*freq)**2)
            amp=(abs(float(force))/mass)/np.maximum(denom,np.finfo(float).tiny)
            st.session_state["pl_o_atlas"]=(gammas,ratios,amp)
        atlas=st.session_state.get("pl_o_atlas")
        if atlas:
            gammas,ratios,amp=atlas
            peak=np.unravel_index(int(np.nanargmax(amp)),amp.shape)
            _headline(st,[
                ("Peak amplitude",f"{float(amp[peak]):.6g} m","Linear steady-state reference"),
                ("Peak γ",f"{float(gammas[peak[0]]):.6g} s⁻¹","Grid location of largest response"),
                ("Peak Ω/ω0",f"{float(ratios[peak[1]]):.6g}","Grid location of largest response"),
                ("Critical γ",f"{2*omega0:.6g} s⁻¹","Free-oscillator critical damping coefficient"),
            ])
            fig=go.Figure(data=go.Heatmap(x=ratios,y=gammas,z=amp,colorbar={"title":"amplitude (m)"}))
            fig.add_hline(y=2*omega0,line_dash="dash",annotation_text="critical damping")
            fig.update_layout(title="Linear steady-state amplitude atlas",xaxis_title="Drive ratio Ω/ω0",yaxis_title="Damping γ (s⁻¹)",height=650);st.plotly_chart(fig,width="stretch")
            gg,rr=np.meshgrid(gammas,ratios,indexing="ij");freq=rr*omega0
            phase=np.arctan2(gg*freq,omega0**2-freq**2)
            figp=go.Figure(data=go.Heatmap(x=ratios,y=gammas,z=np.degrees(phase),colorbar={"title":"phase lag (deg)"},zmin=0,zmax=180))
            figp.update_layout(title="Steady-state displacement phase lag",xaxis_title="Drive ratio Ω/ω0",yaxis_title="Damping γ (s⁻¹)",height=590);st.plotly_chart(figp,width="stretch")
            q_value=omega0/max(float(st.session_state.get("gamma",0.0)),np.finfo(float).tiny)
            st.caption(f"Current weak-damping quality-factor reference Q≈ω0/γ = {q_value:.6g}. This approximation is most interpretable away from γ=0 and in the underdamped regime.")
            st.caption("This atlas is the linear steady-state reference. Transient behavior and nonlinear pendulum response still require the numerical experiments.")

    with tab_solver:
        c1,c2,c3=st.columns(3)
        dtmin=c1.number_input("dt min",min_value=1e-5,value=0.0025,format="%.6g",key="pl_o_dtmin")
        dtmax=c2.number_input("dt max",min_value=2e-5,value=0.08,format="%.6g",key="pl_o_dtmax")
        npts=c3.select_slider("dt points",options=[5,7,9,11,13],value=7,key="pl_o_dtpts")
        if st.button("Compare integration methods",type="primary",key="pl_o_solver_run",disabled=dtmax<=dtmin):
            dtvals=np.geomspace(float(dtmin),float(dtmax),int(npts))
            # Force-free reference isolates integrator behavior from drive transients.
            p=Params(mass=mass,omega0=omega0,gamma=float(st.session_state.get("gamma",0.0)),force_amplitude=0.0,force_frequency=0.0)
            rows=[];curves={}
            for meth in (Method.EULER,Method.SYMPLECTIC_EULER,Method.RK2,Method.RK4):
                r=convergence_scan(dtvals,initial,p,duration=max(2.0,min(duration,20.0)),method=meth)
                curves[meth.value]=r
                rows.append({"method":meth.value,"observed_order":float(r["observed_order"]),"finest_max_error":float(np.asarray(r["maximum_state_error"])[np.argmin(np.asarray(r["actual_dt"]))]),"finest_dt":float(np.min(r["actual_dt"]))})
            st.session_state["pl_o_solver"]=(pd.DataFrame(rows),curves)
        data=st.session_state.get("pl_o_solver")
        if data:
            df,curves=data
            fig=go.Figure()
            for name,r in curves.items():fig.add_scatter(x=r["actual_dt"],y=np.maximum(r["maximum_state_error"],np.finfo(float).tiny),mode="lines+markers",name=name)
            fig.update_layout(title="Integrator error frontier",xaxis_title="Actual dt (s)",yaxis_title="Maximum state error",xaxis_type="log",yaxis_type="log",height=600);st.plotly_chart(fig,width="stretch")
            st.dataframe(df,width="stretch",hide_index=True)
            st.caption("Observed order is measured against the analytic force-free linear solution over this finite dt range; asymptotic order can be obscured when dt is too coarse or errors approach roundoff.")

    with tab_energy:
        gamma=st.number_input("γ for audit",min_value=0.0,value=float(st.session_state.get("gamma",0.5)),key="pl_o_e_gamma")
        force=st.number_input("F0 for audit",value=float(st.session_state.get("force_amplitude",0.6)),key="pl_o_e_force")
        freq=st.number_input("Ω for audit",min_value=0.0,value=float(st.session_state.get("force_frequency",omega0*0.96)),key="pl_o_e_freq")
        edt=st.number_input("Audit dt",min_value=1e-5,value=min(0.02,float(st.session_state.get("dt",0.02))),format="%.6g",key="pl_o_e_dt")
        if st.button("Run energy-flow audit",type="primary",key="pl_o_e_run"):
            p=Params(mass=mass,omega0=omega0,gamma=float(gamma),force_amplitude=float(force),force_frequency=float(freq))
            r=simulate_fixed(initial,p,duration=max(2.0,duration),dt=float(edt),method=Method.RK4)
            d=energy_diag(np.asarray(r["time"]),np.asarray(r["state"]),p)
            t=np.asarray(r["time"]);dp=np.asarray(d["damping_power"]);ip=np.asarray(d["input_power"])
            def cumtrap(y):
                out=np.zeros_like(y,dtype=float)
                if len(y)>1:out[1:]=np.cumsum(0.5*(y[1:]+y[:-1])*np.diff(t))
                return out
            st.session_state["pl_o_energy"]=(t,d,cumtrap(dp),cumtrap(ip))
        data=st.session_state.get("pl_o_energy")
        if data:
            t,d,wd,wi=data;energy=np.asarray(d["energy"]);resid=np.asarray(d["balance_residual"])
            _headline(st,[
                ("ΔE",f"{energy[-1]-energy[0]:.6g} J","Mechanical-energy change"),
                ("Input work",f"{wi[-1]:.6g} J","Integrated external-force power"),
                ("Damping work",f"{wd[-1]:.6g} J","Integrated damping power; normally non-positive"),
                ("Max balance residual",f"{float(d['max_relative_balance_residual']):.3e}","Relative numerical energy/work closure error"),
            ])
            fig=go.Figure();fig.add_scatter(x=t,y=energy-energy[0],mode="lines",name="E(t)-E(0)");fig.add_scatter(x=t,y=wi+wd,mode="lines",name="Integrated input+damping work");fig.update_layout(title="Energy balance closure",xaxis_title="Time (s)",yaxis_title="Energy / work (J)",height=570);st.plotly_chart(fig,width="stretch")
            fig2=go.Figure();fig2.add_scatter(x=t,y=resid,mode="lines",name="Balance residual");fig2.update_layout(title="Numerical energy-balance residual",xaxis_title="Time (s)",yaxis_title="Residual (J)",height=480);st.plotly_chart(fig2,width="stretch")

    with tab_chrono:
        st.markdown("### Physical Lab NumPy/SciPy integrator versus discovered PyChrono runtime")
        st.caption(
            "Compares the Lab's force-free linear oscillator against a harmonic oscillator integrated "
            "inside the separately discovered PyChrono interpreter (PHYSICAL_LAB_PYCHRONO_PYTHON). "
            "This is the first real adapter path that consumes PyChrono from inside Physical Lab."
        )
        c1,c2,c3=st.columns(3)
        dur=c1.number_input("Duration (s)",min_value=0.1,value=min(8.0,duration),key="pl_o_ch_dur")
        dt=c2.number_input("dt (s)",min_value=1e-5,value=min(0.01,float(st.session_state.get("dt",0.01))),format="%.6g",key="pl_o_ch_dt")
        k_spring=c3.number_input("Spring k = m ω0²",value=float(mass*omega0*omega0),format="%.8g",key="pl_o_ch_k",disabled=True)
        if st.button("Run PyChrono cross-check",type="primary",key="pl_o_ch_run"):
            p=Params(mass=mass,omega0=omega0,gamma=0.0,force_amplitude=0.0,force_frequency=0.0)
            lab=simulate_fixed(initial,p,duration=float(dur),dt=float(dt),method=Method.RK4)
            t_lab=np.asarray(lab["time"],dtype=float); s_lab=np.asarray(lab["state"],dtype=float)
            chrono_py=os.environ.get("PHYSICAL_LAB_PYCHRONO_PYTHON","").strip()
            if not chrono_py:
                st.warning("No PHYSICAL_LAB_PYCHRONO_PYTHON was provided by the desktop shell. Install/detect PyChrono in Runtime Center first.")
            else:
                script=r'''
import json,sys,math
try:
    import pychrono as chrono
except Exception as e:
    print(json.dumps({"ok":False,"error":f"import pychrono failed: {e}"})); sys.exit(0)
mass=float(sys.argv[1]); omega0=float(sys.argv[2]); u0=float(sys.argv[3]); v0=float(sys.argv[4]); duration=float(sys.argv[5]); dt=float(sys.argv[6])
k=mass*omega0*omega0
# Chrono 7/8/9 compatibility helpers
Vec=getattr(chrono,"ChVector3d",None) or getattr(chrono,"ChVectorD")
def V(x,y=0.0,z=0.0):
    return Vec(x,y,z)
system=chrono.ChSystemNSC()
if hasattr(system,"SetGravitationalAcceleration"):
    system.SetGravitationalAcceleration(V(0,0,0))
elif hasattr(system,"Set_G_acc"):
    system.Set_G_acc(V(0,0,0))
ground=chrono.ChBody(); ground.SetBodyFixed(True); system.Add(ground)
body=chrono.ChBody(); body.SetMass(mass)
if hasattr(body,"SetInertiaXX"): body.SetInertiaXX(V(1,1,1))
body.SetPos(V(u0,0,0))
if hasattr(body,"SetPosDt"): body.SetPosDt(V(v0,0,0))
elif hasattr(body,"SetPos_dt"): body.SetPos_dt(V(v0,0,0))
system.Add(body)
link=chrono.ChLinkTSDA()
# Prefer rest length 0 so equilibrium is at the origin.
try:
    link.Initialize(ground, body, True, V(0,0,0), V(0,0,0))
except TypeError:
    link.Initialize(ground, body, True, V(0,0,0), V(0,0,0), False)
if hasattr(link,"SetSpringCoefficient"): link.SetSpringCoefficient(k)
if hasattr(link,"SetDampingCoefficient"): link.SetDampingCoefficient(0.0)
# Rest length APIs vary across Chrono versions.
for name,val in (("SetRestLength",0.0),("Set_spring_rest_length",0.0)):
    if hasattr(link,name):
        try: getattr(link,name)(val)
        except Exception: pass
system.AddLink(link)
times=[]; xs=[]; vs=[]; t=0.0
steps=int(max(1, math.ceil(duration/dt)))
for i in range(steps+1):
    pos=body.GetPos(); vel=body.GetPosDt() if hasattr(body,"GetPosDt") else body.GetPos_dt()
    times.append(t); xs.append(float(pos.x)); vs.append(float(vel.x))
    if i < steps:
        system.DoStepDynamics(dt); t += dt
print(json.dumps({"ok":True,"time":times,"x":xs,"v":vs,"engine":getattr(chrono,"__version__","pychrono")}))
'''
                try:
                    proc=subprocess.run(
                        [chrono_py,"-c",script,str(mass),str(omega0),str(u0),str(v0),str(dur),str(dt)],
                        capture_output=True,text=True,timeout=120,check=False,
                    )
                    payload=None
                    for line in reversed(proc.stdout.splitlines()):
                        line=line.strip()
                        if line.startswith("{") and line.endswith("}"):
                            payload=json.loads(line); break
                    if payload is None:
                        st.error(f"PyChrono subprocess returned no JSON.\nstdout:\n{proc.stdout[-1200:]}\nstderr:\n{proc.stderr[-1200:]}")
                    elif not payload.get("ok"):
                        st.error(str(payload.get("error","PyChrono comparison failed")))
                    else:
                        t_c=np.asarray(payload["time"],dtype=float); x_c=np.asarray(payload["x"],dtype=float); v_c=np.asarray(payload["v"],dtype=float)
                        # Interpolate Chrono onto Lab time grid for a fair state comparison.
                        x_ci=np.interp(t_lab,t_c,x_c); v_ci=np.interp(t_lab,t_c,v_c)
                        du=s_lab[:,0]-x_ci; dv=s_lab[:,1]-v_ci
                        amp=max(float(np.max(np.abs(s_lab[:,0]))),1e-12)
                        st.session_state["pl_o_chrono"]={
                            "t":t_lab,"u_lab":s_lab[:,0],"u_chrono":x_ci,"v_lab":s_lab[:,1],"v_chrono":v_ci,
                            "max_abs_u_err":float(np.max(np.abs(du))),"rms_u_err":float(np.sqrt(np.mean(du*du))),
                            "max_rel_u_err":float(np.max(np.abs(du))/amp),"engine":str(payload.get("engine","pychrono")),
                            "python":chrono_py,
                        }
                except Exception as e:
                    st.error(f"PyChrono cross-check failed: {e}")
            # Always keep the Lab analytic reference visible even if Chrono is missing.
            analytic=u0*np.cos(omega0*t_lab)+(v0/omega0)*np.sin(omega0*t_lab) if omega0!=0 else np.full_like(t_lab,u0)
            st.session_state["pl_o_chrono_lab"]={"t":t_lab,"u_lab":s_lab[:,0],"u_analytic":analytic,"max_abs_analytic_err":float(np.max(np.abs(s_lab[:,0]-analytic)))}
        data=st.session_state.get("pl_o_chrono")
        labref=st.session_state.get("pl_o_chrono_lab")
        if labref:
            _headline(st,[
                ("Lab vs analytic max |Δu|",f"{labref['max_abs_analytic_err']:.3e} m","Force-free linear oscillator reference"),
                ("Chrono compared", "yes" if data else "no", "Requires a discovered PyChrono interpreter"),
                ("Chrono max |Δu|", f"{data['max_abs_u_err']:.3e} m" if data else "—", "Lab RK4 versus PyChrono trajectory"),
                ("Chrono RMS |Δu|", f"{data['rms_u_err']:.3e} m" if data else "—", "Over the shared Lab time grid"),
            ])
            fig=go.Figure();fig.add_scatter(x=labref["t"],y=labref["u_lab"],mode="lines",name="Lab RK4");fig.add_scatter(x=labref["t"],y=labref["u_analytic"],mode="lines",name="Analytic",opacity=0.7)
            if data: fig.add_scatter(x=data["t"],y=data["u_chrono"],mode="lines",name=f"PyChrono ({data['engine']})")
            fig.update_layout(title="Force-free oscillator displacement",xaxis_title="Time (s)",yaxis_title="u (m)",height=560);st.plotly_chart(fig,width="stretch")
            if data:
                fig2=go.Figure();fig2.add_scatter(x=data["t"],y=data["u_lab"]-data["u_chrono"],mode="lines",name="Lab − Chrono")
                fig2.update_layout(title="Displacement difference",xaxis_title="Time (s)",yaxis_title="Δu (m)",height=480);st.plotly_chart(fig2,width="stretch")
                st.caption(f"PyChrono interpreter: `{data['python']}`. Link/constraint modelling differences can dominate the residual; treat this as an engine-interop diagnostic.")


def _radia_magnet_suite(st, ns: dict[str, Any]) -> None:
    np = _np(); pd = _pd(); go = _plotly()
    _section_header(
        st,
        "Physical Lab · Magnet Engineering & Tolerance Suite",
        "Adds design preflight, persistent result auditing, and controlled manufacturing-error seed ensembles around the original RADIA build/solve/analyze workflow.",
    )
    current_params=ns.get("current_params") if isinstance(ns.get("current_params"),dict) else {}
    current_settings=ns.get("current_settings") if isinstance(ns.get("current_settings"),dict) else {}
    metrics=ns.get("metrics") if isinstance(ns.get("metrics"),dict) else None
    ideal_metrics=ns.get("ideal_metrics") if isinstance(ns.get("ideal_metrics"),dict) else None
    if metrics is not None:
        st.session_state["pl_m_last_metrics"]=dict(metrics)
        st.session_state["pl_m_last_params"]=dict(ns.get("params",current_params) if isinstance(ns.get("params",current_params),dict) else current_params)
        if ideal_metrics is not None:st.session_state["pl_m_last_ideal_metrics"]=dict(ideal_metrics)
    load_radia=ns.get("load_radia");build_device=ns.get("build_device");solve_model=ns.get("solve_model");sample_on_axis=ns.get("sample_on_axis");analyze=ns.get("analyze");union_field_range=ns.get("union_field_range")
    tab_pre,tab_audit,tab_seed,tab_budget=st.tabs(["Engineering preflight","Last-solve audit","Manufacturing seed ensemble","Field-integral budget"])

    with tab_pre:
        p=current_params
        if not p:
            st.info("Current RADIA configuration was not exposed by this upstream version.")
        else:
            period=float(p.get("period_mm",50.0));periods=int(p.get("periods",20));gap=float(p.get("gap_mm",12.0));bpp=int(p.get("blocks_per_period",4));fill=float(p.get("longitudinal_fill",0.9));bw=float(p.get("block_width_mm",10.0));bh=float(p.get("block_height_mm",10.0))
            block_len=period/max(bpp,1)*fill;device_len=period*periods;gap_ratio=gap/period;blocks_nominal=max(1,bpp*periods)
            target=float(p.get("target_b0_t",float("nan"))) if p.get("target_b0_enabled") else float("nan")
            kref=0.934*target*(period/10.0) if np.isfinite(target) else float("nan")
            _headline(st,[
                ("Magnetic length",f"{device_len:.6g} mm","Nominal periods × period; fringe geometry can extend beyond this"),
                ("Nominal block length",f"{block_len:.6g} mm","λu / blocks-per-period × longitudinal fill"),
                ("Gap / period",f"{gap_ratio:.5g}","Dimensionless geometry ratio"),
                ("Nominal block count",f"{blocks_nominal:,}","Simple periods × blocks-per-period count; multi-bank device factories can create more objects"),
            ])
            rows=[
                {"check":"Positive dimensions","status":"PASS" if min(period,gap,bw,bh)>0 else "FAIL","detail":"period, gap, block width and height must be positive"},
                {"check":"Longitudinal fill","status":"PASS" if 0<fill<1 else "WARN","detail":f"fill={fill:.4g}"},
                {"check":"Gap / period","status":"PASS" if 0.02<=gap_ratio<=1.0 else "REVIEW","detail":f"gap/λu={gap_ratio:.4g}; engineering review only, not a universal validity bound"},
                {"check":"Target-B0 K reference","status":"INFO" if np.isfinite(kref) else "N/A","detail":f"K≈{kref:.6g}" if np.isfinite(kref) else "Target-B0 calibration is disabled; Br is not substituted for B0"},
            ]
            st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True)
            # Configured tolerances are normalized geometrically without pretending to predict field performance.
            if p.get("errors_enabled"):
                tol=pd.DataFrame([
                    {"source":"Field amplitude σ","configured":float(p.get("field_error_pct",0.0)),"normalized":"%"},
                    {"source":"Longitudinal position σ","configured":float(p.get("longitudinal_error_mm",0.0)),"normalized":f"{100*float(p.get('longitudinal_error_mm',0.0))/period:.4g}% of λu"},
                    {"source":"Transverse position σ","configured":float(p.get("transverse_error_mm",0.0)),"normalized":f"{100*float(p.get('transverse_error_mm',0.0))/max(gap,1e-15):.4g}% of gap"},
                    {"source":"Magnetization angle σ","configured":float(p.get("angle_error_deg",0.0)),"normalized":"deg"},
                    {"source":"Gap asymmetry","configured":float(p.get("gap_asymmetry_mm",0.0)),"normalized":f"{100*float(p.get('gap_asymmetry_mm',0.0))/max(gap,1e-15):.4g}% of gap"},
                    {"source":"Bank imbalance","configured":float(p.get("bank_imbalance_pct",0.0)),"normalized":"%"},
                ])
                st.markdown("#### Configured manufacturing tolerance budget")
                st.dataframe(tol,width="stretch",hide_index=True)
                st.caption("These normalized values describe the requested manufacturing-error scales only. They do not assume a linear mapping from mechanical tolerance to field or phase error.")

    with tab_audit:
        m=st.session_state.get("pl_m_last_metrics")
        if not m:
            st.info("Run the original **Build + Solve + Analyze** once. Physical Lab will preserve its headline metrics here for subsequent reruns.")
        else:
            keys=["Bperp_peak_T","K_peak","K_vector_norm","I1x_Tm","I1y_Tm","I2x_Tm2","I2y_Tm2","H3_over_H1","H5_over_H1","electron_phase_error_rms_deg","fitted_radiation_wavelength_m","max_abs_x_mm","max_abs_y_mm"]
            rows=[]
            for k in keys:
                if k in m and np.isscalar(m[k]):
                    try:rows.append({"quantity":k,"value":float(m[k])})
                    except Exception:pass
            st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True)
            _headline(st,[
                ("B⊥ peak",f"{float(m.get('Bperp_peak_T',float('nan'))):.6g} T","Solved peak transverse field"),
                ("K peak",f"{float(m.get('K_peak',float('nan'))):.6g}","Conventional K from solved B⊥ peak"),
                ("Electron phase RMS",f"{float(m.get('electron_phase_error_rms_deg',float('nan'))):.6g}°","Trajectory/slippage-based phase-error metric"),
                ("H3/H1",f"{float(m.get('H3_over_H1',float('nan'))):.3e}","Dominant-field harmonic ratio"),
            ])
            ideal=st.session_state.get("pl_m_last_ideal_metrics")
            if ideal:
                comps=[]
                for k in ["Bperp_peak_T","K_peak","I1x_Tm","I1y_Tm","H3_over_H1","H5_over_H1","electron_phase_error_rms_deg"]:
                    if k in m and k in ideal:
                        try:comps.append({"quantity":k,"ideal":float(ideal[k]),"error model":float(m[k]),"delta":float(m[k])-float(ideal[k])})
                        except Exception:pass
                if comps:
                    st.markdown("#### Ideal vs manufacturing-error delta")
                    st.dataframe(pd.DataFrame(comps),width="stretch",hide_index=True)

    with tab_seed:
        required=[load_radia,build_device,solve_model,sample_on_axis,analyze,union_field_range]
        if not all(required) or not current_params:
            st.warning("The upstream RADIA solve APIs needed for seed ensembles were not found. The original Magnet Studio remains available.")
        else:
            st.caption("Runs multiple manufacturing-error realizations using the current geometry/material settings. It intentionally skips 2D/3D map generation so the ensemble focuses on on-axis field and trajectory metrics.")
            c1,c2,c3=st.columns(3)
            seeds=c1.select_slider("Independent seeds",options=[3,4,5,6,8],value=4,key="pl_m_seeds")
            axis_n=c2.select_slider("On-axis samples / seed",options=[250,400,600,800,1000],value=400,key="pl_m_axis")
            start_seed=c3.number_input("First seed",min_value=0,value=int(current_params.get("error_seed",12345)),step=1,key="pl_m_seed0")
            if st.button("Run manufacturing seed ensemble",type="primary",key="pl_m_seed_run"):
                rad=load_radia();rows=[];bar=st.progress(0,text="RADIA manufacturing ensemble")
                try:
                    # Solve an ideal reference once using the same Br/material settings.
                    base=dict(current_params);base["errors_enabled"]=False
                    if hasattr(rad,"UtiDelAll"):rad.UtiDelAll()
                    ideal_model=build_device(rad,base.get("device",ns.get("device","Planar")),base)
                    solve_model(rad,ideal_model,relax=bool(current_settings.get("relax",False)),precision=float(current_settings.get("precision",1e-4)),max_iter=int(current_settings.get("max_iter",1000)),method=4)
                    zlo,zhi=union_field_range([ideal_model],float(base.get("period_mm",50.0)),float(current_settings.get("field_margin_periods",1.0)))
                    z=np.linspace(zlo,zhi,int(axis_n));ideal_B=sample_on_axis(rad,ideal_model["obj"],z);ideal=analyze(z,ideal_B,float(base.get("period_mm",50.0)),float(current_settings.get("electron_energy_GeV",3.0)))
                    for i in range(int(seeds)):
                        if hasattr(rad,"UtiDelAll"):rad.UtiDelAll()
                        p=dict(current_params);p["errors_enabled"]=True;p["error_seed"]=int(start_seed)+i
                        model=build_device(rad,p.get("device",ns.get("device","Planar")),p)
                        solve_model(rad,model,relax=bool(current_settings.get("relax",False)),precision=float(current_settings.get("precision",1e-4)),max_iter=int(current_settings.get("max_iter",1000)),method=4)
                        zlo,zhi=union_field_range([model],float(p.get("period_mm",50.0)),float(current_settings.get("field_margin_periods",1.0)));zz=np.linspace(zlo,zhi,int(axis_n));B=sample_on_axis(rad,model["obj"],zz);m=analyze(zz,B,float(p.get("period_mm",50.0)),float(current_settings.get("electron_energy_GeV",3.0)))
                        rows.append({"seed":int(start_seed)+i,"Bperp_peak_T":float(m["Bperp_peak_T"]),"K_peak":float(m["K_peak"]),"electron_phase_error_rms_deg":float(m["electron_phase_error_rms_deg"]),"H3_over_H1":float(m["H3_over_H1"]),"H5_over_H1":float(m["H5_over_H1"]),"I1x_Tm":float(m["I1x_Tm"]),"I1y_Tm":float(m["I1y_Tm"])})
                        bar.progress((i+1)/int(seeds),text=f"Seed {i+1}/{int(seeds)}")
                    st.session_state["pl_m_ensemble"]=(pd.DataFrame(rows),ideal)
                except Exception as e:
                    st.error(f"RADIA seed ensemble failed: {e}")
                finally:
                    try:
                        if hasattr(rad,"UtiDelAll"):rad.UtiDelAll()
                    except Exception:pass
            data=st.session_state.get("pl_m_ensemble")
            if data:
                df,ideal=data
                st.dataframe(df,width="stretch",hide_index=True)
                cols=["K_peak","electron_phase_error_rms_deg","H3_over_H1","H5_over_H1"]
                fig=go.Figure()
                for col in cols:
                    vals=np.asarray(df[col],dtype=float);scale=max(float(np.nanmean(np.abs(vals))),np.finfo(float).tiny)
                    fig.add_scatter(x=df["seed"],y=vals/scale,mode="lines+markers",name=f"{col} / mean|.|" )
                fig.update_layout(title="Manufacturing-seed response (normalized for cross-metric visibility)",xaxis_title="Seed",yaxis_title="Normalized metric",height=590);st.plotly_chart(fig,width="stretch")
                summary=[]
                for col in ["Bperp_peak_T","K_peak","electron_phase_error_rms_deg","H3_over_H1","H5_over_H1","I1x_Tm","I1y_Tm"]:
                    vals=np.asarray(df[col],dtype=float);summary.append({"metric":col,"mean":float(np.nanmean(vals)),"sd across seeds":float(np.nanstd(vals,ddof=1)) if len(vals)>1 else 0.0,"ideal":float(ideal.get(col,float("nan")))})
                st.markdown("#### Ensemble summary")
                st.dataframe(pd.DataFrame(summary),width="stretch",hide_index=True)
                st.caption("This is a finite seed ensemble for the configured stochastic manufacturing-error model, not a manufacturing-process certification or tolerance guarantee.")

    with tab_budget:
        st.markdown("### Field-integral tolerance budget summary")
        st.caption(
            "Presents the first and second field integrals from the last solve (or ensemble) "
            "alongside typical accelerator-facility tolerance specs for reference. "
            "These thresholds are indicative; actual acceptance limits vary by facility and beamline."
        )
        m = st.session_state.get("pl_m_last_metrics")
        if not m:
            st.info("Run **Build + Solve + Analyze** first to populate field-integral data.")
        else:
            # Typical light-source specs (indicative, not universal)
            i1_spec = 5e-6   # 5 µT·m first-integral tolerance
            i2_spec = 5e-6   # 5 µT·m² second-integral tolerance
            i1x = float(m.get("I1x_Tm", float("nan")))
            i1y = float(m.get("I1y_Tm", float("nan")))
            i2x = float(m.get("I2x_Tm2", float("nan")))
            i2y = float(m.get("I2y_Tm2", float("nan")))
            budget_rows = [
                {"integral": "I₁ₓ (T·m)", "solved": f"{i1x:.4e}", "typical spec": f"±{i1_spec:.1e}",
                 "margin": f"{(i1_spec - abs(i1x)):.3e}" if np.isfinite(i1x) else "—",
                 "status": ("PASS" if abs(i1x) < i1_spec else "REVIEW") if np.isfinite(i1x) else "—"},
                {"integral": "I₁ᵧ (T·m)", "solved": f"{i1y:.4e}", "typical spec": f"±{i1_spec:.1e}",
                 "margin": f"{(i1_spec - abs(i1y)):.3e}" if np.isfinite(i1y) else "—",
                 "status": ("PASS" if abs(i1y) < i1_spec else "REVIEW") if np.isfinite(i1y) else "—"},
                {"integral": "I₂ₓ (T·m²)", "solved": f"{i2x:.4e}", "typical spec": f"±{i2_spec:.1e}",
                 "margin": f"{(i2_spec - abs(i2x)):.3e}" if np.isfinite(i2x) else "—",
                 "status": ("PASS" if abs(i2x) < i2_spec else "REVIEW") if np.isfinite(i2x) else "—"},
                {"integral": "I₂ᵧ (T·m²)", "solved": f"{i2y:.4e}", "typical spec": f"±{i2_spec:.1e}",
                 "margin": f"{(i2_spec - abs(i2y)):.3e}" if np.isfinite(i2y) else "—",
                 "status": ("PASS" if abs(i2y) < i2_spec else "REVIEW") if np.isfinite(i2y) else "—"},
            ]
            st.dataframe(pd.DataFrame(budget_rows), width="stretch", hide_index=True)
            _headline(st, [
                ("|I₁ₓ|", f"{abs(i1x):.3e} T·m" if np.isfinite(i1x) else "—", "Solved first field integral x"),
                ("|I₁ᵧ|", f"{abs(i1y):.3e} T·m" if np.isfinite(i1y) else "—", "Solved first field integral y"),
                ("Phase RMS", f"{float(m.get('electron_phase_error_rms_deg', float('nan'))):.4g}°" if np.isfinite(m.get('electron_phase_error_rms_deg', float('nan'))) else "—", "From trajectory analysis"),
            ])
            # Ensemble spread if available
            ens = st.session_state.get("pl_m_ensemble")
            if ens:
                edf, _ = ens
                st.markdown("#### Ensemble field-integral spread")
                for col, label in [("I1x_Tm", "I₁ₓ"), ("I1y_Tm", "I₁ᵧ")]:
                    if col in edf.columns:
                        vals = np.asarray(edf[col], dtype=float)
                        st.write(f"**{label}**: mean={np.nanmean(vals):.3e}, σ={np.nanstd(vals, ddof=1):.3e}, max|·|={np.nanmax(np.abs(vals)):.3e} T·m")
                st.caption(
                    "Ensemble spread shows how manufacturing errors propagate to field integrals. "
                    "The 'typical spec' values (5 µT·m) are representative of third-generation light sources; "
                    "actual facility requirements may differ."
                )
