"""Experiment/Compute workflow for Sun-Jupiter-Saturn orbital dynamics."""
from __future__ import annotations

import math
import os
import platform
import sys
from dataclasses import asdict, replace
from typing import Any, Callable, Mapping

import numpy as np

from physical_lab_experiment_kernel import (
    build_experiment_manifest,
    experiment_fingerprint,
    plain,
    validate_manifest,
)
from physical_lab_solar_system_dynamics import (
    MODEL_SCHEMA,
    MODEL_TITLE,
    MODEL_VARIANT,
    PROFILE,
    SolarSystemConfig,
    finite_time_lyapunov_indicator,
    integrate_case,
    result_summary,
    run_refinement_pair,
)

WORKFLOW_SCHEMA = "physical-lab-solar-system-workflow-v1"
CAMPAIGN_SCHEMA = "physical-lab-solar-system-verification-campaign-v1"

PRESETS = {
    "compact": {
        "duration_years": 20.0,
        "samples": 900,
        "ftle_years": 12.0,
        "ftle_segment_years": 2.0,
        "inclinations_deg": [0.0, 10.0, 20.0, 30.0],
        "sweep_duration_years": 8.0,
    },
    "standard": {
        "duration_years": 80.0,
        "samples": 2400,
        "ftle_years": 30.0,
        "ftle_segment_years": 2.5,
        "inclinations_deg": [0.0, 10.0, 20.0, 30.0],
        "sweep_duration_years": 25.0,
    },
}

DEFAULT_REQUIREMENTS = {
    "solver_refinement_max_relative": 2e-5,
    "barycenter_position_drift_AU": 1e-8,
    "absolute_linear_momentum_drift": 1e-10,
    "relative_energy_drift": 2e-8,
    "relative_angular_momentum_drift": 2e-8,
}


def _finite(value: Any, name: str) -> float:
    x = float(value)
    if not math.isfinite(x):
        raise ValueError(f"{name} must be finite")
    return x


def config_parameters(config: SolarSystemConfig) -> dict[str, Any]:
    config.validate()
    return plain(asdict(config))


def config_from_parameters(parameters: Mapping[str, Any]) -> SolarSystemConfig:
    return SolarSystemConfig(
        duration_years=_finite(parameters.get("duration_years", 80.0), "duration_years"),
        samples=int(parameters.get("samples", 2400)),
        inclination_jupiter_deg=_finite(parameters.get("inclination_jupiter_deg", 10.0), "inclination_jupiter_deg"),
        saturn_inclination_factor=_finite(parameters.get("saturn_inclination_factor", 0.25), "saturn_inclination_factor"),
        saturn_backreaction=bool(parameters.get("saturn_backreaction", True)),
        solar_1pn=bool(parameters.get("solar_1pn", False)),
        velocity_cross=bool(parameters.get("velocity_cross", False)),
        radial_drag=bool(parameters.get("radial_drag", False)),
        velocity_cross_strength=_finite(parameters.get("velocity_cross_strength", 1e-4), "velocity_cross_strength"),
        radial_drag_strength=_finite(parameters.get("radial_drag_strength", 1e-8), "radial_drag_strength"),
        omega_z_per_year=_finite(parameters.get("omega_z_per_year", 0.1), "omega_z_per_year"),
        rtol=_finite(parameters.get("rtol", 1e-10), "rtol"),
        atol=_finite(parameters.get("atol", 1e-12), "atol"),
        max_step_years=_finite(parameters.get("max_step_years", 0.03), "max_step_years"),
    )


