"""Nonlinear manufacturing-tolerance ensembles for Physical Lab RADIA Full mode.

Every ensemble member rebuilds and resolves the managed RADIA Magnet Studio
model with an explicit manufacturing-error seed. This is deliberately distinct
from the first-order V&V/UQ screening tools in physical_lab_engineering.py.

The module does not infer tolerances. It uses only the manufacturing-error
magnitudes already entered in RADIA Magnet Studio and refuses to relabel an
ensemble as a confidence interval or validation experiment.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Iterable, Mapping, Sequence

RADIA_MAGNET_STUDIO_REVISION = "3bceb02a5195a6eb14d01458cc44f7206ed6b40a"
RADIA_RUNTIME_REVISION = "7ff3b2dc26cbcccfcb0aaf3c4a290ebd83439698"
MAX_ENSEMBLE_MEMBERS = 32
MAX_ENSEMBLE_POSITIONS = 1201
ERROR_FIELDS = (
    ("field_error_pct", "Field amplitude σ", "%"),
    ("longitudinal_error_mm", "Longitudinal position σ", "mm"),
    ("transverse_error_mm", "Transverse position σ", "mm"),
    ("angle_error_deg", "Magnetization angle σ", "deg"),
    ("gap_asymmetry_mm", "Gap asymmetry", "mm"),
    ("bank_imbalance_pct", "Bank strength imbalance", "%"),
)
COMPONENT_KEYS = {"Bx": "Bx_T", "By": "By_T", "Bz": "Bz_T", "Bperp": "Bperp_T"}


def _require_full_mode() -> None:
    if os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "").strip().lower() != "full":
        raise RuntimeError("RADIA nonlinear tolerance ensembles require Physical Lab Full mode")


def _callable(namespace: Mapping[str, Any], name: str):
    fn = namespace.get(name)
    if not callable(fn):
        raise RuntimeError(f"RADIA Magnet Studio API {name!r} is unavailable in the managed revision")
    return fn


def _cleanup(rad: Any) -> None:
    try:
        if hasattr(rad, "UtiDelAll"):
            rad.UtiDelAll()
    except Exception:
        pass


def active_error_model(params: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, label, unit in ERROR_FIELDS:
        try:
            value = float(params.get(key, 0.0) or 0.0)
        except Exception:
            value = 0.0
        rows.append({"parameter": key, "label": label, "value": value, "unit": unit, "active": abs(value) > 0.0})
    return rows


def _positions(values: Iterable[float]) -> list[float]:
    out = sorted({float(v) for v in values})
    if len(out) < 9:
        raise ValueError("Use at least 9 distinct field positions for a nonlinear tolerance ensemble")
    if len(out) > MAX_ENSEMBLE_POSITIONS:
        raise ValueError(f"Tolerance ensembles are limited to {MAX_ENSEMBLE_POSITIONS} field positions")
    if not all(math.isfinite(v) for v in out):
        raise ValueError("Field positions must be finite")
    return out


def geometry_sampling_positions(namespace: Mapping[str, Any], points: int) -> list[float]:
    """Derive an on-axis sampling range from the current nominal RADIA geometry."""
    _require_full_mode()
    import numpy as np

    n = max(51, min(int(points), MAX_ENSEMBLE_POSITIONS))
    params = dict(namespace.get("current_params") or {})
    settings = dict(namespace.get("current_settings") or {})
    if not params:
        raise RuntimeError("RADIA Magnet Studio did not expose current_params")
    params["errors_enabled"] = False
    load_radia = _callable(namespace, "load_radia")
    build_device = _callable(namespace, "build_device")
    union_field_range = _callable(namespace, "union_field_range")
    rad = load_radia()
    try:
        _cleanup(rad)
        model = build_device(rad, params.get("device"), params)
        z_lo, z_hi = union_field_range(
            [model],
            float(params.get("period_mm")),
            float(settings.get("field_margin_periods", 1.0)),
        )
        return [float(v) for v in np.linspace(float(z_lo), float(z_hi), n)]
    finally:
        _cleanup(rad)


def _field_component(fields: Sequence[Mapping[str, float]], component: str) -> list[float]:
    if component not in COMPONENT_KEYS:
        raise ValueError(f"component must be one of {sorted(COMPONENT_KEYS)}")
    key = COMPONENT_KEYS[component]
    return [float(row[key]) for row in fields]


def summarize_component_ensemble(
    positions_mm: Sequence[float],
    nominal: Sequence[float],
    ensemble: Sequence[Sequence[float]],
    seeds: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Summarize already-computed nonlinear solver curves without inventing a distribution model."""
    import numpy as np

    z = np.asarray(positions_mm, dtype=float)
    y0 = np.asarray(nominal, dtype=float)
    arr = np.asarray(ensemble, dtype=float)
    if z.ndim != 1 or y0.shape != z.shape:
        raise ValueError("nominal field and positions must be aligned 1-D arrays")
    if arr.ndim != 2 or arr.shape[1] != len(z) or arr.shape[0] < 2:
        raise ValueError("ensemble must contain at least two curves aligned to the field positions")
    if not np.all(np.isfinite(z)) or not np.all(np.isfinite(y0)) or not np.all(np.isfinite(arr)):
        raise ValueError("ensemble inputs must be finite")

    q05, q50, q95 = np.quantile(arr, [0.05, 0.50, 0.95], axis=0)
    mean = np.mean(arr, axis=0)
    std = np.std(arr, axis=0, ddof=1)
    minimum = np.min(arr, axis=0)
    maximum = np.max(arr, axis=0)
    seed_list = list(seeds or range(arr.shape[0]))
    if len(seed_list) != arr.shape[0]:
        raise ValueError("seed count must match ensemble member count")

    members: list[dict[str, Any]] = []
    for seed, curve in zip(seed_list, arr):
        delta = curve - y0
        integral = float(np.trapezoid(curve, z)) if hasattr(np, "trapezoid") else float(np.trapz(curve, z))
        members.append({
            "seed": int(seed),
            "peak_abs_T": float(np.max(np.abs(curve))),
            "field_integral_T_mm": integral,
            "max_abs_deviation_from_nominal_T": float(np.max(np.abs(delta))),
            "rms_deviation_from_nominal_T": float(np.sqrt(np.mean(delta * delta))),
        })

    max_dev = np.asarray([m["max_abs_deviation_from_nominal_T"] for m in members], dtype=float)
    peak = np.asarray([m["peak_abs_T"] for m in members], dtype=float)
    integ = np.asarray([m["field_integral_T_mm"] for m in members], dtype=float)
    return {
        "positions_mm": [float(v) for v in z],
        "nominal_T": [float(v) for v in y0],
        "mean_T": [float(v) for v in mean],
        "std_T": [float(v) for v in std],
        "p05_T": [float(v) for v in q05],
        "median_T": [float(v) for v in q50],
        "p95_T": [float(v) for v in q95],
        "min_T": [float(v) for v in minimum],
        "max_T": [float(v) for v in maximum],
        "members": members,
        "summary": {
            "memberCount": int(arr.shape[0]),
            "observedWorstMaxAbsDeviation_T": float(np.max(max_dev)),
            "medianMaxAbsDeviation_T": float(np.median(max_dev)),
            "p95MaxAbsDeviation_T": float(np.quantile(max_dev, 0.95)),
            "peakAbsMedian_T": float(np.median(peak)),
            "peakAbsP05_T": float(np.quantile(peak, 0.05)),
            "peakAbsP95_T": float(np.quantile(peak, 0.95)),
            "fieldIntegralMedian_T_mm": float(np.median(integ)),
            "fieldIntegralP05_T_mm": float(np.quantile(integ, 0.05)),
            "fieldIntegralP95_T_mm": float(np.quantile(integ, 0.95)),
        },
        "boundary": "5th/95th percentiles and observed extrema describe this finite set of explicit RADIA solver realizations only. They are not confidence bounds on manufacturing yield unless the entered error model and sampling assumptions are independently justified.",
    }


