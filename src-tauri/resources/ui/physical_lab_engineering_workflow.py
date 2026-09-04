"""Integrated engineering design workflow for Physical Lab.

This module connects requirement screening, design comparison, finite-ensemble
reliability, measured-field residual analysis, lightweight multiphysics coupling,
closed-loop calibration updates and deterministic batch planning.

The calculations are deliberately transparent. PASS/REVIEW/FAIL labels are
engineering screening outcomes, not regulatory certification. Finite ensembles
are descriptive samples, not automatically probability-of-failure estimates.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from typing import Any

_STATUS_ORDER = {"PASS": 0, "REVIEW": 1, "FAIL": 2}
_H = 6.62607015e-34
_E_CHARGE = 1.602176634e-19
_M_E = 9.1093837139e-31
_C = 299792458.0


def _finite(value: Any, *, name: str = "value") -> float:
    try:
        x = float(value)
    except Exception as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite")
    return x


def _quantile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("cannot compute a quantile of an empty sequence")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be between 0 and 1")
    xs = sorted(float(x) for x in values)
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1.0 - w) + xs[hi] * w


def _trapz(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("x and y must have equal length >= 2")
    total = 0.0
    for i in range(len(x) - 1):
        dx = x[i + 1] - x[i]
        if dx <= 0:
            raise ValueError("positions must be strictly increasing")
        total += 0.5 * dx * (y[i] + y[i + 1])
    return total


def requirement_assessment(
    value: float,
    *,
    lower: float | None = None,
    upper: float | None = None,
    expanded_uncertainty: float = 0.0,
) -> dict[str, Any]:
    """Screen one metric against limits with a symmetric entered uncertainty."""
    y = _finite(value, name="value")
    u = abs(_finite(expanded_uncertainty, name="expanded_uncertainty"))
    lo = None if lower is None else _finite(lower, name="lower")
    hi = None if upper is None else _finite(upper, name="upper")
    if lo is None and hi is None:
        raise ValueError("at least one requirement limit is required")
    if lo is not None and hi is not None and lo > hi:
        raise ValueError("lower requirement exceeds upper requirement")
    interval = (y - u, y + u)
    nominal_in = (lo is None or y >= lo) and (hi is None or y <= hi)
    interval_in = (lo is None or interval[0] >= lo) and (hi is None or interval[1] <= hi)
    status = "FAIL" if not nominal_in else ("PASS" if interval_in else "REVIEW")
    margins: list[float] = []
    if lo is not None:
        margins.append(interval[0] - lo)
    if hi is not None:
        margins.append(hi - interval[1])
    return {
        "status": status,
        "value": y,
        "expanded_interval": [interval[0], interval[1]],
        "lower": lo,
        "upper": hi,
        "minimum_margin_after_uncertainty": min(margins) if margins else None,
    }


def evaluate_requirements(
    metrics: dict[str, float],
    requirements: list[dict[str, Any]],
    uncertainties: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Evaluate a named metric set against a requirement table."""
    uncertainties = uncertainties or {}
    items: list[dict[str, Any]] = []
    for req in requirements:
        metric = str(req.get("metric", "")).strip()
        if not metric:
            raise ValueError("each requirement needs a metric name")
        if metric not in metrics:
            items.append({"metric": metric, "status": "REVIEW", "reason": "metric missing"})
            continue
        result = requirement_assessment(
            metrics[metric],
            lower=req.get("lower"),
            upper=req.get("upper"),
            expanded_uncertainty=uncertainties.get(metric, req.get("expanded_uncertainty", 0.0)),
        )
        result["metric"] = metric
        result["requirement_id"] = req.get("id") or metric
        items.append(result)
    overall = max((item.get("status", "REVIEW") for item in items), key=lambda s: _STATUS_ORDER.get(s, 1), default="REVIEW")
    return {
        "overall_status": overall,
        "requirements": items,
        "boundary": "Screening only; requirement status is not a certification statement.",
    }


