"""Automated engineering campaigns for Physical Lab's five non-accelerator models.

Each campaign executes a deterministic, bounded solver study and emits canonical
metrics consumed by physical_lab_model_engineering.py. The campaigns are
engineering screening/verification tools, not experimental validation or
certification.
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

PRESETS = {
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


def _finite(x: Any) -> float:
    y = float(x)
    if not math.isfinite(y):
        raise ValueError("non-finite campaign metric")
    return y


def _fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _linear_regression_slope(x, y) -> float:
    np = _np()
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    xm = float(np.mean(x)); ym = float(np.mean(y))
    denom = float(np.sum((x - xm) ** 2))
    if denom == 0:
        raise ValueError("degenerate regression axis")
    return float(np.sum((x - xm) * (y - ym)) / denom)


def _autocorrelation_ess(values) -> float:
    """Initial-positive-sequence ESS estimate for one scalar chain."""
    np = _np()
    x = np.asarray(values, dtype=float)
    n = int(x.size)
    if n < 4:
        return float(n)
    x = x - float(np.mean(x))
    var = float(np.dot(x, x) / n)
    if var <= 0:
        return float(n)
    max_lag = min(n // 2, 200)
    rho_sum = 0.0
    for lag in range(1, max_lag + 1):
        rho = float(np.dot(x[:-lag], x[lag:]) / ((n - lag) * var))
        if rho <= 0:
            break
        rho_sum += rho
    tau = max(1.0, 1.0 + 2.0 * rho_sum)
    return float(n / tau)


def _rhat(chains) -> float:
    np = _np()
    arr = np.asarray(chains, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2 or arr.shape[1] < 4:
        raise ValueError("R-hat requires at least two chains with four samples")
    _, n = arr.shape
    means = np.mean(arr, axis=1)
    variances = np.var(arr, axis=1, ddof=1)
    W = float(np.mean(variances))
    if W <= 0:
        return 1.0
    B = float(n * np.var(means, ddof=1))
    var_hat = ((n - 1) / n) * W + B / n
    return float(math.sqrt(max(var_hat / W, 0.0)))


def _score_payload(profile: str, preset: str, config: dict[str, Any], metrics: dict[str, float], cases: list[dict[str, Any]], notes: list[str]) -> dict[str, Any]:
    clean_metrics = {k: _finite(v) for k, v in metrics.items()}
    identity = {"profile": profile, "preset": preset, "config": config}
    return {
        "schema": "physical-lab-model-campaign-v1",
        "profile": profile,
        "preset": preset,
        "campaign_sha256": _fingerprint(identity),
        "config": config,
        "metrics": clean_metrics,
        "cases": cases,
        "notes": notes,
        "boundary": "Deterministic numerical/stochastic engineering screening; not experimental validation, product certification, or a population reliability claim.",
    }


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


def numerical_campaign(config: dict[str, Any], preset: str = "compact") -> dict[str, Any]:
    np = _np()
    grid = int(config["grid"]); tol = float(config["tol"])
    orders = [int(v) for v in config["orders"]]
    x = np.linspace(-math.pi, math.pi, grid)
    truth = np.sin(x)
    cases = []
    for terms in orders:
        started = time.perf_counter()
        approx = _sin_taylor(x, terms)
        err = np.abs(approx - truth)
        elapsed = time.perf_counter() - started
        cases.append({
            "terms": terms,
            "max_abs_error": float(np.max(err)),
            "rms_error": float(math.sqrt(float(np.mean(err ** 2)))),
            "pass_fraction": float(np.mean(err <= tol)),
            "evaluations": int(grid * terms),
            "runtime_s": elapsed,
        })
    final = cases[-1]
    hs = np.asarray([0.2, 0.1, 0.05, 0.025], dtype=float)
    point = 0.73
    derivative_errors = np.abs((np.sin(point + hs) - np.sin(point - hs)) / (2 * hs) - math.cos(point))
    p = math.log(float(derivative_errors[-2] / derivative_errors[-1])) / math.log(2.0)
    metrics = {
        "max_normalized_error": float(final["max_abs_error"] / tol),
        "pass_fraction": float(final["pass_fraction"]),
        "convergence_order": float(p),
    }
    notes = [
        "Taylor scan uses sin(x) on [-pi, pi] against NumPy/libm double-precision reference.",
        "Observed convergence order is independently measured from a centered finite-difference derivative refinement, expected to approach second order.",
        "Evaluation count is an algorithmic work proxy; wall-clock runtime is descriptive and machine-dependent.",
    ]
    return _score_payload("numerical-methods", preset, config, metrics, cases, notes)


def _ising_energy_per_spin(spins) -> float:
    np = _np()
    s = np.asarray(spins, dtype=int)
    return float(-np.sum(s * (np.roll(s, 1, axis=0) + np.roll(s, 1, axis=1))) / s.size)


def _ising_sweep(spins, beta: float, rng) -> None:
    L = spins.shape[0]
    for _ in range(L * L):
        i = int(rng.integers(L)); j = int(rng.integers(L))
        nn = spins[(i + 1) % L, j] + spins[(i - 1) % L, j] + spins[i, (j + 1) % L] + spins[i, (j - 1) % L]
        dE = 2 * spins[i, j] * nn
        if dE <= 0 or rng.random() < math.exp(-beta * dE):
            spins[i, j] *= -1


def _ising_chain(L: int, T: float, burn: int, samples: int, thin: int, seed: int):
    np = _np()
    rng = np.random.default_rng(seed)
    spins = rng.choice(np.asarray([-1, 1], dtype=int), size=(L, L))
    beta = 1.0 / T
    burn_trace = []
    for sweep in range(burn):
        _ising_sweep(spins, beta, rng)
        if sweep >= burn // 2:
            burn_trace.append(_ising_energy_per_spin(spins))
    energies = []
    mags = []
    for _ in range(samples):
        for __ in range(thin):
            _ising_sweep(spins, beta, rng)
        energies.append(_ising_energy_per_spin(spins))
        mags.append(float(abs(np.mean(spins))))
    return np.asarray(energies), np.asarray(mags), np.asarray(burn_trace)


def _exact_ising_energy_4x4(T: float) -> float:
    """Exact canonical <E>/spin for 4x4 periodic zero-field Ising by enumeration."""
    np = _np()
    L = 4; n = L * L; beta = 1.0 / T
    energies = np.empty(1 << n, dtype=float)
    for state in range(1 << n):
        bits = ((state >> np.arange(n)) & 1).astype(int)
        s = (2 * bits - 1).reshape(L, L)
        energies[state] = -np.sum(s * (np.roll(s, 1, axis=0) + np.roll(s, 1, axis=1)))
    e0 = float(np.min(energies))
    weights = np.exp(-beta * (energies - e0))
    return float(np.sum(energies * weights) / np.sum(weights) / n)


def ising_campaign(config: dict[str, Any], preset: str = "compact") -> dict[str, Any]:
    np = _np()
    L = int(config["L"]); T = float(config["temperature"])
    chains = int(config["chains"]); burn = int(config["burn"]); samples = int(config["samples"]); thin = int(config["thin"])
    energy_chains = []; mag_chains = []; drift_scores = []; cases = []
    for c in range(chains):
        e, m, btrace = _ising_chain(L, T, burn, samples, thin, 20260904 + 97 * c)
        energy_chains.append(e); mag_chains.append(m)
        if btrace.size >= 8:
            half = btrace.size // 2
            a = btrace[:half]; b = btrace[-half:]
            pooled = float(np.std(btrace, ddof=1))
            drift_scores.append(abs(float(np.mean(a) - np.mean(b))) / max(pooled, 1e-12))
        cases.append({"chain": c, "mean_energy_per_spin": float(np.mean(e)), "mean_abs_magnetization": float(np.mean(m)), "ess_energy": _autocorrelation_ess(e), "ess_abs_magnetization": _autocorrelation_ess(m)})
    earr = np.asarray(energy_chains); marr = np.asarray(mag_chains)
    rhat_energy = _rhat(earr); rhat_mag = _rhat(marr)
    energy_ess_total = sum(_autocorrelation_ess(e) for e in earr)
    magnetization_ess_total = sum(_autocorrelation_ess(m) for m in marr)
    exact_T = 3.0
    exact = _exact_ising_energy_4x4(exact_T)
    exact_samples = int(config.get("exact_samples", 1600))
    exact_chains = []
    for c in range(4):
        e, _, _ = _ising_chain(4, exact_T, max(200, burn // 2), exact_samples, 1, 9901 + c)
        exact_chains.append(float(np.mean(e)))
    observed = float(np.mean(exact_chains))
    exact_rel = abs(observed - exact) / max(abs(exact), 1e-12)
    metrics = {
        "rhat_max": max(rhat_energy, rhat_mag),
        "effective_samples_min": min(energy_ess_total, magnetization_ess_total),
        "exact_reference_relative_error": exact_rel,
        "equilibration_drift_sigma": max(drift_scores) if drift_scores else 0.0,
    }
    cases.append({"checkpoint": "exact-4x4", "temperature": exact_T, "exact_energy_per_spin": exact, "observed_energy_per_spin": observed, "relative_error": exact_rel})
    notes = [
        "R-hat is the classical between/within-chain variance diagnostic on scalar energy and |magnetization| traces; it is finite-sample evidence, not proof of convergence.",
        "ESS uses an initial-positive autocorrelation sum and is reported as the minimum total effective sample count across energy and |magnetization|.",
        "Exact-reference checkpoint enumerates all 2^16 states of a periodic 4x4 zero-field Ising lattice at T=3.0.",
    ]
    return _score_payload("ising-monte-carlo", preset, config, metrics, cases, notes)


def random_walk_campaign(config: dict[str, Any], preset: str = "compact") -> dict[str, Any]:
    np = _np()
    reps = int(config["replicates"]); walkers = int(config["walkers"]); step_counts = [int(x) for x in config["steps"]]
    max_steps = max(step_counts)
    replicate_estimators = []; all_msd = []; cases = []
    for rep in range(reps):
        rng = np.random.default_rng(44000 + rep)
        x = np.zeros(walkers, dtype=int); y = np.zeros(walkers, dtype=int)
        msd = []; checkpoints = set(step_counts)
        for step in range(1, max_steps + 1):
            directions = rng.integers(0, 4, size=walkers)
            x += (directions == 0).astype(int) - (directions == 1).astype(int)
            y += (directions == 2).astype(int) - (directions == 3).astype(int)
            if step in checkpoints:
                msd.append(float(np.mean(x * x + y * y)))
        all_msd.append(msd)
        replicate_estimators.append(msd[-1] / max_steps)
        cases.append({"replicate": rep, "seed": 44000 + rep, "final_msd": msd[-1], "diffusion_scale_estimate": replicate_estimators[-1]})
    mean_msd = np.mean(np.asarray(all_msd, dtype=float), axis=0)
    slope = _linear_regression_slope(np.log(step_counts), np.log(mean_msd))
    estimator = float(np.mean(replicate_estimators))
    cv = float(np.std(replicate_estimators, ddof=1) / abs(estimator)) if reps > 1 and estimator != 0 else 0.0
    metrics = {
        "msd_exponent_error": abs(slope - 1.0),
        "estimator_relative_error": abs(estimator - 1.0),
        "replicate_cv": cv,
    }
    cases.append({"aggregate": "MSD scaling", "steps": step_counts, "mean_msd": [float(v) for v in mean_msd], "fitted_exponent": slope, "mean_diffusion_scale_estimate": estimator})
    notes = [
        "The walk is a 2D unbiased nearest-neighbor lattice walk with unit step length, so E[r^2]=N and the expected MSD exponent is 1.",
        "Independent seeds quantify finite-replicate stability; replicate CV is descriptive, not a population failure probability.",
        "The final MSD/N ratio is used as the estimator with theoretical target 1.",
    ]
    return _score_payload("random-walk-monte-carlo", preset, config, metrics, cases, notes)


def _duffing_rhs(t: float, state, delta=0.2, gamma=0.3, omega=1.2):
    x, v = state
    return (v, x - x * x * x - delta * v + gamma * math.cos(omega * t))


def _rk4_step(rhs: Callable, t: float, state, dt: float):
    np = _np()
    y = np.asarray(state, dtype=float)
    k1 = np.asarray(rhs(t, y), dtype=float)
    k2 = np.asarray(rhs(t + 0.5 * dt, y + 0.5 * dt * k1), dtype=float)
    k3 = np.asarray(rhs(t + 0.5 * dt, y + 0.5 * dt * k2), dtype=float)
    k4 = np.asarray(rhs(t + dt, y + dt * k3), dtype=float)
    return y + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)


def _duffing_run(dt: float, duration: float, initial=(0.1, 0.0)):
    np = _np()
    n = int(round(duration / dt)); state = np.asarray(initial, dtype=float); t = 0.0
    energies = []; powers = []; times = []; poincare = []
    drive_period = 2 * math.pi / 1.2; next_sample = drive_period
    for _ in range(n):
        x, v = state
        E = 0.5 * v * v - 0.5 * x * x + 0.25 * x ** 4
        power = -0.2 * v * v + 0.3 * v * math.cos(1.2 * t)
        energies.append(E); powers.append(power); times.append(t)
        if t >= next_sample:
            poincare.append(float(x)); next_sample += drive_period
        state = _rk4_step(_duffing_rhs, t, state, dt); t += dt
    x, v = state
    E_final = 0.5 * v * v - 0.5 * x * x + 0.25 * x ** 4
    times = np.asarray(times); powers = np.asarray(powers)
    work = float(np.trapz(powers, times)) if len(times) > 1 else 0.0
    balance = abs((E_final - energies[0]) - work) / max(abs(work), abs(E_final - energies[0]), 1e-9)
    p = np.asarray(poincare, dtype=float)
    indicator = float(np.std(p[-max(4, len(p) // 2):])) if p.size else 0.0
    return {"indicator": indicator, "energy_balance_relative_error": balance, "final_state": [float(z) for z in state], "poincare_points": int(p.size)}


def _duffing_lyapunov(dt: float, duration: float, initial=(0.1, 0.0)) -> float:
    """Finite-time largest Lyapunov estimate using tangent dynamics + renormalization."""
    np = _np(); delta = 0.2
    state = np.asarray(initial, dtype=float); tangent = np.asarray([1.0, 0.0], dtype=float)
    t = 0.0; accum = 0.0; renorm_every = max(1, int(round(0.5 / dt))); count = 0
    def coupled_rhs(tt, yy):
        x, v, dx, dv = yy
        ax = x - x * x * x - delta * v + 0.3 * math.cos(1.2 * tt)
        dax = (1 - 3 * x * x) * dx - delta * dv
        return (v, ax, dv, dax)
    y = np.concatenate([state, tangent]); n = int(round(duration / dt)); burn_steps = int(0.2 * n)
    for i in range(n):
        y = _rk4_step(coupled_rhs, t, y, dt); t += dt
        if (i + 1) % renorm_every == 0:
            norm = float(np.linalg.norm(y[2:]))
            if norm <= 0:
                continue
            if i >= burn_steps:
                accum += math.log(norm); count += 1
            y[2:] /= norm
    elapsed = count * renorm_every * dt
    return float(accum / elapsed) if elapsed > 0 else 0.0


def nonlinear_chaos_campaign(config: dict[str, Any], preset: str = "compact") -> dict[str, Any]:
    np = _np()
    dts = [float(v) for v in config["dts"]]; duration = float(config["duration"]); reps = int(config["lyapunov_replicates"])
    runs = []; indicators = []; balances = []
    for dt in dts:
        run = _duffing_run(dt, duration)
        indicators.append(run["indicator"]); balances.append(run["energy_balance_relative_error"])
        runs.append({"dt": dt, **run})
    a, b = indicators[-2], indicators[-1]
    indicator_change = abs(b - a) / max(abs(a), abs(b), 1e-12)
    lyaps = []
    for i in range(reps):
        lyaps.append(_duffing_lyapunov(dts[-1], duration, (0.1 + 1e-5 * i, 0.0)))
    mean_l = float(np.mean(lyaps))
    spread = float(np.std(lyaps, ddof=1) / max(abs(mean_l), 1e-6)) if reps > 1 else 0.0
    metrics = {
        "indicator_timestep_relative_change": indicator_change,
        "lyapunov_relative_spread": spread,
        "energy_balance_relative_error": balances[-1],
    }
    runs.append({"finite_time_lyapunov_estimates": lyaps, "mean": mean_l, "relative_spread": spread})
    notes = [
        "Duffing equation: x'' + 0.2 x' - x + x^3 = 0.3 cos(1.2 t), integrated with RK4.",
        "Timestep convergence uses a finite Poincare-response spread indicator, not pointwise long-time trajectory agreement.",
        "Finite-time Lyapunov estimates use tangent dynamics with periodic renormalization; replicate spread is descriptive and window-dependent.",
        "Energy/work balance checks dE/dt = -0.2 v^2 + 0.3 v cos(1.2 t).",
    ]
    return _score_payload("nonlinear-chaos", preset, config, metrics, runs, notes)


def _osc_rhs_factory(wn: float, zeta: float):
    def rhs(t, state):
        x, v = state
        return (v, -2 * zeta * wn * v - wn * wn * x)
    return rhs


def _osc_exact(t, wn: float, zeta: float):
    wd = wn * math.sqrt(1 - zeta * zeta); a = zeta * wn
    x = math.exp(-a * t) * (math.cos(wd * t) + (a / wd) * math.sin(wd * t))
    v = -(wn * wn / wd) * math.exp(-a * t) * math.sin(wd * t)
    return x, v


def _osc_run(dt: float, duration: float, wn=2.0, zeta=0.05):
    np = _np(); rhs = _osc_rhs_factory(wn, zeta)
    n = int(round(duration / dt)); state = np.asarray([1.0, 0.0]); t = 0.0
    xs = []; vs = []; ts = []; energies = []; diss = []
    for i in range(n + 1):
        x, v = state
        xs.append(float(x)); vs.append(float(v)); ts.append(t)
        energies.append(0.5 * v * v + 0.5 * wn * wn * x * x)
        diss.append(2 * zeta * wn * v * v)
        if i < n:
            state = _rk4_step(rhs, t, state, dt); t += dt
    xs = np.asarray(xs); vs = np.asarray(vs); ts = np.asarray(ts); energies = np.asarray(energies); diss = np.asarray(diss)
    exact = np.asarray([_osc_exact(float(tt), wn, zeta) for tt in ts])
    amp_error = float(np.max(np.abs(xs - exact[:, 0])) / max(np.max(np.abs(exact[:, 0])), 1e-12))
    idx = np.where((xs[:-1] > 0) & (xs[1:] <= 0))[0]; crossings = []
    for i in idx:
        frac = xs[i] / (xs[i] - xs[i + 1]) if xs[i] != xs[i + 1] else 0.0
        crossings.append(float(ts[i] + frac * dt))
    freq = 2 * math.pi / float(np.mean(np.diff(crossings))) if len(crossings) >= 2 else float("nan")
    wd = wn * math.sqrt(1 - zeta * zeta); freq_err = abs(freq - wd) / wd
    tf = float(ts[-1]); x, v = float(xs[-1]), float(vs[-1]); xe, ve = map(float, exact[-1]); a = zeta * wn
    def phase(xx, vv):
        q = math.exp(a * tf) * xx
        qdot = math.exp(a * tf) * (vv + a * xx)
        return math.atan2(-qdot / wd, q)
    dphi = (phase(x, v) - phase(xe, ve) + math.pi) % (2 * math.pi) - math.pi
    work_loss = float(np.trapz(diss, ts))
    balance = abs((energies[-1] - energies[0]) + work_loss) / max(abs(energies[0]), 1e-12)
    final_err = float(math.hypot(x - xe, (v - ve) / wn))
    return {"frequency_relative_error": freq_err, "amplitude_relative_error": amp_error, "phase_error_rad": abs(dphi), "energy_balance_relative_error": balance, "final_state_error": final_err, "final_state": [x, v], "steps": n}


def oscillation_campaign(config: dict[str, Any], preset: str = "compact") -> dict[str, Any]:
    dts = [float(v) for v in config["dts"]]; duration = float(config["duration"])
    cases = [{"dt": dt, **_osc_run(dt, duration)} for dt in dts]
    fine = cases[-1]; prev = cases[-2]
    dx = fine["final_state"][0] - prev["final_state"][0]
    dv = (fine["final_state"][1] - prev["final_state"][1]) / 2.0
    timestep_change = math.hypot(dx, dv)
    metrics = {
        "frequency_relative_error": fine["frequency_relative_error"],
        "amplitude_relative_error": fine["amplitude_relative_error"],
        "phase_error_rad": fine["phase_error_rad"],
        "energy_balance_relative_error": fine["energy_balance_relative_error"],
        "timestep_relative_change": timestep_change,
    }
    notes = [
        "Underdamped oscillator x'' + 2*zeta*wn*x' + wn^2*x = 0 with wn=2 rad/s, zeta=0.05 and x(0)=1, v(0)=0.",
        "RK4 trajectory is compared with the closed-form underdamped solution; frequency is inferred from interpolated zero crossings.",
        "Energy balance checks mechanical-energy loss against integrated viscous dissipation.",
    ]
    return _score_payload("oscillation-integration", preset, config, metrics, cases, notes)


CAMPAIGNS = {
    "numerical-methods": numerical_campaign,
    "ising-monte-carlo": ising_campaign,
    "random-walk-monte-carlo": random_walk_campaign,
    "nonlinear-chaos": nonlinear_chaos_campaign,
    "oscillation-integration": oscillation_campaign,
}


def run_campaign(profile: str, preset: str = "compact", overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    if profile not in CAMPAIGNS:
        raise ValueError(f"unsupported campaign profile: {profile}")
    if preset not in PRESETS:
        raise ValueError(f"unsupported campaign preset: {preset}")
    config = dict(PRESETS[preset][profile])
    if overrides:
        config.update(overrides)
    return CAMPAIGNS[profile](config, preset=preset)


def canonical_session_metrics(result: dict[str, Any]) -> dict[str, float]:
    return {str(k): _finite(v) for k, v in (result.get("metrics") or {}).items()}


def reference_validation_payload() -> dict[str, Any]:
    out = {}
    for profile in SUPPORTED_PROFILES:
        result = run_campaign(profile, "compact")
        out[profile] = {"campaign_sha256": result["campaign_sha256"], "metrics": result["metrics"], "case_count": len(result["cases"])}
    return {"schema": "physical-lab-model-campaign-reference-v1", "profiles": out}


def render_model_campaign(st: Any, profile: str, namespace: dict[str, Any] | None = None) -> None:
    """Render one-click automated engineering campaigns and publish scorecard metrics."""
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
    st.caption("One command executes the profile's bounded refinement/replicate study and publishes canonical metrics to the Engineering scorecard. Compact is intended for interactive checks; Standard performs a deeper study.")
    c1, c2 = st.columns([2, 1])
    preset = c1.selectbox("Campaign depth", ["compact", "standard"], index=0, key=f"pl_campaign_preset_{profile}")
    run = c2.button("Run engineering campaign", type="primary", width="stretch", key=f"pl_campaign_run_{profile}")
    result_key = f"pl_model_campaign_result_{profile}"
    if run:
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
    cols = st.columns(min(5, max(1, len(metrics))))
    for i, (name, value) in enumerate(metrics.items()):
        cols[i % len(cols)].metric(name.replace("_", " "), f"{value:.6g}")
    st.caption(f"Campaign fingerprint: {str(result.get('campaign_sha256', ''))[:16]} · runtime: {float(result.get('observed_runtime_s', 0.0)):.3f} s · preset: {result.get('preset', '—')}")
    cases = result.get("cases") or []
    if cases:
        try:
            st.dataframe(pd.json_normalize(cases), width="stretch", hide_index=True)
        except Exception:
            st.json(cases)
    for note in result.get("notes") or []:
        st.caption(f"• {note}")
    st.caption(str(result.get("boundary", "")))
    st.download_button("Export campaign JSON", data=json.dumps(result, indent=2, allow_nan=False).encode("utf-8"), file_name=f"physical-lab-{profile}-{result.get('preset', 'campaign')}.json", mime="application/json", key=f"pl_campaign_export_{profile}")
