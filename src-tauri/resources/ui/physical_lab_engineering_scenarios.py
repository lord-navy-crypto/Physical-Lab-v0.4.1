"""Engineering decision layer for Physical Lab physics scenarios.

Physical Lab intentionally keeps only two top-level modes for the hybrid Labs:
Mathematical Tool and Physics Scenario.  This module does not introduce a third
mode.  Instead it upgrades Physics Scenario output into an engineering review:

    design variable -> physical response -> requirement -> margin -> decision

The checks are editable screening requirements, not standards, certification or
experimental validation.  They are designed to make the computational-physics
work useful for engineering design reasoning while preserving the underlying
physics model and numerical evidence.
"""
from __future__ import annotations

import math
from typing import Any, Mapping


SCENARIO_META = {
    "numerical-methods": {
        "title": "Engineering lens · quantum confinement design verification",
        "objective": "Choose a numerical resolution and dimensional tolerance that keep a predicted confinement energy inside an engineering error budget.",
        "result_key": "pl_physics_scene_quantum_result",
    },
    "ising-monte-carlo": {
        "title": "Engineering lens · thermal operating-window screening",
        "objective": "Treat magnetic order as a design response and estimate whether an operating point retains margin from loss of order and critical sensitivity.",
        "result_key": "pl_physics_scene_ising_result",
    },
    "random-walk-monte-carlo": {
        "title": "Engineering lens · stochastic transport characterization",
        "objective": "Validate transport-parameter recovery before using the stochastic model for path-length and timing decisions.",
        "result_key": "pl_physics_scene_transport_result",
    },
}


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return float(default)
    return out if math.isfinite(out) else float(default)


def _requirement_le(label: str, observed: float, limit: float, unit: str = "") -> dict[str, Any]:
    observed = _finite(observed)
    limit = _finite(limit)
    margin = limit - observed
    return {
        "requirement": label,
        "observed": observed,
        "limit": f"≤ {limit:g}{(' ' + unit) if unit else ''}",
        "margin": margin,
        "unit": unit,
        "status": "PASS" if margin >= 0 else "REVIEW",
    }


def _requirement_ge(label: str, observed: float, limit: float, unit: str = "") -> dict[str, Any]:
    observed = _finite(observed)
    limit = _finite(limit)
    margin = observed - limit
    return {
        "requirement": label,
        "observed": observed,
        "limit": f"≥ {limit:g}{(' ' + unit) if unit else ''}",
        "margin": margin,
        "unit": unit,
        "status": "PASS" if margin >= 0 else "REVIEW",
    }


def _requirement_band(label: str, observed: float, lower: float, upper: float) -> dict[str, Any]:
    observed = _finite(observed)
    lower = _finite(lower)
    upper = _finite(upper)
    margin = min(observed - lower, upper - observed)
    return {
        "requirement": label,
        "observed": observed,
        "limit": f"{lower:g}–{upper:g}",
        "margin": margin,
        "unit": "",
        "status": "PASS" if margin >= 0 else "REVIEW",
    }


def _status(requirements: list[Mapping[str, Any]]) -> str:
    return "PASS" if requirements and all(row.get("status") == "PASS" for row in requirements) else "REVIEW"


