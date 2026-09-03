"""Engineering verification, tolerance and uncertainty tools for Physical Lab.

The module is deliberately explicit about what is known and what is assumed.
It separates measurement, manufacturing, model-input, numerical and model-form
uncertainties instead of collapsing every error into one number. Linearized
propagation and tolerance stacks are engineering screening tools, not substitutes
for nonlinear solver ensembles or physical validation experiments.
"""
from __future__ import annotations

import math
from typing import Any

CATEGORIES = [
    "measurement",
    "manufacturing",
    "model input",
    "numerical",
    "model-form",
    "sampling",
]

PROFILE_COMPONENTS = {
    "numerical-methods": [
        ("input representation", "model input", "Input representation / reduction uncertainty"),
        ("truncation / discretization", "numerical", "Finite-term or discretization uncertainty"),
        ("roundoff / cancellation", "numerical", "Floating-point and cancellation uncertainty"),
        ("reference backend", "model-form", "Reference-model/backend discrepancy"),
    ],
    "ising-monte-carlo": [
        ("temperature calibration", "measurement", "Temperature/control calibration"),
        ("sampling uncertainty", "sampling", "Finite Monte Carlo sampling uncertainty"),
        ("finite-size effect", "model-form", "Finite lattice versus target system"),
        ("update / equilibration bias", "numerical", "Finite equilibration and algorithmic bias"),
    ],
    "random-walk-monte-carlo": [
        ("sampling uncertainty", "sampling", "Finite trial / replicate uncertainty"),
        ("step-model parameter", "model input", "Input probability or step-model uncertainty"),
        ("RNG / QMC replicate", "numerical", "Finite pseudorandom or scrambled-QMC realization"),
        ("model-form", "model-form", "Difference between chosen walk model and target process"),
    ],
    "nonlinear-chaos": [
        ("initial-condition tolerance", "model input", "Initial-state preparation uncertainty"),
        ("physical parameter tolerance", "model input", "Mass/length/gravity/damping uncertainty"),
        ("time-step / integration", "numerical", "Finite-step numerical uncertainty"),
        ("finite-window classification", "model-form", "Finite-time indicator versus global dynamics"),
    ],
    "oscillation-integration": [
        ("mass tolerance", "manufacturing", "Mass / equivalent inertia tolerance"),
        ("stiffness / natural frequency", "manufacturing", "Spring or identified-frequency tolerance"),
        ("damping calibration", "measurement", "Damping coefficient identification uncertainty"),
        ("drive calibration", "measurement", "Drive amplitude/frequency calibration"),
        ("time-step / solver", "numerical", "Numerical integration uncertainty"),
        ("model-form", "model-form", "Linear/idealized oscillator versus physical device"),
    ],
    "radia-magnet-studio": [
        ("gap tolerance", "manufacturing", "Mechanical gap manufacturing / assembly tolerance"),
        ("period / block placement", "manufacturing", "Longitudinal placement tolerance"),
        ("remanence Br", "manufacturing", "Magnet batch / material variation"),
        ("magnetization angle", "manufacturing", "Magnetization orientation tolerance"),
        ("field measurement calibration", "measurement", "Hall probe / positioning calibration"),
        ("RADIA solve", "numerical", "Relaxation/discretization/solver uncertainty"),
        ("magnet model-form", "model-form", "Material/geometry idealization discrepancy"),
    ],
    "radiation-platform": [
        ("electron energy", "model input", "Beam-energy setting / spread uncertainty"),
        ("undulator K / field", "model input", "Realized-field / K uncertainty"),
        ("period", "manufacturing", "Undulator period manufacturing uncertainty"),
        ("observation angle", "measurement", "Alignment / angular calibration uncertainty"),
        ("trajectory / radiation numerics", "numerical", "Trajectory and radiation integration uncertainty"),
        ("detector / readout", "measurement", "Detector calibration / response uncertainty"),
        ("radiation model-form", "model-form", "Idealizations omitted by the selected radiation model"),
    ],
}