def build_solar_system_manifest(
    config: SolarSystemConfig,
    *,
    preset: str = "compact",
    requirements: Mapping[str, float] | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    if preset not in PRESETS:
        raise ValueError(f"unsupported solar-system preset: {preset}")
    config.validate()
    req = dict(DEFAULT_REQUIREMENTS)
    if requirements:
        for key, value in requirements.items():
            if key in req:
                req[key] = _finite(value, key)

    requirement_rows = [
        {"metric": "solver_refinement_max_relative", "operator": "<=", "limit": req["solver_refinement_max_relative"]},
        {"metric": "barycenter_position_drift_AU", "operator": "<=", "limit": req["barycenter_position_drift_AU"], "unit": "AU"},
        {"metric": "absolute_linear_momentum_drift", "operator": "<=", "limit": req["absolute_linear_momentum_drift"], "unit": "M_sun AU/yr"},
        {"metric": "relative_energy_drift", "operator": "<=", "limit": req["relative_energy_drift"], "applies_when": "Newtonian baseline only"},
        {"metric": "relative_angular_momentum_drift", "operator": "<=", "limit": req["relative_angular_momentum_drift"], "applies_when": "Newtonian baseline only"},
    ]

    manifest = build_experiment_manifest(
        PROFILE,
        parameters=config_parameters(config),
        inputs={
            "system": "Sun-Jupiter-Saturn",
            "frame": "barycentric Cartesian",
            "units": {"length": "AU", "time": "yr", "mass": "M_sun", "G": "4*pi^2"},
            "legacy_source_mapping": {
                "ENABLE_DELAY": "not promoted to production solver; original mutable-history method is not a valid adaptive DDE integration",
                "ENABLE_RELATIVITY": "replaced by optional central-Sun 1PN approximation",
                "ENABLE_SPIN": "renamed phenomenological velocity-cross perturbation",
                "ENABLE_GW": "renamed phenomenological radial-drag perturbation",
            },
        },
        execution={
            "mode": "solar-system-verification-campaign",
            "preset": preset,
            "model_variant": MODEL_VARIANT,
        },
        requirements=requirement_rows,
        uncertainty={
            "mode": "deterministic-initial-condition-and-model-sensitivity",
            "probabilistic": False,
            "boundary": "Finite deterministic sweeps only; not a posterior, measurement uncertainty, or population distribution.",
        },
        provenance={
            "source_profile": PROFILE,
            "source_commit": source_commit or os.environ.get("PHYSICAL_LAB_SOURCE_COMMIT") or None,
            "engine_mode": os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "safe"),
            "solver_backend": "SciPy solve_ivp DOP853",
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "model_schema": MODEL_SCHEMA,
            "workflow_schema": WORKFLOW_SCHEMA,
        },
    )
    manifest["model"] = {
        "title": MODEL_TITLE,
        "domain": "celestial-mechanics-nonlinear-dynamics",
        "profile_title": "Nonlinear Dynamics & Chaos",
        "variant": MODEL_VARIANT,
        "adapter_capabilities": ["manifest", "model-campaign"],
        "physics_boundary": (
            "Baseline is barycentric Newtonian point-mass dynamics. Optional central-Sun 1PN is an approximation; "
            "legacy velocity-cross/radial-drag terms are phenomenological and are not physical spin/GW models."
        ),
    }
    manifest["experiment_sha256"] = experiment_fingerprint(manifest)
    check = validate_manifest(manifest)
    if not check["valid"]:
        raise ValueError("invalid solar-system manifest: " + "; ".join(check["errors"]))
    return manifest


def is_solar_system_manifest(manifest: Mapping[str, Any], runner_config: Mapping[str, Any] | None = None) -> bool:
    model = manifest.get("model") if isinstance(manifest.get("model"), Mapping) else {}
    execution = manifest.get("execution") if isinstance(manifest.get("execution"), Mapping) else {}
    candidates = {
        str(model.get("variant") or ""),
        str(execution.get("model_variant") or ""),
        str((runner_config or {}).get("model_variant") or ""),
    }
    return MODEL_VARIANT in candidates


def _bounded_config(config: SolarSystemConfig, preset: str) -> SolarSystemConfig:
    p = PRESETS[preset]
    return replace(
        config,
        duration_years=min(float(config.duration_years), float(p["duration_years"])),
        samples=min(int(config.samples), int(p["samples"])),
        rtol=min(float(config.rtol), 1e-10),
        atol=min(float(config.atol), 1e-12),
        max_step_years=min(float(config.max_step_years), 0.03),
    )


def _safe_relative_delta(a: float, b: float) -> float:
    return abs(float(a) - float(b)) / max(1.0, abs(float(b)))


def _inclination_sweep(config: SolarSystemConfig, preset: str) -> list[dict[str, Any]]:
    p = PRESETS[preset]
    rows = []
    for inc in p["inclinations_deg"]:
        variant = replace(
            config,
            inclination_jupiter_deg=float(inc),
            duration_years=min(float(config.duration_years), float(p["sweep_duration_years"])),
            samples=min(int(config.samples), 700 if preset == "compact" else 1200),
        )
        summary = result_summary(integrate_case(variant))
        rows.append({"inclination_jupiter_deg": float(inc), **plain(summary)})
    return rows