def quantum_engineering_review(
    result: Mapping[str, Any],
    *,
    max_energy_error_pct: float = 0.10,
    width_tolerance_pct: float = 1.0,
    max_tolerance_energy_shift_pct: float = 2.5,
    convergence_order_band: tuple[float, float] = (1.7, 2.3),
) -> dict[str, Any]:
    """Turn the infinite-well verification scene into a design-resolution review."""
    energies = list(result.get("energies") or [])
    if not energies:
        raise ValueError("quantum result has no energy levels")
    inputs = dict(result.get("inputs") or {})
    width_nm = _finite(inputs.get("well_width_nm"), 1.0)
    if width_nm <= 0:
        raise ValueError("well width must be positive")
    tol_pct = max(0.0, min(_finite(width_tolerance_pct), 49.0))
    tol_fraction = tol_pct / 100.0
    e1_exact = _finite(energies[0].get("exact_eV"))
    lower_width_factor = max(1e-9, 1.0 - tol_fraction)
    upper_width_factor = 1.0 + tol_fraction
    # Infinite-well scaling E ~ L^-2; this is a sensitivity estimate, not a process model.
    high_energy = e1_exact / (lower_width_factor**2)
    low_energy = e1_exact / (upper_width_factor**2)
    max_shift_pct = 0.0 if e1_exact == 0 else 100.0 * max(abs(high_energy - e1_exact), abs(low_energy - e1_exact)) / abs(e1_exact)
    numerical_error_pct = 100.0 * _finite(energies[0].get("relative_error"))
    order = _finite(result.get("observed_convergence_order"), float("nan"))
    if not math.isfinite(order):
        order = -1.0
    requirements = [
        _requirement_le("E1 numerical error", numerical_error_pct, max_energy_error_pct, "%"),
        _requirement_band("Observed grid convergence order", order, convergence_order_band[0], convergence_order_band[1]),
        _requirement_le("Energy sensitivity from ± width tolerance", max_shift_pct, max_tolerance_energy_shift_pct, "%"),
    ]
    status = _status(requirements)
    consequence = (
        "Resolution and geometric sensitivity are inside the current screening budget; this configuration is suitable for the next model-fidelity step."
        if status == "PASS" else
        "At least one screening requirement lacks margin. Increase numerical resolution, tighten dimensional tolerance, or change the confinement geometry before treating the energy prediction as design-ready."
    )
    return {
        "schema": "physical-lab-engineering-scenario-review-v1",
        "profile": "numerical-methods",
        "scenario": "quantum-confinement-design-verification",
        "screening_status": status,
        "design_variables": {
            "well_width_nm": width_nm,
            "grid_points": int(inputs.get("grid_points", 0) or 0),
            "width_tolerance_pct": tol_pct,
        },
        "responses": {
            "E1_exact_eV": e1_exact,
            "E1_numerical_error_pct": numerical_error_pct,
            "observed_convergence_order": order,
            "max_width_tolerance_energy_shift_pct": max_shift_pct,
            "E1_tolerance_envelope_eV": [low_energy, high_energy],
        },
        "requirements": requirements,
        "design_consequence": consequence,
        "boundary": (
            "Engineering screening built on the ideal 1D infinite-well model. Width sensitivity uses E∝L^-2 and does not represent fabrication statistics, interfaces, material band structure, temperature, defects or experimental calibration."
        ),
    }


def ising_engineering_review(
    result: Mapping[str, Any],
    *,
    operating_temperature: float = 2.0,
    minimum_abs_magnetization: float = 0.70,
    minimum_critical_distance: float = 0.20,
) -> dict[str, Any]:
    """Convert the Ising sweep into a bounded thermal-operating-window review."""
    rows = list(result.get("rows") or [])
    if not rows:
        raise ValueError("Ising result has no temperature rows")
    t_op = _finite(operating_temperature)
    min_order = max(0.0, min(_finite(minimum_abs_magnetization), 1.0))
    min_distance = max(0.0, _finite(minimum_critical_distance))
    nearest = min(rows, key=lambda row: abs(_finite(row.get("T_over_JkB")) - t_op))
    sampled_t = _finite(nearest.get("T_over_JkB"))
    order = _finite(nearest.get("abs_magnetization_per_spin"))
    tc = _finite(result.get("infinite_lattice_Tc_over_JkB"))
    critical_distance = abs(t_op - tc)
    retained = [
        _finite(row.get("T_over_JkB"))
        for row in rows
        if _finite(row.get("abs_magnetization_per_spin")) >= min_order
    ]
    retention_limit = max(retained) if retained else min(_finite(row.get("T_over_JkB")) for row in rows)
    thermal_margin = retention_limit - t_op
    requirements = [
        _requirement_ge("Magnetic order at nearest sampled operating point", order, min_order),
        _requirement_ge("Distance from infinite-lattice critical temperature", critical_distance, min_distance, "J/kB"),
        _requirement_ge("Order-retention thermal margin", thermal_margin, 0.0, "J/kB"),
    ]
    status = _status(requirements)
    consequence = (
        "The selected operating point retains the requested order parameter with positive scanned thermal margin and is separated from the critical reference."
        if status == "PASS" else
        "The operating point is too close to loss of order, too close to the critical region, or outside the scanned retention window. Move the operating point or change the model/material assumptions before proceeding."
    )
    return {
        "schema": "physical-lab-engineering-scenario-review-v1",
        "profile": "ising-monte-carlo",
        "scenario": "thermal-magnetic-operating-window-screening",
        "screening_status": status,
        "design_variables": {
            "operating_temperature_J_over_kB": t_op,
            "minimum_abs_magnetization": min_order,
            "minimum_critical_distance_J_over_kB": min_distance,
        },
        "responses": {
            "nearest_sample_temperature_J_over_kB": sampled_t,
            "abs_magnetization_at_nearest_sample": order,
            "critical_distance_J_over_kB": critical_distance,
            "order_retention_limit_J_over_kB": retention_limit,
            "thermal_margin_J_over_kB": thermal_margin,
        },
        "requirements": requirements,
        "design_consequence": consequence,
        "boundary": (
            "This is a dimensionless finite-size Ising screening model, not a calibrated real magnetic material model. It supports reasoning about operating-window robustness, not material selection, certification or hardware temperature limits."
        ),
    }


