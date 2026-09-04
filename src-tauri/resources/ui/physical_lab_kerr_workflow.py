"""Kerr experiment/workflow adapter for Physical Lab.

This module sits above ``physical_lab_kerr_geodesics``.  It turns an interactive
Kerr configuration into an Experiment Kernel manifest and provides the bounded
worker-native verification campaign used by the persistent Compute Engine.

Scientific boundaries:
- Standard unperturbed Kerr geodesics are treated as integrable benchmarks.
- All solver inputs remain dimensionless geometric units (G=c=M=1).
- Optional solar-mass scaling is presentation/provenance only; it does not alter
  the dimensionless trajectory.
- The tolerance envelope is deterministic local sensitivity evidence, not a
  probability distribution or experimental uncertainty model.
"""
from __future__ import annotations

import math
import os
import platform
import sys
from dataclasses import asdict
from typing import Any, Callable, Mapping

import numpy as np

from physical_lab_experiment_kernel import (
    build_experiment_manifest,
    experiment_fingerprint,
    plain,
    validate_manifest,
)
from physical_lab_kerr_geodesics import (
    MASS,
    MODEL_SCHEMA,
    PROFILE,
    KerrOrbitConfig,
    horizon_radius,
    integrate_case,
    radial_potential,
    radial_potential_dr,
    result_summary,
    run_refinement_pair,
    theta_potential,
)

WORKFLOW_SCHEMA = "physical-lab-kerr-workflow-v1"
CAMPAIGN_SCHEMA = "physical-lab-kerr-verification-campaign-v1"
MODEL_VARIANT = "kerr-geodesic"
MODEL_TITLE = "Kerr Geodesic Dynamics"

# SI values are used only for optional scale labels.
G_SI = 6.67430e-11
C_SI = 299_792_458.0
SOLAR_MASS_KG = 1.98847e30

DEFAULT_REQUIREMENTS = {
    "first_integral_residual_max": 1e-6,
    "constraint_residual_max": 1e-8,
    "refinement_relative_change_max": 5e-4,
    "minimum_horizon_margin_M": 0.10,
}

PRESETS = {
    "compact": {
        "lam_massive": 5.0,
        "lam_photon": 1.2,
        "samples_massive": 700,
        "samples_photon": 500,
        "sensitivity_fraction": 0.01,
        "inclination_delta_deg": 1.0,
        "spin_sweep": [0.0, 0.3, 0.6, 0.9],
    },
    "standard": {
        "lam_massive": 9.0,
        "lam_photon": 2.2,
        "samples_massive": 1200,
        "samples_photon": 800,
        "sensitivity_fraction": 0.02,
        "inclination_delta_deg": 2.0,
        "spin_sweep": [0.0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9, 0.96],
    },
}


def _finite(value: Any, name: str = "value") -> float:
    x = float(value)
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite")
    return x


def geometric_scale(solar_masses: float) -> dict[str, float]:
    """Return physical scales for one geometric M, without changing the solver."""
    m_solar = _finite(solar_masses, "solar_masses")
    if m_solar <= 0:
        raise ValueError("solar_masses must be positive")
    mass_kg = m_solar * SOLAR_MASS_KG
    length_m = G_SI * mass_kg / (C_SI * C_SI)
    time_s = G_SI * mass_kg / (C_SI ** 3)
    return {
        "solar_masses": m_solar,
        "mass_kg": mass_kg,
        "one_M_length_m": length_m,
        "one_M_time_s": time_s,
        "one_M_length_km": length_m / 1000.0,
        "one_M_time_us": time_s * 1e6,
    }


def config_parameters(config: KerrOrbitConfig) -> dict[str, Any]:
    config.validate()
    return {
        "spin_a_over_M": float(config.spin),
        "inclination_deg": float(config.inclination_deg),
        "particle_type": str(config.particle_type),
        "periapsis_r_over_M": float(config.periapsis),
        "apoapsis_r_over_M": float(config.apoapsis),
        "mino_time_span": float(config.lam_max),
        "samples": int(config.samples),
        "rtol": float(config.rtol),
        "atol": float(config.atol),
        "horizon_guard_M": float(config.horizon_pad),
    }