def measured_field_residual(
    positions: list[float],
    model_field: list[float],
    measured_field: list[float],
    standard_uncertainty: list[float] | None = None,
) -> dict[str, Any]:
    """Compare co-registered 1-D model and measured field series.

    Positions can use any unit if used consistently. Field values and uncertainty
    must share one unit. The normalized residual statistic is descriptive and is
    intentionally not labeled chi-square because no distributional assumptions
    are inferred here.
    """
    if not (len(positions) == len(model_field) == len(measured_field)) or len(positions) < 2:
        raise ValueError("positions, model_field and measured_field must have equal length >= 2")
    x = [_finite(v, name="position") for v in positions]
    model = [_finite(v, name="model_field") for v in model_field]
    measured = [_finite(v, name="measured_field") for v in measured_field]
    residual = [m - s for m, s in zip(measured, model)]
    mae = statistics.fmean(abs(r) for r in residual)
    rmse = math.sqrt(statistics.fmean(r * r for r in residual))
    max_abs = max(abs(r) for r in residual)
    model_rms = math.sqrt(statistics.fmean(v * v for v in model))
    normalized_rms = rmse / model_rms if model_rms > 0 else None
    model_integral = _trapz(x, model)
    measured_integral = _trapz(x, measured)
    out: dict[str, Any] = {
        "n": len(x),
        "mae": mae,
        "rmse": rmse,
        "max_abs_residual": max_abs,
        "relative_rmse_to_model_rms": normalized_rms,
        "model_integral": model_integral,
        "measured_integral": measured_integral,
        "integral_difference": measured_integral - model_integral,
        "residual": residual,
    }
    if standard_uncertainty is not None:
        if len(standard_uncertainty) != len(x):
            raise ValueError("standard_uncertainty must match the field series length")
        sigma = [abs(_finite(v, name="standard_uncertainty")) for v in standard_uncertainty]
        valid = [(r, s) for r, s in zip(residual, sigma) if s > 0]
        if valid:
            z = [r / s for r, s in valid]
            out["uncertainty_normalized_rms"] = math.sqrt(statistics.fmean(v * v for v in z))
            out["fraction_within_2u"] = sum(abs(v) <= 2.0 for v in z) / len(z)
            out["normalized_residual_count"] = len(z)
        else:
            out["uncertainty_normalized_rms"] = None
            out["fraction_within_2u"] = None
            out["normalized_residual_count"] = 0
    out["boundary"] = "Residual statistics compare co-registered series; they do not establish experimental validity without real measurement provenance and uncertainty evidence."
    return out


