"""Read-only Local AI assistant bridge for Physical Lab.

The scientific solvers remain authoritative. This module only sends a bounded,
structured snapshot of the current Physical Lab state to a user-selected local
Ollama-compatible model and returns explanatory text.

Supported local endpoints are intentionally fixed to loopback:
- OpenPenguin private runtime: 127.0.0.1:11435
- existing/external Ollama:     127.0.0.1:11434

The bridge never downloads models, executes model-provided code, changes physics
parameters, or contacts a cloud endpoint.
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

_SYSTEM_PROMPT = """You are the read-only Local AI Assistant inside Physical Lab, a computational and engineering physics workspace.

Rules:
1. The numerical solvers, measured datasets, and validation checks are authoritative; you are not a replacement for them.
2. Explain parameter meanings, units, model assumptions, diagnostics, and possible next experiments using only the supplied context plus general physics knowledge.
3. Never invent a unit, measured value, solver result, validation status, or hardware state. If context is missing, say what is missing.
4. Distinguish clearly between measured data, simulated/model data, fitted quantities, and suggestions.
5. You may suggest parameter changes, but you cannot apply them and must not imply that you changed the application.
6. Do not claim a model is experimentally validated merely because a simulation converged or a fit improved.
7. Prefer concise, technically precise explanations and name the exact Physical Lab parameter when possible.
"""


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
        if math.isfinite(value):
            return value
        return str(value)
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
    return f"<{type(value).__name__}>"


def build_physics_context(profile: str, namespace: Mapping[str, Any], session_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {
        "schema": "physical-lab-local-ai-context-v1",
        "profile": profile,
        "engineMode": os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "safe"),
        "authoritativeSources": ["current model parameters", "current solver settings", "selected UI parameters", "recorded result summaries"],
        "boundary": "Local AI explains this state but does not modify it or replace scientific solvers.",
    }
    for key in ("current_params", "current_settings", "current_ui"):
        value = namespace.get(key)
        if isinstance(value, Mapping):
            context[key] = _plain(value)

    if session_state is not None:
        selected: dict[str, Any] = {}
        for key, value in session_state.items():
            if not isinstance(key, str):
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
    st.markdown("---")
    with st.expander("Local AI Assistant · OpenPenguin / Ollama", expanded=False):
        st.caption(
            "Optional, local-only explanation layer. Physical Lab sends a bounded structured snapshot of the current physics state to a model running on this Mac. "
            "The assistant can explain and suggest; it cannot change parameters or replace a solver."
        )
        engines = discover_local_ai_engines()
        running = [engine for engine in engines if engine["running"]]
        if not running:
            st.info(
                "No local model API is running. Start the OpenPenguin private runtime or an external Ollama service, then reopen this assistant. "
                "Physical Lab itself remains fully functional without Local AI."
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
        context = build_physics_context(profile, namespace, st.session_state)
        with st.expander("Context sent to the local model", expanded=False):
            st.json(context)

        question = st.text_area(
            "Ask about the current experiment",
            placeholder="Example: What does gap_mm control, why might reducing it increase field strength, and which result should I watch?",
            key=f"pl_local_ai_question_{profile}",
            height=110,
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
            st.caption("AI explanation is advisory. Check units, model assumptions, measured data, and solver validation before drawing scientific conclusions.")
