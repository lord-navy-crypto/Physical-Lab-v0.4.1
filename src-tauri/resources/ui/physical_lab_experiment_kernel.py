"""Physical Lab Experiment Kernel v1.

The kernel defines a common, JSON-serializable experiment contract shared by all
managed Labs.  It deliberately separates scientific content from UI state and
runtime timestamps so experiments can be fingerprinted, queued, compared and
replayed without making Streamlit session state the system of record.

This is an integration kernel, not a claim that every legacy Lab solver has
already been rewritten around it.  Adapters may initially expose manifest-only
capability while native worker execution is migrated incrementally.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import sys
from datetime import datetime, timezone
from typing import Any, Mapping

EXPERIMENT_SCHEMA = "physical-lab-experiment-v1"
KERNEL_VERSION = "1"

PROFILE_CONTRACTS: dict[str, dict[str, Any]] = {
    "numerical-methods": {
        "title": "Numerical Error Analysis",
        "domain": "numerical-analysis",
        "worker_capabilities": ["manifest", "model-campaign"],
        "default_resource_class": "light",
    },
    "ising-monte-carlo": {
        "title": "Ising Monte Carlo Lab",
        "domain": "statistical-physics",
        "worker_capabilities": ["manifest", "model-campaign"],
        "default_resource_class": "medium",
    },
    "random-walk-monte-carlo": {
        "title": "Random Walk & Monte Carlo",
        "domain": "stochastic-simulation",
        "worker_capabilities": ["manifest", "model-campaign"],
        "default_resource_class": "medium",
    },
    "nonlinear-chaos": {
        "title": "Nonlinear Dynamics & Chaos",
        "domain": "nonlinear-dynamics",
        "worker_capabilities": ["manifest", "model-campaign"],
        "default_resource_class": "medium",
    },
    "oscillation-integration": {
        "title": "Oscillation & Numerical Integration",
        "domain": "dynamics",
        "worker_capabilities": ["manifest", "model-campaign"],
        "default_resource_class": "light",
    },
    "radia-magnet-studio": {
        "title": "RADIA Magnet Studio",
        "domain": "magnetostatics",
        "worker_capabilities": ["manifest"],
        "default_resource_class": "heavy",
        "migration_note": "Native RADIA worker execution is intentionally not claimed until the solver lifecycle is extracted from the legacy UI process.",
    },
    "radiation-platform": {
        "title": "Radiation Platform",
        "domain": "accelerator-radiation",
        "worker_capabilities": ["manifest"],
        "default_resource_class": "heavy",
        "migration_note": "Native radiation worker execution is intentionally not claimed until field/trajectory/radiation solver orchestration is extracted from the legacy UI process.",
    },
}

_RESULT_TOKENS = (
    "result", "metric", "summary", "history", "frame", "scan", "spectrum",
    "field_map", "trajectory", "statistics", "validation", "scorecard",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite_float(value: Any) -> float | None:
    try:
        x = float(value)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def plain(value: Any, *, depth: int = 0, max_items: int = 240) -> Any:
    """Convert common scientific/session objects to bounded JSON-safe values."""
    if depth > 6:
        return {"type": type(value).__name__, "summary": "depth-limit"}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "infinity" if value > 0 else "-infinity"
        return value
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return plain(value.item(), depth=depth + 1, max_items=max_items)
        if isinstance(value, np.ndarray):
            arr = np.asarray(value)
            if arr.size <= 256:
                return {
                    "type": "ndarray",
                    "shape": list(arr.shape),
                    "data": plain(arr.tolist(), depth=depth + 1, max_items=max_items),
                }
            out: dict[str, Any] = {
                "type": "ndarray-summary",
                "shape": list(arr.shape),
                "dtype": str(arr.dtype),
                "size": int(arr.size),
            }
            if np.issubdtype(arr.dtype, np.number):
                finite = arr[np.isfinite(arr)]
                if finite.size:
                    out.update({
                        "min": float(np.min(finite)),
                        "max": float(np.max(finite)),
                        "mean": float(np.mean(finite)),
                    })
            return out
    except Exception:
        pass
    try:
        import pandas as pd
        if isinstance(value, pd.DataFrame):
            if len(value) <= 80 and len(value.columns) <= 24:
                return {
                    "type": "dataframe",
                    "columns": [str(x) for x in value.columns],
                    "records": plain(value.to_dict(orient="records"), depth=depth + 1, max_items=max_items),
                }
            return {
                "type": "dataframe-summary",
                "rows": int(len(value)),
                "columns": [str(x) for x in value.columns[:64]],
            }
        if isinstance(value, pd.Series):
            return plain(value.to_dict(), depth=depth + 1, max_items=max_items)
    except Exception:
        pass
    if isinstance(value, Mapping):
        return {
            str(k): plain(v, depth=depth + 1, max_items=max_items)
            for k, v in list(value.items())[:max_items]
        }
    if isinstance(value, (list, tuple)):
        return [plain(v, depth=depth + 1, max_items=max_items) for v in list(value)[:max_items]]
    return {"type": type(value).__name__, "repr": repr(value)[:400]}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _scientific_content(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable content used for experiment identity/fingerprinting."""
    return {
        "schema": manifest.get("schema"),
        "profile": manifest.get("profile"),
        "model": manifest.get("model"),
        "parameters": manifest.get("parameters") or {},
        "inputs": manifest.get("inputs") or {},
        "execution": manifest.get("execution") or {},
        "requirements": manifest.get("requirements") or [],
        "uncertainty": manifest.get("uncertainty") or {},
        "provenance": {
            key: (manifest.get("provenance") or {}).get(key)
            for key in ("engine_mode", "source_commit", "source_profile", "solver_backend")
            if (manifest.get("provenance") or {}).get(key) is not None
        },
    }