def _model_effect_audit(config: SolarSystemConfig, preset: str) -> list[dict[str, Any]]:
    p = PRESETS[preset]
    base_kwargs = dict(
        duration_years=min(float(config.duration_years), 8.0 if preset == "compact" else 20.0),
        samples=min(int(config.samples), 600 if preset == "compact" else 1000),
    )
    variants = [
        ("newtonian-baseline", replace(config, **base_kwargs, solar_1pn=False, velocity_cross=False, radial_drag=False)),
        ("central-sun-1pn", replace(config, **base_kwargs, solar_1pn=True, velocity_cross=False, radial_drag=False)),
        ("legacy-velocity-cross", replace(config, **base_kwargs, solar_1pn=False, velocity_cross=True, radial_drag=False)),
        ("legacy-radial-drag", replace(config, **base_kwargs, solar_1pn=False, velocity_cross=False, radial_drag=True)),
    ]
    rows = []
    baseline = None
    for label, variant in variants:
        summary = result_summary(integrate_case(variant))
        if baseline is None:
            baseline = summary
        rows.append({
            "case": label,
            "summary": plain(summary),
            "delta_final_period_ratio_vs_newtonian": 0.0 if baseline is summary else _safe_relative_delta(summary["final_period_ratio"], baseline["final_period_ratio"]),
            "delta_jupiter_a_vs_newtonian": 0.0 if baseline is summary else _safe_relative_delta(summary["jupiter_final_a_AU"], baseline["jupiter_final_a_AU"]),
        })
    return rows


def evaluate_requirements(metrics: Mapping[str, Any], requirements: Mapping[str, float], *, invariants_expected: bool) -> dict[str, Any]:
    rows = []
    overall = "PASS"
    for metric in (
        "solver_refinement_max_relative",
        "barycenter_position_drift_AU",
        "absolute_linear_momentum_drift",
        "relative_energy_drift",
        "relative_angular_momentum_drift",
    ):
        observed = float(metrics[metric])
        limit = float(requirements[metric])
        applicable = invariants_expected or metric not in {"relative_energy_drift", "relative_angular_momentum_drift"}
        if not applicable:
            status = "N/A"
            margin = None
        else:
            margin = limit - observed
            status = "PASS" if margin >= 0 else "REVIEW"
            if status == "REVIEW":
                overall = "REVIEW"
        rows.append({
            "metric": metric,
            "observed": observed,
            "limit": limit,
            "signed_margin": margin,
            "status": status,
        })
    return {
        "status": overall,
        "requirements": rows,
        "boundary": "Computational screening only; PASS is not experimental validation or certification.",
    }