def default_budget(profile: str) -> list[dict[str, Any]]:
    rows = PROFILE_COMPONENTS.get(profile, [("input uncertainty", "model input", "Engineering input uncertainty")])
    return [
        {
            "component": name,
            "category": category,
            "standard_uncertainty": 0.0,
            "sensitivity": 0.0,
            "tolerance_half_width": 0.0,
            "note": note,
        }
        for name, category, note in rows
    ]


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def linear_uncertainty_budget(rows: list[dict[str, Any]], correlation: list[list[float]] | None = None) -> dict[str, Any]:
    """First-order propagation y≈y0+Σ c_i δx_i.

    `standard_uncertainty` is the standard uncertainty of input x_i and
    `sensitivity` is dy/dx_i. Correlation, when supplied, is a dimensionless
    correlation matrix. The function does not infer distributions or units.
    """
    active = []
    for row in rows:
        u = abs(_finite(row.get("standard_uncertainty")))
        c = _finite(row.get("sensitivity"))
        active.append((row, c * u))
    n = len(active)
    corr = correlation
    if corr is None:
        corr = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    if len(corr) != n or any(len(r) != n for r in corr):
        raise ValueError("correlation matrix must match the number of budget rows")
    variance = 0.0
    for i in range(n):
        for j in range(n):
            rho = _finite(corr[i][j])
            if abs(rho) > 1.0000001:
                raise ValueError("correlation coefficients must be between -1 and 1")
            variance += active[i][1] * active[j][1] * rho
    variance = max(0.0, variance)
    uc = math.sqrt(variance)
    contributions = []
    independent_denom = sum(v * v for _, v in active)
    for row, effect in active:
        contributions.append({
            "component": str(row.get("component", "component")),
            "category": str(row.get("category", "unspecified")),
            "standard_effect": effect,
            "independent_variance_share": (effect * effect / independent_denom) if independent_denom > 0 else 0.0,
        })
    return {
        "combined_standard_uncertainty": uc,
        "expanded_uncertainty_k2": 2.0 * uc,
        "variance": variance,
        "contributions": contributions,
        "assumption": "first-order local sensitivity propagation",
    }


def tolerance_stack(rows: list[dict[str, Any]]) -> dict[str, float]:
    effects = [abs(_finite(r.get("sensitivity")) * _finite(r.get("tolerance_half_width"))) for r in rows]
    return {
        "rss_half_width": math.sqrt(sum(x * x for x in effects)),
        "worst_case_half_width": sum(effects),
    }


def requirement_assessment(nominal: float, lower: float | None, upper: float | None, expanded_uncertainty: float) -> dict[str, Any]:
    y = _finite(nominal)
    u = abs(_finite(expanded_uncertainty))
    lo = None if lower is None else _finite(lower)
    hi = None if upper is None else _finite(upper)
    if lo is not None and hi is not None and lo > hi:
        raise ValueError("lower requirement exceeds upper requirement")
    interval_lo, interval_hi = y - u, y + u
    nominal_in = (lo is None or y >= lo) and (hi is None or y <= hi)
    interval_in = (lo is None or interval_lo >= lo) and (hi is None or interval_hi <= hi)
    if not nominal_in:
        status = "FAIL"
    elif interval_in:
        status = "PASS"
    else:
        status = "REVIEW"
    margins = []
    if lo is not None:
        margins.append(interval_lo - lo)
    if hi is not None:
        margins.append(hi - interval_hi)
    return {
        "status": status,
        "nominal": y,
        "expanded_interval": [interval_lo, interval_hi],
        "minimum_margin_after_uncertainty": min(margins) if margins else None,
    }


def validation_comparison(simulated: float, measured: float, u_sim: float, u_meas: float, u_model_form: float = 0.0) -> dict[str, float | str | None]:
    discrepancy = abs(_finite(simulated) - _finite(measured))
    combined = math.sqrt(_finite(u_sim) ** 2 + _finite(u_meas) ** 2 + _finite(u_model_form) ** 2)
    ratio = discrepancy / combined if combined > 0 else None
    if ratio is None:
        interpretation = "uncertainty not specified"
    elif ratio <= 1.0:
        interpretation = "discrepancy is within the entered combined standard-uncertainty scale"
    else:
        interpretation = "discrepancy exceeds the entered combined standard-uncertainty scale"
    return {
        "absolute_discrepancy": discrepancy,
        "combined_standard_uncertainty": combined,
        "normalized_discrepancy": ratio,
        "interpretation": interpretation,
    }


