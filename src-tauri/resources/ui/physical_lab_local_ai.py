"""Read-only Local AI assistant bridge for Physical Lab.

Scientific solvers and measured datasets remain authoritative. This module sends
only a bounded structured snapshot of current Physical Lab state to a local
Ollama-compatible model and returns explanatory text.

Supported loopback runtimes:
- OpenPenguin private runtime: 127.0.0.1:11435
- existing/external Ollama:   127.0.0.1:11434

The bridge does not download models, execute model-provided code, change physics
parameters, or contact a cloud endpoint. Vision input is optional and is sent
only to a model that explicitly reports a local ``vision`` capability.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOCAL_ENGINES = {
    "OpenPenguin private runtime": "http://127.0.0.1:11435",
    "External Ollama": "http://127.0.0.1:11434",
}
MAX_CONTEXT_BYTES = 96 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_VISION_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VISION_IMAGES = 2
MAX_AI_NOTE_ANSWER_CHARS = 200_000
_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}

_SYSTEM_PROMPT = """You are the read-only Physics Parameter Tutor inside Physical Lab.

Rules:
1. Numerical solvers, imported measurements, project provenance, and validation checks are authoritative; you are not a replacement for them.
2. Explain parameter meanings, units, model assumptions, diagnostics, and possible next experiments from the supplied context plus general physics knowledge.
3. Never invent a unit, measured value, solver result, uncertainty, validation status, or hardware state. If context is missing, say exactly what is missing.
4. Clearly distinguish MEASURED DATA, SIMULATED/MODEL DATA, FITTED QUANTITIES, VISUAL OBSERVATIONS, and AI SUGGESTIONS.
5. You may suggest parameter changes, but you cannot apply them and must not imply that you changed the application.
6. A converged simulation or improved fit is not, by itself, experimental validation.
7. When suggesting a change, name the exact parameter, explain the expected physical direction, identify the observable that should respond, and state what result would contradict the expectation.
8. A screenshot or plot image is supplementary visual evidence. Never read an approximate pixel position as a more authoritative number than the supplied structured solver context.
9. If an image and structured context appear inconsistent, identify the inconsistency instead of silently choosing one.
10. Prefer concise, technically precise explanations.
"""

# Explicit metadata prevents a local model from guessing units merely from names.
# Unknown controls remain visible in selectedSessionState but are not assigned an
# invented meaning or unit by Physical Lab.
PARAMETER_GUIDES: dict[str, dict[str, dict[str, str]]] = {
    "radia-magnet-studio": {
        "cfg_device": {"unit": "device type", "meaning": "Magnetic-device geometry family."},
        "cfg_period_mm": {"unit": "mm", "meaning": "Magnetic period λu; affects geometry and undulator K."},
        "cfg_periods": {"unit": "periods", "meaning": "Number of magnetic periods in the modeled device."},
        "cfg_gap_mm": {"unit": "mm", "meaning": "Magnetic gap; changing it can strongly change on-axis field strength."},
        "cfg_blocks_per_period": {"unit": "blocks/period", "meaning": "Longitudinal discretization of the magnet pattern."},
        "cfg_block_width_mm": {"unit": "mm", "meaning": "Transverse x width of each permanent-magnet block."},
        "cfg_block_height_mm": {"unit": "mm", "meaning": "Block height or radial thickness used by the selected geometry."},
        "cfg_longitudinal_fill": {"unit": "fraction", "meaning": "Longitudinal fraction of each block slot occupied by magnet material."},
        "cfg_br_t": {"unit": "T", "meaning": "Permanent-magnet remanent induction Br used by the RADIA model."},
        "cfg_material_mode": {"unit": "model choice", "meaning": "Fixed remanence or linear NdFeB + relaxation material treatment."},
        "cfg_mu_parallel": {"unit": "relative permeability", "meaning": "Relative permeability parallel to the selected material axis."},
        "cfg_mu_perpendicular": {"unit": "relative permeability", "meaning": "Relative permeability perpendicular to the selected material axis."},
        "cfg_seg_n": {"unit": "subdivisions/axis", "meaning": "RADIA magnet subdivision resolution; larger values increase solver cost."},
        "cfg_target_b0_enabled": {"unit": "boolean", "meaning": "Enables calibration of Br to a requested B0 definition."},
        "cfg_target_b0_t": {"unit": "T", "meaning": "Requested target peak-field value for optional Br calibration."},
        "cfg_errors_enabled": {"unit": "boolean", "meaning": "Enables the explicit manufacturing-error model."},
        "cfg_field_error_pct": {"unit": "% RMS scale", "meaning": "Random field-amplitude error scale in the manufacturing-error model."},
        "cfg_longitudinal_error_mm": {"unit": "mm RMS scale", "meaning": "Random longitudinal block-position error scale."},
        "cfg_transverse_error_mm": {"unit": "mm RMS scale", "meaning": "Random transverse block-position error scale."},
        "cfg_angle_error_deg": {"unit": "deg RMS scale", "meaning": "Random magnetization-angle error scale."},
        "cfg_gap_asymmetry_mm": {"unit": "mm", "meaning": "Deterministic gap asymmetry in the error model."},
        "cfg_bank_imbalance_pct": {"unit": "%", "meaning": "Deterministic relative strength imbalance between magnet banks."},
        "cfg_axis_samples": {"unit": "samples", "meaning": "Number of on-axis field samples used for analysis."},
        "cfg_field_margin_periods": {"unit": "periods", "meaning": "Margin beyond outer blocks included in fringe-field integrals."},
        "cfg_electron_energy_GeV": {"unit": "GeV", "meaning": "Electron energy used for trajectory and electron-phase calculations."},
        "cfg_make_2d": {"unit": "boolean", "meaning": "Enables the 2-D field slice."},
        "cfg_make_3d": {"unit": "boolean", "meaning": "Enables the sparse 3-D field map."},
        "cfg_transverse_half_mm": {"unit": "mm", "meaning": "Half-width of the transverse field-map sampling region."},
        "cfg_precision": {"unit": "T", "meaning": "Requested RADIA relaxation precision when relaxation is enabled."},
        "cfg_max_iter": {"unit": "iterations", "meaning": "Maximum RADIA relaxation-iteration budget."},
    },
    "random-walk-monte-carlo": {
        "rw_dimension": {"unit": "dimensions", "meaning": "Spatial dimension of the random walk."},
        "rw_steps": {"unit": "steps/walker", "meaning": "Length of each random-walk trajectory."},
        "rw_walkers": {"unit": "walkers", "meaning": "Number of ensemble trajectories used for statistics."},
    },
    "ising-monte-carlo": {
        "size": {"unit": "lattice sites per side", "meaning": "Linear lattice size; larger systems reduce some finite-size effects but cost more computation."},
        "temperature": {"unit": "model temperature", "meaning": "Thermal control parameter using this Lab's normalization."},
    },
    "nonlinear-chaos": {
        "trajectory_duration": {"unit": "simulation time", "meaning": "Total integration duration."},
        "trajectory_dt": {"unit": "simulation time/step", "meaning": "Numerical integration step controlling temporal resolution."},
    },
    "oscillation-integration": {
        "gamma": {"unit": "model damping parameter", "meaning": "Controls damping strength using this Lab's equation convention."},
        "force_amplitude": {"unit": "model force amplitude", "meaning": "Amplitude of the external driving term."},
    },
}


# Advanced Physical Lab controls are defined by the injected research suites.
# Keep their metadata separate from upstream/core controls so a local model can
# distinguish the original Lab state from Physical Lab's additional experiment
# orchestration. Every key below comes from an actual Streamlit widget key in
# physical_lab_advanced.py; units are explicit where the UI/equation defines one.
ADVANCED_PARAMETER_GUIDES: dict[str, dict[str, dict[str, str]]] = {
    "numerical-methods": {
        "pl_n_xmax": {"unit": "rad", "meaning": "Maximum |x| used when mapping the sine-evaluation reliability frontier."},
        "pl_n_points": {"unit": "scan points", "meaning": "Number of x samples in the reliability-frontier scan."},
        "pl_n_dtype": {"unit": "arithmetic type", "meaning": "Floating-point arithmetic used by the frontier comparison (float32 or float64)."},
        "pl_n_at_method": {"unit": "method choice", "meaning": "Taylor evaluation strategy used by the cancellation atlas: raw or range-reduced."},
        "pl_n_at_dtype": {"unit": "arithmetic type", "meaning": "Floating-point arithmetic used by the cancellation atlas."},
        "pl_n_at_xmax": {"unit": "rad", "meaning": "Maximum input magnitude represented on the cancellation atlas."},
        "pl_n_at_grid": {"unit": "grid samples/axis", "meaning": "Resolution used for both input magnitude and Taylor-term sampling in the cancellation atlas."},
        "pl_n_at_terms": {"unit": "Taylor terms", "meaning": "Maximum fixed Taylor-series term count explored by the cancellation atlas."},
        "pl_n_micro_x": {"unit": "rad", "meaning": "Single input x inspected term-by-term in the numerical error microscope."},
        "pl_n_micro_dtype": {"unit": "arithmetic type", "meaning": "Floating-point arithmetic used by the term-by-term microscope."},
        "pl_n_micro_n": {"unit": "Taylor terms", "meaning": "Maximum term count inspected in the term-by-term error microscope."},
    },
    "ising-monte-carlo": {
        "pl_i_tmin": {"unit": "model temperature", "meaning": "Lower temperature bound of the coarse critical-region scan."},
        "pl_i_tmax": {"unit": "model temperature", "meaning": "Upper temperature bound of the coarse critical-region scan."},
        "pl_i_cn": {"unit": "temperature points", "meaning": "Number of coarse temperature samples before adaptive refinement."},
        "pl_i_rn": {"unit": "temperature points", "meaning": "Number of samples used in the refined critical-region window."},
        "pl_i_method": {"unit": "sampler choice", "meaning": "Monte Carlo update method used for the adaptive critical scan."},
        "pl_i_peak_seeds": {"unit": "independent RNG seeds", "meaning": "Number of independent repetitions used to audit critical-peak location stability."},
        "pl_i_peak_eq": {"unit": "equilibration cycles/seed", "meaning": "Thermalization budget for each independent critical-peak audit run."},
        "pl_i_peak_mc": {"unit": "measurement cycles/seed", "meaning": "Sampling budget for each independent critical-peak audit run."},
        "pl_i_sizes": {"unit": "lattice-size list", "meaning": "Comma-separated linear lattice sizes L used for the Binder-cumulant finite-size probe."},
        "pl_i_bmin": {"unit": "model temperature", "meaning": "Lower temperature bound of the Binder-cumulant scan."},
        "pl_i_bmax": {"unit": "model temperature", "meaning": "Upper temperature bound of the Binder-cumulant scan."},
        "pl_i_bpoints": {"unit": "temperature points", "meaning": "Number of temperature samples per lattice size in the Binder analysis."},
        "pl_i_dist_L": {"unit": "lattice sites/side", "meaning": "Linear lattice size used by the magnetization-distribution microscope."},
        "pl_i_dist_T": {"unit": "model temperature", "meaning": "Temperature used to sample the magnetization distribution."},
        "pl_i_eff_t": {"unit": "model temperature", "meaning": "Temperature at which compatible Monte Carlo samplers are compared by effective samples per work unit."},
    },
    "random-walk-monte-carlo": {
        "pl_rw_s_dim": {"unit": "dimensions", "meaning": "Spatial dimension used by the diffusion-scaling scan."},
        "pl_rw_s_walkers": {"unit": "walkers/scan point", "meaning": "Ensemble size used at each step-count value in the diffusion-scaling scan."},
        "pl_rw_s_nmin": {"unit": "steps/walker", "meaning": "Minimum random-walk length in the log-spaced diffusion-scaling scan."},
        "pl_rw_s_nmax": {"unit": "steps/walker", "meaning": "Maximum random-walk length in the log-spaced diffusion-scaling scan."},
        "pl_rw_s_points": {"unit": "scan points", "meaning": "Number of log-spaced walk lengths used to fit diffusion exponents."},
        "pl_rw_d_max": {"unit": "dimensions", "meaning": "Highest spatial dimension included in the dimension-concentration study."},
        "pl_rw_d_steps": {"unit": "steps/walker", "meaning": "Walk length held fixed while dimension is scanned."},
        "pl_rw_d_walkers": {"unit": "walkers/dimension", "meaning": "Ensemble size used at each dimension in the concentration study."},
        "pl_rw_q_powers": {"unit": "powers of two", "meaning": "Comma-separated exponents p defining matched sample budgets N=2^p for MC versus scrambled Sobol QMC."},
        "pl_rw_q_reps": {"unit": "independent replicates", "meaning": "Number of pseudorandom trials or independently scrambled Sobol replicates per sample budget."},
        "pl_rw_r_horizons": {"unit": "steps", "meaning": "Comma-separated finite observation horizons used for return-to-origin probability."},
        "pl_rw_r_dims": {"unit": "dimensions", "meaning": "Comma-separated spatial dimensions included in the recurrence-horizon study."},
        "pl_rw_r_trials": {"unit": "trials/point", "meaning": "Independent random-walk trials used for each dimension/horizon recurrence estimate."},
    },
    "nonlinear-chaos": {
        "pl_c_pair_dur": {"unit": "s", "meaning": "Integration duration for the nearby twin-trajectory divergence experiment."},
        "pl_c_pair_dt": {"unit": "s/step", "meaning": "Integrator time step used for the paired-trajectory divergence experiment."},
        "pl_c_pair_pert": {"unit": "log10(rad)", "meaning": "Base-10 exponent of the initial theta1 angular perturbation between the twin trajectories."},
        "pl_c_ly_dur": {"unit": "s", "meaning": "Finite observation duration used for the largest-Lyapunov-exponent estimate."},
        "pl_c_ly_dt": {"unit": "s/step", "meaning": "Integrator time step used by the finite-time Lyapunov calculation."},
        "pl_c_ly_ren": {"unit": "s", "meaning": "Time interval between perturbation renormalizations in the Benettin-style Lyapunov estimate."},
        "pl_c_at_span": {"unit": "rad", "meaning": "Symmetric initial-angle span sampled on each axis of the flip-time stability atlas."},
        "pl_c_at_res": {"unit": "initial conditions/axis", "meaning": "Grid resolution of the two-angle initial-condition stability atlas."},
        "pl_c_at_tmax": {"unit": "s", "meaning": "Finite maximum observation time for detecting a flip in the stability atlas."},
        "pl_c_at_dt": {"unit": "s/step", "meaning": "Integrator time step used by the flip-time atlas."},
        "pl_c_d_amin": {"unit": "model drive amplitude", "meaning": "Lower drive-amplitude bound of the driven Poincare scan."},
        "pl_c_d_amax": {"unit": "model drive amplitude", "meaning": "Upper drive-amplitude bound of the driven Poincare scan."},
        "pl_c_d_points": {"unit": "amplitude points", "meaning": "Number of drive-amplitude values in the stroboscopic response scan."},
        "pl_c_d_periods": {"unit": "drive periods", "meaning": "Number of forcing periods simulated at each drive amplitude."},
        "pl_c_d_gamma": {"unit": "model damping parameter", "meaning": "Damping parameter used by the driven-pendulum Poincare experiment."},
        "pl_c_d_freq": {"unit": "model angular-frequency convention", "meaning": "Drive frequency passed to the upstream driven-pendulum model."},
    },
    "oscillation-integration": {
        "pl_o_gmax": {"unit": "s^-1", "meaning": "Maximum damping coefficient gamma included in the linear damping-versus-drive atlas."},
        "pl_o_rmin": {"unit": "Omega/omega0", "meaning": "Minimum drive-to-natural-frequency ratio in the response atlas."},
        "pl_o_rmax": {"unit": "Omega/omega0", "meaning": "Maximum drive-to-natural-frequency ratio in the response atlas."},
        "pl_o_res": {"unit": "grid samples/axis", "meaning": "Resolution of the damping-versus-frequency-ratio response atlas."},
        "pl_o_force": {"unit": "N", "meaning": "Drive-force amplitude F0 used by the linear steady-state response atlas."},
        "pl_o_dtmin": {"unit": "s/step", "meaning": "Smallest integration time step included in the solver-convergence comparison."},
        "pl_o_dtmax": {"unit": "s/step", "meaning": "Largest integration time step included in the solver-convergence comparison."},
        "pl_o_dtpts": {"unit": "dt points", "meaning": "Number of geometrically spaced time-step values used to estimate integrator error/order."},
        "pl_o_e_gamma": {"unit": "s^-1", "meaning": "Damping coefficient used for the energy-flow audit."},
        "pl_o_e_force": {"unit": "N", "meaning": "External drive-force amplitude used for the energy-flow audit."},
        "pl_o_e_freq": {"unit": "rad/s", "meaning": "Drive angular frequency used for the energy-flow audit."},
        "pl_o_e_dt": {"unit": "s/step", "meaning": "RK4 integration step used for the energy-flow audit."},
    },
    "radia-magnet-studio": {
        "pl_m_seeds": {"unit": "independent RNG seeds", "meaning": "Number of manufacturing-error realizations in the RADIA seed ensemble."},
        "pl_m_axis": {"unit": "on-axis samples/seed", "meaning": "Number of longitudinal field samples used to analyze each manufacturing-error realization."},
        "pl_m_seed0": {"unit": "integer RNG seed", "meaning": "First manufacturing-error seed; subsequent ensemble runs increment from this value."},
    },
    "radiation-platform": {
        "pl_rad_gmin": {"unit": "Lorentz factor gamma", "meaning": "Minimum electron Lorentz factor in the ideal resonance sensitivity atlas."},
        "pl_rad_gmax": {"unit": "Lorentz factor gamma", "meaning": "Maximum electron Lorentz factor in the ideal resonance sensitivity atlas."},
        "pl_rad_kmin": {"unit": "dimensionless K", "meaning": "Minimum undulator-strength parameter K in the ideal resonance sensitivity atlas."},
        "pl_rad_kmax": {"unit": "dimensionless K", "meaning": "Maximum undulator-strength parameter K in the ideal resonance sensitivity atlas."},
        "pl_rad_period": {"unit": "mm", "meaning": "Undulator period lambda_u used by the ideal two-parameter sensitivity atlas."},
        "pl_rad_theta": {"unit": "mrad", "meaning": "Observation-angle magnitude used by the ideal resonance sensitivity atlas."},
        "pl_rad_harmonic": {"unit": "harmonic number", "meaning": "Odd ideal undulator harmonic used in the resonance calculation."},
        "pl_rad_res": {"unit": "grid samples/axis", "meaning": "Resolution of the gamma-versus-K ideal sensitivity atlas."},
        "pl_rad_inv_ev": {"unit": "eV", "meaning": "Target photon energy for the inverse ideal-resonance design calculation."},
        "pl_rad_inv_k": {"unit": "dimensionless K", "meaning": "Design K assumed while solving the ideal resonance relation backward for gamma."},
        "pl_rad_inv_h": {"unit": "harmonic number", "meaning": "Odd harmonic assumed by the inverse ideal-resonance design calculation."},
        "pl_rad_inv_angle": {"unit": "mrad", "meaning": "Observation angle assumed by the inverse ideal-resonance design calculation."},
        "pl_rad_inv_period": {"unit": "mm", "meaning": "Undulator period assumed by the inverse ideal-resonance design calculation."},
        "pl_rad_rep_axis": {"unit": "data-column choice", "meaning": "Numeric scan column treated as the independent variable for representative-point selection."},
        "pl_rad_rep_obs": {"unit": "data-column choice", "meaning": "Numeric observable used to identify feature-rich or representative scan locations."},
        "pl_rad_cmp_axis": {"unit": "data-column choice", "meaning": "Numeric upstream scan column used as the horizontal axis in analytic-reference comparison."},
        "pl_rad_cmp_sem": {"unit": "axis semantics", "meaning": "Physical interpretation assigned to the selected comparison axis: gamma, K, or observation angle."},
        "pl_rad_cmp_q": {"unit": "quantity choice", "meaning": "Analytic reference quantity displayed in comparison: photon energy or wavelength."},
        "pl_rad_cmp_gamma": {"unit": "Lorentz factor gamma", "meaning": "Fixed gamma used when the selected comparison axis is not gamma."},
        "pl_rad_cmp_k": {"unit": "dimensionless K", "meaning": "Fixed K used when the selected comparison axis is not K."},
        "pl_rad_cmp_period": {"unit": "mm", "meaning": "Reference undulator period used by the analytic comparison curve."},
        "pl_rad_cmp_obs": {"unit": "data-column choice", "meaning": "Optional upstream observable overlaid on the ideal analytic reference."},
    },
}

_RESULT_KEYS = (
    "metrics", "ideal_metrics", "classification", "key_results", "results",
    "result", "summary", "diagnostics", "comparison", "cmp", "stats",
    "statistics", "calibration_history", "rlx", "z_lo", "z_hi",
)


def _request_json(base: str, path: str, payload: Mapping[str, Any] | None = None, *, timeout: float = 8.0) -> Any:
    if base not in LOCAL_ENGINES.values():
        raise ValueError("Local AI endpoint is not on the Physical Lab loopback allowlist")
    url = base + path
    data = None
    headers = {"Accept": "application/json"}
    method = "GET"
    if payload is not None:
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise RuntimeError(f"Local model runtime returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Local model runtime is unavailable at {base}: {exc.reason}") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeError("Local model response exceeded the Physical Lab safety limit")
    return json.loads(raw.decode("utf-8"))


def discover_local_ai_engines() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for label, base in LOCAL_ENGINES.items():
        try:
            payload = _request_json(base, "/api/tags", timeout=1.2)
            models = []
            for item in payload.get("models", []) if isinstance(payload, dict) else []:
                name = item.get("name") or item.get("model")
                if isinstance(name, str) and name.strip():
                    models.append(name.strip())
            found.append({"label": label, "base": base, "models": sorted(set(models)), "running": True})
        except Exception:
            found.append({"label": label, "base": base, "models": [], "running": False})
    return found


def inspect_local_model(base: str, model: str) -> dict[str, Any]:
    """Return only bounded model metadata needed to gate optional capabilities."""
    try:
        payload = _request_json(base, "/api/show", {"model": model}, timeout=4.0)
    except Exception as exc:
        return {"capabilities": [], "vision": False, "reported": False, "error": str(exc)}
    capabilities = []
    if isinstance(payload, Mapping):
        raw = payload.get("capabilities")
        if isinstance(raw, (list, tuple)):
            capabilities = sorted({str(item).strip().lower() for item in raw if str(item).strip()})
    return {
        "capabilities": capabilities,
        "vision": "vision" in capabilities,
        "reported": bool(capabilities),
    }


def _plain(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "<depth-limit>"
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Mapping):
        output = {}
        for key, item in list(value.items())[:80]:
            if isinstance(key, str) and not key.lower().endswith(("token", "secret", "password", "key")):
                output[key] = _plain(item, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple)):
        return [_plain(item, depth=depth + 1) for item in list(value)[:120]]
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return _plain(value.item(), depth=depth + 1)
        if isinstance(value, np.ndarray):
            flat = value.reshape(-1)
            return {
                "type": "ndarray",
                "shape": list(value.shape),
                "sample": [_plain(item.item() if hasattr(item, "item") else item, depth=depth + 1) for item in flat[:24]],
            }
    except Exception:
        pass
    try:
        import pandas as pd
        if isinstance(value, pd.DataFrame):
            head = value.head(6).where(value.head(6).notna(), None)
            return {"type": "DataFrame", "rows": int(len(value)), "columns": [str(c) for c in list(value.columns)[:40]], "head": head.to_dict(orient="records")}
    except Exception:
        pass
    return f"<{type(value).__name__}>"


def _extract_result_summary(namespace: Mapping[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in _RESULT_KEYS:
        if key not in namespace:
            continue
        value = namespace.get(key)
        if callable(value):
            continue
        plain = _plain(value)
        if isinstance(plain, str) and plain.startswith("<") and plain.endswith(">"):
            continue
        values[key] = plain
        if len(values) >= 12:
            break
    if not values:
        return {}
    return {
        "provenance": "SIMULATED/MODEL DATA unless a nested record explicitly identifies measured or fitted provenance",
        "values": values,
    }


def _parameter_guide(profile: str, session_state: Mapping[str, Any] | None) -> dict[str, Any]:
    guide: dict[str, dict[str, str]] = {}
    guide.update(PARAMETER_GUIDES.get(profile, {}))
    guide.update(ADVANCED_PARAMETER_GUIDES.get(profile, {}))
    if not guide or session_state is None:
        return dict(guide)
    present = {str(key) for key in session_state.keys()}
    visible = {key: value for key, value in guide.items() if key in present}
    return visible or dict(guide)


def build_physics_context(profile: str, namespace: Mapping[str, Any], session_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {
        "schema": "physical-lab-local-ai-context-v3",
        "profile": profile,
        "engineMode": os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "safe"),
        "provenanceRules": {
            "MEASURED DATA": "Only explicitly imported or acquired measurements may be called measured.",
            "SIMULATED/MODEL DATA": "Numerical and RADIA solver outputs are simulated/model data.",
            "FITTED QUANTITIES": "Calibration and inverse/profile outputs are fitted or inferred quantities with stated limits.",
            "VISUAL OBSERVATIONS": "Screenshot/plot observations are qualitative unless a numeric value is independently present in structured context.",
            "AI SUGGESTIONS": "Suggested parameter changes are advisory and have not been applied.",
        },
        "boundary": "Local AI explains this state but does not modify it or replace scientific solvers.",
    }
    for key in ("current_params", "current_settings", "current_ui"):
        value = namespace.get(key)
        if isinstance(value, Mapping):
            context[key] = _plain(value)

    guide = _parameter_guide(profile, session_state)
    if guide:
        context["parameterGuide"] = guide

    result_summary = _extract_result_summary(namespace)
    if result_summary:
        context["latestResultSummary"] = result_summary
    elif session_state is not None:
        cached = session_state.get(f"__physical_lab_result_summary_{profile}")
        if isinstance(cached, Mapping):
            context["latestResultSummary"] = _plain(cached)

    if session_state is not None:
        selected: dict[str, Any] = {}
        for key, value in session_state.items():
            if not isinstance(key, str) or key.startswith(("pl_local_ai_", "pl_ai_seed_", "__")):
                continue
            if key.startswith(("cfg_", "pl_")) or key in {
                "method_label", "dtype", "size", "temperature", "gamma", "force_amplitude",
                "rw_dimension", "rw_steps", "rw_walkers", "trajectory_duration", "trajectory_dt",
            }:
                selected[key] = _plain(value)
            if len(selected) >= 120:
                break
        if selected:
            context["selectedSessionState"] = selected

    encoded = json.dumps(context, allow_nan=False, sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_CONTEXT_BYTES:
        context.pop("selectedSessionState", None)
        context["contextTruncated"] = True
    encoded = json.dumps(context, allow_nan=False, sort_keys=True).encode("utf-8")
    if len(encoded) > MAX_CONTEXT_BYTES:
        context.pop("latestResultSummary", None)
        context["resultSummaryTruncated"] = True
    return context


def _prepare_vision_images(uploaded_files: Any) -> tuple[list[str], list[dict[str, Any]]]:
    images: list[str] = []
    metadata: list[dict[str, Any]] = []
    for uploaded in list(uploaded_files or [])[:MAX_VISION_IMAGES]:
        mime = str(getattr(uploaded, "type", "") or "").lower()
        name = str(getattr(uploaded, "name", "image"))
        if mime not in _ALLOWED_IMAGE_TYPES:
            raise ValueError(f"Unsupported image type for {name}: {mime or 'unknown'}")
        raw = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
        if len(raw) > MAX_VISION_IMAGE_BYTES:
            raise ValueError(f"Vision image {name} exceeds the {MAX_VISION_IMAGE_BYTES // (1024 * 1024)} MB limit")
        images.append(base64.b64encode(raw).decode("ascii"))
        metadata.append({"name": name, "mime": mime, "bytes": len(raw), "provenance": "USER-SUPPLIED VISUAL CONTEXT"})
    return images, metadata


def ask_local_model(
    base: str,
    model: str,
    question: str,
    context: Mapping[str, Any],
    *,
    temperature: float = 0.2,
    images: list[str] | None = None,
) -> str:
    model = model.strip()
    question = question.strip()
    if not model:
        raise ValueError("Choose a local model first")
    if not question:
        raise ValueError("Enter a question for the Local AI Assistant")
    context_json = json.dumps(context, ensure_ascii=False, allow_nan=False, indent=2)
    if len(context_json.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("Physical Lab context is too large for the local assistant bridge")
    user_message: dict[str, Any] = {
        "role": "user",
        "content": f"Physical Lab structured context:\n{context_json}\n\nUser question:\n{question}",
    }
    if images:
        user_message["images"] = list(images[:MAX_VISION_IMAGES])
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            user_message,
        ],
        "options": {"temperature": float(temperature)},
    }
    result = _request_json(base, "/api/chat", payload, timeout=600.0)
    text = ""
    if isinstance(result, Mapping):
        message = result.get("message")
        if isinstance(message, Mapping):
            text = str(message.get("content") or "")
        if not text:
            text = str(result.get("response") or "")
    if not text.strip():
        raise RuntimeError("Local model returned an empty response")
    return text.strip()




def _current_parameter_rows(profile: str, session_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return documented parameters that are actually present in this UI session."""
    guide = _parameter_guide(profile, session_state)
    rows: list[dict[str, Any]] = []
    advanced = ADVANCED_PARAMETER_GUIDES.get(profile, {})
    for key in sorted(guide):
        if key not in session_state:
            continue
        meta = guide[key]
        rows.append({
            "parameter": key,
            "value": _plain(session_state.get(key)),
            "unit": str(meta.get("unit") or ""),
            "meaning": str(meta.get("meaning") or ""),
            "source": "Physical Lab advanced" if key in advanced else "Lab/core",
        })
    return rows



