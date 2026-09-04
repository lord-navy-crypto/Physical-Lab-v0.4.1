"""Model-specific engineering scorecards for Physical Lab's non-accelerator Labs.

The generic V&V/UQ layer is intentionally kept separate from this module. These
profiles translate each Lab's native scientific diagnostics into engineering
questions such as requirement margin, convergence, computational efficiency and
replicate robustness.

All thresholds are editable screening defaults. They are not standards,
certification criteria, experimental validation, or claims of physical-product
reliability.
"""
from __future__ import annotations

import math
import statistics
from typing import Any

SUPPORTED_PROFILES = (
    "numerical-methods",
    "ising-monte-carlo",
    "random-walk-monte-carlo",
    "nonlinear-chaos",
    "oscillation-integration",
)

PROFILE_TITLES = {
    "numerical-methods": "Numerical Error · Accuracy & Precision Engineering",
    "ising-monte-carlo": "Ising Monte Carlo · Sampling & Criticality Engineering",
    "random-walk-monte-carlo": "Random Walk / Monte Carlo · Estimator Engineering",
    "nonlinear-chaos": "Nonlinear Dynamics · Robust Classification Engineering",
    "oscillation-integration": "Oscillation / Integration · Dynamic-System Engineering",
}

PROFILE_NOTES = {
    "numerical-methods": (
        "Treat floating-point precision, range reduction, truncation order and reference precision "
        "as an accuracy/cost design problem rather than only a numerical demonstration."
    ),
    "ising-monte-carlo": (
        "Judge a Monte Carlo result by equilibration, chain agreement, autocorrelation, effective "
        "sample size, exact/reference agreement and work per effective sample—not raw sweep count."
    ),
    "random-walk-monte-carlo": (
        "Treat seed-to-seed spread, asymptotic scaling, estimator bias and work-versus-precision as "
        "the primary engineering quantities."
    ),
    "nonlinear-chaos": (
        "For chaotic dynamics, raw long-time trajectory agreement is not a sensible requirement. "
        "Engineer convergence of indicators, event times, invariants and Lyapunov statistics instead."
    ),
    "oscillation-integration": (
        "Translate solver output into frequency, amplitude, phase, energy/work balance and timestep "
        "convergence requirements that map naturally to a physical dynamic system."
    ),
}

# Editable defaults. These are useful starting scorecards, not universal standards.
PROFILE_REQUIREMENTS: dict[str, list[dict[str, Any]]] = {
    "numerical-methods": [
        {"metric": "max_normalized_error", "upper": 1.0, "label": "Worst normalized error"},
        {"metric": "pass_fraction", "lower": 0.99, "label": "Scan pass fraction"},
        {"metric": "convergence_order", "lower": 1.0, "label": "Observed convergence order"},
    ],
    "ising-monte-carlo": [
        {"metric": "rhat_max", "upper": 1.05, "label": "Worst multi-chain R-hat"},
        {"metric": "effective_samples_min", "lower": 100.0, "label": "Minimum effective samples"},
        {"metric": "exact_reference_relative_error", "upper": 0.05, "label": "Exact/reference relative error"},
        {"metric": "equilibration_drift_sigma", "upper": 2.0, "label": "Equilibration drift / sigma"},
    ],
    "random-walk-monte-carlo": [
        {"metric": "msd_exponent_error", "upper": 0.10, "label": "|MSD exponent - theory|"},
        {"metric": "estimator_relative_error", "upper": 0.05, "label": "Estimator relative error"},
        {"metric": "replicate_cv", "upper": 0.10, "label": "Replicate coefficient of variation"},
    ],
    "nonlinear-chaos": [
        {"metric": "indicator_timestep_relative_change", "upper": 0.05, "label": "Indicator timestep sensitivity"},
        {"metric": "lyapunov_relative_spread", "upper": 0.10, "label": "Lyapunov replicate spread"},
        {"metric": "energy_balance_relative_error", "upper": 0.01, "label": "Energy/work-balance relative error"},
    ],
    "oscillation-integration": [
        {"metric": "frequency_relative_error", "upper": 0.01, "label": "Frequency relative error"},
        {"metric": "amplitude_relative_error", "upper": 0.02, "label": "Amplitude relative error"},
        {"metric": "phase_error_rad", "upper": 0.05, "label": "Phase error (rad)"},
        {"metric": "energy_balance_relative_error", "upper": 0.01, "label": "Energy/work-balance relative error"},
        {"metric": "timestep_relative_change", "upper": 0.01, "label": "Timestep sensitivity"},
    ],
}

