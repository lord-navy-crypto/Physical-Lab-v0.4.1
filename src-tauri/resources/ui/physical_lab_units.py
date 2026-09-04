"""Lightweight canonical unit layer for Physical Lab.

The UI may accept familiar engineering units, while scientific records persist an
explicit canonical value/unit pair. This module intentionally implements a small,
auditable allow-list instead of silently guessing arbitrary unit strings.

Hot numerical solvers should continue using plain floats/ndarrays in canonical
units; this layer belongs at UI/manifest/evidence boundaries.
"""
from __future__ import annotations

import math
from typing import Any

EV_J = 1.602_176_634e-19
DEG_RAD = math.pi / 180.0

# normalized unit -> (dimension, factor_to_canonical, canonical_unit)
_UNITS: dict[str, tuple[str, float, str]] = {
    "1": ("dimensionless", 1.0, "1"),
    "%": ("dimensionless", 1e-2, "1"),
    "m": ("length", 1.0, "m"),
    "cm": ("length", 1e-2, "m"),
    "mm": ("length", 1e-3, "m"),
    "um": ("length", 1e-6, "m"),
    "nm": ("length", 1e-9, "m"),
    "s": ("time", 1.0, "s"),
    "ms": ("time", 1e-3, "s"),
    "us": ("time", 1e-6, "s"),
    "ns": ("time", 1e-9, "s"),
    "hz": ("frequency", 1.0, "Hz"),
    "khz": ("frequency", 1e3, "Hz"),
    "mhz": ("frequency", 1e6, "Hz"),
    "ghz": ("frequency", 1e9, "Hz"),
    "t": ("magnetic-field", 1.0, "T"),
    "mt": ("magnetic-field", 1e-3, "T"),
    "g": ("magnetic-field", 1e-4, "T"),
    "j": ("energy", 1.0, "J"),
    "ev": ("energy", EV_J, "J"),
    "kev": ("energy", 1e3 * EV_J, "J"),
    "mev": ("energy", 1e6 * EV_J, "J"),
    "rad": ("angle", 1.0, "rad"),
    "mrad": ("angle", 1e-3, "rad"),
    "deg": ("angle", DEG_RAD, "rad"),
    "a": ("current", 1.0, "A"),
    "ma": ("current", 1e-3, "A"),
    "v": ("voltage", 1.0, "V"),
    "mv": ("voltage", 1e-3, "V"),
    "kg": ("mass", 1.0, "kg"),
    "g_mass": ("mass", 1e-3, "kg"),
    "k": ("temperature", 1.0, "K"),
    "n": ("force", 1.0, "N"),
    "mn": ("force", 1e-3, "N"),
    "pa": ("pressure", 1.0, "Pa"),
    "kpa": ("pressure", 1e3, "Pa"),
    "mpa": ("pressure", 1e6, "Pa"),
    "gpa": ("pressure", 1e9, "Pa"),
    "m/s": ("velocity", 1.0, "m/s"),
    "um/s": ("velocity", 1e-6, "m/s"),
    "m2/s": ("diffusion", 1.0, "m^2/s"),
    "um2/s": ("diffusion", 1e-12, "m^2/s"),
}

_ALIASES = {
    "": "1",
    "dimensionless": "1",
    "µm": "um",
    "μm": "um",
    "µs": "us",
    "μs": "us",
    "µm/s": "um/s",
    "μm/s": "um/s",
    "µm²/s": "um2/s",
    "μm²/s": "um2/s",
    "um²/s": "um2/s",
    "m²/s": "m2/s",
    "gauss": "g",
    "tesla": "t",
    "kelvin": "k",
    "newton": "n",
    "newtons": "n",
    "pascal": "pa",
    "pascals": "pa",
    "degree": "deg",
    "degrees": "deg",
}


def normalize_unit(unit: str) -> str:
    raw = str(unit or "").strip()
    if raw in _ALIASES:
        return _ALIASES[raw]
    lowered = raw.lower().replace(" ", "")
    if lowered in _ALIASES:
        return _ALIASES[lowered]
    if lowered == "g" and raw == "g":
        # In Physical Lab the bare symbol G is Gauss; gram is exposed as g_mass.
        return "g"
    return lowered


def unit_info(unit: str) -> dict[str, Any]:
    normalized = normalize_unit(unit)
    item = _UNITS.get(normalized)
    if item is None:
        return {"known": False, "unit": str(unit), "normalized_unit": normalized}
    dimension, factor, canonical = item
    return {
        "known": True,
        "unit": str(unit),
        "normalized_unit": normalized,
        "dimension": dimension,
        "factor_to_canonical": factor,
        "canonical_unit": canonical,
    }


def canonicalize(value: float, unit: str) -> dict[str, Any]:
    info = unit_info(unit)
    try:
        numeric = float(value)
    except Exception as exc:
        raise ValueError("value must be numeric") from exc
    if not math.isfinite(numeric):
        raise ValueError("value must be finite")
    if not info.get("known"):
        raise ValueError(f"unsupported unit: {unit!r}")
    canonical_value = numeric * float(info["factor_to_canonical"])
    return {
        "value": numeric,
        "unit": str(unit),
        "dimension": info["dimension"],
        "canonical_value": canonical_value,
        "canonical_unit": info["canonical_unit"],
    }


def convert(value: float, from_unit: str, to_unit: str) -> float:
    source = canonicalize(value, from_unit)
    target = unit_info(to_unit)
    if not target.get("known"):
        raise ValueError(f"unsupported unit: {to_unit!r}")
    if source["dimension"] != target["dimension"]:
        raise ValueError(
            f"incompatible units: {from_unit!r} ({source['dimension']}) -> {to_unit!r} ({target['dimension']})"
        )
    return float(source["canonical_value"]) / float(target["factor_to_canonical"])


def compatible(unit_a: str, unit_b: str) -> bool:
    a = unit_info(unit_a)
    b = unit_info(unit_b)
    return bool(a.get("known") and b.get("known") and a.get("dimension") == b.get("dimension"))


def supported_units() -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for symbol, (dimension, _factor, _canonical) in _UNITS.items():
        grouped.setdefault(dimension, []).append(symbol)
    return {key: sorted(values) for key, values in sorted(grouped.items())}
