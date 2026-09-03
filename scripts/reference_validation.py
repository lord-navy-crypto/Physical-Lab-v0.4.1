#!/usr/bin/env python3
"""Deterministic reference checks for Physical Lab.

These checks validate small analytic/numerical identities without pretending to
replace a full scientific validation campaign. RADIA Full-mode remains an
explicit external/native validation boundary.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "docs" / "reference-validation.json"
MD_PATH = ROOT / "docs" / "REFERENCE_VALIDATION.md"


def taylor_sine(x: float, terms: int = 8) -> float:
    return sum(((-1) ** k) * x ** (2 * k + 1) / math.factorial(2 * k + 1) for k in range(terms))


def rk4_harmonic(period: float = 2 * math.pi, dt: float = 0.01) -> tuple[float, float, int]:
    # x' = v, v' = -x, x(0)=1, v(0)=0
    x, v, t = 1.0, 0.0, 0.0
    steps = math.ceil(period / dt)
    h = period / steps
    for _ in range(steps):
        k1x, k1v = v, -x
        k2x, k2v = v + 0.5 * h * k1v, -(x + 0.5 * h * k1x)
        k3x, k3v = v + 0.5 * h * k2v, -(x + 0.5 * h * k2x)
        k4x, k4v = v + h * k3v, -(x + h * k3x)
        x += h * (k1x + 2 * k2x + 2 * k3x + k4x) / 6
        v += h * (k1v + 2 * k2v + 2 * k3v + k4v) / 6
        t += h
    return x, v, steps


def exact_random_walk_msd(steps: int = 100) -> float:
    # Propagate the exact probability mass function for a symmetric 1-D walk.
    probs = {0: 1.0}
    for _ in range(steps):
        nxt: dict[int, float] = {}
        for pos, p in probs.items():
            nxt[pos - 1] = nxt.get(pos - 1, 0.0) + 0.5 * p
            nxt[pos + 1] = nxt.get(pos + 1, 0.0) + 0.5 * p
        probs = nxt
    return sum((pos * pos) * p for pos, p in probs.items())


def build_results() -> dict:
    x = 0.1
    approx = taylor_sine(x)
    sine_error = abs(approx - math.sin(x))

    osc_x, osc_v, osc_steps = rk4_harmonic()
    osc_state_error = math.hypot(osc_x - 1.0, osc_v - 0.0)

    rw_steps = 100
    rw_msd = exact_random_walk_msd(rw_steps)

    ising_tc = 2.0 / math.log(1.0 + math.sqrt(2.0))
    # Exact 2-D Ising Onsager/Yang exponents (k_B=1, J=1 conventions).
    ising_nu = 1.0
    ising_beta = 1.0 / 8.0
    ising_gamma = 7.0 / 4.0
    ising_gamma_over_nu = ising_gamma / ising_nu
    ising_beta_over_nu = ising_beta / ising_nu

    lambda_u = 0.05
    gamma = 1000.0
    k = 0.7
    n_periods = 20
    lambda_1 = lambda_u * (1.0 + k * k / 2.0) / (2.0 * gamma * gamma)
    # Photon energy from wavelength: E[eV] = hc[eV·m] / λ[m]
    hc_ev_m = 1.2398419843320026e-6
    e1_ev = hc_ev_m / lambda_1
    harmonic_ladder = []
    for n in (1, 3, 5, 7, 9):
        en = n * e1_ev
        rel_bw = 1.0 / (n * n_periods)
        harmonic_ladder.append(
            {
                "harmonic": n,
                "photon_energy_ev": en,
                "relative_bandwidth_1_over_nN": rel_bw,
                "absolute_bandwidth_ev": en * rel_bw,
            }
        )

    return {
        "schema": "physical-lab-reference-validation-v1",
        "purpose": "Deterministic analytic/numerical references; not a substitute for experimental validation.",
        "checks": {
            "numerical_taylor_sine": {
                "input": {"x": x, "terms": 8},
                "computed": approx,
                "reference": math.sin(x),
                "absolute_error": sine_error,
                "pass": sine_error < 1e-14,
            },
            "oscillation_rk4_harmonic_period": {
                "input": {"period": 2 * math.pi, "target_dt": 0.01, "steps": osc_steps},
                "computed_final_state": {"x": osc_x, "v": osc_v},
                "reference_final_state": {"x": 1.0, "v": 0.0},
                "state_l2_error": osc_state_error,
                "pass": osc_state_error < 1e-8,
            },
            "random_walk_exact_msd": {
                "input": {"steps": rw_steps, "model": "symmetric 1-D ±1 walk"},
                "computed": rw_msd,
                "reference": float(rw_steps),
                "absolute_error": abs(rw_msd - rw_steps),
                "pass": abs(rw_msd - rw_steps) < 1e-10,
            },
            "ising_2d_exact_critical_temperature": {
                "input": {"model": "2-D square-lattice zero-field Ising", "units": "k_B T / J"},
                "reference": ising_tc,
                "formula": "2 / ln(1 + sqrt(2))",
                "status": "analytic-reference",
            },
            "ising_2d_exact_exponents": {
                "input": {"model": "2-D square-lattice zero-field Ising"},
                "nu": ising_nu,
                "beta": ising_beta,
                "gamma": ising_gamma,
                "gamma_over_nu": ising_gamma_over_nu,
                "beta_over_nu": ising_beta_over_nu,
                "status": "analytic-reference",
                "notes": "Used by Physical Lab Advanced Suite finite-size scaling diagnostics as exact thermodynamic-limit guides.",
            },
            "ideal_undulator_first_harmonic": {
                "input": {"lambda_u_m": lambda_u, "gamma": gamma, "K": k, "observation": "on-axis planar ideal-undulator reference"},
                "reference_wavelength_m": lambda_1,
                "reference_wavelength_nm": lambda_1 * 1e9,
                "formula": "lambda_u * (1 + K^2/2) / (2 gamma^2)",
                "status": "analytic-reference",
            },
            "ideal_undulator_linewidth_ladder": {
                "input": {
                    "lambda_u_m": lambda_u,
                    "gamma": gamma,
                    "K": k,
                    "periods_N": n_periods,
                    "harmonics": [1, 3, 5, 7, 9],
                    "bandwidth_model": "ideal finite-N estimate ΔE/E ≈ 1/(nN)",
                },
                "fundamental_photon_energy_ev": e1_ev,
                "ladder": harmonic_ladder,
                "status": "analytic-reference",
                "notes": "Design reference only; emittance, energy spread, tapering and field errors broaden realized spectra.",
            },
            "radia_full_mode": {
                "status": "not-run-in-source-ci",
                "pass": None,
                "reason": "Requires a native RADIA runtime and a real Full-mode field solve; no result is fabricated in CI.",
                "required_evidence": [
                    "actual RADIA field solve",
                    "recorded geometry and material inputs",
                    "field/trajectory/radiation outputs",
                    "comparison against matched analytic or measured reference",
                    "source/runtime provenance",
                ],
            },
        },
    }


def markdown(results: dict) -> str:
    c = results["checks"]
    lines = [
        "# Reference Validation Snapshot",
        "",
        "This file is generated by `scripts/reference_validation.py`. It contains deterministic references that can run in source CI without native physics engines. It is **not** presented as experimental validation or as a substitute for a RADIA Full-mode solve.",
        "",
        "| Check | Result | Reference | Status |",
        "|---|---:|---:|---|",
        f"| Taylor sin(0.1), 8 terms | error {c['numerical_taylor_sine']['absolute_error']:.3e} | `math.sin(0.1)` | {'PASS' if c['numerical_taylor_sine']['pass'] else 'FAIL'} |",
        f"| Harmonic oscillator RK4, one period | state error {c['oscillation_rk4_harmonic_period']['state_l2_error']:.3e} | (x,v)=(1,0) | {'PASS' if c['oscillation_rk4_harmonic_period']['pass'] else 'FAIL'} |",
        f"| Symmetric random walk MSD, N=100 | {c['random_walk_exact_msd']['computed']:.12g} | 100 | {'PASS' if c['random_walk_exact_msd']['pass'] else 'FAIL'} |",
        f"| 2-D Ising exact critical temperature | {c['ising_2d_exact_critical_temperature']['reference']:.12g} | 2/ln(1+sqrt(2)) | ANALYTIC REFERENCE |",
        f"| 2-D Ising exponents | γ/ν={c['ising_2d_exact_exponents']['gamma_over_nu']:.4g}, β/ν={c['ising_2d_exact_exponents']['beta_over_nu']:.4g} | Onsager/Yang | ANALYTIC REFERENCE |",
        f"| Ideal undulator first harmonic | {c['ideal_undulator_first_harmonic']['reference_wavelength_nm']:.9g} nm | ideal on-axis formula | ANALYTIC REFERENCE |",
        f"| Ideal undulator linewidth ladder | E1={c['ideal_undulator_linewidth_ladder']['fundamental_photon_energy_ev']:.9g} eV | ΔE/E≈1/(nN) | ANALYTIC REFERENCE |",
        "| RADIA Full mode | — | native 3-D field solve | NOT RUN IN SOURCE CI |",
        "",
        "## Boundary",
        "",
        "A green source-CI result means the deterministic reference machinery is internally consistent. It does not prove that a realized magnet, sensor, or radiation system matches the model. Full accelerator-physics claims require an actual RADIA run and, where experimental validation is claimed, calibrated measurement data.",
        "",
    ]
    return "\n".join(lines)


def serialize(results: dict) -> tuple[str, str]:
    return json.dumps(results, indent=2, sort_keys=True) + "\n", markdown(results)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="write the committed JSON/Markdown snapshots")
    parser.add_argument("--check", action="store_true", help="verify committed snapshots match generated results")
    args = parser.parse_args()

    results = build_results()
    json_text, md_text = serialize(results)

    failed = [name for name, item in results["checks"].items() if item.get("pass") is False]
    if failed:
        raise SystemExit("Reference validation failed: " + ", ".join(failed))

    if args.write:
        JSON_PATH.write_text(json_text, encoding="utf-8")
        MD_PATH.write_text(md_text, encoding="utf-8")
        print(f"wrote {JSON_PATH.relative_to(ROOT)}")
        print(f"wrote {MD_PATH.relative_to(ROOT)}")

    if args.check:
        if not JSON_PATH.exists() or not MD_PATH.exists():
            raise SystemExit("Committed reference-validation snapshots are missing; run with --write")
        if JSON_PATH.read_text(encoding="utf-8") != json_text:
            raise SystemExit("docs/reference-validation.json is stale; run scripts/reference_validation.py --write")
        if MD_PATH.read_text(encoding="utf-8") != md_text:
            raise SystemExit("docs/REFERENCE_VALIDATION.md is stale; run scripts/reference_validation.py --write")
        print("reference-validation snapshots: PASS")

    if not args.write and not args.check:
        print(json_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