def config_from_parameters(parameters: Mapping[str, Any]) -> KerrOrbitConfig:
    particle = str(parameters.get("particle_type") or "massive")
    return KerrOrbitConfig(
        spin=_finite(parameters.get("spin_a_over_M", 0.6), "spin"),
        inclination_deg=_finite(parameters.get("inclination_deg", 60.0), "inclination"),
        particle_type=particle,
        periapsis=_finite(parameters.get("periapsis_r_over_M", 6.5), "periapsis"),
        apoapsis=_finite(parameters.get("apoapsis_r_over_M", 10.0), "apoapsis"),
        lam_max=_finite(parameters.get("mino_time_span", 6.0), "mino_time_span"),
        samples=int(parameters.get("samples", 900)),
        rtol=_finite(parameters.get("rtol", 1e-9), "rtol"),
        atol=_finite(parameters.get("atol", 1e-11), "atol"),
        horizon_pad=_finite(parameters.get("horizon_guard_M", 0.05), "horizon_guard_M"),
    )


def build_kerr_manifest(
    config: KerrOrbitConfig,
    *,
    preset: str = "compact",
    solar_masses: float | None = None,
    requirements: Mapping[str, float] | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    if preset not in PRESETS:
        raise ValueError(f"unsupported Kerr preset: {preset}")
    config.validate()
    req = dict(DEFAULT_REQUIREMENTS)
    if requirements:
        for key, value in requirements.items():
            if key in req:
                req[key] = _finite(value, key)
    req_rows = [
        {"metric": "first_integral_residual_max", "operator": "<=", "limit": req["first_integral_residual_max"]},
        {"metric": "constraint_residual_max", "operator": "<=", "limit": req["constraint_residual_max"]},
        {"metric": "refinement_relative_change_max", "operator": "<=", "limit": req["refinement_relative_change_max"]},
        {"metric": "minimum_horizon_margin_M", "operator": ">=", "limit": req["minimum_horizon_margin_M"], "unit": "M"},
    ]
    scale = geometric_scale(solar_masses) if solar_masses is not None else None
    manifest = build_experiment_manifest(
        PROFILE,
        parameters=config_parameters(config),
        inputs={
            "coordinate_system": "Boyer-Lindquist",
            "units": "geometric G=c=M=1",
            "physical_scale": scale,
        },
        execution={
            "mode": "kerr-verification-campaign",
            "preset": preset,
            "model_variant": MODEL_VARIANT,
        },
        requirements=req_rows,
        uncertainty={
            "mode": "deterministic-local-tolerance-envelope",
            "probabilistic": False,
            "boundary": "Local sensitivity only; not a population distribution or measurement uncertainty model.",
        },
        provenance={
            "source_profile": PROFILE,
            "source_commit": source_commit or os.environ.get("PHYSICAL_LAB_SOURCE_COMMIT") or None,
            "engine_mode": os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "safe"),
            "solver_backend": "SciPy solve_ivp RK45 + Carter-Mino first integrals",
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "model_schema": MODEL_SCHEMA,
            "workflow_schema": WORKFLOW_SCHEMA,
        },
    )
    manifest["model"] = {
        "title": MODEL_TITLE,
        "domain": "general-relativity-geodesic-dynamics",
        "profile_title": "Nonlinear Dynamics & Chaos",
        "variant": MODEL_VARIANT,
        "adapter_capabilities": ["manifest", "model-campaign"],
        "integrability_boundary": (
            "Standard unperturbed Kerr geodesics are integrable; stability and "
            "Poincare diagnostics are not generic chaos claims."
        ),
    }
    manifest["experiment_sha256"] = experiment_fingerprint(manifest)
    check = validate_manifest(manifest)
    if not check["valid"]:
        raise ValueError("invalid Kerr experiment manifest: " + "; ".join(check["errors"]))
    return manifest