def _workspaces_root_from_environment() -> Path | None:
    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve() / "workspaces"


def list_local_workspaces() -> list[dict[str, str]]:
    """List managed .physlab workspaces visible to this local Lab process."""
    root = _workspaces_root_from_environment()
    if root is None or not root.is_dir():
        return []
    output: list[dict[str, str]] = []
    for path in sorted(root.glob("*.physlab"), key=lambda item: item.name.lower()):
        if not path.is_dir():
            continue
        name = path.stem
        workspace_id = path.stem
        project = path / "project.json"
        try:
            data = json.loads(project.read_text(encoding="utf-8"))
            if isinstance(data, Mapping):
                raw_name = data.get("name")
                raw_id = data.get("id")
                if isinstance(raw_name, str) and raw_name.strip():
                    name = raw_name.strip()
                if isinstance(raw_id, str) and raw_id.strip():
                    workspace_id = raw_id.strip()
        except Exception:
            pass
        output.append({"id": workspace_id, "name": name, "path": str(path.resolve())})
    return output


def save_ai_research_note(
    workspace_path: str,
    *,
    profile: str,
    runtime_label: str,
    runtime_base: str,
    model: str,
    question: str,
    answer: str,
    context: Mapping[str, Any],
    user_note: str = "",
) -> str:
    """Persist one explicit advisory exchange under provenance/ai-notes/."""
    root = _workspaces_root_from_environment()
    if root is None or not root.is_dir():
        raise RuntimeError("Physical Lab workspace root is unavailable in this Lab process")
    root = root.resolve()
    workspace = Path(workspace_path).expanduser().resolve()
    try:
        workspace.relative_to(root)
    except ValueError as exc:
        raise ValueError("AI notes can only be saved inside the managed Physical Lab workspaces directory") from exc
    if workspace.parent != root or workspace.suffix != ".physlab" or not workspace.is_dir():
        raise ValueError("Choose an existing top-level .physlab workspace")

    plain_context = _plain(context)
    canonical_context = json.dumps(
        plain_context,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    context_hash = hashlib.sha256(canonical_context.encode("utf-8")).hexdigest()
    answer_text = str(answer)
    truncated = len(answer_text) > MAX_AI_NOTE_ANSWER_CHARS
    if truncated:
        answer_text = answer_text[:MAX_AI_NOTE_ANSWER_CHARS]

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
    notes_dir = workspace / "provenance" / "ai-notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    destination = notes_dir / f"{stamp}-{profile}-local-ai.json"
    record = {
        "schema": "physical-lab-local-ai-note-v1",
        "createdUtc": now.isoformat(),
        "classification": "AI ADVISORY NOTE",
        "scientificAuthority": (
            "Not a measurement, solver result, fitted quantity, or validation record. "
            "Preserve the linked structured context and verify claims against Physical Lab evidence."
        ),
        "profile": profile,
        "runtime": {"label": runtime_label, "base": runtime_base},
        "model": model,
        "question": str(question),
        "answer": answer_text,
        "answerTruncated": truncated,
        "userNote": str(user_note).strip(),
        "contextSha256": context_hash,
        "context": plain_context,
    }
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)
    return str(destination)

