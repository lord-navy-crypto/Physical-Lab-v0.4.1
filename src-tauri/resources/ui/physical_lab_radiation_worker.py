#!/usr/bin/env python3
"""Run pinned Radiation Platform scalar physics on one Physical Lab 3-D field map.

This worker is intentionally executed with the managed Radiation Platform .venv,
not the RADIA Magnet Studio .venv. It preserves Physical Lab's per-Lab dependency
isolation while allowing an explicit, provenance-recorded cross-model workflow.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
from typing import Any

RADIATION_PLATFORM_REVISION = "6d19b36304c9d30f9b608214f7cfb9fcbaf941d4"


def _finite(value: Any) -> float | None:
    try:
        x = float(value)
    except Exception:
        return None
    return x if math.isfinite(x) else None


def _observer_vector(distance_m: float, theta_x_mrad: float, theta_y_mrad: float):
    import numpy as np

    tx = 1e-3 * float(theta_x_mrad)
    ty = 1e-3 * float(theta_y_mrad)
    return np.asarray([
        float(distance_m) * math.tan(tx),
        float(distance_m) * math.tan(ty),
        float(distance_m),
    ], dtype=float)


def _extract_result(result: dict[str, Any]) -> dict[str, Any]:
    photon = result.get("photon_energy") if isinstance(result.get("photon_energy"), dict) else {}
    kcomp = result.get("K_components") if isinstance(result.get("K_components"), dict) else {}
    names = [
        "f0", "P_larmor", "relative_linewidth", "spectral_fwhm_hz",
        "spectral_quality_factor", "P_circ", "gamma_avg",
        "max_transverse_excursion_m", "period_repeatability_rms_m",
        "orbit_phase_error_rms_rad", "exit_xprime_rad", "exit_yprime_rad",
        "frequency_relative_residual",
    ]
    out = {name: _finite(result.get(name)) for name in names}
    out["photon_energy_eV"] = _finite(photon.get("eV"))
    for key in ("K0", "Kx", "Ky", "K_eff_rms"):
        out[f"K_{key}"] = _finite(kcomp.get(key))
    return out


def run(config_path: Path, output_path: Path) -> None:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    source = Path(str(cfg["radiationPlatformSource"])).resolve()
    map_path = Path(str(cfg["fieldMapNpz"])).resolve()
    if not source.is_dir():
        raise RuntimeError(f"Radiation Platform source is missing: {source}")
    if not map_path.is_file():
        raise RuntimeError(f"3-D field-map evidence is missing: {map_path}")

    sys.path.insert(0, str(source))
    import numpy as np
    import pandas as pd
    import undulator_v11_radia_integrated_v9 as v11

    data = np.load(map_path, allow_pickle=False)
    x_mm = np.asarray(data["x_mm"], dtype=float)
    y_mm = np.asarray(data["y_mm"], dtype=float)
    z_mm = np.asarray(data["z_mm"], dtype=float)
    field = np.asarray(data["B_T"], dtype=float)
    expected = (len(z_mm), len(y_mm), len(x_mm), 3)
    if field.shape != expected:
        raise ValueError(f"field-map shape {field.shape} does not match expected {expected}")
    if min(len(x_mm), len(y_mm)) < 3 or len(z_mm) < 9:
        raise ValueError("field map is too small for a 3-D Radiation Platform device")
    if not np.all(np.isfinite(field)):
        raise ValueError("field map contains non-finite values")

    # RADIA sample_3d is (Nz, Ny, Nx, 3); V11 regular field maps are indexed
    # as (Nx, Ny, Nz). Build a dataframe and let the pinned V11 field-map
    # constructor enforce regular-grid ordering and SI-unit conventions.
    bt = np.transpose(field, (2, 1, 0, 3))
    X, Y, Z = np.meshgrid(x_mm * 1e-3, y_mm * 1e-3, z_mm * 1e-3, indexing="ij")
    frame = pd.DataFrame({
        "x_m": X.ravel(), "y_m": Y.ravel(), "z_m": Z.ravel(),
        "Bx_T": bt[..., 0].ravel(), "By_T": bt[..., 1].ravel(), "Bz_T": bt[..., 2].ravel(),
    })
    device = v11._field_map_from_dataframe(
        frame,
        lambda_u=float(cfg["periodMm"]) * 1e-3,
        device_name=str(cfg.get("deviceName", "radia-field-map")),
        handedness=int(cfg.get("handedness", 1)),
        shift_z_to_zero=True,
        source_label=str(cfg.get("sourceLabel", "Physical Lab RADIA manufacturing realization")),
    )

    gamma = float(cfg["gamma"])
    n_periods = int(cfg["nPeriods"])
    ppp = int(cfg.get("pointsPerPeriod", 48))
    span = v11.simulation_span_for_device(gamma, device, n_periods=n_periods)
    n_base = v11.samples_for_periods(
        n_periods,
        pts_per_period=ppp,
        min_pts=max(1000, n_periods * ppp),
        max_pts=max(4000, n_periods * ppp + 1),
    )
    observer = _observer_vector(
        float(cfg.get("observerDistanceM", 100.0)),
        float(cfg.get("thetaXMrad", 0.0)),
        float(cfg.get("thetaYMrad", 0.0)),
    )
    result = v11.run_sim_scalar(
        device,
        None,
        span,
        observer,
        n_base=n_base,
        gamma0_input=gamma,
        rtol=float(cfg.get("rtol", 1e-9)),
        atol=float(cfg.get("atol", 1e-11)),
    )
    if not result:
        raise RuntimeError("Radiation Platform returned no scalar result")

    payload = {
        "schema": "physical-lab-radia-radiation-worker-v1",
        "radiationPlatformRevision": RADIATION_PLATFORM_REVISION,
        "fieldMap": {
            "nx": int(len(x_mm)), "ny": int(len(y_mm)), "nz": int(len(z_mm)),
            "points": int(len(x_mm) * len(y_mm) * len(z_mm)),
        },
        "inputs": {
            "gamma": gamma,
            "nPeriods": n_periods,
            "pointsPerPeriod": ppp,
            "observerDistanceM": float(cfg.get("observerDistanceM", 100.0)),
            "thetaXMrad": float(cfg.get("thetaXMrad", 0.0)),
            "thetaYMrad": float(cfg.get("thetaYMrad", 0.0)),
        },
        "observables": _extract_result(result),
        "boundary": "These observables come from the pinned Radiation Platform single-electron field-map solver. They do not include bunch emittance, energy spread, coherent effects, beamline optics or detector response.",
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(Path(args.config), Path(args.output))


if __name__ == "__main__":
    main()