def execute_solar_system_manifest(
    manifest: Mapping[str, Any],
    *,
    runner_config: Mapping[str, Any] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[str, float, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if not is_solar_system_manifest(manifest, runner_config):
        raise ValueError("manifest is not a Sun-Jupiter-Saturn workflow")
    check = validate_manifest(manifest)
    if not check["valid"]:
        raise ValueError("invalid experiment manifest: " + "; ".join(check["errors"]))
    preset = str((runner_config or {}).get("preset") or (manifest.get("execution") or {}).get("preset") or "compact")
    if preset not in PRESETS:
        raise ValueError("solar-system preset must be compact or standard")
    config = _bounded_config(config_from_parameters(manifest.get("parameters") or {}), preset)

    def checkpoint(stage: str, progress: float, payload: Mapping[str, Any] | None = None) -> None:
        if cancel_check and cancel_check():
            raise InterruptedError("solar-system campaign cancelled")
        if progress_callback:
            progress_callback(stage, progress, payload or {})

    checkpoint("base-run", 0.10, {"preset": preset})
    base_result = integrate_case(config)
    base_summary = result_summary(base_result)

    checkpoint("refinement", 0.34, {})
    refinement = run_refinement_pair(config)

    checkpoint("finite-time-divergence", 0.55, {})
    p = PRESETS[preset]
    ftle = finite_time_lyapunov_indicator(
        config,
        segment_years=float(p["ftle_segment_years"]),
        max_years=float(p["ftle_years"]),
    )

    checkpoint("inclination-sweep", 0.70, {})
    inclination_rows = _inclination_sweep(config, preset)

    checkpoint("model-effect-audit", 0.84, {})
    effect_rows = _model_effect_audit(config, preset)

    req = dict(DEFAULT_REQUIREMENTS)
    for row in manifest.get("requirements") or []:
        if isinstance(row, Mapping) and row.get("metric") in req:
            req[str(row["metric"])] = float(row["limit"])
    metrics = {
        "solver_refinement_max_relative": float(refinement["max_relative_change"]),
        "barycenter_position_drift_AU": float(base_summary["barycenter_position_drift_AU"]),
        "absolute_linear_momentum_drift": float(base_summary["absolute_linear_momentum_drift"]),
        "relative_energy_drift": float(base_summary["relative_energy_drift"]),
        "relative_angular_momentum_drift": float(base_summary["relative_angular_momentum_drift"]),
        "finite_time_divergence_rate_per_year": float(ftle["finite_time_rate_per_year"]),
        "minimum_jupiter_saturn_separation_AU": float(base_summary["minimum_separation_AU"]),
        "final_period_ratio": float(base_summary["final_period_ratio"]),
        "final_5_2_resonance_deviation": float(base_summary["final_resonance_deviation_5_2"]),
    }
    screening = evaluate_requirements(metrics, req, invariants_expected=bool(base_summary["invariants_expected"]))
    checkpoint("screening", 0.94, {"status": screening["status"]})

    return {
        "schema": CAMPAIGN_SCHEMA,
        "model_variant": MODEL_VARIANT,
        "experiment_sha256": manifest.get("experiment_sha256"),
        "preset": preset,
        "base_summary": plain(base_summary),
        "refinement": plain(refinement),
        "finite_time_divergence": plain(ftle),
        "inclination_sweep": plain(inclination_rows),
        "model_effect_audit": plain(effect_rows),
        "metrics": plain(metrics),
        "screening": plain(screening),
        "scientific_boundary": (
            "Baseline is Newtonian barycentric point-mass dynamics. Central-Sun 1PN is approximate; "
            "velocity-cross/radial-drag are phenomenological legacy perturbations. Finite-time divergence is not proof of chaos."
        ),
    }


def render_report_markdown(manifest: Mapping[str, Any], campaign: Mapping[str, Any]) -> str:
    metrics = campaign.get("metrics") or {}
    screening = campaign.get("screening") or {}
    params = manifest.get("parameters") or {}
    lines = [
        f"# Physical Lab · {MODEL_TITLE} Report",
        "",
        f"- Experiment SHA-256: `{manifest.get('experiment_sha256')}`",
        f"- Model variant: `{MODEL_VARIANT}`",
        f"- Campaign preset: `{campaign.get('preset')}`",
        f"- Screening: **{screening.get('status', 'REVIEW')}**",
        "",
        "## Scientific configuration",
        "",
    ]
    for key, value in sorted(params.items()):
        lines.append(f"- `{key}`: {value}")
    lines += ["", "## Verification metrics", "", "| Metric | Value |", "|---|---:|"]
    for key, value in metrics.items():
        if isinstance(value, (int, float)):
            lines.append(f"| {key} | {float(value):.8g} |")
    lines += ["", "## Requirement screening", "", "| Metric | Observed | Limit | Margin | Status |", "|---|---:|---:|---:|---|"]
    for row in screening.get("requirements") or []:
        margin = "N/A" if row.get("signed_margin") is None else f"{float(row['signed_margin']):.6g}"
        lines.append(
            f"| {row.get('metric')} | {float(row.get('observed', float('nan'))):.6g} | {float(row.get('limit', float('nan'))):.6g} | {margin} | {row.get('status')} |"
        )
    lines += [
        "",
        "## Interpretation boundary",
        "",
        str(campaign.get("scientific_boundary") or ""),
        "",
        "The original standalone delay implementation is not promoted as a physical retarded-gravity solver because adaptive ODE internal/rejected steps cannot safely define a mutable deque history. The former spin and GW terms are retained only as explicitly phenomenological perturbation comparisons.",
        "",
        "PASS/REVIEW is a computational screening result, not experimental validation, astronomical inference, or certification.",
        "",
    ]
    return "\n".join(lines)