def is_kerr_manifest(manifest: Mapping[str, Any], runner_config: Mapping[str, Any] | None = None) -> bool:
    model = manifest.get("model")
    model_variant = model.get("variant") if isinstance(model, Mapping) else None
    config_variant = (runner_config or {}).get("model_variant")
    execution = manifest.get("execution")
    execution_variant = execution.get("model_variant") if isinstance(execution, Mapping) else None
    return MODEL_VARIANT in {str(model_variant or ""), str(config_variant or ""), str(execution_variant or "")}


def _constraint_residual(result: Mapping[str, Any], config: KerrOrbitConfig) -> dict[str, float]:
    case = result["case"]
    a = float(case["a"])
    e = float(case["E"])
    lz = float(case["Lz"])
    q = float(case["Q"])
    mu = float(case["mu"])
    theta_min = float(case["theta_min"])

    def normalized_r(r: float) -> float:
        raw = abs(float(radial_potential(r, a, e, lz, q, mu)))
        return raw / max(1.0, abs(r) ** 4)

    theta_raw = abs(float(theta_potential(theta_min, a, e, lz, q, mu)))
    theta_norm = theta_raw / max(1.0, abs(q) + abs(lz) ** 2 + a * a + 1.0)

    if case["particle_type"] == "massive":
        rp = float(config.periapsis)
        ra = float(config.apoapsis)
        rows = {
            "radial_periapsis": normalized_r(rp),
            "radial_apoapsis": normalized_r(ra),
            "polar_turning": theta_norm,
        }
    else:
        r0 = float(case["r0"])
        dr_raw = abs(float(radial_potential_dr(r0, a, e, lz, q, mu)))
        rows = {
            "radial_spherical": normalized_r(r0),
            "radial_derivative_spherical": dr_raw / max(1.0, abs(r0) ** 3),
            "polar_turning": theta_norm,
        }
    rows["combined_max"] = max(float(v) for v in rows.values())
    return rows


def _refinement_relative_change(refinement: Mapping[str, Any]) -> float:
    tight = refinement["tight"]
    deltas = refinement["absolute_deltas"]
    values = []
    for key, delta in deltas.items():
        scale = max(1.0, abs(float(tight[key])))
        values.append(abs(float(delta)) / scale)
    return max(values) if values else 0.0


def _bounded_config(config: KerrOrbitConfig, preset: str) -> KerrOrbitConfig:
    p = PRESETS[preset]
    is_photon = config.particle_type == "photon"
    return KerrOrbitConfig(
        spin=config.spin,
        inclination_deg=config.inclination_deg,
        particle_type=config.particle_type,
        periapsis=config.periapsis,
        apoapsis=config.apoapsis,
        lam_max=min(
            float(config.lam_max),
            float(p["lam_photon"] if is_photon else p["lam_massive"]),
        ),
        samples=min(
            int(config.samples),
            int(p["samples_photon"] if is_photon else p["samples_massive"]),
        ),
        rtol=min(float(config.rtol), 1e-9),
        atol=min(float(config.atol), 1e-11),
        horizon_pad=config.horizon_pad,
    )


def _perturbations(config: KerrOrbitConfig, preset: str) -> list[tuple[str, KerrOrbitConfig]]:
    p = PRESETS[preset]
    frac = float(p["sensitivity_fraction"])
    inc_delta = float(p["inclination_delta_deg"])
    rows: list[tuple[str, KerrOrbitConfig]] = []

    spins = [
        ("spin-low", max(0.0, float(config.spin) - frac)),
        ("spin-high", min(0.98, float(config.spin) + frac)),
    ]
    for label, spin in spins:
        rows.append((label, KerrOrbitConfig(**{**asdict(config), "spin": spin})))

    for label, incl in (
        ("inclination-low", max(0.0, float(config.inclination_deg) - inc_delta)),
        ("inclination-high", min(85.0, float(config.inclination_deg) + inc_delta)),
    ):
        rows.append((label, KerrOrbitConfig(**{**asdict(config), "inclination_deg": incl})))

    if config.particle_type == "massive":
        rp_delta = max(0.02, abs(float(config.periapsis)) * frac)
        ra_delta = max(0.02, abs(float(config.apoapsis)) * frac)
        candidates = [
            ("periapsis-low", max(horizon_radius(config.spin) + config.horizon_pad + 0.02, config.periapsis - rp_delta), config.apoapsis),
            ("periapsis-high", config.periapsis + rp_delta, config.apoapsis),
            ("apoapsis-low", config.periapsis, max(config.periapsis + 0.05, config.apoapsis - ra_delta)),
            ("apoapsis-high", config.periapsis, config.apoapsis + ra_delta),
        ]
        for label, rp, ra in candidates:
            rows.append((label, KerrOrbitConfig(**{**asdict(config), "periapsis": rp, "apoapsis": ra})))
    return rows