def experiment_fingerprint(manifest: Mapping[str, Any]) -> str:
    return sha256_json(_scientific_content(manifest))


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if manifest.get("schema") != EXPERIMENT_SCHEMA:
        errors.append(f"schema must be {EXPERIMENT_SCHEMA}")
    profile = str(manifest.get("profile") or "")
    if profile not in PROFILE_CONTRACTS:
        errors.append(f"unsupported profile: {profile or '<missing>'}")
    for key in ("model", "parameters", "inputs", "execution", "provenance"):
        if key not in manifest:
            errors.append(f"missing field: {key}")
    if "parameters" in manifest and not isinstance(manifest.get("parameters"), Mapping):
        errors.append("parameters must be an object")
    if "inputs" in manifest and not isinstance(manifest.get("inputs"), Mapping):
        errors.append("inputs must be an object")
    if "execution" in manifest and not isinstance(manifest.get("execution"), Mapping):
        errors.append("execution must be an object")
    if "provenance" in manifest and not isinstance(manifest.get("provenance"), Mapping):
        errors.append("provenance must be an object")
    supplied = str(manifest.get("experiment_sha256") or "")
    calculated = experiment_fingerprint(manifest) if not errors else None
    if supplied and calculated and supplied != calculated:
        errors.append("experiment_sha256 does not match scientific content")
    contract = PROFILE_CONTRACTS.get(profile) or {}
    if contract.get("worker_capabilities") == ["manifest"]:
        warnings.append(str(contract.get("migration_note") or "worker-native solver adapter not available"))
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "calculated_sha256": calculated,
        "contract": plain(contract),
    }