def transport_engineering_review(
    result: Mapping[str, Any],
    *,
    max_diffusion_error_pct: float = 5.0,
    max_drift_error_um_s: float = 0.05,
    characteristic_length_um: float = 10.0,
) -> dict[str, Any]:
    """Convert Brownian parameter recovery into transport-model qualification."""
    inputs = dict(result.get("inputs") or {})
    D = _finite(inputs.get("diffusion_um2_s"))
    drift = _finite(inputs.get("drift_x_um_s"))
    length = max(1e-9, _finite(characteristic_length_um, 10.0))
    diffusion_error_pct = 100.0 * _finite(result.get("diffusion_relative_error"))
    drift_error = _finite(result.get("drift_absolute_error_um_s"))
    peclet = abs(drift) * length / D if D > 0 else float("inf")
    diffusion_time = length * length / (4.0 * D) if D > 0 else float("inf")
    advection_time = length / abs(drift) if abs(drift) > 1e-15 else None
    requirements = [
        _requirement_le("Recovered diffusion-coefficient error", diffusion_error_pct, max_diffusion_error_pct, "%"),
        _requirement_le("Recovered drift absolute error", drift_error, max_drift_error_um_s, "µm/s"),
    ]
    status = _status(requirements)
    consequence = (
        "Transport parameters meet the current recovery tolerances, so the model is suitable for preliminary path-length and timing calculations within this idealized drift-diffusion boundary."
        if status == "PASS" else
        "Parameter recovery is outside the current error budget. Increase ensemble/time resolution or revisit the stochastic model before using it for transport sizing or timing decisions."
    )
    return {
        "schema": "physical-lab-engineering-scenario-review-v1",
        "profile": "random-walk-monte-carlo",
        "scenario": "stochastic-transport-model-qualification",
        "screening_status": status,
        "design_variables": {
            "characteristic_length_um": length,
            "max_diffusion_error_pct": max_diffusion_error_pct,
            "max_drift_error_um_s": max_drift_error_um_s,
        },
        "responses": {
            "peclet_number": peclet,
            "diffusion_time_scale_s": diffusion_time,
            "advection_time_scale_s": advection_time,
            "diffusion_error_pct": diffusion_error_pct,
            "drift_error_um_s": drift_error,
        },
        "requirements": requirements,
        "design_consequence": consequence,
        "boundary": (
            "Characteristic times and Pe use the ideal constant-D, constant-drift Brownian model. They do not include boundaries, flow profiles, reactions, particle interactions, non-Gaussian transport, device geometry or experimental calibration."
        ),
    }


def _render_requirement_table(st: Any, review: Mapping[str, Any]) -> None:
    rows = []
    for row in review.get("requirements", []):
        unit = str(row.get("unit") or "")
        observed = _finite(row.get("observed"))
        margin = _finite(row.get("margin"))
        rows.append({
            "Requirement": row.get("requirement"),
            "Observed": f"{observed:.6g}{(' ' + unit) if unit else ''}",
            "Limit": row.get("limit"),
            "Margin": f"{margin:.6g}{(' ' + unit) if unit else ''}",
            "Status": row.get("status"),
        })
    st.table(rows)


def _render_quantum_controls(st: Any, result: Mapping[str, Any]) -> dict[str, Any]:
    c1, c2, c3 = st.columns(3)
    max_error = c1.number_input("Max E1 numerical error (%)", min_value=0.001, max_value=10.0, value=0.10, step=0.01, key="pl_eng_quantum_max_error")
    width_tol = c2.number_input("Width tolerance (±%)", min_value=0.0, max_value=20.0, value=1.0, step=0.1, key="pl_eng_quantum_width_tol")
    max_shift = c3.number_input("Max energy shift from width tolerance (%)", min_value=0.01, max_value=50.0, value=2.5, step=0.1, key="pl_eng_quantum_max_shift")
    return quantum_engineering_review(
        result,
        max_energy_error_pct=float(max_error),
        width_tolerance_pct=float(width_tol),
        max_tolerance_energy_shift_pct=float(max_shift),
    )


