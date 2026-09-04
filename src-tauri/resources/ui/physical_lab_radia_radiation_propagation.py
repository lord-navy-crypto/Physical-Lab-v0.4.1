"""Propagate RADIA manufacturing realizations into pinned trajectory/radiation physics.

Architecture:
  current RADIA Magnet Studio parameters
    -> real 3-D RADIA rebuild/solve/sample_3d per seed
    -> temporary NPZ field-map evidence
    -> managed Radiation Platform .venv worker
    -> pinned FieldMapInsertionDevice + run_sim_scalar
    -> finite-ensemble trajectory/radiation observables

The workflow is intentionally bounded and provenance-heavy. It does not claim
manufacturing yield, experimental validation, bunch physics, beamline optics or
detector response.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Iterable, Mapping, Sequence

RADIA_MAGNET_STUDIO_REVISION = "3bceb02a5195a6eb14d01458cc44f7206ed6b40a"
RADIATION_PLATFORM_REVISION = "6d19b36304c9d30f9b608214f7cfb9fcbaf941d4"
MAX_MEMBERS = 8
MAX_FIELD_POINTS_PER_MEMBER = 60000
SUMMARY_METRICS = (
    "photon_energy_eV",
    "f0",
    "P_larmor",
    "relative_linewidth",
    "P_circ",
    "max_transverse_excursion_m",
    "period_repeatability_rms_m",
    "orbit_phase_error_rms_rad",
    "exit_xprime_rad",
    "exit_yprime_rad",
)


def _full_mode() -> bool:
    return os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "").strip().lower() == "full"


def _managed_radiation_paths() -> tuple[Path, Path]:
    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
    if not raw:
        raise RuntimeError("PHYSICAL_LAB_DATA_DIR is unavailable")
    root = Path(raw).expanduser().resolve()
    module = root / "modules" / "radiation-platform"
    return module / "source", module / ".venv" / "bin" / "python"


def _verify_radiation_source(source: Path) -> dict[str, Any]:
    if not source.is_dir():
        raise RuntimeError("Radiation Platform is not installed in Physical Lab yet")
    meta_path = source / "physical-lab-source.json"
    if not meta_path.is_file():
        raise RuntimeError("Radiation Platform source metadata is missing; reinstall the managed module so its pinned revision can be verified")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    revision = str(meta.get("revision") or "")
    if revision != RADIATION_PLATFORM_REVISION:
        raise RuntimeError(
            f"Radiation Platform revision mismatch: managed={revision or 'unknown'} required={RADIATION_PLATFORM_REVISION}"
        )
    return meta


def radiation_platform_status() -> dict[str, Any]:
    try:
        source, python = _managed_radiation_paths()
        meta = _verify_radiation_source(source)
        ready = python.is_file()
        return {
            "ready": ready,
            "source": str(source),
            "python": str(python),
            "revision": meta.get("revision"),
            "detail": "Pinned Radiation Platform source and isolated Python environment are ready" if ready else "Radiation Platform source exists but its isolated .venv is missing",
        }
    except Exception as exc:
        return {"ready": False, "detail": str(exc)}


def _active_manufacturing_errors(params: Mapping[str, Any]) -> dict[str, float]:
    keys = [
        "field_error_pct", "longitudinal_error_mm", "transverse_error_mm",
        "angle_error_deg", "gap_asymmetry_mm", "bank_imbalance_pct",
    ]
    out: dict[str, float] = {}
    for key in keys:
        try:
            out[key] = float(params.get(key, 0.0) or 0.0)
        except Exception:
            out[key] = 0.0
    return out


def _finite(value: Any) -> float | None:
    try:
        x = float(value)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def summarize_propagation_records(
    nominal: Mapping[str, Any],
    members: Sequence[Mapping[str, Any]],
    metrics: Iterable[str] = SUMMARY_METRICS,
) -> dict[str, Any]:
    """Summarize already-computed cross-model records without distribution claims."""
    import numpy as np

    if len(members) < 2:
        raise ValueError("At least two propagated manufacturing realizations are required")
    nominal_obs = nominal.get("observables") if isinstance(nominal.get("observables"), Mapping) else nominal
    rows: dict[str, Any] = {}
    for metric in metrics:
        n0 = _finite(nominal_obs.get(metric))
        values: list[float] = []
        for member in members:
            obs = member.get("observables") if isinstance(member.get("observables"), Mapping) else member
            x = _finite(obs.get(metric))
            if x is not None:
                values.append(x)
        if not values:
            continue
        arr = np.asarray(values, dtype=float)
        q05, q50, q95 = np.quantile(arr, [0.05, 0.50, 0.95])
        row = {
            "nominal": n0,
            "count": int(len(arr)),
            "mean": float(np.mean(arr)),
            "sampleStdDev": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
            "min": float(np.min(arr)),
            "p05": float(q05),
            "median": float(q50),
            "p95": float(q95),
            "max": float(np.max(arr)),
        }
        if n0 is not None:
            delta = arr - n0
            row.update({
                "meanDeltaFromNominal": float(np.mean(delta)),
                "maxAbsDeltaFromNominal": float(np.max(np.abs(delta))),
                "p95AbsDeltaFromNominal": float(np.quantile(np.abs(delta), 0.95)),
            })
        rows[metric] = row
    return {
        "metrics": rows,
        "memberCount": len(members),
        "boundary": "Percentiles and extrema summarize only the explicit propagated solver realizations. They are not confidence intervals or manufacturing-yield guarantees unless the underlying process/error distribution is independently justified.",
    }


def assess_propagated_requirement(
    members: Sequence[Mapping[str, Any]],
    metric: str,
    *,
    lower: float | None = None,
    upper: float | None = None,
) -> dict[str, Any]:
    if lower is None and upper is None:
        raise ValueError("At least one requirement bound is required")
    values: list[float] = []
    for member in members:
        obs = member.get("observables") if isinstance(member.get("observables"), Mapping) else member
        x = _finite(obs.get(metric))
        if x is not None:
            values.append(x)
    if not values:
        raise ValueError(f"No finite values were produced for {metric}")
    passed = [
        (lower is None or x >= float(lower)) and (upper is None or x <= float(upper))
        for x in values
    ]
    return {
        "metric": metric,
        "status": "PASS" if all(passed) else "REVIEW",
        "lower": lower,
        "upper": upper,
        "observedPassCount": sum(passed),
        "observedCount": len(passed),
        "observedPassFraction": sum(passed) / len(passed),
        "observedMin": min(values),
        "observedMax": max(values),
        "boundary": "PASS means every sampled propagated realization met the entered engineering bound. It is not an unsampled production-yield certification.",
    }


def _build_and_sample_3d(
    namespace: Mapping[str, Any],
    params: Mapping[str, Any],
    *,
    x_mm,
    y_mm,
    z_mm,
):
    load_radia = namespace.get("load_radia")
    build_device = namespace.get("build_device")
    solve_model = namespace.get("solve_model")
    sample_3d = namespace.get("sample_3d")
    settings = dict(namespace.get("current_settings") or {})
    if not all(callable(x) for x in (load_radia, build_device, solve_model, sample_3d)):
        raise RuntimeError("Current RADIA Magnet Studio revision did not expose the 3-D solve APIs required for propagation")
    rad = load_radia()
    try:
        if hasattr(rad, "UtiDelAll"):
            rad.UtiDelAll()
        model = build_device(rad, params.get("device"), dict(params))
        solve_model(
            rad,
            model,
            relax=bool(settings.get("relax", False)),
            precision=float(settings.get("precision", 1e-4)),
            max_iter=int(settings.get("max_iter", 1000)),
            method=4,
        )
        return sample_3d(rad, model["obj"], x_mm, y_mm, z_mm)
    finally:
        try:
            if hasattr(rad, "UtiDelAll"):
                rad.UtiDelAll()
        except Exception:
            pass


def _z_grid(namespace: Mapping[str, Any], params: Mapping[str, Any], samples_per_period: int):
    import numpy as np

    load_radia = namespace.get("load_radia")
    build_device = namespace.get("build_device")
    union_field_range = namespace.get("union_field_range")
    settings = dict(namespace.get("current_settings") or {})
    if not all(callable(x) for x in (load_radia, build_device, union_field_range)):
        raise RuntimeError("RADIA geometry/range APIs are unavailable")
    p = dict(params)
    p["errors_enabled"] = False
    rad = load_radia()
    try:
        if hasattr(rad, "UtiDelAll"):
            rad.UtiDelAll()
        model = build_device(rad, p.get("device"), p)
        lo, hi = union_field_range(
            [model],
            float(p.get("period_mm", 50.0)),
            float(settings.get("field_margin_periods", 1.0)),
        )
    finally:
        try:
            if hasattr(rad, "UtiDelAll"):
                rad.UtiDelAll()
        except Exception:
            pass
    periods = max(2, int(p.get("periods", 20)))
    count = max(33, periods * int(samples_per_period) + 1)
    return np.linspace(float(lo), float(hi), count)


def _invoke_radiation_worker(
    source: Path,
    python: Path,
    map_path: Path,
    config: Mapping[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    worker = Path(__file__).resolve().with_name("physical_lab_radiation_worker.py")
    cfg = dict(config)
    cfg["radiationPlatformSource"] = str(source)
    cfg["fieldMapNpz"] = str(map_path)
    config_path = output_path.with_suffix(".config.json")
    config_path.write_text(json.dumps(cfg, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    proc = subprocess.run(
        [str(python), str(worker), "--config", str(config_path), "--output", str(output_path)],
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "Radiation Platform worker failed").strip()
        raise RuntimeError(detail[-5000:])
    return json.loads(output_path.read_text(encoding="utf-8"))


def run_radia_to_radiation_ensemble(
    namespace: Mapping[str, Any],
    *,
    members: int,
    seed_start: int,
    transverse_half_width_mm: float,
    transverse_points: int,
    z_samples_per_period: int,
    gamma: float,
    observer_distance_m: float,
    theta_x_mrad: float,
    theta_y_mrad: float,
    tracking_points_per_period: int,
) -> dict[str, Any]:
    if not _full_mode():
        raise RuntimeError("RADIA → Radiation propagation requires Physical Lab Full mode")
    source, python = _managed_radiation_paths()
    source_meta = _verify_radiation_source(source)
    if not python.is_file():
        raise RuntimeError("Radiation Platform isolated .venv is missing; repair/install that Lab first")
    params = dict(namespace.get("current_params") or {})
    if not params:
        raise RuntimeError("Current RADIA parameters are unavailable")
    if bool(params.get("target_b0_enabled")):
        raise ValueError("Freeze calibrated Br and disable target-B0 calibration before propagating manufacturing errors")
    errors = _active_manufacturing_errors(params)
    if not any(abs(x) > 0 for x in errors.values()):
        raise ValueError("Enter at least one non-zero RADIA manufacturing-error magnitude before propagation")
    n = int(members)
    if n < 2 or n > MAX_MEMBERS:
        raise ValueError(f"Use between 2 and {MAX_MEMBERS} propagated manufacturing realizations")
    nx = int(transverse_points)
    if nx not in {3, 5, 7}:
        raise ValueError("transverse_points must be 3, 5, or 7")
    if transverse_half_width_mm <= 0:
        raise ValueError("transverse half-width must be positive")
    if gamma <= 1.0:
        raise ValueError("electron gamma must be > 1")

    import numpy as np

    x_mm = np.linspace(-float(transverse_half_width_mm), float(transverse_half_width_mm), nx)
    y_mm = x_mm.copy()
    z_mm = _z_grid(namespace, params, int(z_samples_per_period))
    field_points = len(x_mm) * len(y_mm) * len(z_mm)
    if field_points > MAX_FIELD_POINTS_PER_MEMBER:
        raise ValueError(f"3-D field grid would contain {field_points:,} points/member; limit is {MAX_FIELD_POINTS_PER_MEMBER:,}")

    common_worker = {
        "periodMm": float(params.get("period_mm", 50.0)),
        "deviceName": str(params.get("device", "radia-field-map")),
        "gamma": float(gamma),
        "nPeriods": int(params.get("periods", 20)),
        "pointsPerPeriod": int(tracking_points_per_period),
        "observerDistanceM": float(observer_distance_m),
        "thetaXMrad": float(theta_x_mrad),
        "thetaYMrad": float(theta_y_mrad),
    }
    seeds = [int(seed_start) + i for i in range(n)]
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="physical-lab-radia-radiation-") as td:
        tmp = Path(td)
        nominal_params = dict(params)
        nominal_params["errors_enabled"] = False
        nominal_field = _build_and_sample_3d(namespace, nominal_params, x_mm=x_mm, y_mm=y_mm, z_mm=z_mm)
        nominal_map = tmp / "nominal.npz"
        np.savez_compressed(nominal_map, x_mm=x_mm, y_mm=y_mm, z_mm=z_mm, B_T=nominal_field)
        nominal = _invoke_radiation_worker(
            source, python, nominal_map,
            {**common_worker, "sourceLabel": "Physical Lab nominal RADIA 3-D field map"},
            tmp / "nominal.json",
        )
        nominal["seed"] = None
        nominal["kind"] = "nominal"

        for seed in seeds:
            p = dict(params)
            p["errors_enabled"] = True
            p["error_seed"] = int(seed)
            field = _build_and_sample_3d(namespace, p, x_mm=x_mm, y_mm=y_mm, z_mm=z_mm)
            map_path = tmp / f"seed-{seed}.npz"
            np.savez_compressed(map_path, x_mm=x_mm, y_mm=y_mm, z_mm=z_mm, B_T=field)
            record = _invoke_radiation_worker(
                source, python, map_path,
                {**common_worker, "sourceLabel": f"Physical Lab RADIA manufacturing seed {seed}"},
                tmp / f"seed-{seed}.json",
            )
            record["seed"] = int(seed)
            record["kind"] = "manufacturing-realization"
            records.append(record)

    return {
        "schema": "physical-lab-radia-radiation-propagation-v1",
        "radiaMagnetStudioRevision": RADIA_MAGNET_STUDIO_REVISION,
        "radiationPlatformRevision": RADIATION_PLATFORM_REVISION,
        "radiationPlatformSourceMetadata": source_meta,
        "manufacturingErrorModel": errors,
        "grid": {
            "transverseHalfWidthMm": float(transverse_half_width_mm),
            "nx": len(x_mm), "ny": len(y_mm), "nz": len(z_mm),
            "pointsPerRealization": field_points,
            "zSamplesPerPeriodRequested": int(z_samples_per_period),
        },
        "physicsInputs": common_worker,
        "nominal": nominal,
        "members": records,
        "summary": summarize_propagation_records(nominal, records),
        "boundary": "Each member uses a real 3-D RADIA manufacturing realization followed by the pinned Radiation Platform single-electron field-map solver. The finite ensemble is an engineering tolerance propagation study, not experimental validation, bunch-beam simulation, detector simulation or manufacturing-yield certification.",
    }


def render_radia_radiation_propagation(st: Any, namespace: Mapping[str, Any]) -> None:
    st.markdown("---")
    st.markdown("## Physical Lab · RADIA → Trajectory → Radiation Tolerance Propagation")
    st.caption(
        "Propagate the same manufacturing-error model through a real 3-D RADIA field map and the pinned Radiation Platform single-electron solver. "
        "This is deliberately more expensive than the on-axis field-envelope study."
    )
    status = radiation_platform_status()
    if not status.get("ready"):
        st.info(f"Radiation Platform is not ready for cross-model propagation: {status.get('detail')}")
        return
    if not _full_mode():
        st.info("Switch RADIA Magnet Studio to **Full mode** before generating 3-D manufacturing realizations.")
        return
    st.success(f"Pinned Radiation Platform ready · {str(status.get('revision'))[:12]}")

    params = dict(namespace.get("current_params") or {})
    if not params:
        st.warning("Current RADIA Magnet Studio parameters are unavailable.")
        return
    if bool(params.get("target_b0_enabled")):
        st.warning("Freeze the calibrated Br and disable target-B0 calibration before propagation so each random manufacturing seed is not re-tuned to the same field target.")

    c1, c2, c3, c4 = st.columns(4)
    members = c1.select_slider("Manufacturing realizations", options=[2, 3, 4, 6, 8], value=3, key="pl_rrp_members")
    nxy = c2.selectbox("3-D transverse grid", [3, 5, 7], index=1, format_func=lambda n: f"{n} × {n}", key="pl_rrp_nxy")
    half = c3.number_input("Transverse half-width (mm)", min_value=0.1, value=2.0, step=0.25, key="pl_rrp_half")
    zpp = c4.select_slider("RADIA z samples / period", options=[6, 8, 12, 16], value=8, key="pl_rrp_zpp")

    c5, c6, c7, c8 = st.columns(4)
    gamma = c5.number_input("Electron γ", min_value=1.01, value=100.0, step=1.0, format="%.6g", key="pl_rrp_gamma")
    distance = c6.number_input("Observer distance (m)", min_value=1.0, value=100.0, step=10.0, key="pl_rrp_distance")
    tx = c7.number_input("Observer θx (mrad)", value=0.0, step=0.05, key="pl_rrp_tx")
    ty = c8.number_input("Observer θy (mrad)", value=0.0, step=0.05, key="pl_rrp_ty")
    c9, c10 = st.columns(2)
    ppp = c9.select_slider("Trajectory samples / period", options=[32, 48, 64, 96], value=48, key="pl_rrp_ppp")
    seed0 = c10.number_input("First manufacturing seed", min_value=0, value=int(params.get("error_seed", 12345)), step=1, key="pl_rrp_seed0")
    estimated = int(nxy) * int(nxy) * (max(2, int(params.get("periods", 20))) * int(zpp) + 1) * (int(members) + 1)
    st.caption(f"Approximate RADIA field samples including nominal: {estimated:,}; each field map is then propagated through a separate Radiation Platform trajectory/radiation solve.")

    if st.button("Run field → trajectory → radiation propagation", type="primary", key="pl_rrp_run"):
        try:
            with st.spinner("Running cross-model engineering tolerance propagation…"):
                result = run_radia_to_radiation_ensemble(
                    namespace,
                    members=int(members),
                    seed_start=int(seed0),
                    transverse_half_width_mm=float(half),
                    transverse_points=int(nxy),
                    z_samples_per_period=int(zpp),
                    gamma=float(gamma),
                    observer_distance_m=float(distance),
                    theta_x_mrad=float(tx),
                    theta_y_mrad=float(ty),
                    tracking_points_per_period=int(ppp),
                )
            st.session_state["pl_rrp_result"] = result
        except Exception as exc:
            st.error(f"Cross-model propagation failed: {exc}")

    result = st.session_state.get("pl_rrp_result")
    if not result:
        return
    import pandas as pd
    import plotly.graph_objects as go

    summary_rows = []
    for metric, row in (result.get("summary") or {}).get("metrics", {}).items():
        summary_rows.append({"observable": metric, **row})
    if summary_rows:
        st.markdown("#### Propagated observable envelope")
        st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

    member_rows = []
    for member in result.get("members", []):
        member_rows.append({"seed": member.get("seed"), **(member.get("observables") or {})})
    frame = pd.DataFrame(member_rows)
    if not frame.empty:
        st.markdown("#### Manufacturing realization → radiation response")
        st.dataframe(frame, width="stretch", hide_index=True)
        metric_options = [m for m in SUMMARY_METRICS if m in frame.columns and pd.to_numeric(frame[m], errors="coerce").notna().any()]
        if metric_options:
            metric = st.selectbox("Distribution observable", metric_options, key="pl_rrp_plot_metric")
            values = pd.to_numeric(frame[metric], errors="coerce")
            nominal_value = _finite((result.get("nominal") or {}).get("observables", {}).get(metric))
            fig = go.Figure()
            fig.add_scatter(x=frame["seed"], y=values, mode="lines+markers", name="Manufacturing realization")
            if nominal_value is not None:
                fig.add_hline(y=nominal_value, line_dash="dash", annotation_text="nominal")
            fig.update_layout(title=f"Propagated {metric} by RADIA manufacturing seed", xaxis_title="Manufacturing seed", yaxis_title=metric, height=500)
            st.plotly_chart(fig, width="stretch")

            use_req = st.toggle("Check an engineering bound for this observable", value=False, key="pl_rrp_use_req")
            if use_req:
                mode = st.radio("Bound type", ["Upper maximum", "Lower minimum", "Two-sided"], horizontal=True, key="pl_rrp_req_mode")
                lower = upper = None
                if mode in {"Lower minimum", "Two-sided"}:
                    lower = st.number_input("Lower bound", value=float(values.min()), format="%.8g", key="pl_rrp_lower")
                if mode in {"Upper maximum", "Two-sided"}:
                    upper = st.number_input("Upper bound", value=float(values.max()), format="%.8g", key="pl_rrp_upper")
                assessment = assess_propagated_requirement(result["members"], metric, lower=lower, upper=upper)
                st.write(assessment)
                st.caption(assessment["boundary"])

    st.download_button(
        "Download propagated engineering evidence (.json)",
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False),
        "physical-lab-radia-radiation-propagation.json",
        "application/json",
        key="pl_rrp_download",
    )
    st.caption(result["boundary"])