def estimate_resources(profile: str, execution: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return transparent local scheduling hints, not measured resource guarantees."""
    if profile not in PROFILE_CONTRACTS:
        raise ValueError(f"unsupported profile: {profile}")
    execution = execution or {}
    resource_class = str(PROFILE_CONTRACTS[profile]["default_resource_class"])
    preset = str(execution.get("preset") or execution.get("depth") or "").lower()
    if preset in {"standard", "deep", "full"} and resource_class == "light":
        resource_class = "medium"
    elif preset in {"standard", "deep", "full"} and resource_class == "medium":
        resource_class = "heavy"
    table = {
        "light": {"cpu_slots": 1, "memory_mb_hint": 512, "parallelism_hint": 2},
        "medium": {"cpu_slots": 1, "memory_mb_hint": 1024, "parallelism_hint": 1},
        "heavy": {"cpu_slots": 2, "memory_mb_hint": 2048, "parallelism_hint": 1},
    }
    out = {"resource_class": resource_class, **table[resource_class]}
    out["boundary"] = "Scheduling hint only; values are not measured peak resource requirements."
    return out


def _session_parameter_candidates(profile: str, session_state: Mapping[str, Any]) -> dict[str, Any]:
    """Capture bounded parameter-like state without treating result payloads as inputs."""
    output: dict[str, Any] = {}
    for key, value in list(session_state.items()):
        k = str(key)
        lower = k.lower()
        if k.startswith("__") or k.startswith(("pl_vault_", "pl_local_ai_")):
            continue
        if any(token in lower for token in _RESULT_TOKENS):
            continue
        is_simple = value is None or isinstance(value, (str, bool, int, float))
        is_small_list = (
            isinstance(value, (list, tuple))
            and len(value) <= 64
            and all(v is None or isinstance(v, (str, bool, int, float)) for v in value)
        )
        if is_simple or is_small_list:
            output[k] = plain(value)
        if len(output) >= 220:
            break
    return output


def _namespace_scalar_summary(namespace: Mapping[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for key, value in list(namespace.items())[:400]:
        lower = str(key).lower()
        if not any(token in lower for token in ("metric", "result", "summary", "energy", "field", "error", "frequency", "amplitude", "phase", "k_peak")):
            continue
        if value is None or isinstance(value, (str, bool, int, float)):
            summary[str(key)] = plain(value)
        elif isinstance(value, Mapping):
            scalars = {
                str(k): plain(v)
                for k, v in list(value.items())[:80]
                if v is None or isinstance(v, (str, bool, int, float))
            }
            if scalars:
                summary[str(key)] = scalars
        if len(summary) >= 80:
            break
    return summary


def build_experiment_manifest(
    profile: str,
    *,
    parameters: Mapping[str, Any] | None = None,
    inputs: Mapping[str, Any] | None = None,
    execution: Mapping[str, Any] | None = None,
    requirements: list[Mapping[str, Any]] | None = None,
    uncertainty: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    result_reference: Mapping[str, Any] | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    if profile not in PROFILE_CONTRACTS:
        raise ValueError(f"unsupported profile: {profile}")
    contract = PROFILE_CONTRACTS[profile]
    manifest: dict[str, Any] = {
        "schema": EXPERIMENT_SCHEMA,
        "kernel_version": KERNEL_VERSION,
        "profile": profile,
        "model": {
            "title": contract["title"],
            "domain": contract["domain"],
            "adapter_capabilities": list(contract["worker_capabilities"]),
        },
        "parameters": plain(dict(parameters or {})),
        "inputs": plain(dict(inputs or {})),
        "execution": plain(dict(execution or {})),
        "requirements": plain(list(requirements or [])),
        "uncertainty": plain(dict(uncertainty or {})),
        "provenance": plain(dict(provenance or {})),
        "result_reference": plain(dict(result_reference or {})),
        "created_at": created_at or utc_now(),
    }
    manifest["experiment_sha256"] = experiment_fingerprint(manifest)
    return manifest


def build_session_manifest(
    profile: str,
    namespace: Mapping[str, Any] | None,
    session_state: Mapping[str, Any] | None,
    *,
    execution: Mapping[str, Any] | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    namespace = namespace or {}
    session_state = session_state or {}
    parameters = _session_parameter_candidates(profile, session_state)
    result_reference = _namespace_scalar_summary(namespace)
    provenance = {
        "source_profile": profile,
        "engine_mode": os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "safe"),
        "source_commit": source_commit,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "capture": "Physical Lab session adapter",
    }
    return build_experiment_manifest(
        profile,
        parameters=parameters,
        execution=execution or {"mode": "interactive-session"},
        provenance=provenance,
        result_reference=result_reference,
    )


def manifest_summary(manifest: Mapping[str, Any]) -> dict[str, Any]:
    check = validate_manifest(manifest)
    profile = str(manifest.get("profile") or "")
    return {
        "schema": manifest.get("schema"),
        "profile": profile,
        "title": (manifest.get("model") or {}).get("title") if isinstance(manifest.get("model"), Mapping) else None,
        "experiment_sha256": manifest.get("experiment_sha256"),
        "parameter_count": len(manifest.get("parameters") or {}),
        "input_count": len(manifest.get("inputs") or {}),
        "valid": check["valid"],
        "warnings": check["warnings"],
        "resource_estimate": estimate_resources(profile, manifest.get("execution") or {}) if profile in PROFILE_CONTRACTS else None,
    }