PROFILE_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "numerical-methods": {
        "max_normalized_error": ("maximum_normalized_error", "max_normalized_error", "normalized_error_max"),
        "pass_fraction": ("pass_fraction", "fraction_passed", "scan_pass_fraction"),
        "convergence_order": ("convergence_order", "observed_order", "order"),
    },
    "ising-monte-carlo": {
        "rhat_max": ("rhat_max", "rhat_energy", "rhat_abs_magnetization"),
        "effective_samples_min": ("effective_samples_min", "effective_samples_energy", "effective_samples_abs_magnetization"),
        "exact_reference_relative_error": ("exact_reference_relative_error", "relative_exact_error", "analytic_relative_error"),
        "equilibration_drift_sigma": ("equilibration_drift_sigma", "mean_drift_sigma"),
    },
    "random-walk-monte-carlo": {
        "msd_exponent_error": ("msd_exponent_error", "diffusion_exponent_error", "scaling_exponent_error"),
        "estimator_relative_error": ("estimator_relative_error", "relative_error", "integration_relative_error"),
        "replicate_cv": ("replicate_cv", "coefficient_of_variation", "seed_cv"),
    },
    "nonlinear-chaos": {
        "indicator_timestep_relative_change": ("indicator_timestep_relative_change", "timestep_relative_change", "dt_relative_change"),
        "lyapunov_relative_spread": ("lyapunov_relative_spread", "lyapunov_cv", "lyapunov_spread"),
        "energy_balance_relative_error": ("energy_balance_relative_error", "relative_energy_error", "energy_drift_relative"),
    },
    "oscillation-integration": {
        "frequency_relative_error": ("frequency_relative_error", "relative_frequency_error", "natural_frequency_relative_error"),
        "amplitude_relative_error": ("amplitude_relative_error", "relative_amplitude_error"),
        "phase_error_rad": ("phase_error_rad", "phase_error"),
        "energy_balance_relative_error": ("energy_balance_relative_error", "relative_energy_error", "work_energy_relative_error"),
        "timestep_relative_change": ("timestep_relative_change", "dt_relative_change", "step_relative_change"),
    },
}


def _finite(value: Any, *, name: str = "value") -> float:
    try:
        x = float(value)
    except Exception as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite")
    return x