def render_local_ai_assistant(st: Any, profile: str, namespace: Mapping[str, Any]) -> None:
    result_summary = _extract_result_summary(namespace)
    if result_summary:
        st.session_state[f"__physical_lab_result_summary_{profile}"] = result_summary

    st.markdown("---")
    with st.expander("Local AI Physics Tutor · OpenPenguin / Ollama", expanded=False):
        st.caption(
            "Optional, local-only explanation layer. Physical Lab sends a bounded structured snapshot of parameters, explicit units/meanings, assumptions and available result summaries to a model running on this Mac. "
            "Vision-capable local models may additionally inspect user-supplied screenshots or plots. The tutor can explain and suggest; it cannot change parameters or replace a solver."
        )
        engines = discover_local_ai_engines()
        running = [engine for engine in engines if engine["running"]]
        if not running:
            st.info(
                "No local model API is running. Start the OpenPenguin private runtime or an external Ollama service, then reopen this tutor. Physical Lab itself remains fully functional without Local AI."
            )
            return

        labels = [f"{engine['label']} · {engine['base']}" for engine in running]
        selected = st.selectbox("Local runtime", labels, key=f"pl_local_ai_runtime_{profile}")
        engine = running[labels.index(selected)]
        models = engine["models"]
        if not models:
            st.warning("The selected local runtime is available but has no installed model.")
            return

        c1, c2 = st.columns([2, 1])
        model = c1.selectbox("Model", models, key=f"pl_local_ai_model_{profile}")
        temperature = c2.slider("Explanation creativity", 0.0, 0.8, 0.2, 0.05, key=f"pl_local_ai_temp_{profile}")
        model_info = inspect_local_model(engine["base"], model)
        if model_info["vision"]:
            st.success("Vision capability detected locally. Structured physics context remains authoritative for numerical values.")
        elif model_info["reported"]:
            st.caption("This model does not report a vision capability; the tutor will use structured physics context only.")
        else:
            st.caption("The local runtime did not report model capabilities; vision input remains disabled rather than guessed.")

        question_key = f"pl_local_ai_question_{profile}"


        parameter_rows = _current_parameter_rows(profile, st.session_state)
        if parameter_rows:
            with st.expander("Parameter Explorer · current documented controls", expanded=False):
                st.caption(
                    "Read-only view of parameters that are both documented by Physical Lab and present in the current UI session. "
                    "Selecting a parameter can prepare a focused Tutor question; it does not change the control."
                )
                st.dataframe(parameter_rows, width="stretch", hide_index=True)
                parameter_keys = [row["parameter"] for row in parameter_rows]
                selected_parameter = st.selectbox(
                    "Parameter to inspect",
                    parameter_keys,
                    key=f"pl_local_ai_parameter_{profile}",
                )
                selected_row = next(row for row in parameter_rows if row["parameter"] == selected_parameter)
                p1, p2, p3 = st.columns([1.3, 1, 2.7])
                p1.metric("Current value", str(selected_row["value"]))
                p2.metric("Unit / convention", selected_row["unit"] or "documented meaning only")
                p3.info(selected_row["meaning"])
                a1, a2 = st.columns(2)
                if a1.button("Explain selected parameter", key=f"pl_ai_explain_parameter_{profile}", width="stretch"):
                    st.session_state[question_key] = (
                        f"Explain the current parameter `{selected_parameter}`. Its documented unit/convention is `{selected_row['unit']}` and its current value is `{selected_row['value']}`. "
                        "Explain its physical or numerical role, what increasing and decreasing it would usually change in this specific Lab, which observable/result should respond, and which assumptions limit that expectation. Do not change the parameter."
                    )
                if a2.button("Plan a controlled scan of it", key=f"pl_ai_scan_parameter_{profile}", width="stretch"):
                    st.session_state[question_key] = (
                        f"Plan one conservative controlled scan of `{selected_parameter}` from its current value `{selected_row['value']}` using the supplied Physical Lab context. "
                        "Give a bounded range or direction only when supported, say what must be held fixed, name the observable to monitor, and state what result would contradict the expected trend. Do not claim the scan has been run and do not modify the UI."
                    )

        st.markdown("#### Physics Tutor shortcuts")
        q1, q2, q3, q4 = st.columns(4)
        if q1.button("Explain setup", key=f"pl_ai_seed_setup_{profile}", width="stretch"):
            st.session_state[question_key] = "Explain my current setup parameter by parameter. For each important parameter, state its unit/meaning, what increasing or decreasing it physically changes, and which result should respond."
        if q2.button("Check assumptions", key=f"pl_ai_seed_assumptions_{profile}", width="stretch"):
            st.session_state[question_key] = "Audit the current setup for unit, model-assumption, numerical-resolution, and interpretation risks. Separate definite issues from things that merely deserve checking."
        if q3.button("Interpret results", key=f"pl_ai_seed_results_{profile}", width="stretch"):
            st.session_state[question_key] = "Interpret the latest available result summary. Distinguish simulated/model, measured, and fitted quantities. Explain what the numbers support and what they do not prove."
        if q4.button("Plan next scan", key=f"pl_ai_seed_scan_{profile}", width="stretch"):
            st.session_state[question_key] = "Suggest one controlled next parameter scan. Name the exact parameter, give a conservative direction/range based only on available context, identify the observable to monitor, and state what outcome would contradict the expectation. Do not claim the scan has been run."

        context = build_physics_context(profile, namespace, st.session_state)
        uploaded_files = []
        if model_info["vision"]:
            with st.expander("Optional local vision context", expanded=False):
                st.caption(
                    "Upload up to two PNG/JPEG/WebP screenshots or plots from the current experiment. Images stay on this Mac and are sent only to the selected loopback model. "
                    "Use structured solver values for exact numbers; vision is for geometry, plot shape, layout, annotations and qualitative anomalies."
                )
                uploaded_files = st.file_uploader(
                    "Screenshots / plots",
                    type=["png", "jpg", "jpeg", "webp"],
                    accept_multiple_files=True,
                    key=f"pl_local_ai_vision_{profile}",
                )
                if uploaded_files:
                    for uploaded in uploaded_files[:MAX_VISION_IMAGES]:
                        st.image(uploaded, caption=getattr(uploaded, "name", "visual context"), width="content")
                    if len(uploaded_files) > MAX_VISION_IMAGES:
                        st.warning(f"Only the first {MAX_VISION_IMAGES} images will be sent.")

        with st.expander("Physics context sent to the local model", expanded=False):
            st.json(context)

        question = st.text_area(
            "Ask about the current experiment",
            placeholder="Example: What does cfg_gap_mm control, why might reducing it change field strength, and which result should I watch?",
            key=question_key,
            height=120,
        )
        if st.button("Ask Local AI", type="primary", key=f"pl_local_ai_ask_{profile}"):
            try:
                images: list[str] = []
                visual_metadata: list[dict[str, Any]] = []
                if uploaded_files:
                    images, visual_metadata = _prepare_vision_images(uploaded_files)
                    context = dict(context)
                    context["visualContext"] = {
                        "provenance": "USER-SUPPLIED VISUAL CONTEXT",
                        "images": visual_metadata,
                        "authority": "qualitative supplement; structured solver context is authoritative for exact numerical values",
                    }
                with st.spinner(f"Asking {model} locally…"):
                    answer = ask_local_model(
                        engine["base"], model, question, context,
                        temperature=temperature, images=images,
                    )
                st.session_state[f"pl_local_ai_answer_{profile}"] = answer
                st.session_state[f"__physical_lab_ai_exchange_{profile}"] = {
                    "profile": profile,
                    "runtimeLabel": engine["label"],
                    "runtimeBase": engine["base"],
                    "model": model,
                    "question": question,
                    "answer": answer,
                    "context": _plain(context),
                }
            except Exception as exc:
                st.error(f"Local AI request failed: {exc}")
        answer = st.session_state.get(f"pl_local_ai_answer_{profile}")
        if answer:
            st.markdown("#### Explanation")
            st.write(answer)
            st.caption("AI explanation is advisory. Check units, model assumptions, measured data, uncertainty and solver validation before drawing scientific conclusions.")

            exchange = st.session_state.get(f"__physical_lab_ai_exchange_{profile}")
            workspaces = list_local_workspaces()
            if isinstance(exchange, Mapping) and workspaces:
                with st.expander("Save this exchange to .physlab provenance", expanded=False):
                    st.caption(
                        "Nothing is saved automatically. This writes a JSON advisory note under the selected project's provenance/ai-notes folder. "
                        "It is explicitly labeled as AI advice and is not mixed with measured data or solver results."
                    )
                    workspace_labels = [f"{item['name']} · {item['id']}" for item in workspaces]
                    workspace_label = st.selectbox(
                        "Research workspace",
                        workspace_labels,
                        key=f"pl_local_ai_note_workspace_{profile}",
                    )
                    workspace = workspaces[workspace_labels.index(workspace_label)]
                    research_note = st.text_input(
                        "Optional research note",
                        placeholder="Why is this explanation or scan idea worth preserving?",
                        key=f"pl_local_ai_note_text_{profile}",
                    )
                    if st.button(
                        "Save advisory note to .physlab",
                        key=f"pl_local_ai_save_note_{profile}",
                        width="stretch",
                    ):
                        try:
                            saved = save_ai_research_note(
                                workspace["path"],
                                profile=str(exchange.get("profile") or profile),
                                runtime_label=str(exchange.get("runtimeLabel") or "local runtime"),
                                runtime_base=str(exchange.get("runtimeBase") or "loopback"),
                                model=str(exchange.get("model") or model),
                                question=str(exchange.get("question") or ""),
                                answer=str(exchange.get("answer") or answer),
                                context=(
                                    exchange.get("context")
                                    if isinstance(exchange.get("context"), Mapping)
                                    else {}
                                ),
                                user_note=research_note,
                            )
                            st.success(f"Saved advisory provenance note: {saved}")
                        except Exception as exc:
                            st.error(f"Could not save AI research note: {exc}")