def linearized_monte_carlo(rows: list[dict[str, Any]], nominal: float, samples: int = 10000, seed: int = 2026) -> dict[str, Any]:
    """Monte Carlo propagation through the same local linear surrogate.

    This samples independent normal input perturbations. It is useful for
    checking the linear budget numerically; it is not a nonlinear solver
    ensemble and is labeled as such in the UI.
    """
    import numpy as np
    n = max(100, min(int(samples), 200000))
    rng = np.random.default_rng(int(seed))
    y = np.full(n, float(nominal), dtype=float)
    for row in rows:
        u = abs(_finite(row.get("standard_uncertainty")))
        c = _finite(row.get("sensitivity"))
        if u > 0 and c != 0:
            y += c * rng.normal(0.0, u, size=n)
    q = np.quantile(y, [0.025, 0.5, 0.975])
    return {
        "samples": n,
        "mean": float(np.mean(y)),
        "std": float(np.std(y, ddof=1)),
        "p2_5": float(q[0]),
        "median": float(q[1]),
        "p97_5": float(q[2]),
        "values": y,
        "model": "independent-normal inputs through first-order linear surrogate",
    }


def render_engineering_vvuq(st: Any, profile: str, namespace: dict[str, Any] | None = None) -> None:
    import pandas as pd
    import plotly.graph_objects as go

    st.markdown("---")
    st.markdown("## Physical Lab · Engineering V&V / Uncertainty")
    st.caption(
        "Engineering screening layer for error budgets, tolerance stacks, requirement margins and simulation↔measurement comparison. "
        "It separates uncertainty sources and does not convert a model into a validated product by itself."
    )
    tab_budget, tab_req, tab_val = st.tabs(["Error budget & propagation", "Tolerance / requirement margin", "Simulation ↔ measurement"])

    key = f"pl_eng_budget_{profile}"
    if key not in st.session_state:
        st.session_state[key] = pd.DataFrame(default_budget(profile))

    with tab_budget:
        st.caption("Enter standard uncertainties and local sensitivities in mutually consistent units. Zero means 'not quantified yet', not 'known to be zero'.")
        edited = st.data_editor(
            st.session_state[key],
            num_rows="dynamic",
            width="stretch",
            key=f"pl_eng_editor_{profile}",
            column_config={
                "standard_uncertainty": st.column_config.NumberColumn("u(x)", min_value=0.0, format="%.6g"),
                "sensitivity": st.column_config.NumberColumn("dy/dx", format="%.6g"),
                "tolerance_half_width": st.column_config.NumberColumn("± tolerance", min_value=0.0, format="%.6g"),
            },
        )
        st.session_state[key] = edited
        rows = edited.to_dict(orient="records")
        budget = linear_uncertainty_budget(rows)
        stack = tolerance_stack(rows)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Combined standard u", f"{budget['combined_standard_uncertainty']:.6g}")
        c2.metric("Expanded U (k=2)", f"{budget['expanded_uncertainty_k2']:.6g}")
        c3.metric("RSS tolerance ±", f"{stack['rss_half_width']:.6g}")
        c4.metric("Worst-case tolerance ±", f"{stack['worst_case_half_width']:.6g}")
        contrib = pd.DataFrame(budget["contributions"])
        if len(contrib):
            fig = go.Figure(go.Bar(x=contrib["component"], y=100.0 * contrib["independent_variance_share"]))
            fig.update_layout(title="Independent variance contribution screening", xaxis_title="Component", yaxis_title="Variance share (%)", height=480)
            st.plotly_chart(fig, width="stretch")
        st.caption("RSS assumes independent signed effects. Worst-case sums absolute tolerance effects. The k=2 interval is an expanded-uncertainty convention, not an automatic 95% guarantee for arbitrary distributions.")
        mc1, mc2, mc3 = st.columns(3)
        nominal_mc = mc1.number_input("Nominal response for linearized MC", value=0.0, format="%.8g", key=f"pl_eng_mc_nom_{profile}")
        samples = mc2.select_slider("Linearized MC samples", options=[1000, 5000, 10000, 25000, 50000], value=10000, key=f"pl_eng_mc_n_{profile}")
        seed = mc3.number_input("MC seed", min_value=0, value=2026, step=1, key=f"pl_eng_mc_seed_{profile}")
        if st.button("Propagate through linearized Monte Carlo", key=f"pl_eng_mc_run_{profile}"):
            st.session_state[f"pl_eng_mc_result_{profile}"] = linearized_monte_carlo(rows, float(nominal_mc), int(samples), int(seed))
        mcr = st.session_state.get(f"pl_eng_mc_result_{profile}")
        if mcr:
            st.write({k: v for k, v in mcr.items() if k != "values"})
            fig = go.Figure(go.Histogram(x=mcr["values"], nbinsx=50, histnorm="probability density"))
            fig.update_layout(title="Linearized uncertainty propagation distribution", xaxis_title="Response", yaxis_title="Density", height=470)
            st.plotly_chart(fig, width="stretch")
            st.warning("This histogram uses a local linear surrogate and independent normal inputs. Use a real solver ensemble when nonlinearities, bounds or interactions matter.")

    with tab_req:
        rows = st.session_state[key].to_dict(orient="records")
        budget = linear_uncertainty_budget(rows)
        c1, c2, c3, c4 = st.columns(4)
        nominal = c1.number_input("Nominal response", value=0.0, format="%.8g", key=f"pl_eng_req_nom_{profile}")
        use_lo = c2.toggle("Lower requirement", value=False, key=f"pl_eng_req_use_lo_{profile}")
        lower = c2.number_input("Lower limit", value=0.0, format="%.8g", disabled=not use_lo, key=f"pl_eng_req_lo_{profile}")
        use_hi = c3.toggle("Upper requirement", value=True, key=f"pl_eng_req_use_hi_{profile}")
        upper = c3.number_input("Upper limit", value=1.0, format="%.8g", disabled=not use_hi, key=f"pl_eng_req_hi_{profile}")
        basis = c4.selectbox("Uncertainty basis", ["Expanded U (k=2)", "RSS tolerance", "Worst-case tolerance"], key=f"pl_eng_req_basis_{profile}")
        stack = tolerance_stack(rows)
        half = budget["expanded_uncertainty_k2"] if basis.startswith("Expanded") else (stack["rss_half_width"] if basis.startswith("RSS") else stack["worst_case_half_width"])
        try:
            r = requirement_assessment(float(nominal), float(lower) if use_lo else None, float(upper) if use_hi else None, float(half))
            st.metric("Engineering screening status", r["status"])
            st.write(r)
            st.caption("PASS means the entered uncertainty/tolerance interval stays inside the entered limits. REVIEW means the nominal is inside but the interval crosses a limit. This is a screening rule, not a certification standard.")
        except Exception as exc:
            st.error(str(exc))

    with tab_val:
        st.caption("Compare one simulated quantity with one measured quantity while keeping simulation, measurement and model-form uncertainty separate.")
        c1, c2 = st.columns(2)
        sim = c1.number_input("Simulated value", value=0.0, format="%.10g", key=f"pl_eng_val_sim_{profile}")
        meas = c2.number_input("Measured value", value=0.0, format="%.10g", key=f"pl_eng_val_meas_{profile}")
        c3, c4, c5 = st.columns(3)
        us = c3.number_input("Simulation standard uncertainty", min_value=0.0, value=0.0, format="%.8g", key=f"pl_eng_val_us_{profile}")
        um = c4.number_input("Measurement standard uncertainty", min_value=0.0, value=0.0, format="%.8g", key=f"pl_eng_val_um_{profile}")
        uf = c5.number_input("Model-form standard uncertainty", min_value=0.0, value=0.0, format="%.8g", key=f"pl_eng_val_uf_{profile}")
        r = validation_comparison(sim, meas, us, um, uf)
        a, b, c = st.columns(3)
        a.metric("|Simulation − measurement|", f"{r['absolute_discrepancy']:.6g}")
        b.metric("Combined standard uncertainty", f"{r['combined_standard_uncertainty']:.6g}")
        c.metric("Normalized discrepancy", "—" if r["normalized_discrepancy"] is None else f"{r['normalized_discrepancy']:.6g}")
        st.info(str(r["interpretation"]))
        st.caption("This is a transparent comparison metric. It does not claim ASME/NIST certification and does not infer uncertainty values that you did not enter or compute.")
