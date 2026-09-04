"""Automated engineering campaigns for Physical Lab's five non-accelerator Labs.

Each campaign runs a deterministic, bounded solver/refinement study and returns
canonical metrics consumed by ``physical_lab_model_engineering``. These are
computational verification and engineering-screening tools, not experimental
validation or certification.
"""
from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Any, Callable

SUPPORTED_PROFILES = (
    "numerical-methods",
    "ising-monte-carlo",
    "random-walk-monte-carlo",
    "nonlinear-chaos",
    "oscillation-integration",
)

PRESETS: dict[str, dict[str, dict[str, Any]]] = {
    "compact": {
        "numerical-methods": {"grid": 161, "orders": [3, 5, 7, 9, 11, 13, 15], "tol": 1e-10},
        "ising-monte-carlo": {"L": 8, "temperature": 2.4, "chains": 4, "burn": 250, "samples": 700, "thin": 2, "exact_samples": 1600},
        "random-walk-monte-carlo": {"replicates": 8, "walkers": 1200, "steps": [100, 200, 400, 800]},
        "nonlinear-chaos": {"dts": [0.04, 0.02, 0.01], "duration": 80.0, "lyapunov_replicates": 4},
        "oscillation-integration": {"dts": [0.08, 0.04, 0.02], "duration": 30.0},
    },
    "standard": {
        "numerical-methods": {"grid": 321, "orders": [3, 5, 7, 9, 11, 13, 15, 17], "tol": 1e-11},
        "ising-monte-carlo": {"L": 12, "temperature": 2.35, "chains": 4, "burn": 500, "samples": 1200, "thin": 2, "exact_samples": 3000},
        "random-walk-monte-carlo": {"replicates": 12, "walkers": 2400, "steps": [100, 200, 400, 800, 1600]},
        "nonlinear-chaos": {"dts": [0.03, 0.015, 0.0075], "duration": 80.0, "lyapunov_replicates": 5},
        "oscillation-integration": {"dts": [0.06, 0.03, 0.015], "duration": 45.0},
    },
}


def _np():
    import numpy as np
    return np


def _finite(value: Any) -> float:
    x = float(value)
    if not math.isfinite(x):
        raise ValueError("campaign metric must be finite")
    return x