def assess_observed_tolerance(summary: Mapping[str, Any], allowed_max_deviation_t: float) -> dict[str, Any]:
    limit = float(allowed_max_deviation_t)
    if not math.isfinite(limit) or limit <= 0:
        raise ValueError("allowed maximum deviation must be a positive finite value")
    members = list(summary.get("members") or [])
    if not members:
        raise ValueError("ensemble summary contains no members")
    passed = [float(m["max_abs_deviation_from_nominal_T"]) <= limit for m in members]
    worst = max(float(m["max_abs_deviation_from_nominal_T"]) for m in members)
    return {
        "status": "PASS" if all(passed) else "REVIEW",
        "observedPassCount": sum(1 for x in passed if x),
        "observedMemberCount": len(passed),
        "observedPassFraction": sum(1 for x in passed if x) / len(passed),
        "allowedMaxDeviation_T": limit,
        "observedWorstDeviation_T": worst,
        "observedWorstMargin_T": limit - worst,
        "boundary": "PASS means every sampled solver realization met the entered limit. It is not a statistical yield guarantee for unsampled manufactured units.",
    }


def run_radia_manufacturing_ensemble(
    namespace: Mapping[str, Any],
    positions_mm: Iterable[float],
    *,
    component: str = "Bperp",
    members: int = 12,
    seed_start: int | None = None,
) -> dict[str, Any]:
    """Run repeated real RADIA forward solves using the current manufacturing-error magnitudes."""
    _require_full_mode()
    from physical_lab_radia_adapter import run_current_radia_forward_model

    positions = _positions(positions_mm)
    n = int(members)
    if n < 2 or n > MAX_ENSEMBLE_MEMBERS:
        raise ValueError(f"Use between 2 and {MAX_ENSEMBLE_MEMBERS} ensemble members")
    params = dict(namespace.get("current_params") or {})
    if not params:
        raise RuntimeError("RADIA Magnet Studio did not expose current_params")
    if bool(params.get("target_b0_enabled")):
        raise ValueError("Disable target-B0 calibration before a manufacturing ensemble. Freeze the calibrated Br first so each random realization is not re-tuned back to the same target field.")
    error_model = active_error_model(params)
    if not any(row["active"] for row in error_model):
        raise ValueError("Enter at least one non-zero RADIA manufacturing-error magnitude before running an ensemble")

    first_seed = int(params.get("error_seed", 12345) if seed_start is None else seed_start)
    nominal_namespace = dict(namespace)
    nominal_params = dict(params)
    nominal_params["errors_enabled"] = False
    nominal_namespace["current_params"] = nominal_params
    nominal_result = run_current_radia_forward_model(nominal_namespace, positions)
    nominal_curve = _field_component(nominal_result["fields"], component)

    seeds = [first_seed + i for i in range(n)]
    curves: list[list[float]] = []
    for seed in seeds:
        sample_namespace = dict(namespace)
        sample_params = dict(params)
        sample_params["errors_enabled"] = True
        sample_params["error_seed"] = int(seed)
        sample_namespace["current_params"] = sample_params
        sample = run_current_radia_forward_model(sample_namespace, positions)
        curves.append(_field_component(sample["fields"], component))

    summarized = summarize_component_ensemble(positions, nominal_curve, curves, seeds)
    return {
        "schema": "physical-lab-radia-manufacturing-ensemble-v1",
        "radiaMagnetStudioRevision": RADIA_MAGNET_STUDIO_REVISION,
        "radiaRuntimeRevision": RADIA_RUNTIME_REVISION,
        "component": component,
        "errorModel": error_model,
        "seedStart": first_seed,
        "seeds": seeds,
        "nominalParameters": nominal_params,
        "ensemble": summarized,
        "boundary": "Each member is a real RADIA Full-mode rebuild and solve using the current Magnet Studio manufacturing-error model. The finite seed ensemble is an engineering tolerance study, not experimental validation or a manufacturing-yield certification.",
    }