def _summary_scalar_view(summary: Mapping[str, Any]) -> dict[str, float | str]:
    keys = (
        "particle_type", "spin", "inclination_deg", "E", "Lz", "Q",
        "first_integral_residual_max", "r_min", "r_max",
        "radial_period_mino", "polar_period_mino", "mean_phi_rate_mino",
        "photon_radial_instability_mino",
        "photon_radial_instability_coordinate_time",
    )
    return {key: plain(summary.get(key)) for key in keys if key in summary}


def _sensitivity_rows(
    config: KerrOrbitConfig,
    preset: str,
    base_summary: Mapping[str, Any],
    *,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, float, Mapping[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    variants = _perturbations(config, preset)
    for index, (label, variant) in enumerate(variants):
        if cancel_check and cancel_check():
            raise InterruptedError("Kerr verification campaign cancelled")
        result = integrate_case(_bounded_config(variant, preset))
        summary = result_summary(result)
        comparison: dict[str, float] = {}
        for key in ("r_min", "r_max", "mean_phi_rate_mino"):
            base = float(base_summary[key])
            observed = float(summary[key])
            comparison[f"{key}_relative_change"] = abs(observed - base) / max(1.0, abs(base))
        if config.particle_type == "photon":
            base_gamma = float(base_summary["photon_radial_instability_mino"])
            gamma = float(summary["photon_radial_instability_mino"])
            comparison["photon_instability_relative_change"] = abs(gamma - base_gamma) / max(1.0, abs(base_gamma))
        rows.append({
            "label": label,
            "parameters": config_parameters(variant),
            "summary": _summary_scalar_view(summary),
            "relative_changes": comparison,
        })
        if progress_callback:
            progress_callback(
                "sensitivity",
                0.50 + 0.25 * (index + 1) / max(len(variants), 1),
                {"case": label},
            )
    return rows


def _spin_sweep(
    base: KerrOrbitConfig,
    preset: str,
    *,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, float, Mapping[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    spins = [float(v) for v in PRESETS[preset]["spin_sweep"]]
    rows: list[dict[str, Any]] = []
    # Use a shorter path for the cross-spin characterization so the campaign is bounded.
    for index, spin in enumerate(spins):
        if cancel_check and cancel_check():
            raise InterruptedError("Kerr verification campaign cancelled")
        variant = KerrOrbitConfig(
            spin=spin,
            inclination_deg=base.inclination_deg,
            particle_type=base.particle_type,
            periapsis=base.periapsis,
            apoapsis=base.apoapsis,
            lam_max=min(_bounded_config(base, preset).lam_max, 2.5 if base.particle_type == "massive" else 0.8),
            samples=min(_bounded_config(base, preset).samples, 450 if base.particle_type == "massive" else 320),
            rtol=1e-9,
            atol=1e-11,
            horizon_pad=base.horizon_pad,
        )
        result = integrate_case(variant)
        summary = result_summary(result)
        rows.append(_summary_scalar_view(summary))
        if progress_callback:
            progress_callback(
                "spin-sweep",
                0.76 + 0.19 * (index + 1) / max(len(spins), 1),
                {"spin": spin},
            )
    return rows


def _requirements_from_manifest(manifest: Mapping[str, Any]) -> dict[str, float]:
    req = dict(DEFAULT_REQUIREMENTS)
    for row in manifest.get("requirements") or []:
        if not isinstance(row, Mapping):
            continue
        metric = str(row.get("metric") or "")
        if metric in req and row.get("limit") is not None:
            req[metric] = _finite(row["limit"], metric)
    return req


def evaluate_requirements(metrics: Mapping[str, float], requirements: Mapping[str, float]) -> dict[str, Any]:
    checks = [
        ("first_integral_residual_max", "<=", metrics["first_integral_residual_max"], requirements["first_integral_residual_max"]),
        ("constraint_residual_max", "<=", metrics["constraint_residual_max"], requirements["constraint_residual_max"]),
        ("refinement_relative_change_max", "<=", metrics["refinement_relative_change_max"], requirements["refinement_relative_change_max"]),
        ("minimum_horizon_margin_M", ">=", metrics["minimum_horizon_margin_M"], requirements["minimum_horizon_margin_M"]),
    ]
    rows = []
    for metric, operator, observed, limit in checks:
        if operator == "<=":
            passed = observed <= limit
            margin = limit - observed
        else:
            passed = observed >= limit
            margin = observed - limit
        rows.append({
            "metric": metric,
            "operator": operator,
            "observed": float(observed),
            "limit": float(limit),
            "signed_margin": float(margin),
            "status": "PASS" if passed else "REVIEW",
        })
    return {
        "status": "PASS" if all(row["status"] == "PASS" for row in rows) else "REVIEW",
        "checks": rows,
        "boundary": "Computational screening only; PASS is not experimental validation or certification.",
    }


def run_kerr_verification_campaign(
    config: KerrOrbitConfig,
    *,
    preset: str = "compact",
    requirements: Mapping[str, float] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, float, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if preset not in PRESETS:
        raise ValueError(f"unsupported Kerr preset: {preset}")
    bounded = _bounded_config(config, preset)
    bounded.validate()
    req = dict(DEFAULT_REQUIREMENTS)
    if requirements:
        req.update({k: _finite(v, k) for k, v in requirements.items() if k in req})

    def progress(stage: str, value: float, payload: Mapping[str, Any] | None = None) -> None:
        if progress_callback:
            progress_callback(stage, float(value), dict(payload or {}))

    if cancel_check and cancel_check():
        raise InterruptedError("Kerr verification campaign cancelled")
    progress("base-run", 0.10, {"particle_type": bounded.particle_type})
    base_result = integrate_case(bounded)
    base_summary = result_summary(base_result)
    constraints = _constraint_residual(base_result, bounded)

    if cancel_check and cancel_check():
        raise InterruptedError("Kerr verification campaign cancelled")
    progress("refinement", 0.32, {})
    refinement = run_refinement_pair(bounded)
    refinement_relative = _refinement_relative_change(refinement)

    progress("sensitivity", 0.50, {})
    sensitivity = _sensitivity_rows(
        bounded,
        preset,
        base_summary,
        cancel_check=cancel_check,
        progress_callback=progress_callback,
    )
    sensitivity_max = 0.0
    for row in sensitivity:
        for value in (row.get("relative_changes") or {}).values():
            sensitivity_max = max(sensitivity_max, float(value))

    progress("spin-sweep", 0.76, {})
    spin_sweep = _spin_sweep(
        bounded,
        preset,
        cancel_check=cancel_check,
        progress_callback=progress_callback,
    )

    horizon_margin = float(base_summary["r_min"]) - horizon_radius(float(base_summary["spin"]))
    metrics = {
        "first_integral_residual_max": float(base_summary["first_integral_residual_max"]),
        "constraint_residual_max": float(constraints["combined_max"]),
        "refinement_relative_change_max": float(refinement_relative),
        "minimum_horizon_margin_M": float(horizon_margin),
        "local_tolerance_response_max": float(sensitivity_max),
    }
    screening = evaluate_requirements(metrics, req)
    progress("complete", 1.0, {"status": screening["status"]})

    return {
        "schema": CAMPAIGN_SCHEMA,
        "profile": PROFILE,
        "model_variant": MODEL_VARIANT,
        "model_title": MODEL_TITLE,
        "preset": preset,
        "config": config_parameters(bounded),
        "kerr_metrics": metrics,
        "constraint_residuals": constraints,
        "screening": screening,
        "base_summary": _summary_scalar_view(base_summary),
        "refinement": plain(refinement),
        "sensitivity_cases": plain(sensitivity),
        "spin_sweep": plain(spin_sweep),
        "notes": [
            "Standard unperturbed Kerr geodesics are integrable; this campaign is a relativistic-dynamics verification workflow, not a generic chaos demonstration.",
            "First-integral and turning-condition residuals are numerical consistency checks.",
            "Refinement compares stable observables rather than demanding pointwise long-time trajectory identity.",
            "Sensitivity cases form a deterministic local tolerance envelope; they are not a probability distribution.",
            "Optional physical mass scaling is display/provenance only and does not alter the G=c=M=1 solver.",
        ],
        "boundary": (
            "Simulation verification and deterministic sensitivity screening only; "
            "not experimental validation, astrophysical parameter inference, or certification."
        ),
    }


def execute_kerr_manifest(
    manifest: Mapping[str, Any],
    *,
    preset: str | None = None,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, float, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    check = validate_manifest(manifest)
    if not check["valid"]:
        raise ValueError("invalid experiment manifest: " + "; ".join(check["errors"]))
    if not is_kerr_manifest(manifest):
        raise ValueError("manifest is not a Kerr geodesic experiment")
    config = config_from_parameters(manifest.get("parameters") or {})
    execution = manifest.get("execution") if isinstance(manifest.get("execution"), Mapping) else {}
    selected_preset = str(preset or execution.get("preset") or "compact")
    req = _requirements_from_manifest(manifest)
    return run_kerr_verification_campaign(
        config,
        preset=selected_preset,
        requirements=req,
        cancel_check=cancel_check,
        progress_callback=progress_callback,
    )


def render_kerr_report_markdown(
    manifest: Mapping[str, Any],
    campaign: Mapping[str, Any],
) -> str:
    screening = campaign.get("screening") or {}
    metrics = campaign.get("kerr_metrics") or {}
    base = campaign.get("base_summary") or {}
    lines = [
        f"# Physical Lab · {MODEL_TITLE}",
        "",
        f"- Experiment fingerprint: `{manifest.get('experiment_sha256') or ''}`",
        f"- Campaign schema: `{campaign.get('schema') or ''}`",
        f"- Preset: `{campaign.get('preset') or ''}`",
        f"- Screening status: **{screening.get('status') or 'REVIEW'}**",
        "",
        "## Scientific question",
        "",
        "How do Kerr spin, orbital geometry and numerical controls change the verified geodesic observables while preserving the Carter first-integral structure?",
        "",
        "## Model and assumptions",
        "",
        "- Boyer–Lindquist coordinates.",
        "- Geometric units `G=c=M=1` in the numerical solver.",
        "- Bound timelike geodesic or spherical null geodesic.",
        "- Carter–Mino separated first integrals.",
        "- Standard unperturbed Kerr geodesics are integrable; stability diagnostics are not generic chaos evidence.",
        "",
        "## Base result",
        "",
    ]
    for key in ("particle_type", "spin", "inclination_deg", "E", "Lz", "Q", "r_min", "r_max"):
        if key in base:
            lines.append(f"- {key}: `{base[key]}`")
    lines += [
        "",
        "## Verification metrics",
        "",
        "| Metric | Observed |",
        "|---|---:|",
    ]
    for key, value in metrics.items():
        lines.append(f"| {key} | {value:.6g} |")
    lines += [
        "",
        "## Requirement screening",
        "",
        "| Metric | Requirement | Observed | Signed margin | Status |",
        "|---|---:|---:|---:|---|",
    ]
    for row in screening.get("checks") or []:
        lines.append(
            f"| {row.get('metric')} | {row.get('operator')} {float(row.get('limit', 0)):.6g} "
            f"| {float(row.get('observed', 0)):.6g} | {float(row.get('signed_margin', 0)):.6g} "
            f"| {row.get('status')} |"
        )
    lines += [
        "",
        "## V&V / UQ boundary",
        "",
        str(campaign.get("boundary") or ""),
        "",
        "The deterministic tolerance envelope is sensitivity evidence, not a measurement-derived uncertainty distribution. "
        "A PASS means the configured computational screening criteria were met; it is not experimental validation or astrophysical parameter inference.",
        "",
    ]
    return "\n".join(lines)