def _finite_or_none(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def _quantile(values: list[float], q: float) -> float:
    xs = sorted(_finite(v) for v in values)
    if not xs:
        raise ValueError("values cannot be empty")
    if len(xs) == 1:
        return xs[0]
    pos = q * (len(xs) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    w = pos - lo
    return xs[lo] * (1.0 - w) + xs[hi] * w


def relative_change(a: float, b: float, *, floor: float = 1e-30) -> float:
    """Symmetric magnitude change normalized to the larger response scale."""
    x = _finite(a, name="a")
    y = _finite(b, name="b")
    scale = max(abs(x), abs(y), abs(_finite(floor, name="floor")))
    return abs(y - x) / scale


def estimate_convergence_order(coarse_error: float, fine_error: float, refinement_ratio: float) -> float | None:
    """Estimate p from e_coarse/e_fine = r**p for a refinement ratio r > 1."""
    ec = abs(_finite(coarse_error, name="coarse_error"))
    ef = abs(_finite(fine_error, name="fine_error"))
    r = _finite(refinement_ratio, name="refinement_ratio")
    if r <= 1.0:
        raise ValueError("refinement_ratio must be > 1")
    if ec == 0.0 and ef == 0.0:
        return None
    if ec == 0.0 or ef == 0.0:
        return math.inf if ef == 0.0 else -math.inf
    return math.log(ec / ef) / math.log(r)


def replicate_stability(values: list[float]) -> dict[str, Any]:
    """Descriptive seed/replicate stability without assuming a probability model."""
    xs = [_finite(v) for v in values]
    if not xs:
        raise ValueError("values cannot be empty")
    mean = statistics.fmean(xs)
    sample_std = statistics.stdev(xs) if len(xs) >= 2 else 0.0
    abs_mean = abs(mean)
    cv = sample_std / abs_mean if abs_mean > 0 else None
    return {
        "n": len(xs),
        "mean": mean,
        "sample_std": sample_std,
        "coefficient_of_variation": cv,
        "min": min(xs),
        "p05": _quantile(xs, 0.05),
        "median": _quantile(xs, 0.50),
        "p95": _quantile(xs, 0.95),
        "max": max(xs),
        "range": max(xs) - min(xs),
        "boundary": "Descriptive finite-replicate statistics; not a certified population distribution or failure probability.",
    }


def cost_accuracy_front(cases: list[dict[str, Any]], *, error_key: str = "error", cost_key: str = "cost") -> dict[str, Any]:
    """Return cases non-dominated in both lower error and lower computational cost."""
    prepared: list[tuple[int, float, float]] = []
    for i, case in enumerate(cases):
        error = abs(_finite(case.get(error_key), name=error_key))
        cost = _finite(case.get(cost_key), name=cost_key)
        if cost < 0:
            raise ValueError("cost cannot be negative")
        prepared.append((i, error, cost))
    front: list[int] = []
    for i, err_i, cost_i in prepared:
        dominated = False
        for j, err_j, cost_j in prepared:
            if i == j:
                continue
            no_worse = err_j <= err_i and cost_j <= cost_i
            strictly_better = err_j < err_i or cost_j < cost_i
            if no_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            front.append(i)
    front.sort(key=lambda idx: (_finite(cases[idx].get(cost_key)), abs(_finite(cases[idx].get(error_key)))))
    return {
        "indices": front,
        "cases": [cases[i] for i in front],
        "boundary": "Efficiency frontier uses only the entered cost/error pair and does not prove global algorithmic optimality.",
    }


def _assessment(value: float, lower: float | None, upper: float | None, uncertainty: float = 0.0) -> dict[str, Any]:
    y = _finite(value)
    u = abs(_finite(uncertainty))
    lo = None if lower is None else _finite(lower)
    hi = None if upper is None else _finite(upper)
    if lo is not None and hi is not None and lo > hi:
        raise ValueError("lower requirement exceeds upper requirement")
    nominal_ok = (lo is None or y >= lo) and (hi is None or y <= hi)
    interval_ok = (lo is None or y - u >= lo) and (hi is None or y + u <= hi)
    status = "FAIL" if not nominal_ok else ("PASS" if interval_ok else "REVIEW")
    margins: list[float] = []
    if lo is not None:
        margins.append(y - u - lo)
    if hi is not None:
        margins.append(hi - (y + u))
    return {
        "status": status,
        "value": y,
        "expanded_interval": [y - u, y + u],
        "lower": lo,
        "upper": hi,
        "minimum_margin_after_uncertainty": min(margins) if margins else None,
    }


def profile_scorecard(
    profile: str,
    metrics: dict[str, float],
    *,
    uncertainties: dict[str, float] | None = None,
    requirements: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate one Lab's domain-specific engineering scorecard."""
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"unsupported engineering profile: {profile}")
    uncertainties = uncertainties or {}
    reqs = requirements or PROFILE_REQUIREMENTS[profile]
    rows: list[dict[str, Any]] = []
    severity = {"PASS": 0, "REVIEW": 1, "FAIL": 2}
    for req in reqs:
        metric = str(req["metric"])
        label = str(req.get("label") or metric)
        if metric not in metrics:
            rows.append({
                "metric": metric,
                "label": label,
                "status": "REVIEW",
                "reason": "metric not supplied",
                "lower": req.get("lower"),
                "upper": req.get("upper"),
            })
            continue
        result = _assessment(
            metrics[metric],
            req.get("lower"),
            req.get("upper"),
            uncertainties.get(metric, req.get("expanded_uncertainty", 0.0)),
        )
        result.update({"metric": metric, "label": label})
        rows.append(result)
    overall = max((r["status"] for r in rows), key=lambda s: severity[s], default="REVIEW")
    completeness = sum("value" in r for r in rows) / len(rows) if rows else 0.0
    return {
        "profile": profile,
        "title": PROFILE_TITLES[profile],
        "overall_status": overall,
        "metric_completeness": completeness,
        "requirements": rows,
        "boundary": "Editable engineering screening defaults only; not a laboratory standard, certification, or experimental-validation claim.",
    }


def _flatten_numeric(value: Any, prefix: str = "", depth: int = 0) -> dict[str, float]:
    """Flatten common Lab/session containers while retaining semantic column names."""
    if depth > 5:
        return {}
    if isinstance(value, bool):
        return {}
    if isinstance(value, (int, float)):
        x = _finite_or_none(value)
        return {prefix: x} if prefix and x is not None else {}
    if isinstance(value, dict):
        out: dict[str, float] = {}
        for key, item in list(value.items())[:300]:
            child = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten_numeric(item, child, depth + 1))
        return out
    if isinstance(value, (list, tuple)):
        out: dict[str, float] = {}
        for index, item in enumerate(list(value)[:300]):
            child = f"{prefix}.{index}" if prefix else str(index)
            out.update(_flatten_numeric(item, child, depth + 1))
        return out
    try:
        if hasattr(value, "to_dict"):
            return _flatten_numeric(value.to_dict(), prefix, depth + 1)
        if hasattr(value, "item"):
            return _flatten_numeric(value.item(), prefix, depth + 1)
    except Exception:
        return {}
    return {}


def _path_match_rank(path: str, aliases: tuple[str, ...]) -> int | None:
    aliases_lower = {name.lower() for name in aliases}
    components = [part.lower() for part in path.split(".") if part]
    if not components:
        return None
    if components[-1] in aliases_lower:
        return 0
    if any(part in aliases_lower for part in components):
        return 1
    return None


def discover_metrics_with_provenance(profile: str, sources: list[Any]) -> dict[str, dict[str, Any]]:
    """Best-effort canonical metric discovery with source paths for auditability."""
    aliases = PROFILE_ALIASES.get(profile, {})
    flat: dict[str, float] = {}
    for source in sources:
        flat.update(_flatten_numeric(source))
    found: dict[str, dict[str, Any]] = {}
    for canonical, names in aliases.items():
        candidates: list[tuple[int, int, str, float]] = []
        for order, (path, value) in enumerate(flat.items()):
            rank = _path_match_rank(path, names)
            if rank is not None:
                candidates.append((rank, order, path, value))
        if not candidates:
            continue
        best_rank = min(item[0] for item in candidates)
        best = [item for item in candidates if item[0] == best_rank]
        if canonical == "rhat_max":
            chosen = max(best, key=lambda item: item[3])
        elif canonical == "effective_samples_min":
            chosen = min(best, key=lambda item: item[3])
        else:
            chosen = best[-1]
        found[canonical] = {"value": chosen[3], "path": chosen[2], "match_rank": chosen[0]}
    return found


def discover_metrics(profile: str, sources: list[Any]) -> dict[str, float]:
    """Backward-compatible value-only metric discovery."""
    return {name: float(item["value"]) for name, item in discover_metrics_with_provenance(profile, sources).items()}


def synchronize_scorecard_rows(
    profile: str,
    existing_rows: list[dict[str, Any]] | None,
    discovered: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Refresh solver-derived values while preserving human overrides and limits.

    v0.8.1 initialized the scorecard only once in Streamlit session state, so a
    later solver run could leave the table showing stale or empty values. This
    rebuilds canonical rows every render. Manual overrides, uncertainty and
    edited limits are preserved; automatic values and provenance are refreshed
    from the current Lab state and cleared when no current value is discoverable.
    """
    if profile not in SUPPORTED_PROFILES:
        raise ValueError(f"unsupported engineering profile: {profile}")
    previous = {str(row.get("metric")): dict(row) for row in (existing_rows or []) if row.get("metric")}
    rows: list[dict[str, Any]] = []
    for req in PROFILE_REQUIREMENTS[profile]:
        metric = str(req["metric"])
        old = previous.get(metric, {})
        auto = discovered.get(metric, {})
        rows.append({
            "metric": metric,
            "engineering_quantity": old.get("engineering_quantity") or req.get("label", metric),
            "auto_value": _finite_or_none(auto.get("value")),
            "auto_source": str(auto.get("path") or ""),
            "manual_override": _finite_or_none(old.get("manual_override")),
            "expanded_uncertainty": abs(_finite_or_none(old.get("expanded_uncertainty")) or 0.0),
            "lower": _finite_or_none(old.get("lower")) if "lower" in old else _finite_or_none(req.get("lower")),
            "upper": _finite_or_none(old.get("upper")) if "upper" in old else _finite_or_none(req.get("upper")),
        })
    return rows


def _effective_value(row: dict[str, Any]) -> tuple[float | None, str]:
    manual = _finite_or_none(row.get("manual_override"))
    if manual is not None:
        return manual, "manual"
    auto = _finite_or_none(row.get("auto_value"))
    return auto, ("auto" if auto is not None else "missing")


def profile_reference_cases() -> dict[str, dict[str, float]]:
    """Deterministic synthetic scorecards used by source validation."""
    return {
        "numerical-methods": {"max_normalized_error": 0.42, "pass_fraction": 0.997, "convergence_order": 3.9},
        "ising-monte-carlo": {"rhat_max": 1.012, "effective_samples_min": 640.0, "exact_reference_relative_error": 0.018, "equilibration_drift_sigma": 0.7},
        "random-walk-monte-carlo": {"msd_exponent_error": 0.025, "estimator_relative_error": 0.013, "replicate_cv": 0.038},
        "nonlinear-chaos": {"indicator_timestep_relative_change": 0.018, "lyapunov_relative_spread": 0.044, "energy_balance_relative_error": 0.003},
        "oscillation-integration": {"frequency_relative_error": 0.0025, "amplitude_relative_error": 0.006, "phase_error_rad": 0.012, "energy_balance_relative_error": 0.002, "timestep_relative_change": 0.003},
    }


def render_model_engineering(st: Any, profile: str, namespace: dict[str, Any] | None = None) -> None:
    """Render a synchronized domain-specific engineering panel."""
    if profile not in SUPPORTED_PROFILES:
        return
    import pandas as pd
    import plotly.graph_objects as go

    st.markdown("---")
    st.markdown(f"## Physical Lab · {PROFILE_TITLES[profile]}")
    st.caption(PROFILE_NOTES[profile])
    st.info(
        "Automatic values are refreshed from the current Lab state on every render. "
        "Manual overrides and edited limits are preserved. Missing metrics remain REVIEW."
    )

    sources: list[Any] = [namespace or {}]
    try:
        sources.append(dict(st.session_state))
    except Exception:
        pass
    discovered = discover_metrics_with_provenance(profile, sources)

    score_tab, convergence_tab, robustness_tab = st.tabs(
        ["Domain scorecard", "Convergence / cost", "Replicate robustness"]
    )
    state_key = f"pl_model_eng_scorecard_{profile}"
    existing_rows: list[dict[str, Any]] = []
    if state_key in st.session_state:
        existing = st.session_state[state_key]
        try:
            existing_rows = existing.to_dict(orient="records")
        except Exception:
            if isinstance(existing, list):
                existing_rows = [dict(row) for row in existing if isinstance(row, dict)]
    synced_rows = synchronize_scorecard_rows(profile, existing_rows, discovered)
    st.session_state[state_key] = pd.DataFrame(synced_rows)

    with score_tab:
        if discovered:
            st.caption(
                f"Auto-detected {len(discovered)} canonical metric(s). Source paths are shown so the mapping can be audited before screening."
            )
        else:
            st.caption("No canonical metrics are currently auto-detected. Complete the relevant Lab run or enter a manual override.")
        edited = st.data_editor(
            st.session_state[state_key],
            width="stretch",
            hide_index=True,
            key=f"pl_model_eng_editor_{profile}",
            column_config={
                "metric": st.column_config.TextColumn("Canonical metric", disabled=True),
                "engineering_quantity": st.column_config.TextColumn("Engineering quantity", disabled=True),
                "auto_value": st.column_config.NumberColumn("Current solver value", disabled=True, format="%.8g"),
                "auto_source": st.column_config.TextColumn("Detected source", disabled=True),
                "manual_override": st.column_config.NumberColumn("Manual override", format="%.8g"),
                "expanded_uncertainty": st.column_config.NumberColumn("± expanded uncertainty", min_value=0.0, format="%.6g"),
                "lower": st.column_config.NumberColumn("Lower target", format="%.8g"),
                "upper": st.column_config.NumberColumn("Upper target", format="%.8g"),
            },
        )
        st.session_state[state_key] = edited
        metrics: dict[str, float] = {}
        uncertainties: dict[str, float] = {}
        custom_reqs: list[dict[str, Any]] = []
        source_rows: list[dict[str, Any]] = []
        for row in edited.to_dict(orient="records"):
            metric = str(row.get("metric", ""))
            value, source = _effective_value(row)
            if value is not None:
                metrics[metric] = value
            uncertainties[metric] = abs(_finite_or_none(row.get("expanded_uncertainty")) or 0.0)
            custom_reqs.append({
                "metric": metric,
                "label": row.get("engineering_quantity") or metric,
                "lower": _finite_or_none(row.get("lower")),
                "upper": _finite_or_none(row.get("upper")),
            })
            source_rows.append({"metric": metric, "effective_source": source, "effective_value": value})
        result = profile_scorecard(profile, metrics, uncertainties=uncertainties, requirements=custom_reqs)
        a, b, c, d = st.columns(4)
        a.metric("Overall screening", result["overall_status"])
        b.metric("Metrics supplied", f"{100 * result['metric_completeness']:.0f}%")
        c.metric("Auto-detected now", str(len(discovered)))
        fail_count = sum(r["status"] == "FAIL" for r in result["requirements"])
        d.metric("Failed nominal targets", str(fail_count))
        display = pd.DataFrame(result["requirements"])
        preferred = [col for col in ["label", "status", "value", "expanded_interval", "lower", "upper", "minimum_margin_after_uncertainty", "reason"] if col in display.columns]
        st.dataframe(display[preferred], width="stretch", hide_index=True)
        st.dataframe(pd.DataFrame(source_rows), width="stretch", hide_index=True)
        st.caption(result["boundary"])

    with convergence_tab:
        st.caption(
            "Use two levels of timestep, grid, Taylor order, lattice size, sample count, or another refinement variable. "
            "The formula assumes the supplied error is in an asymptotic power-law regime."
        )
        c1, c2, c3 = st.columns(3)
        coarse_error = c1.number_input("Coarse error", min_value=0.0, value=0.02, format="%.10g", key=f"pl_model_eng_ec_{profile}")
        fine_error = c2.number_input("Fine error", min_value=0.0, value=0.005, format="%.10g", key=f"pl_model_eng_ef_{profile}")
        ratio = c3.number_input("Refinement ratio (>1)", min_value=1.000001, value=2.0, format="%.6g", key=f"pl_model_eng_ratio_{profile}")
        try:
            order = estimate_convergence_order(coarse_error, fine_error, ratio)
            st.metric("Observed convergence order p", "—" if order is None else ("∞" if math.isinf(order) and order > 0 else f"{order:.6g}"))
        except Exception as exc:
            st.error(str(exc))

        st.markdown("#### Cost ↔ accuracy design points")
        default_cases = pd.DataFrame([
            {"design": "coarse", "cost": 1.0, "error": 0.02},
            {"design": "balanced", "cost": 2.0, "error": 0.007},
            {"design": "fine", "cost": 5.0, "error": 0.003},
        ])
        cost_key = f"pl_model_eng_cost_{profile}"
        if cost_key not in st.session_state:
            st.session_state[cost_key] = default_cases
        cost_df = st.data_editor(
            st.session_state[cost_key], num_rows="dynamic", width="stretch", hide_index=True,
            key=f"pl_model_eng_cost_editor_{profile}"
        )
        st.session_state[cost_key] = cost_df
        try:
            cases = cost_df.to_dict(orient="records")
            front = cost_accuracy_front(cases)
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=cost_df["cost"], y=cost_df["error"], mode="markers+text",
                text=cost_df["design"], textposition="top center", name="designs"
            ))
            if front["cases"]:
                fig.add_trace(go.Scatter(
                    x=[float(x["cost"]) for x in front["cases"]],
                    y=[abs(float(x["error"])) for x in front["cases"]],
                    mode="lines+markers", name="non-dominated frontier"
                ))
            fig.update_layout(
                title="Computational cost versus error", xaxis_title="Relative / measured cost",
                yaxis_title="Error magnitude", height=450
            )
            st.plotly_chart(fig, width="stretch")
            st.caption(front["boundary"])
        except Exception as exc:
            st.warning(f"Cost/accuracy frontier unavailable: {exc}")

    with robustness_tab:
        st.caption(
            "Paste a finite set of seed, chain, timestep, lattice-size, or repeat-run values for the same engineering response. "
            "For chaos, prefer indicators or event statistics rather than raw long-time coordinates."
        )
        raw = st.text_area(
            "Replicate values (comma or whitespace separated)",
            value="1.00, 1.02, 0.99, 1.01, 1.00",
            key=f"pl_model_eng_rep_{profile}",
        )
        try:
            values = [float(token) for token in raw.replace(",", " ").split()]
            result = replicate_stability(values)
            a, b, c, d = st.columns(4)
            a.metric("Replicates", str(result["n"]))
            b.metric("Mean", f"{result['mean']:.8g}")
            c.metric("Sample std", f"{result['sample_std']:.6g}")
            d.metric("CV", "—" if result["coefficient_of_variation"] is None else f"{100 * result['coefficient_of_variation']:.4g}%")
            st.write({k: v for k, v in result.items() if k != "boundary"})
            st.caption(result["boundary"])
        except Exception as exc:
            st.warning(f"Replicate summary unavailable: {exc}")