def _render_ising_controls(st: Any, result: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(result.get("rows") or [])
    t_values = [_finite(row.get("T_over_JkB")) for row in rows]
    t_min = min(t_values); t_max = max(t_values)
    default_t = min(max(2.0, t_min), t_max)
    c1, c2, c3 = st.columns(3)
    t_op = c1.number_input("Operating T (J/kB)", min_value=float(t_min), max_value=float(t_max), value=float(default_t), step=0.05, key="pl_eng_ising_top")
    min_order = c2.number_input("Minimum |M| per spin", min_value=0.0, max_value=1.0, value=0.70, step=0.05, key="pl_eng_ising_min_order")
    min_distance = c3.number_input("Minimum distance from Tc (J/kB)", min_value=0.0, max_value=max(0.1, float(t_max - t_min)), value=min(0.20, max(0.1, float(t_max - t_min))), step=0.05, key="pl_eng_ising_min_tc_distance")
    return ising_engineering_review(
        result,
        operating_temperature=float(t_op),
        minimum_abs_magnetization=float(min_order),
        minimum_critical_distance=float(min_distance),
    )


def _render_transport_controls(st: Any, result: Mapping[str, Any]) -> dict[str, Any]:
    c1, c2, c3 = st.columns(3)
    max_D = c1.number_input("Max D recovery error (%)", min_value=0.1, max_value=50.0, value=5.0, step=0.5, key="pl_eng_transport_D_error")
    max_v = c2.number_input("Max drift recovery error (µm/s)", min_value=0.001, max_value=10.0, value=0.05, step=0.01, key="pl_eng_transport_v_error")
    length = c3.number_input("Characteristic path length (µm)", min_value=0.1, max_value=10000.0, value=10.0, step=1.0, key="pl_eng_transport_length")
    return transport_engineering_review(
        result,
        max_diffusion_error_pct=float(max_D),
        max_drift_error_um_s=float(max_v),
        characteristic_length_um=float(length),
    )


def render_engineering_scenario_review(st: Any, profile: str) -> None:
    """Render engineering decision context after a Physics Scenario result exists."""
    meta = SCENARIO_META.get(profile)
    if not meta:
        return
    if st.session_state.get(f"pl_application_mode_{profile}") != "Physics scenario":
        return
    result = st.session_state.get(meta["result_key"])
    if not result:
        return

    st.markdown("---")
    st.markdown(f"### {meta['title']}")
    st.caption(meta["objective"])
    st.caption("This keeps the same Physics Scenario but adds engineering requirements, signed margins and a design consequence. Thresholds below are editable screening targets, not standards or certification limits.")

    if profile == "numerical-methods":
        review = _render_quantum_controls(st, result)
        responses = review["responses"]
        a, b, c = st.columns(3)
        a.metric("Grid E1 error", f"{responses['E1_numerical_error_pct']:.5g}%")
        b.metric("Width-tolerance energy shift", f"{responses['max_width_tolerance_energy_shift_pct']:.5g}%")
        c.metric("Convergence order", f"{responses['observed_convergence_order']:.4g}")
    elif profile == "ising-monte-carlo":
        review = _render_ising_controls(st, result)
        responses = review["responses"]
        a, b, c = st.columns(3)
        a.metric("|M| at nearest operating sample", f"{responses['abs_magnetization_at_nearest_sample']:.4g}")
        b.metric("Thermal margin", f"{responses['thermal_margin_J_over_kB']:.4g} J/kB")
        c.metric("Distance from Tc", f"{responses['critical_distance_J_over_kB']:.4g} J/kB")
    else:
        review = _render_transport_controls(st, result)
        responses = review["responses"]
        a, b, c = st.columns(3)
        a.metric("Péclet number", f"{responses['peclet_number']:.5g}")
        b.metric("Diffusion time scale", f"{responses['diffusion_time_scale_s']:.5g} s")
        adv = responses.get("advection_time_scale_s")
        c.metric("Advection time scale", "∞" if adv is None else f"{adv:.5g} s")

    st.session_state[f"pl_engineering_scene_review_{profile}"] = review
    _render_requirement_table(st, review)
    if review["screening_status"] == "PASS":
        st.success(f"Engineering screening: PASS — {review['design_consequence']}")
    else:
        st.warning(f"Engineering screening: REVIEW — {review['design_consequence']}")
    st.caption(review["boundary"])
