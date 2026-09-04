#!/usr/bin/env python3
"""Validate a model-field -> measurement-like field -> radiation propagation path.

The expected CI fixture is synthetic and deterministic. This script is also usable
with real co-registered field maps when provenance is supplied by the caller, but
it never labels a synthetic fixture as experimental validation.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "src-tauri" / "resources" / "ui" / "physical_lab_engineering_workflow.py"
spec = importlib.util.spec_from_file_location("physical_lab_engineering_workflow", MOD)
eng = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(eng)


def _centerline(npz_path: Path) -> tuple[list[float], list[float], dict]:
    with np.load(npz_path) as data:
        x = np.asarray(data["x_mm"], dtype=float)
        y = np.asarray(data["y_mm"], dtype=float)
        z = np.asarray(data["z_mm"], dtype=float)
        b = np.asarray(data["B_T"], dtype=float)
    if b.shape != (len(z), len(y), len(x), 3):
        raise ValueError(f"unexpected field-map shape {b.shape}")
    ix = int(np.argmin(np.abs(x)))
    iy = int(np.argmin(np.abs(y)))
    by = b[:, iy, ix, 1]
    return z.tolist(), by.tolist(), {"shape": list(b.shape), "center_indices": [ix, iy], "x_mm": float(x[ix]), "y_mm": float(y[iy])}


def _worker(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    obs = data.get("observables", {})
    for key in ("f0", "photon_energy_eV", "max_transverse_excursion_m"):
        value = float(obs[key])
        if not math.isfinite(value):
            raise ValueError(f"non-finite worker observable {key}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nominal-field", required=True)
    parser.add_argument("--measured-field", required=True)
    parser.add_argument("--nominal-worker", required=True)
    parser.add_argument("--measured-worker", required=True)
    parser.add_argument("--measurement-standard-uncertainty-t", type=float, default=3e-4)
    parser.add_argument("--source-type", choices=["synthetic-benchmark", "measured"], default="synthetic-benchmark")
    parser.add_argument("--source-label", default="Physical Lab deterministic measurement-like CI fixture")
    parser.add_argument("--evidence-out", required=True)
    args = parser.parse_args()

    z0, b0, meta0 = _centerline(Path(args.nominal_field))
    z1, b1, meta1 = _centerline(Path(args.measured_field))
    if z0 != z1:
        raise SystemExit("nominal and measurement-like maps do not share the same z grid")
    sigma = [abs(float(args.measurement_standard_uncertainty_t))] * len(z0)
    field = eng.measured_field_residual(z0, b0, b1, sigma)
    nominal = _worker(Path(args.nominal_worker))
    measured = _worker(Path(args.measured_worker))
    nobs = nominal["observables"]
    mobs = measured["observables"]

    def rel_change(key: str) -> float:
        a = float(nobs[key])
        b = float(mobs[key])
        if a == 0.0:
            return b - a
        return b / a - 1.0

    propagated = {
        "frequency_relative_change": rel_change("f0"),
        "photon_energy_relative_change": rel_change("photon_energy_eV"),
        "max_transverse_excursion_relative_change": rel_change("max_transverse_excursion_m"),
    }
    finite_changes = all(math.isfinite(v) for v in propagated.values())
    nonzero_field_discrepancy = field["rmse"] > 0.0 and field["max_abs_residual"] > 0.0
    status = "PASS" if finite_changes and nonzero_field_discrepancy else "FAIL"
    evidence = {
        "schema": "physical-lab-measured-field-radiation-validation-v1",
        "source": {"type": args.source_type, "label": args.source_label},
        "field_maps": {"nominal": meta0, "comparison": meta1},
        "field_residual": {k: v for k, v in field.items() if k != "residual"},
        "nominal_observables": {k: nobs.get(k) for k in ("f0", "photon_energy_eV", "max_transverse_excursion_m", "phase_error_rad", "exit_steering_rad")},
        "comparison_observables": {k: mobs.get(k) for k in ("f0", "photon_energy_eV", "max_transverse_excursion_m", "phase_error_rad", "exit_steering_rad")},
        "propagated_changes": propagated,
        "status": status,
        "boundary": "The CI default is a deterministic synthetic measurement-like field map. PASS proves the residual-to-radiation software path is active; it is not evidence of a real magnet measurement unless source.type is measured and external provenance is supplied.",
    }
    Path(args.evidence_out).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
