"""Read-only Local AI assistant bridge for Physical Lab.

Scientific solvers and measured datasets remain authoritative. This module sends
only a bounded structured snapshot of current Physical Lab state to a local
Ollama-compatible model and returns explanatory text.

Supported loopback runtimes:
- OpenPenguin private runtime: 127.0.0.1:11435
- existing/external Ollama:   127.0.0.1:11434

The bridge does not download models, execute model-provided code, change physics
parameters, or contact a cloud endpoint.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOCAL_ENGINES = {
    "OpenPenguin private runtime": "http://127.0.0.1:11435",
    "External Ollama": "http://127.0.0.1:11434",
}
MAX_CONTEXT_BYTES = 96 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024

_SYSTEM_PROMPT = """You are the read-only Physics Parameter Tutor inside Physical Lab.

Rules:
1. Numerical solvers, imported measurements, project provenance, and validation checks are authoritative; you are not a replacement for them.
2. Explain parameter meanings, units, model assumptions, diagnostics, and possible next experiments from the supplied context plus general physics knowledge.
3. Never invent a unit, measured value, solver result, uncertainty, validation status, or hardware state. If context is missing, say exactly what is missing.
4. Clearly distinguish MEASURED DATA, SIMULATED/MODEL DATA, FITTED QUANTITIES, and AI SUGGESTIONS.
5. You may suggest parameter changes, but you cannot apply them and must not imply that you changed the application.
6. A converged simulation or improved fit is not, by itself, experimental validation.
7. When suggesting a change, name the exact parameter, explain the expected physical direction, identify the observable that should respond, and state what result would contradict the expectation.
8. Prefer concise, technically precise explanations.
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
    guide = PARAMETER_GUIDES.get(profile, {})
    if not guide or session_state is None:
        return dict(guide)
    present = {str(key) for key in session_state.keys()}
    visible = {key: value for key, value in guide.items() if key in present}
    return visible or dict(guide)


def build_physics_context(profile: str, namespace: Mapping[str, Any], session_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {
        "schema": "physical-lab-local-ai-context-v2",
        "profile": profile,
        "engineMode": os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "safe"),
        "provenanceRules": {
            "MEASURED DATA": "Only explicitly imported or acquired measurements may be called measured.",
            "SIMULATED/MODEL DATA": "Numerical and RADIA solver outputs are simulated/model data.",
            "FITTED QUANTITIES": "Calibration and inverse/profile outputs are fitted or inferred quantities with stated limits.",
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


def ask_local_model(base: str, model: str, question: str, context: Mapping[str, Any], *, temperature: float = 0.2) -> str:
    model = model.strip()
    question = question.strip()
    if not model:
        raise ValueError("Choose a local model first")
    if not question:
        raise ValueError("Enter a question for the Local AI Assistant")
    context_json = json.dumps(context, ensure_ascii=False, allow_nan=False, indent=2)
    if len(context_json.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise ValueError("Physical Lab context is too large for the local assistant bridge")
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Physical Lab structured context:\n{context_json}\n\nUser question:\n{question}"},
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


def render_local_ai_assistant(st: Any, profile: str, namespace: Mapping[str, Any]) -> None:
    result_summary = _extract_result_summary(namespace)
    if result_summary:
        st.session_state[f"__physical_lab_result_summary_{profile}"] = result_summary

    st.markdown("---")
    with st.expander("Local AI Physics Tutor · OpenPenguin / Ollama", expanded=False):
        st.caption(
            "Optional, local-only explanation layer. Physical Lab sends a bounded structured snapshot of parameters, explicit units/meanings, assumptions and available result summaries to a model running on this Mac. "
            "The tutor can explain and suggest; it cannot change parameters or replace a solver."
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

        st.markdown("#### Physics Tutor shortcuts")
        q1, q2, q3, q4 = st.columns(4)
        question_key = f"pl_local_ai_question_{profile}"
        if q1.button("Explain setup", key=f"pl_ai_seed_setup_{profile}", width="stretch"):
            st.session_state[question_key] = "Explain my current setup parameter by parameter. For each important parameter, state its unit/meaning, what increasing or decreasing it physically changes, and which result should respond."
        if q2.button("Check assumptions", key=f"pl_ai_seed_assumptions_{profile}", width="stretch"):
            st.session_state[question_key] = "Audit the current setup for unit, model-assumption, numerical-resolution, and interpretation risks. Separate definite issues from things that merely deserve checking."
        if q3.button("Interpret results", key=f"pl_ai_seed_results_{profile}", width="stretch"):
            st.session_state[question_key] = "Interpret the latest available result summary. Distinguish simulated/model, measured, and fitted quantities. Explain what the numbers support and what they do not prove."
        if q4.button("Plan next scan", key=f"pl_ai_seed_scan_{profile}", width="stretch"):
            st.session_state[question_key] = "Suggest one controlled next parameter scan. Name the exact parameter, give a conservative direction/range based only on available context, identify the observable to monitor, and state what outcome would contradict the expectation. Do not claim the scan has been run."

        context = build_physics_context(profile, namespace, st.session_state)
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
                with st.spinner(f"Asking {model} locally…"):
                    answer = ask_local_model(engine["base"], model, question, context, temperature=temperature)
                st.session_state[f"pl_local_ai_answer_{profile}"] = answer
            except Exception as exc:
                st.error(f"Local AI request failed: {exc}")
        answer = st.session_state.get(f"pl_local_ai_answer_{profile}")
        if answer:
            st.markdown("#### Explanation")
            st.write(answer)
            st.caption("AI explanation is advisory. Check units, model assumptions, measured data, uncertainty and solver validation before drawing scientific conclusions.")
