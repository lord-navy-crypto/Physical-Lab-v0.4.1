#!/usr/bin/env python3
"""Analytic planar-undulator benchmark for Physical Lab accelerator workflows.

The benchmark is intentionally narrow: a regular sinusoidal planar field with a
known peak field and period. It supplies an independent analytic resonance
reference for the cross-engine field-map -> trajectory/radiation acceptance
path without claiming experimental validation of a manufactured device.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

C0 = 299_792_458.0
E_CHARGE = 1.602176634e-19
H_PLANCK = 6.62607015e-34
M_E = 9.1093837139e-31
DEFAULT_REFERENCE = Path(__file__).resolve().parents[1] / "docs" / "accelerator-reference-benchmark.json"


def planar_undulator_reference(peak_field_t: float, period_m: float, gamma: float) -> dict[str, Any]:
    peak_field_t = float(peak_field_t)
    period_m = float(period_m)
    gamma = float(gamma)
    if not math.isfinite(peak_field_t) or peak_field_t < 0.0:
        raise ValueError("peak_field_t must be finite and non-negative")
    if not math.isfinite(period_m) or period_m <= 0.0:
        raise ValueError("period_m must be finite and positive")
    if not math.isfinite(gamma) or gamma <= 1.0:
        raise ValueError("gamma must be finite and greater than 1")

    k = E_CHARGE * peak_field_t * period_m / (2.0 * math.pi * M_E * C0)
    resonance_denominator = 1.0 + 0.5 * k * k
    wavelength_m = period_m * resonance_denominator / (2.0 * gamma * gamma)
    f0_hz = C0 / wavelength_m
    photon_energy_ev = H_PLANCK * f0_hz / E_CHARGE
    return {
        "schema": "physical-lab-planar-undulator-reference-v1",
        "inputs": {
            "peak_field_T": peak_field_t,
            "period_m": period_m,
            "gamma": gamma,
        },
        "reference": {
            "K": k,
            "resonance_denominator": resonance_denominator,
            "fundamental_wavelength_m": wavelength_m,
            "f0_Hz": f0_hz,
            "photon_energy_eV": photon_energy_ev,
        },
        "boundary": (
            "Analytic on-axis single-electron planar-undulator resonance for a sinusoidal field. "
            "It does not include bunch emittance, beam energy spread, coherent effects, beamline optics, "
            "detector response, manufacturing statistics, or experimental uncertainty."
        ),
    }


def _relative_error(observed: float, reference: float) -> float:
    return (float(observed) - float(reference)) / float(reference)


def _finite_positive(value: Any, name: str) -> float:
    try:
        out = float(value)
    except Exception as exc:
        raise ValueError(f"{name} is not numeric: {value!r}") from exc
    if not math.isfinite(out) or out <= 0.0:
        raise ValueError(f"{name} must be finite and positive, found {out!r}")
    return out


def compare_worker_output(
    worker_output: Path,
    peak_field_t: float,
    period_m: float,
    gamma: float,
    max_relative_error: float,
) -> dict[str, Any]:
    payload = json.loads(worker_output.read_text(encoding="utf-8"))
    observables = payload.get("observables")
    if not isinstance(observables, dict):
        raise ValueError("worker output is missing an observables object")

    observed_f0 = _finite_positive(observables.get("f0"), "observables.f0")
    observed_energy = _finite_positive(observables.get("photon_energy_eV"), "observables.photon_energy_eV")
    reference = planar_undulator_reference(peak_field_t, period_m, gamma)
    ref = reference["reference"]

    frequency_relative_error = _relative_error(observed_f0, ref["f0_Hz"])
    photon_energy_relative_error = _relative_error(observed_energy, ref["photon_energy_eV"])
    observed_energy_from_frequency = H_PLANCK * observed_f0 / E_CHARGE
    photon_frequency_consistency_relative_error = _relative_error(observed_energy, observed_energy_from_frequency)

    reported_residual = observables.get("frequency_relative_residual")
    residual_consistency_error = None
    if reported_residual is not None:
        reported_residual = float(reported_residual)
        if not math.isfinite(reported_residual):
            raise ValueError("frequency_relative_residual is not finite")
        residual_consistency_error = reported_residual - frequency_relative_error

    threshold = float(max_relative_error)
    if not math.isfinite(threshold) or threshold <= 0.0:
        raise ValueError("max_relative_error must be finite and positive")

    passed = (
        abs(frequency_relative_error) <= threshold
        and abs(photon_energy_relative_error) <= threshold
        and abs(photon_frequency_consistency_relative_error) <= 1e-10
        and (residual_consistency_error is None or abs(residual_consistency_error) <= 1e-8)
    )

    evidence = {
        "schema": "physical-lab-cross-engine-physics-benchmark-v1",
        "test": "sinusoidal planar 3-D field map -> Radiation Platform vs analytic undulator resonance",
        "reference": reference,
        "observed": {
            "f0_Hz": observed_f0,
            "photon_energy_eV": observed_energy,
            "frequency_relative_residual_reported": reported_residual,
        },
        "comparison": {
            "frequency_relative_error": frequency_relative_error,
            "photon_energy_relative_error": photon_energy_relative_error,
            "photon_frequency_consistency_relative_error": photon_frequency_consistency_relative_error,
            "reported_residual_consistency_error": residual_consistency_error,
            "max_allowed_reference_relative_error": threshold,
        },
        "status": "PASS" if passed else "FAIL",
        "boundary": (
            "This benchmark checks one deliberately simple analytic resonance invariant against the pinned "
            "single-electron field-map solver. Passing does not validate a specific magnet, beam, detector, "
            "manufacturing process, or experiment."
        ),
    }
    if not passed:
        raise AssertionError(json.dumps(evidence, indent=2, sort_keys=True))
    return evidence


def _assert_close(actual: float, expected: float, rel_tol: float = 1e-13) -> None:
    if not math.isclose(float(actual), float(expected), rel_tol=rel_tol, abs_tol=0.0):
        raise AssertionError(f"reference drift: actual={actual!r} expected={expected!r}")


def check_reference(reference_path: Path = DEFAULT_REFERENCE) -> dict[str, Any]:
    committed = json.loads(reference_path.read_text(encoding="utf-8"))
    inputs = committed["inputs"]
    regenerated = planar_undulator_reference(
        inputs["peak_field_T"], inputs["period_m"], inputs["gamma"]
    )
    for key in ("K", "resonance_denominator", "fundamental_wavelength_m", "f0_Hz", "photon_energy_eV"):
        _assert_close(regenerated["reference"][key], committed["reference"][key])
    if committed.get("schema") != regenerated["schema"]:
        raise AssertionError("reference schema drift")
    print("Accelerator analytic reference benchmark: PASS")
    print(json.dumps(regenerated, indent=2, sort_keys=True))
    return regenerated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="validate the committed analytic reference snapshot")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE))
    parser.add_argument("--worker-output", help="Radiation worker JSON to compare against the analytic reference")
    parser.add_argument("--peak-field-t", type=float, default=0.05)
    parser.add_argument("--period-mm", type=float, default=20.0)
    parser.add_argument("--gamma", type=float, default=80.0)
    parser.add_argument("--max-relative-error", type=float, default=5e-4)
    parser.add_argument("--evidence-out")
    args = parser.parse_args()

    if args.check:
        check_reference(Path(args.reference))
        return

    if args.worker_output:
        evidence = compare_worker_output(
            Path(args.worker_output),
            args.peak_field_t,
            args.period_mm * 1e-3,
            args.gamma,
            args.max_relative_error,
        )
        text = json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False)
        if args.evidence_out:
            Path(args.evidence_out).write_text(text + "\n", encoding="utf-8")
        print(text)
        return

    print(json.dumps(
        planar_undulator_reference(args.peak_field_t, args.period_mm * 1e-3, args.gamma),
        indent=2,
        sort_keys=True,
    ))


if __name__ == "__main__":
    main()