def _fingerprint(profile: str, preset: str, config: dict[str, Any]) -> str:
    raw = json.dumps(
        {"profile": profile, "preset": preset, "config": config},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _payload(
    profile: str,
    preset: str,
    config: dict[str, Any],
    metrics: dict[str, float],
    cases: list[dict[str, Any]],
    notes: list[str],
) -> dict[str, Any]:
    return {
        "schema": "physical-lab-model-campaign-v1",
        "profile": profile,
        "preset": preset,
        "campaign_sha256": _fingerprint(profile, preset, config),
        "config": config,
        "metrics": {str(k): _finite(v) for k, v in metrics.items()},
        "cases": cases,
        "notes": notes,
        "boundary": "Deterministic numerical/stochastic engineering screening; not experimental validation, product certification, or a population reliability claim.",
    }


def _linear_slope(x, y) -> float:
    np = _np()
    xx = np.asarray(x, dtype=float)
    yy = np.asarray(y, dtype=float)
    xc = xx - float(np.mean(xx))
    denom = float(np.dot(xc, xc))
    if denom <= 0:
        raise ValueError("degenerate regression axis")
    return float(np.dot(xc, yy - float(np.mean(yy))) / denom)


def _ess(values) -> float:
    """Initial-positive-sequence scalar effective sample size estimate."""
    np = _np()
    x = np.asarray(values, dtype=float)
    n = int(x.size)
    if n < 4:
        return float(n)
    x = x - float(np.mean(x))
    var = float(np.dot(x, x) / n)
    if var <= 0:
        return float(n)
    rho_sum = 0.0
    for lag in range(1, min(n // 2, 200) + 1):
        rho = float(np.dot(x[:-lag], x[lag:]) / ((n - lag) * var))
        if rho <= 0:
            break
        rho_sum += rho
    return float(n / max(1.0, 1.0 + 2.0 * rho_sum))


def _rhat(chains) -> float:
    np = _np()
    arr = np.asarray(chains, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2 or arr.shape[1] < 4:
        raise ValueError("R-hat requires at least two chains with four samples")
    n = arr.shape[1]
    means = np.mean(arr, axis=1)
    within = float(np.mean(np.var(arr, axis=1, ddof=1)))
    if within <= 0:
        return 1.0
    between = float(n * np.var(means, ddof=1))
    variance = ((n - 1) / n) * within + between / n
    return float(math.sqrt(max(variance / within, 0.0)))


# ---------------------------------------------------------------------------
# Numerical Error
# ---------------------------------------------------------------------------

def _sin_taylor(x, terms: int):
    np = _np()
    x = np.asarray(x, dtype=float)
    out = np.zeros_like(x)
    term = x.copy()
    out += term
    for k in range(1, terms):
        term *= -(x * x) / ((2 * k) * (2 * k + 1))
        out += term
    return out


def numerical_campaign(config: dict[str, Any], preset: str) -> dict[str, Any]:
    np = _np()
    grid = int(config["grid"])
    tolerance = float(config["tol"])
    orders = [int(v) for v in config["orders"]]
    x = np.linspace(-math.pi, math.pi, grid)
    reference = np.sin(x)
    cases: list[dict[str, Any]] = []
    for terms in orders:
        started = time.perf_counter()
        approx = _sin_taylor(x, terms)
        error = np.abs(approx - reference)
        cases.append({
            "terms": terms,
            "max_abs_error": float(np.max(error)),
            "rms_error": float(math.sqrt(float(np.mean(error * error)))),
            "pass_fraction": float(np.mean(error <= tolerance)),
            "evaluations": grid * terms,
            "runtime_s": time.perf_counter() - started,
        })

    h = np.asarray([0.2, 0.1, 0.05, 0.025], dtype=float)
    point = 0.73
    d_error = np.abs((np.sin(point + h) - np.sin(point - h)) / (2.0 * h) - math.cos(point))
    observed_order = math.log(float(d_error[-2] / d_error[-1])) / math.log(2.0)
    final = cases[-1]
    return _payload(
        "numerical-methods",
        preset,
        config,
        {
            "max_normalized_error": float(final["max_abs_error"]) / tolerance,
            "pass_fraction": float(final["pass_fraction"]),
            "convergence_order": observed_order,
        },
        cases,
        [
            "Taylor scan uses sin(x) on [-pi, pi] against the NumPy/libm double-precision reference.",
            "Observed convergence order comes from an independent centered finite-difference derivative refinement, expected to approach second order.",
            "Evaluation count is an algorithmic work proxy; wall-clock runtime is descriptive and machine-dependent.",
        ],
    )


# ---------------------------------------------------------------------------
# Ising Monte Carlo
# ---------------------------------------------------------------------------

def _ising_energy_per_spin(spins) -> float:
    np = _np()
    s = np.asarray(spins, dtype=int)
    return float(-np.sum(s * (np.roll(s, 1, axis=0) + np.roll(s, 1, axis=1))) / s.size)


def _ising_sweep(spins, beta: float, rng) -> None:
    L = int(spins.shape[0])
    for _ in range(L * L):
        i = int(rng.integers(L))
        j = int(rng.integers(L))
        neighbors = (
            spins[(i + 1) % L, j]
            + spins[(i - 1) % L, j]
            + spins[i, (j + 1) % L]
            + spins[i, (j - 1) % L]
        )
        delta_e = 2 * spins[i, j] * neighbors
        if delta_e <= 0 or rng.random() < math.exp(-beta * delta_e):
            spins[i, j] *= -1


def _ising_chain(L: int, temperature: float, burn: int, samples: int, thin: int, seed: int):
    np = _np()
    rng = np.random.default_rng(seed)
    spins = rng.choice(np.asarray([-1, 1], dtype=int), size=(L, L))
    beta = 1.0 / temperature
    burn_trace: list[float] = []
    for sweep in range(burn):
        _ising_sweep(spins, beta, rng)
        if sweep >= burn // 2:
            burn_trace.append(_ising_energy_per_spin(spins))
    energies: list[float] = []
    magnetizations: list[float] = []
    for _ in range(samples):
        for __ in range(thin):
            _ising_sweep(spins, beta, rng)
        energies.append(_ising_energy_per_spin(spins))
        magnetizations.append(float(abs(np.mean(spins))))
    return np.asarray(energies), np.asarray(magnetizations), np.asarray(burn_trace)


def _exact_ising_energy_4x4(temperature: float) -> float:
    """Exact periodic 4x4 zero-field canonical energy per spin by enumeration."""
    np = _np()
    L = 4
    n = L * L
    beta = 1.0 / temperature
    energies = np.empty(1 << n, dtype=float)
    bit_index = np.arange(n)
    for state in range(1 << n):
        bits = ((state >> bit_index) & 1).astype(int)
        spins = (2 * bits - 1).reshape(L, L)
        energies[state] = -np.sum(
            spins * (np.roll(spins, 1, axis=0) + np.roll(spins, 1, axis=1))
        )
    offset = float(np.min(energies))
    weights = np.exp(-beta * (energies - offset))
    return float(np.sum(energies * weights) / np.sum(weights) / n)


def ising_campaign(config: dict[str, Any], preset: str) -> dict[str, Any]:
    np = _np()
    L = int(config["L"])
    temperature = float(config["temperature"])
    chains = int(config["chains"])
    burn = int(config["burn"])
    samples = int(config["samples"])
    thin = int(config["thin"])

    energy_chains = []
    magnetization_chains = []
    drift_scores: list[float] = []
    cases: list[dict[str, Any]] = []
    for chain_id in range(chains):
        energy, magnetization, burn_trace = _ising_chain(
            L, temperature, burn, samples, thin, 20260904 + 97 * chain_id
        )
        energy_chains.append(energy)
        magnetization_chains.append(magnetization)
        if burn_trace.size >= 8:
            half = burn_trace.size // 2
            early = burn_trace[:half]
            late = burn_trace[-half:]
            scale = max(float(np.std(burn_trace, ddof=1)), 1e-12)
            drift_scores.append(abs(float(np.mean(early) - np.mean(late))) / scale)
        cases.append({
            "chain": chain_id,
            "mean_energy_per_spin": float(np.mean(energy)),
            "mean_abs_magnetization": float(np.mean(magnetization)),
            "ess_energy": _ess(energy),
            "ess_abs_magnetization": _ess(magnetization),
        })

    energy_arr = np.asarray(energy_chains)
    magnetization_arr = np.asarray(magnetization_chains)
    rhat_energy = _rhat(energy_arr)
    rhat_magnetization = _rhat(magnetization_arr)
    ess_energy = sum(_ess(chain) for chain in energy_arr)
    ess_magnetization = sum(_ess(chain) for chain in magnetization_arr)

    exact_temperature = 3.0
    exact_energy = _exact_ising_energy_4x4(exact_temperature)
    exact_samples = int(config.get("exact_samples", 1600))
    observed_exact = []
    for chain_id in range(4):
        energy, _, _ = _ising_chain(
            4,
            exact_temperature,
            max(200, burn // 2),
            exact_samples,
            1,
            9901 + chain_id,
        )
        observed_exact.append(float(np.mean(energy)))
    observed_energy = float(np.mean(observed_exact))
    exact_relative_error = abs(observed_energy - exact_energy) / max(abs(exact_energy), 1e-12)
    cases.append({
        "checkpoint": "exact-4x4",
        "temperature": exact_temperature,
        "exact_energy_per_spin": exact_energy,
        "observed_energy_per_spin": observed_energy,
        "relative_error": exact_relative_error,
    })

    return _payload(
        "ising-monte-carlo",
        preset,
        config,
        {
            "rhat_max": max(rhat_energy, rhat_magnetization),
            "effective_samples_min": min(ess_energy, ess_magnetization),
            "exact_reference_relative_error": exact_relative_error,
            "equilibration_drift_sigma": max(drift_scores) if drift_scores else 0.0,
        },
        cases,
        [
            "R-hat is the classical between/within-chain scalar diagnostic; it is finite-sample evidence, not proof of convergence.",
            "ESS uses an initial-positive autocorrelation sum and reports the minimum total effective count across energy and |magnetization|.",
            "The exact checkpoint enumerates all 2^16 states of a periodic 4x4 zero-field Ising lattice at T=3.0.",
        ],
    )


# ---------------------------------------------------------------------------
# Random Walk / Monte Carlo
# ---------------------------------------------------------------------------

def random_walk_campaign(config: dict[str, Any], preset: str) -> dict[str, Any]:
    np = _np()
    replicates = int(config["replicates"])
    walkers = int(config["walkers"])
    step_counts = [int(v) for v in config["steps"]]
    max_steps = max(step_counts)
    checkpoints = set(step_counts)
    all_msd = []
    estimators: list[float] = []
    cases: list[dict[str, Any]] = []

    for replicate in range(replicates):
        seed = 44000 + replicate
        rng = np.random.default_rng(seed)
        x = np.zeros(walkers, dtype=int)
        y = np.zeros(walkers, dtype=int)
        msd: list[float] = []
        for step in range(1, max_steps + 1):
            direction = rng.integers(0, 4, size=walkers)
            x += (direction == 0).astype(int) - (direction == 1).astype(int)
            y += (direction == 2).astype(int) - (direction == 3).astype(int)
            if step in checkpoints:
                msd.append(float(np.mean(x * x + y * y)))
        all_msd.append(msd)
        estimate = msd[-1] / max_steps
        estimators.append(estimate)
        cases.append({
            "replicate": replicate,
            "seed": seed,
            "final_msd": msd[-1],
            "diffusion_scale_estimate": estimate,
        })

    mean_msd = np.mean(np.asarray(all_msd, dtype=float), axis=0)
    exponent = _linear_slope(np.log(step_counts), np.log(mean_msd))
    estimator = float(np.mean(estimators))
    replicate_cv = (
        float(np.std(estimators, ddof=1) / abs(estimator))
        if replicates > 1 and estimator != 0
        else 0.0
    )
    cases.append({
        "aggregate": "MSD scaling",
        "steps": step_counts,
        "mean_msd": [float(v) for v in mean_msd],
        "fitted_exponent": exponent,
        "mean_diffusion_scale_estimate": estimator,
    })
    return _payload(
        "random-walk-monte-carlo",
        preset,
        config,
        {
            "msd_exponent_error": abs(exponent - 1.0),
            "estimator_relative_error": abs(estimator - 1.0),
            "replicate_cv": replicate_cv,
        },
        cases,
        [
            "Reference model is a 2D unbiased nearest-neighbor unit-step walk, so E[r^2]=N and the MSD exponent target is 1.",
            "Independent deterministic seeds quantify finite-replicate stability; CV is descriptive, not a population failure probability.",
            "The final MSD/N ratio is used as the estimator with theoretical target 1 for this selected model.",
        ],
    )


# ---------------------------------------------------------------------------
# Nonlinear Dynamics / Chaos
# ---------------------------------------------------------------------------

def _rk4_step(rhs: Callable, t: float, state, dt: float):
    np = _np()
    y = np.asarray(state, dtype=float)
    k1 = np.asarray(rhs(t, y), dtype=float)
    k2 = np.asarray(rhs(t + dt / 2.0, y + dt * k1 / 2.0), dtype=float)
    k3 = np.asarray(rhs(t + dt / 2.0, y + dt * k2 / 2.0), dtype=float)
    k4 = np.asarray(rhs(t + dt, y + dt * k3), dtype=float)
    return y + dt * (k1 + 2.0 * k2 + 2.0 * k3 + k4) / 6.0


def _duffing_rhs(t: float, state):
    x, velocity = state
    return (velocity, x - x**3 - 0.2 * velocity + 0.3 * math.cos(1.2 * t))


def _duffing_run(dt: float, duration: float, initial=(0.1, 0.0)) -> dict[str, Any]:
    np = _np()
    steps = int(round(duration / dt))
    state = np.asarray(initial, dtype=float)
    time_value = 0.0
    energy: list[float] = []
    power: list[float] = []
    times: list[float] = []
    poincare: list[float] = []
    drive_period = 2.0 * math.pi / 1.2
    next_sample = drive_period

    for _ in range(steps):
        x, velocity = state
        energy.append(0.5 * velocity**2 - 0.5 * x**2 + 0.25 * x**4)
        power.append(-0.2 * velocity**2 + 0.3 * velocity * math.cos(1.2 * time_value))
        times.append(time_value)
        if time_value >= next_sample:
            poincare.append(float(x))
            next_sample += drive_period
        state = _rk4_step(_duffing_rhs, time_value, state, dt)
        time_value += dt

    x, velocity = state
    final_energy = 0.5 * velocity**2 - 0.5 * x**2 + 0.25 * x**4
    time_array = np.asarray(times, dtype=float)
    power_array = np.asarray(power, dtype=float)
    work = float(np.trapezoid(power_array, time_array)) if time_array.size > 1 else 0.0
    energy_change = final_energy - energy[0]
    balance_error = abs(energy_change - work) / max(abs(energy_change), abs(work), 1e-9)
    poincare_array = np.asarray(poincare, dtype=float)
    if poincare_array.size:
        tail = poincare_array[-max(4, poincare_array.size // 2):]
        indicator = float(np.std(tail))
    else:
        indicator = 0.0
    return {
        "indicator": indicator,
        "energy_balance_relative_error": balance_error,
        "final_state": [float(v) for v in state],
        "poincare_points": int(poincare_array.size),
    }


def _duffing_lyapunov(dt: float, duration: float, initial=(0.1, 0.0)) -> float:
    np = _np()

    def coupled_rhs(t: float, state):
        x, velocity, dx, dv = state
        acceleration = x - x**3 - 0.2 * velocity + 0.3 * math.cos(1.2 * t)
        tangent_acceleration = (1.0 - 3.0 * x**2) * dx - 0.2 * dv
        return (velocity, acceleration, dv, tangent_acceleration)

    state = np.asarray([initial[0], initial[1], 1.0, 0.0], dtype=float)
    steps = int(round(duration / dt))
    burn_steps = int(0.2 * steps)
    renormalize_every = max(1, int(round(0.5 / dt)))
    time_value = 0.0
    log_growth = 0.0
    samples = 0
    for index in range(steps):
        state = _rk4_step(coupled_rhs, time_value, state, dt)
        time_value += dt
        if (index + 1) % renormalize_every != 0:
            continue
        norm = float(np.linalg.norm(state[2:]))
        if norm <= 0:
            continue
        if index >= burn_steps:
            log_growth += math.log(norm)
            samples += 1
        state[2:] /= norm
    elapsed = samples * renormalize_every * dt
    return float(log_growth / elapsed) if elapsed > 0 else 0.0


def nonlinear_chaos_campaign(config: dict[str, Any], preset: str) -> dict[str, Any]:
    np = _np()
    dts = [float(v) for v in config["dts"]]
    duration = float(config["duration"])
    replicates = int(config["lyapunov_replicates"])
    cases: list[dict[str, Any]] = []
    indicators: list[float] = []
    balance_errors: list[float] = []

    for dt in dts:
        run = _duffing_run(dt, duration)
        indicators.append(float(run["indicator"]))
        balance_errors.append(float(run["energy_balance_relative_error"]))
        cases.append({"dt": dt, **run})

    indicator_change = abs(indicators[-1] - indicators[-2]) / max(
        abs(indicators[-1]), abs(indicators[-2]), 1e-12
    )
    lyapunov = [
        _duffing_lyapunov(dts[-1], duration, (0.1 + 1e-5 * index, 0.0))
        for index in range(replicates)
    ]
    mean_lyapunov = float(np.mean(lyapunov))
    lyapunov_spread = (
        float(np.std(lyapunov, ddof=1) / max(abs(mean_lyapunov), 1e-6))
        if replicates > 1
        else 0.0
    )
    cases.append({
        "finite_time_lyapunov_estimates": lyapunov,
        "mean": mean_lyapunov,
        "relative_spread": lyapunov_spread,
    })

    return _payload(
        "nonlinear-chaos",
        preset,
        config,
        {
            "indicator_timestep_relative_change": indicator_change,
            "lyapunov_relative_spread": lyapunov_spread,
            "energy_balance_relative_error": balance_errors[-1],
        },
        cases,
        [
            "Duffing reference: x'' + 0.2 x' - x + x^3 = 0.3 cos(1.2 t), integrated with RK4.",
            "Timestep convergence targets a finite Poincare-response indicator rather than pointwise long-time trajectory agreement.",
            "Finite-time Lyapunov estimates use tangent dynamics and periodic renormalization; their spread is finite-window evidence.",
            "Energy/work closure checks dE/dt = -0.2 v^2 + 0.3 v cos(1.2 t).",
        ],
    )


# ---------------------------------------------------------------------------
# Oscillation / Numerical Integration
# ---------------------------------------------------------------------------

def _oscillator_rhs(omega_n: float, zeta: float):
    def rhs(_t: float, state):
        x, velocity = state
        return (velocity, -2.0 * zeta * omega_n * velocity - omega_n**2 * x)
    return rhs


def _oscillator_exact(time_value: float, omega_n: float, zeta: float) -> tuple[float, float]:
    omega_d = omega_n * math.sqrt(1.0 - zeta**2)
    decay = zeta * omega_n
    envelope = math.exp(-decay * time_value)
    x = envelope * (
        math.cos(omega_d * time_value)
        + (decay / omega_d) * math.sin(omega_d * time_value)
    )
    velocity = -(omega_n**2 / omega_d) * envelope * math.sin(omega_d * time_value)
    return x, velocity


def _oscillator_run(dt: float, duration: float, omega_n: float = 2.0, zeta: float = 0.05) -> dict[str, Any]:
    np = _np()
    rhs = _oscillator_rhs(omega_n, zeta)
    steps = int(round(duration / dt))
    state = np.asarray([1.0, 0.0], dtype=float)
    times: list[float] = []
    x_values: list[float] = []
    v_values: list[float] = []
    energy: list[float] = []
    dissipation: list[float] = []
    time_value = 0.0

    for index in range(steps + 1):
        x, velocity = state
        times.append(time_value)
        x_values.append(float(x))
        v_values.append(float(velocity))
        energy.append(0.5 * velocity**2 + 0.5 * omega_n**2 * x**2)
        dissipation.append(2.0 * zeta * omega_n * velocity**2)
        if index < steps:
            state = _rk4_step(rhs, time_value, state, dt)
            time_value += dt

    t = np.asarray(times, dtype=float)
    x = np.asarray(x_values, dtype=float)
    v = np.asarray(v_values, dtype=float)
    exact = np.asarray([_oscillator_exact(float(tt), omega_n, zeta) for tt in t])
    amplitude_error = float(np.max(np.abs(x - exact[:, 0])) / max(np.max(np.abs(exact[:, 0])), 1e-12))

    crossing_indices = np.where((x[:-1] > 0) & (x[1:] <= 0))[0]
    crossings: list[float] = []
    for index in crossing_indices:
        fraction = x[index] / (x[index] - x[index + 1]) if x[index] != x[index + 1] else 0.0
        crossings.append(float(t[index] + fraction * dt))
    omega_d = omega_n * math.sqrt(1.0 - zeta**2)
    observed_frequency = (
        2.0 * math.pi / float(np.mean(np.diff(crossings)))
        if len(crossings) >= 2
        else float("nan")
    )
    frequency_error = abs(observed_frequency - omega_d) / omega_d

    final_time = float(t[-1])
    decay = zeta * omega_n
    exact_x, exact_v = map(float, exact[-1])
    final_x = float(x[-1])
    final_v = float(v[-1])

    def phase(position: float, velocity: float) -> float:
        q = math.exp(decay * final_time) * position
        qdot = math.exp(decay * final_time) * (velocity + decay * position)
        return math.atan2(-qdot / omega_d, q)

    phase_error = (phase(final_x, final_v) - phase(exact_x, exact_v) + math.pi) % (2.0 * math.pi) - math.pi
    energy_array = np.asarray(energy, dtype=float)
    dissipation_array = np.asarray(dissipation, dtype=float)
    dissipated_work = float(np.trapezoid(dissipation_array, t))
    balance_error = abs((energy_array[-1] - energy_array[0]) + dissipated_work) / max(abs(energy_array[0]), 1e-12)
    final_state_error = math.hypot(final_x - exact_x, (final_v - exact_v) / omega_n)

    return {
        "frequency_relative_error": frequency_error,
        "amplitude_relative_error": amplitude_error,
        "phase_error_rad": abs(phase_error),
        "energy_balance_relative_error": balance_error,
        "final_state_error": float(final_state_error),
        "final_state": [final_x, final_v],
        "steps": steps,
    }


def oscillation_campaign(config: dict[str, Any], preset: str) -> dict[str, Any]:
    dts = [float(v) for v in config["dts"]]
    duration = float(config["duration"])
    cases = [{"dt": dt, **_oscillator_run(dt, duration)} for dt in dts]
    fine = cases[-1]
    previous = cases[-2]
    delta_x = float(fine["final_state"][0]) - float(previous["final_state"][0])
    delta_v_scaled = (float(fine["final_state"][1]) - float(previous["final_state"][1])) / 2.0
    timestep_change = math.hypot(delta_x, delta_v_scaled)
    return _payload(
        "oscillation-integration",
        preset,
        config,
        {
            "frequency_relative_error": float(fine["frequency_relative_error"]),
            "amplitude_relative_error": float(fine["amplitude_relative_error"]),
            "phase_error_rad": float(fine["phase_error_rad"]),
            "energy_balance_relative_error": float(fine["energy_balance_relative_error"]),
            "timestep_relative_change": timestep_change,
        },
        cases,
        [
            "Reference is an underdamped oscillator with omega_n=2 rad/s, zeta=0.05, x(0)=1 and v(0)=0.",
            "RK4 is compared with the closed-form solution; frequency uses linearly interpolated zero crossings.",
            "Energy closure compares mechanical-energy loss with integrated viscous dissipation.",
        ],
    )


CAMPAIGNS: dict[str, Callable[[dict[str, Any], str], dict[str, Any]]] = {
    "numerical-methods": numerical_campaign,
    "ising-monte-carlo": ising_campaign,
    "random-walk-monte-carlo": random_walk_campaign,
    "nonlinear-chaos": nonlinear_chaos_campaign,
    "oscillation-integration": oscillation_campaign,
}


def run_campaign(
    profile: str,
    preset: str = "compact",
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if profile not in CAMPAIGNS:
        raise ValueError(f"unsupported campaign profile: {profile}")
    if preset not in PRESETS:
        raise ValueError(f"unsupported campaign preset: {preset}")
    config = dict(PRESETS[preset][profile])
    if overrides:
        config.update(overrides)
    return CAMPAIGNS[profile](config, preset)


def canonical_session_metrics(result: dict[str, Any]) -> dict[str, float]:
    return {str(key): _finite(value) for key, value in (result.get("metrics") or {}).items()}


def reference_validation_payload() -> dict[str, Any]:
    profiles = {}
    for profile in SUPPORTED_PROFILES:
        result = run_campaign(profile, "compact")
        profiles[profile] = {
            "campaign_sha256": result["campaign_sha256"],
            "metrics": result["metrics"],
            "case_count": len(result["cases"]),
        }
    return {"schema": "physical-lab-model-campaign-reference-v1", "profiles": profiles}


def render_model_campaign(st: Any, profile: str, namespace: dict[str, Any] | None = None) -> None:
    """Render a one-click campaign and publish its canonical scorecard metrics."""
    if profile not in SUPPORTED_PROFILES:
        return
    import pandas as pd

    titles = {
        "numerical-methods": "Numerical Accuracy / Cost Campaign",
        "ising-monte-carlo": "Multi-Chain Sampling Campaign",
        "random-walk-monte-carlo": "Multi-Seed Estimator Campaign",
        "nonlinear-chaos": "Nonlinear Robustness Campaign",
        "oscillation-integration": "Dynamic-System Convergence Campaign",
    }
    st.markdown("---")
    st.markdown(f"## Physical Lab · {titles[profile]}")
    st.caption(
        "Run a bounded refinement/replicate study and publish canonical metrics to the existing Engineering scorecard. "
        "Compact is intended for interactive checks; Standard is deeper but remains bounded."
    )
    left, right = st.columns([2, 1])
    preset = left.selectbox(
        "Campaign depth", ["compact", "standard"], index=0,
        key=f"pl_campaign_preset_{profile}",
    )
    should_run = right.button(
        "Run engineering campaign", type="primary", width="stretch",
        key=f"pl_campaign_run_{profile}",
    )
    result_key = f"pl_model_campaign_result_{profile}"
    if should_run:
        started = time.perf_counter()
        try:
            with st.spinner(f"Running {titles[profile]}..."):
                result = run_campaign(profile, preset)
            result["observed_runtime_s"] = time.perf_counter() - started
            st.session_state[result_key] = result
            st.success("Campaign complete. Engineering scorecard metrics were refreshed.")
        except Exception as exc:
            st.error(f"Campaign failed: {exc}")

    result = st.session_state.get(result_key)
    if not isinstance(result, dict):
        st.info("No automated campaign has been run in this session yet.")
        return

    metrics = canonical_session_metrics(result)
    st.session_state[f"pl_model_campaign_metrics_{profile}"] = metrics
    columns = st.columns(min(5, max(1, len(metrics))))
    for index, (name, value) in enumerate(metrics.items()):
        columns[index % len(columns)].metric(name.replace("_", " "), f"{value:.6g}")

    st.caption(
        f"Campaign fingerprint: {str(result.get('campaign_sha256', ''))[:16]} · "
        f"runtime: {float(result.get('observed_runtime_s', 0.0)):.3f} s · "
        f"preset: {result.get('preset', '—')}"
    )
    cases = result.get("cases") or []
    if cases:
        try:
            st.dataframe(pd.json_normalize(cases), width="stretch", hide_index=True)
        except Exception:
            st.json(cases)
    for note in result.get("notes") or []:
        st.caption(f"• {note}")
    st.caption(str(result.get("boundary", "")))
    st.download_button(
        "Export campaign JSON",
        data=json.dumps(result, indent=2, allow_nan=False).encode("utf-8"),
        file_name=f"physical-lab-{profile}-{result.get('preset', 'campaign')}.json",
        mime="application/json",
        key=f"pl_campaign_export_{profile}",
    )