def render_radia_tolerance_workspace(st: Any, namespace: Mapping[str, Any]) -> None:
    st.markdown("---")
    st.markdown("## Physical Lab · Nonlinear RADIA Tolerance Ensemble")
    st.caption(
        "Rebuild and solve the real RADIA magnet repeatedly with the manufacturing-error magnitudes entered in Magnet Studio. "
        "Use this when linear RSS/sensitivity screening is insufficient."
    )
    if os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "").strip().lower() != "full":
        st.info("Switch RADIA Magnet Studio to **Full mode** to run nonlinear manufacturing ensembles.")
        return

    params = dict(namespace.get("current_params") or {})
    if not params:
        st.warning("Current RADIA parameters are unavailable.")
        return
    rows = active_error_model(params)
    st.dataframe(rows, width="stretch", hide_index=True)
    if bool(params.get("target_b0_enabled")):
        st.warning("Target-B0 calibration is enabled. Freeze the calibrated Br and disable target-B0 calibration before running a tolerance ensemble; otherwise re-tuning can hide manufacturing variation.")

    c1, c2, c3, c4 = st.columns(4)
    component = c1.selectbox("Field component", ["Bperp", "By", "Bx", "Bz"], key="pl_radia_tol_component")
    members = c2.select_slider("RADIA realizations", options=[4, 8, 12, 16, 24, 32], value=12, key="pl_radia_tol_members")
    points = c3.select_slider("On-axis points", options=[101, 201, 401, 801, 1201], value=201, key="pl_radia_tol_points")
    seed_start = c4.number_input("First seed", min_value=0, value=int(params.get("error_seed", 12345)), step=1, key="pl_radia_tol_seed")
    st.caption("Runtime scales approximately with ensemble members × RADIA rebuild/solve cost. Start with 4–12 realizations while developing a design.")

    if st.button("Run nonlinear manufacturing ensemble", type="primary", key="pl_radia_tol_run"):
        try:
            positions = geometry_sampling_positions(namespace, int(points))
            with st.spinner(f"Running {int(members)} real RADIA manufacturing realizations…"):
                result = run_radia_manufacturing_ensemble(
                    namespace,
                    positions,
                    component=str(component),
                    members=int(members),
                    seed_start=int(seed_start),
                )
            st.session_state["pl_radia_tol_result"] = result
        except Exception as exc:
            st.error(f"Nonlinear RADIA tolerance ensemble failed: {exc}")

    result = st.session_state.get("pl_radia_tol_result")
    if not result:
        return

    import pandas as pd
    import plotly.graph_objects as go

    ensemble = result["ensemble"]
    z = ensemble["positions_mm"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=z, y=ensemble["p95_T"], mode="lines", line={"width": 0}, name="95th percentile", showlegend=False))
    fig.add_trace(go.Scatter(x=z, y=ensemble["p05_T"], mode="lines", fill="tonexty", line={"width": 0}, name="5–95% finite-seed envelope"))
    fig.add_trace(go.Scatter(x=z, y=ensemble["mean_T"], mode="lines", name="Ensemble mean"))
    fig.add_trace(go.Scatter(x=z, y=ensemble["nominal_T"], mode="lines", name="Nominal / no manufacturing errors"))
    fig.update_layout(
        title=f"Nonlinear RADIA manufacturing envelope · {result['component']}",
        xaxis_title="z (mm)",
        yaxis_title=f"{result['component']} (T)",
        height=560,
    )
    st.plotly_chart(fig, width="stretch")

    summary = ensemble["summary"]
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Realizations", summary["memberCount"])
    h2.metric("Worst observed max |ΔB|", f"{summary['observedWorstMaxAbsDeviation_T']:.6g} T")
    h3.metric("95th pct max |ΔB|", f"{summary['p95MaxAbsDeviation_T']:.6g} T")
    h4.metric("Median peak |B|", f"{summary['peakAbsMedian_T']:.6g} T")

    member_df = pd.DataFrame(ensemble["members"])
    st.dataframe(member_df, width="stretch", hide_index=True)
    hist = go.Figure(go.Histogram(x=member_df["max_abs_deviation_from_nominal_T"], nbinsx=min(15, len(member_df))))
    hist.update_layout(title="Observed maximum field deviation by manufacturing realization", xaxis_title="max |ΔB| from nominal (T)", yaxis_title="Count", height=430)
    st.plotly_chart(hist, width="stretch")

    use_limit = st.toggle("Check an engineering max-deviation requirement", value=False, key="pl_radia_tol_use_limit")
    if use_limit:
        limit = st.number_input("Allowed max |ΔB| from nominal (T)", min_value=1e-12, value=0.01, format="%.8g", key="pl_radia_tol_limit")
        assessment = assess_observed_tolerance(ensemble, float(limit))
        st.write(assessment)
        if assessment["status"] == "PASS":
            st.success("Every sampled RADIA realization meets the entered deviation limit.")
        else:
            st.warning("At least one sampled RADIA realization exceeds the entered deviation limit.")
        st.caption(assessment["boundary"])

    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)
    st.download_button(
        "Download nonlinear tolerance evidence (.json)",
        payload,
        "physical-lab-radia-nonlinear-tolerance.json",
        "application/json",
        key="pl_radia_tol_download",
    )
    st.caption(result["boundary"])