def local_sensitivity_screening(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank supplied one-at-a-time finite-difference perturbations by |dy/dx|."""
    rows: list[dict[str, Any]] = []
    for case in cases:
        parameter = str(case.get("parameter", "parameter"))
        dx = _finite(case.get("delta_parameter"), name="delta_parameter")
        dy = _finite(case.get("delta_response"), name="delta_response")
        if dx == 0.0:
            raise ValueError("delta_parameter cannot be zero")
        sensitivity = dy / dx
        rows.append({
            "parameter": parameter,
            "delta_parameter": dx,
            "delta_response": dy,
            "sensitivity": sensitivity,
            "absolute_sensitivity": abs(sensitivity),
        })
    rows.sort(key=lambda row: row["absolute_sensitivity"], reverse=True)
    return rows


def pareto_front(designs: list[dict[str, Any]], objectives: dict[str, str]) -> dict[str, Any]:
    """Return the non-dominated subset for explicit min/max objectives."""
    if not designs:
        return {"indices": [], "designs": [], "objectives": objectives}
    if not objectives:
        raise ValueError("at least one objective is required")
    normalized: dict[str, int] = {}
    for metric, direction in objectives.items():
        d = str(direction).lower().strip()
        if d not in {"min", "max"}:
            raise ValueError(f"objective {metric} must be 'min' or 'max'")
        normalized[metric] = 1 if d == "min" else -1

    values: list[dict[str, float]] = []
    for design in designs:
        values.append({metric: _finite(design.get(metric), name=metric) for metric in normalized})

    front: list[int] = []
    for i, a in enumerate(values):
        dominated = False
        for j, b in enumerate(values):
            if i == j:
                continue
            no_worse = all(normalized[m] * b[m] <= normalized[m] * a[m] for m in normalized)
            strictly_better = any(normalized[m] * b[m] < normalized[m] * a[m] for m in normalized)
            if no_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            front.append(i)
    return {
        "indices": front,
        "designs": [designs[i] for i in front],
        "objectives": {k: ("min" if v == 1 else "max") for k, v in normalized.items()},
        "boundary": "Pareto membership reflects only the entered objective columns and does not imply overall engineering optimality.",
    }


def robust_design_summary(
    ensembles: dict[str, list[dict[str, float]]],
    requirements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize finite solver/manufacturing ensembles for robust-design screening."""
    designs: list[dict[str, Any]] = []
    for design_name, samples in ensembles.items():
        if not samples:
            designs.append({"design": design_name, "samples": 0, "status": "REVIEW", "pass_fraction": None, "metrics": {}})
            continue
        metric_names = sorted({str(k) for sample in samples for k in sample.keys()})
        metric_stats: dict[str, Any] = {}
        for metric in metric_names:
            vals = [_finite(sample[metric], name=metric) for sample in samples if metric in sample]
            if not vals:
                continue
            metric_stats[metric] = {
                "mean": statistics.fmean(vals),
                "sample_std": statistics.stdev(vals) if len(vals) >= 2 else 0.0,
                "p05": _quantile(vals, 0.05),
                "median": _quantile(vals, 0.50),
                "p95": _quantile(vals, 0.95),
                "min": min(vals),
                "max": max(vals),
            }
        passes = 0
        sample_statuses: list[str] = []
        for sample in samples:
            assessment = evaluate_requirements(sample, requirements)
            sample_statuses.append(assessment["overall_status"])
            if assessment["overall_status"] == "PASS":
                passes += 1
        pass_fraction = passes / len(samples)
        status = "PASS" if passes == len(samples) else ("FAIL" if passes == 0 else "REVIEW")
        designs.append({
            "design": design_name,
            "samples": len(samples),
            "status": status,
            "pass_fraction": pass_fraction,
            "metrics": metric_stats,
            "sample_statuses": sample_statuses,
        })
    designs.sort(key=lambda d: (-(d["pass_fraction"] if d["pass_fraction"] is not None else -1.0), d["design"]))
    return {
        "designs": designs,
        "boundary": "Pass fractions are descriptive finite-ensemble screening results; they are not automatically manufacturing yield or certified failure probabilities.",
    }


def bounded_calibration_update(
    current_parameter: float,
    measured_response: float,
    target_response: float,
    response_sensitivity: float,
    *,
    gain: float = 0.5,
    lower_bound: float | None = None,
    upper_bound: float | None = None,
) -> dict[str, Any]:
    """One bounded model-based calibration/control update, without hardware I/O."""
    p = _finite(current_parameter, name="current_parameter")
    measured = _finite(measured_response, name="measured_response")
    target = _finite(target_response, name="target_response")
    sensitivity = _finite(response_sensitivity, name="response_sensitivity")
    g = _finite(gain, name="gain")
    if sensitivity == 0.0:
        raise ValueError("response_sensitivity cannot be zero")
    if not 0.0 < g <= 1.0:
        raise ValueError("gain must be in (0, 1]")
    requested_delta = g * (target - measured) / sensitivity
    requested = p + requested_delta
    applied = requested
    clipped = False
    if lower_bound is not None:
        lo = _finite(lower_bound, name="lower_bound")
        if applied < lo:
            applied = lo
            clipped = True
    if upper_bound is not None:
        hi = _finite(upper_bound, name="upper_bound")
        if lower_bound is not None and _finite(lower_bound) > hi:
            raise ValueError("lower_bound exceeds upper_bound")
        if applied > hi:
            applied = hi
            clipped = True
    return {
        "current_parameter": p,
        "response_error": target - measured,
        "requested_delta": requested_delta,
        "next_parameter": applied,
        "clipped": clipped,
        "boundary": "Numerical update only. Physical hardware commands require a separately reviewed device-specific safety layer.",
    }


def undulator_thermal_coupling(
    period_m: float,
    peak_field_t: float,
    gamma: float,
    alpha_per_k: float,
    delta_t_k: float,
    *,
    field_temp_coeff_per_k: float = 0.0,
) -> dict[str, Any]:
    """First-order thermal expansion + optional field-temperature coupling.

    This is a transparent screening model: uniform temperature, linear expansion,
    and a user-supplied fractional field coefficient per kelvin.
    """
    period = _finite(period_m, name="period_m")
    field = _finite(peak_field_t, name="peak_field_t")
    g = _finite(gamma, name="gamma")
    alpha = _finite(alpha_per_k, name="alpha_per_k")
    dt = _finite(delta_t_k, name="delta_t_k")
    beta_b = _finite(field_temp_coeff_per_k, name="field_temp_coeff_per_k")
    if period <= 0 or g <= 1:
        raise ValueError("period_m must be > 0 and gamma must be > 1")

    def resonance(p: float, b: float) -> tuple[float, float, float]:
        k = _E_CHARGE * b * p / (2.0 * math.pi * _M_E * _C)
        wavelength = p * (1.0 + 0.5 * k * k) / (2.0 * g * g)
        energy_ev = (_H * _C / wavelength) / _E_CHARGE
        return k, wavelength, energy_ev

    new_period = period * (1.0 + alpha * dt)
    new_field = field * (1.0 + beta_b * dt)
    k0, lam0, e0 = resonance(period, field)
    k1, lam1, e1 = resonance(new_period, new_field)
    return {
        "nominal": {"period_m": period, "peak_field_t": field, "K": k0, "wavelength_m": lam0, "photon_energy_eV": e0},
        "heated": {"period_m": new_period, "peak_field_t": new_field, "K": k1, "wavelength_m": lam1, "photon_energy_eV": e1},
        "changes": {
            "period_relative": new_period / period - 1.0,
            "field_relative": (new_field / field - 1.0) if field != 0 else None,
            "photon_energy_relative": e1 / e0 - 1.0,
        },
        "boundary": "Uniform linear thermal screening model; it does not replace structural/thermal FEA or a temperature-dependent magnet material model.",
    }


def stable_case_fingerprint(case: dict[str, Any]) -> str:
    raw = json.dumps(case, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_batch_plan(cases: list[dict[str, Any]], *, workers: int = 1, chunk_size: int = 1) -> dict[str, Any]:
    """Build a deterministic resumable batch plan without executing jobs."""
    w = max(1, int(workers))
    c = max(1, int(chunk_size))
    jobs = [
        {"index": i, "fingerprint": stable_case_fingerprint(case), "case": case}
        for i, case in enumerate(cases)
    ]
    chunks = [jobs[i : i + c] for i in range(0, len(jobs), c)]
    waves = math.ceil(len(chunks) / w) if chunks else 0
    return {
        "case_count": len(jobs),
        "worker_count": w,
        "chunk_size": c,
        "chunk_count": len(chunks),
        "minimum_scheduling_waves": waves,
        "chunks": [[job["fingerprint"] for job in chunk] for chunk in chunks],
        "jobs": jobs,
        "boundary": "Scheduling plan only; solver parallel safety, memory limits and external-engine licensing must be checked by each adapter.",
    }


def render_engineering_workflow(st: Any, profile: str, namespace: dict[str, Any] | None = None) -> None:
    """Streamlit engineering workspace layered on the existing per-Lab VVUQ UI."""
    import pandas as pd
    import plotly.graph_objects as go

    st.markdown("---")
    st.markdown("## Physical Lab · Engineering Design Workflow")
    st.caption(
        "Requirement-driven design, Pareto comparison, finite-ensemble robustness, measured-field residuals, "
        "thermal coupling, bounded calibration updates and resumable batch planning."
    )
    tabs = st.tabs([
        "Requirements",
        "Design / Pareto",
        "Reliability",
        "Measured field",
        "Thermal / control",
        "Batch / HPC",
    ])

    with tabs[0]:
        st.caption("Enter metrics and limits in consistent units. Uncertainty is a symmetric expanded screening interval.")
        default = pd.DataFrame([
            {"metric": "response", "value": 1.0, "lower": 0.8, "upper": 1.2, "expanded_uncertainty": 0.05},
        ])
        df = st.data_editor(default, num_rows="dynamic", width="stretch", key=f"pl_engwf_req_{profile}")
        reqs, metrics, unc = [], {}, {}
        for row in df.to_dict(orient="records"):
            metric = str(row.get("metric", "")).strip()
            if not metric:
                continue
            metrics[metric] = float(row.get("value", 0.0))
            reqs.append({"metric": metric, "lower": row.get("lower"), "upper": row.get("upper")})
            unc[metric] = float(row.get("expanded_uncertainty", 0.0) or 0.0)
        if reqs:
            try:
                assessment = evaluate_requirements(metrics, reqs, unc)
                st.metric("Overall engineering status", assessment["overall_status"])
                st.dataframe(pd.DataFrame(assessment["requirements"]), width="stretch")
            except Exception as exc:
                st.error(str(exc))

    with tabs[1]:
        st.caption("Non-dominated designs are computed only from the objective columns selected below.")
        designs_df = st.data_editor(pd.DataFrame([
            {"design": "A", "performance": 10.0, "cost": 7.0},
            {"design": "B", "performance": 12.0, "cost": 10.0},
            {"design": "C", "performance": 9.0, "cost": 5.0},
        ]), num_rows="dynamic", width="stretch", key=f"pl_engwf_pareto_{profile}")
        cols = [c for c in designs_df.columns if c != "design"]
        if cols:
            c1, c2 = st.columns(2)
            x_metric = c1.selectbox("Objective 1", cols, key=f"pl_engwf_obj1_{profile}")
            x_dir = c2.selectbox("Objective 1 direction", ["max", "min"], key=f"pl_engwf_obj1dir_{profile}")
            remaining = [c for c in cols if c != x_metric] or cols
            c3, c4 = st.columns(2)
            y_metric = c3.selectbox("Objective 2", remaining, key=f"pl_engwf_obj2_{profile}")
            y_dir = c4.selectbox("Objective 2 direction", ["min", "max"], key=f"pl_engwf_obj2dir_{profile}")
            try:
                rows = designs_df.to_dict(orient="records")
                front = pareto_front(rows, {x_metric: x_dir, y_metric: y_dir})
                st.write("Pareto candidates:", [r.get("design", i) for i, r in zip(front["indices"], front["designs"])])
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=designs_df[x_metric], y=designs_df[y_metric], mode="markers+text", text=designs_df["design"], textposition="top center", name="designs"))
                if front["indices"]:
                    fdf = designs_df.iloc[front["indices"]]
                    fig.add_trace(go.Scatter(x=fdf[x_metric], y=fdf[y_metric], mode="markers", marker={"size": 14, "symbol": "circle-open"}, name="Pareto"))
                fig.update_layout(height=460, xaxis_title=x_metric, yaxis_title=y_metric)
                st.plotly_chart(fig, width="stretch")
            except Exception as exc:
                st.error(str(exc))

    with tabs[2]:
        st.caption("Finite-ensemble pass fractions describe the supplied samples; they are not automatically manufacturing yield.")
        samples_df = st.data_editor(pd.DataFrame([
            {"design": "A", "sample": 1, "response": 0.98},
            {"design": "A", "sample": 2, "response": 1.03},
            {"design": "B", "sample": 1, "response": 0.91},
            {"design": "B", "sample": 2, "response": 1.16},
        ]), num_rows="dynamic", width="stretch", key=f"pl_engwf_rel_{profile}")
        c1, c2 = st.columns(2)
        lo = c1.number_input("Response lower requirement", value=0.9, format="%.8g", key=f"pl_engwf_rel_lo_{profile}")
        hi = c2.number_input("Response upper requirement", value=1.1, format="%.8g", key=f"pl_engwf_rel_hi_{profile}")
        ensembles: dict[str, list[dict[str, float]]] = {}
        for row in samples_df.to_dict(orient="records"):
            name = str(row.get("design", "design"))
            ensembles.setdefault(name, []).append({"response": float(row.get("response", 0.0))})
        try:
            summary = robust_design_summary(ensembles, [{"metric": "response", "lower": float(lo), "upper": float(hi)}])
            st.dataframe(pd.DataFrame([{k: v for k, v in d.items() if k not in {"metrics", "sample_statuses"}} for d in summary["designs"]]), width="stretch")
        except Exception as exc:
            st.error(str(exc))

    with tabs[3]:
        st.caption("Use co-registered position/model/measured values. Synthetic examples are labeled; real validation requires provenance.")
        field_df = st.data_editor(pd.DataFrame([
            {"position": 0.0, "model": 0.0, "measured": 0.001, "u": 0.002},
            {"position": 1.0, "model": 0.5, "measured": 0.497, "u": 0.002},
            {"position": 2.0, "model": 0.0, "measured": -0.001, "u": 0.002},
            {"position": 3.0, "model": -0.5, "measured": -0.496, "u": 0.002},
        ]), num_rows="dynamic", width="stretch", key=f"pl_engwf_field_{profile}")
        try:
            rows = field_df.to_dict(orient="records")
            residual = measured_field_residual(
                [float(r["position"]) for r in rows],
                [float(r["model"]) for r in rows],
                [float(r["measured"]) for r in rows],
                [float(r["u"]) for r in rows],
            )
            a, b, c = st.columns(3)
            a.metric("RMSE", f"{residual['rmse']:.6g}")
            b.metric("Max |residual|", f"{residual['max_abs_residual']:.6g}")
            c.metric("Normalized RMS", "—" if residual.get("uncertainty_normalized_rms") is None else f"{residual['uncertainty_normalized_rms']:.6g}")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=field_df["position"], y=field_df["model"], mode="lines+markers", name="model"))
            fig.add_trace(go.Scatter(x=field_df["position"], y=field_df["measured"], mode="lines+markers", name="measured"))
            st.plotly_chart(fig, width="stretch")
        except Exception as exc:
            st.error(str(exc))

    with tabs[4]:
        left, right = st.columns(2)
        with left:
            st.markdown("**Uniform thermal coupling screen**")
            period_mm = st.number_input("Undulator period (mm)", min_value=0.001, value=20.0, key=f"pl_engwf_th_period_{profile}")
            b0 = st.number_input("Peak field (T)", value=0.05, key=f"pl_engwf_th_b_{profile}")
            gamma = st.number_input("Electron gamma", min_value=1.0001, value=80.0, key=f"pl_engwf_th_gamma_{profile}")
            alpha = st.number_input("Linear expansion coefficient (1/K)", value=12e-6, format="%.8g", key=f"pl_engwf_th_alpha_{profile}")
            dt = st.number_input("Temperature change (K)", value=10.0, key=f"pl_engwf_th_dt_{profile}")
            beta = st.number_input("Fractional field coefficient (1/K)", value=0.0, format="%.8g", key=f"pl_engwf_th_beta_{profile}")
            try:
                thermal = undulator_thermal_coupling(period_mm / 1000.0, b0, gamma, alpha, dt, field_temp_coeff_per_k=beta)
                st.write(thermal["changes"])
            except Exception as exc:
                st.error(str(exc))
        with right:
            st.markdown("**Bounded calibration/control update**")
            p = st.number_input("Current parameter", value=1.0, key=f"pl_engwf_ctl_p_{profile}")
            meas = st.number_input("Measured response", value=0.9, key=f"pl_engwf_ctl_meas_{profile}")
            target = st.number_input("Target response", value=1.0, key=f"pl_engwf_ctl_target_{profile}")
            sens = st.number_input("Local response sensitivity dy/dp", value=2.0, key=f"pl_engwf_ctl_sens_{profile}")
            gain = st.slider("Update gain", min_value=0.05, max_value=1.0, value=0.5, step=0.05, key=f"pl_engwf_ctl_gain_{profile}")
            try:
                update = bounded_calibration_update(p, meas, target, sens, gain=gain)
                st.write(update)
                st.caption("This computes a numerical next step only; it never commands hardware.")
            except Exception as exc:
                st.error(str(exc))

    with tabs[5]:
        c1, c2, c3 = st.columns(3)
        n = c1.number_input("Cases", min_value=0, max_value=100000, value=100, step=1, key=f"pl_engwf_batch_n_{profile}")
        workers = c2.number_input("Workers", min_value=1, max_value=128, value=4, step=1, key=f"pl_engwf_batch_w_{profile}")
        chunk = c3.number_input("Cases per chunk", min_value=1, max_value=10000, value=5, step=1, key=f"pl_engwf_batch_c_{profile}")
        plan = build_batch_plan([{"case": i, "profile": profile} for i in range(int(n))], workers=int(workers), chunk_size=int(chunk))
        a, b, c = st.columns(3)
        a.metric("Chunks", plan["chunk_count"])
        b.metric("Minimum scheduling waves", plan["minimum_scheduling_waves"])
        c.metric("Stable case fingerprints", plan["case_count"])
        st.caption("The planner is deterministic and resumable. Actual parallel execution stays adapter-specific so unsafe or non-thread-safe solvers are not launched blindly.")
