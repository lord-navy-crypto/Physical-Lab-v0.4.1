"""Kerr geodesic dynamics model for Physical Lab.

This module upgrades an earlier standalone Kerr-orbit script into a reusable,
verification-oriented model. It intentionally treats the standard Kerr
geodesic problem as an integrable relativistic dynamics benchmark rather than
as evidence of generic chaos.

Scientific scope:
- Boyer-Lindquist coordinates, geometric units G=c=M=1.
- Bound timelike geodesics parameterized by periapsis, apoapsis and polar
  turning angle.
- Spherical null geodesics with R(r0)=0 and dR/dr(r0)=0.
- Carter-Mino time integration.
- First-integral residuals, solver-refinement checks and a local radial
  instability exponent for spherical photon orbits.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

MODEL_SCHEMA = "physical-lab-kerr-geodesic-v1"
PROFILE = "nonlinear-chaos"
MASS = 1.0
MIN_DELTA = 1e-10


@dataclass(frozen=True)
class KerrOrbitConfig:
    spin: float
    inclination_deg: float
    particle_type: str
    periapsis: float = 6.5
    apoapsis: float = 10.0
    lam_max: float = 20.0
    samples: int = 2500
    rtol: float = 1e-9
    atol: float = 1e-11
    horizon_pad: float = 0.05

    def validate(self) -> None:
        if not (0.0 <= abs(float(self.spin)) < 1.0):
            raise ValueError("|a/M| must be < 1 for a Kerr black hole")
        if not (0.0 <= float(self.inclination_deg) < 89.5):
            raise ValueError("inclination must be in [0, 89.5) degrees")
        if self.particle_type not in {"massive", "photon"}:
            raise ValueError("particle_type must be 'massive' or 'photon'")
        if self.particle_type == "massive":
            if not (self.periapsis > horizon_radius(self.spin) + self.horizon_pad):
                raise ValueError("periapsis must remain outside the horizon guard")
            if not (self.apoapsis > self.periapsis):
                raise ValueError("apoapsis must be larger than periapsis")
        if not (self.lam_max > 0):
            raise ValueError("lam_max must be positive")
        if not (200 <= int(self.samples) <= 12000):
            raise ValueError("samples must be between 200 and 12000")
        if not (1e-13 <= float(self.rtol) <= 1e-3):
            raise ValueError("rtol outside supported range")
        if not (1e-15 <= float(self.atol) <= 1e-5):
            raise ValueError("atol outside supported range")


def delta(r: Any, a: float) -> Any:
    return np.asarray(r) ** 2 - 2.0 * MASS * np.asarray(r) + float(a) ** 2


def sigma(r: Any, theta: Any, a: float) -> Any:
    r_arr = np.asarray(r)
    th_arr = np.asarray(theta)
    return r_arr ** 2 + float(a) ** 2 * np.cos(th_arr) ** 2


def horizon_radius(a: float) -> float:
    disc = MASS * MASS - float(a) * float(a)
    if disc < 0:
        raise ValueError("|a/M| > 1 is not a Kerr black hole")
    return MASS + math.sqrt(max(disc, 0.0))


def theta_min_from_inclination(inclination_deg: float) -> float:
    theta_min = math.pi / 2.0 - math.radians(float(inclination_deg))
    return max(theta_min, math.radians(0.5))


def carter_q_from_theta_min(
    theta_min: float,
    a: float,
    energy: float,
    lz: float,
    mu: float,
) -> float:
    s = math.sin(theta_min)
    c = math.cos(theta_min)
    if abs(s) < 1e-14:
        raise ValueError("polar turning angle is too close to the coordinate axis")
    return c * c * (a * a * (mu * mu - energy * energy) + lz * lz / (s * s))


def radial_potential(
    r: Any,
    a: float,
    energy: float,
    lz: float,
    carter_q: float,
    mu: float,
) -> Any:
    r_arr = np.asarray(r)
    p = energy * (r_arr * r_arr + a * a) - a * lz
    return p * p - delta(r_arr, a) * (
        mu * mu * r_arr * r_arr + (lz - a * energy) ** 2 + carter_q
    )


def radial_potential_dr(
    r: Any,
    a: float,
    energy: float,
    lz: float,
    carter_q: float,
    mu: float,
) -> Any:
    r_arr = np.asarray(r)
    p = energy * (r_arr * r_arr + a * a) - a * lz
    dp = 2.0 * energy * r_arr
    ddel = 2.0 * r_arr - 2.0 * MASS
    term = mu * mu * r_arr * r_arr + (lz - a * energy) ** 2 + carter_q
    return 2.0 * p * dp - ddel * term - delta(r_arr, a) * (2.0 * mu * mu * r_arr)


def theta_potential(
    theta: Any,
    a: float,
    energy: float,
    lz: float,
    carter_q: float,
    mu: float,
) -> Any:
    th = np.asarray(theta)
    s = np.sin(th)
    c = np.cos(th)
    s2 = np.maximum(s * s, 1e-30)
    return carter_q - c * c * (
        a * a * (mu * mu - energy * energy) + lz * lz / s2
    )


def theta_potential_dtheta(
    theta: Any,
    a: float,
    energy: float,
    lz: float,
    carter_q: float,
    mu: float,
) -> Any:
    th = np.asarray(theta)
    s = np.sin(th)
    c = np.cos(th)
    s2 = np.maximum(s * s, 1e-30)
    bracket = a * a * (mu * mu - energy * energy) + lz * lz / s2
    dbracket = -2.0 * lz * lz * c / np.maximum(np.abs(s) ** 3, 1e-30)
    dbracket = np.where(s < 0, -dbracket, dbracket)
    return 2.0 * s * c * bracket - c * c * dbracket


def _safe_delta(r: Any, a: float) -> Any:
    d = np.asarray(delta(r, a), dtype=float)
    sign = np.where(d >= 0.0, 1.0, -1.0)
    return np.where(np.abs(d) < MIN_DELTA, sign * MIN_DELTA, d)


def mino_phi_rate(r: Any, theta: Any, a: float, energy: float, lz: float) -> Any:
    r_arr = np.asarray(r)
    th = np.asarray(theta)
    s2 = np.maximum(np.sin(th) ** 2, 1e-30)
    p = energy * (r_arr * r_arr + a * a) - a * lz
    return -(a * energy - lz / s2) + a * p / _safe_delta(r_arr, a)


def mino_t_rate(r: Any, theta: Any, a: float, energy: float, lz: float) -> Any:
    r_arr = np.asarray(r)
    th = np.asarray(theta)
    p = energy * (r_arr * r_arr + a * a) - a * lz
    return (
        (r_arr * r_arr + a * a) * p / _safe_delta(r_arr, a)
        + a * lz
        - a * a * energy * np.sin(th) ** 2
    )


def _scipy():
    try:
        from scipy.integrate import solve_ivp
        from scipy.optimize import root, brentq
    except Exception as exc:
        raise RuntimeError(
            "SciPy is required for the Kerr geodesic model. Install/repair the Chaos Lab environment."
        ) from exc
    return solve_ivp, root, brentq


def solve_massive_bound_constants(
    a: float,
    inclination_deg: float,
    periapsis: float,
    apoapsis: float,
) -> tuple[float, float, float]:
    _, root, _ = _scipy()
    theta_min = theta_min_from_inclination(inclination_deg)

    def equations(x: np.ndarray) -> np.ndarray:
        energy, lz = float(x[0]), float(x[1])
        q = carter_q_from_theta_min(theta_min, a, energy, lz, 1.0)
        return np.asarray(
            [
                radial_potential(periapsis, a, energy, lz, q, 1.0),
                radial_potential(apoapsis, a, energy, lz, q, 1.0),
            ],
            dtype=float,
        )

    seeds = (
        (0.95, 3.0 - 0.35 * a),
        (0.97, 3.6 - 0.55 * a),
        (0.92, 2.5 - 0.2 * a),
        (0.99, 4.2 - 0.7 * a),
    )
    candidates: list[tuple[float, float, float, float]] = []
    for seed in seeds:
        sol = root(equations, seed, method="hybr", tol=1e-12, options={"maxfev": 6000})
        if not sol.success:
            continue
        energy, lz = map(float, sol.x)
        q = float(carter_q_from_theta_min(theta_min, a, energy, lz, 1.0))
        residual = float(np.linalg.norm(equations(np.asarray([energy, lz]))))
        if 0.0 < energy < 1.0 and q >= -1e-9 and np.isfinite(residual):
            candidates.append((residual, energy, lz, max(q, 0.0)))
    if not candidates:
        raise RuntimeError("No physical bound-orbit root converged for the selected parameters")
    _, energy, lz, q = min(candidates, key=lambda row: row[0])
    return energy, lz, q


def solve_photon_spherical_constants(
    a: float,
    inclination_deg: float,
) -> tuple[float, float, float, float]:
    _, root, brentq = _scipy()
    theta_min = theta_min_from_inclination(inclination_deg)
    energy = 1.0
    mu = 0.0

    if abs(a) < 1e-10:
        r0 = 3.0 * MASS
        lz = 3.0 * math.sqrt(3.0) * math.sin(theta_min)
        q = 27.0 * math.cos(theta_min) ** 2
        return energy, lz, q, r0

    def equations(x: np.ndarray) -> np.ndarray:
        r0, lz = map(float, x)
        q = carter_q_from_theta_min(theta_min, a, energy, lz, mu)
        return np.asarray(
            [
                radial_potential(r0, a, energy, lz, q, mu),
                radial_potential_dr(r0, a, energy, lz, q, mu),
            ],
            dtype=float,
        )

    def spherical_xi_eta(r0: float) -> tuple[float, float]:
        denom_xi = a * (MASS - r0)
        denom_eta = a * a * (r0 - MASS) ** 2
        if abs(denom_xi) < 1e-14 or abs(denom_eta) < 1e-14:
            return float("nan"), float("nan")
        xi = (
            r0 ** 3 - 3.0 * MASS * r0 ** 2 + a * a * r0 + a * a * MASS
        ) / denom_xi
        eta = (
            r0 ** 3
            * (4.0 * a * a * MASS - r0 * (r0 - 3.0 * MASS) ** 2)
            / denom_eta
        )
        return float(xi), float(eta)

    def inclination_residual(r0: float) -> float:
        xi, eta = spherical_xi_eta(float(r0))
        if not (np.isfinite(xi) and np.isfinite(eta)):
            return float("nan")
        q_from_inc = carter_q_from_theta_min(theta_min, a, energy, xi, mu)
        return float(eta - q_from_inc)

    rh = horizon_radius(a)
    grid = np.linspace(rh + 1e-5, 6.0 * MASS, 3000)
    vals = np.asarray([inclination_residual(float(x)) for x in grid], dtype=float)
    roots: list[tuple[float, float, float, float]] = []
    for i in range(len(grid) - 1):
        f0, f1 = vals[i], vals[i + 1]
        if not (np.isfinite(f0) and np.isfinite(f1)):
            continue
        if f0 == 0.0:
            r0 = float(grid[i])
        elif f0 * f1 > 0.0:
            continue
        else:
            try:
                r0 = float(
                    brentq(
                        inclination_residual,
                        float(grid[i]),
                        float(grid[i + 1]),
                        xtol=1e-13,
                    )
                )
            except Exception:
                continue
        lz, q = spherical_xi_eta(r0)
        if q < -1e-8:
            continue
        residual = float(np.linalg.norm(equations(np.asarray([r0, lz], dtype=float))))
        roots.append((residual, r0, lz, max(q, 0.0)))

    prograde = [row for row in roots if row[2] > 0.0]
    candidates = prograde or roots
    if not candidates:
        schwarz_lz = 3.0 * math.sqrt(3.0) * math.sin(theta_min)
        seeds = (
            (3.0, schwarz_lz - a),
            (2.3, schwarz_lz - 1.5 * a),
            (3.5, -schwarz_lz - a),
        )
        fallback: list[tuple[float, float, float, float]] = []
        for seed in seeds:
            sol = root(equations, seed, method="hybr", tol=1e-12, options={"maxfev": 8000})
            if not sol.success:
                continue
            r0, lz = map(float, sol.x)
            q = float(carter_q_from_theta_min(theta_min, a, energy, lz, mu))
            residual = float(np.linalg.norm(equations(np.asarray([r0, lz]))))
            if r0 > rh + 1e-5 and q >= -1e-8 and np.isfinite(residual):
                fallback.append((residual, r0, lz, max(q, 0.0)))
        candidates = [row for row in fallback if row[2] > 0.0] or fallback
    if not candidates:
        raise RuntimeError("No physical spherical-photon root converged for the selected parameters")
    _, r0, lz, q = min(candidates, key=lambda row: row[0])
    return energy, lz, q, r0


def build_case(config: KerrOrbitConfig) -> dict[str, Any]:
    config.validate()
    a = float(config.spin)
    theta_min = theta_min_from_inclination(config.inclination_deg)
    if config.particle_type == "massive":
        energy, lz, q = solve_massive_bound_constants(
            a, config.inclination_deg, config.periapsis, config.apoapsis
        )
        mu = 1.0
        r0 = float(config.apoapsis)
        pr0 = 0.0
    else:
        energy, lz, q, r0 = solve_photon_spherical_constants(a, config.inclination_deg)
        mu = 0.0
        pr0 = 0.0

    theta0 = math.pi / 2.0
    theta_value = float(theta_potential(theta0, a, energy, lz, q, mu))
    if theta_value < -1e-8:
        raise RuntimeError("selected constants produce a negative polar potential at the start")
    ptheta0 = math.sqrt(max(theta_value, 0.0))
    y0 = np.asarray([0.0, r0, theta0, 0.0, pr0, ptheta0], dtype=float)
    return {
        "schema": MODEL_SCHEMA,
        "a": a,
        "inclination_deg": float(config.inclination_deg),
        "theta_min": theta_min,
        "particle_type": config.particle_type,
        "mu": mu,
        "E": float(energy),
        "Lz": float(lz),
        "Q": float(q),
        "r0": float(r0),
        "y0": y0,
    }


def geodesic_rhs(
    lam: float,
    y: np.ndarray,
    a: float,
    energy: float,
    lz: float,
    carter_q: float,
    mu: float,
) -> np.ndarray:
    del lam
    r = float(y[1])
    theta = float(y[2])
    pr = float(y[4])
    ptheta = float(y[5])
    return np.asarray(
        [
            float(mino_t_rate(r, theta, a, energy, lz)),
            pr,
            ptheta,
            float(mino_phi_rate(r, theta, a, energy, lz)),
            0.5 * float(radial_potential_dr(r, a, energy, lz, carter_q, mu)),
            0.5 * float(theta_potential_dtheta(theta, a, energy, lz, carter_q, mu)),
        ],
        dtype=float,
    )


def _first_integral_residuals(case: dict[str, Any], y: np.ndarray) -> dict[str, float]:
    a, e, lz, q, mu = (case["a"], case["E"], case["Lz"], case["Q"], case["mu"])
    r, th, pr, pth = y[1], y[2], y[4], y[5]
    rr = np.asarray(radial_potential(r, a, e, lz, q, mu), dtype=float)
    tt = np.asarray(theta_potential(th, a, e, lz, q, mu), dtype=float)
    r_scale = np.maximum(1.0, np.abs(rr) + np.abs(pr * pr))
    t_scale = np.maximum(1.0, np.abs(tt) + np.abs(pth * pth))
    r_res = np.abs(pr * pr - rr) / r_scale
    t_res = np.abs(pth * pth - tt) / t_scale
    return {
        "radial_max": float(np.nanmax(r_res)),
        "polar_max": float(np.nanmax(t_res)),
        "combined_max": float(np.nanmax(np.maximum(r_res, t_res))),
    }


def integrate_case(config: KerrOrbitConfig) -> dict[str, Any]:
    solve_ivp, _, _ = _scipy()
    case = build_case(config)
    r_horizon = horizon_radius(case["a"])

    def horizon_event(lam: float, y: np.ndarray, *args: Any) -> float:
        del lam, args
        return float(y[1] - (r_horizon + config.horizon_pad))

    horizon_event.terminal = True
    horizon_event.direction = -1

    sol = solve_ivp(
        geodesic_rhs,
        (0.0, float(config.lam_max)),
        case["y0"],
        method="RK45",
        rtol=float(config.rtol),
        atol=float(config.atol),
        dense_output=True,
        events=(horizon_event,),
        args=(case["a"], case["E"], case["Lz"], case["Q"], case["mu"]),
        max_step=max(float(config.lam_max) / 500.0, 1e-4),
    )
    if sol.sol is None:
        raise RuntimeError("integrator did not provide a dense solution")
    lam_end = float(sol.t[-1])
    lam = np.linspace(0.0, lam_end, int(config.samples))
    y = np.asarray(sol.sol(lam), dtype=float)
    horizon_hit = bool(sol.t_events and len(sol.t_events[0]))
    if sol.status < 0:
        status = f"failed: {sol.message}"
    elif horizon_hit:
        status = "horizon-guard"
    else:
        status = "completed"

    residuals = _first_integral_residuals(case, y)
    diagnostics = orbit_diagnostics(case, lam, y)
    return {
        "schema": MODEL_SCHEMA,
        "case": case,
        "lambda": lam,
        "state": y,
        "status": status,
        "solver_message": str(sol.message),
        "nfev": int(sol.nfev),
        "residuals": residuals,
        "diagnostics": diagnostics,
    }


def _turning_indices(values: np.ndarray, *, kind: str) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if values.size < 5:
        return np.asarray([], dtype=int)
    left = values[1:-1] - values[:-2]
    right = values[2:] - values[1:-1]
    if kind == "min":
        mask = (left < 0.0) & (right > 0.0)
    else:
        mask = (left > 0.0) & (right < 0.0)
    return np.flatnonzero(mask) + 1


def _period_from_indices(lam: np.ndarray, indices: np.ndarray) -> float:
    if indices.size < 2:
        return float("nan")
    return float(np.mean(np.diff(lam[indices])))


def photon_radial_instability(case: dict[str, Any]) -> dict[str, float]:
    if case["particle_type"] != "photon":
        return {"mino_exponent": float("nan"), "coordinate_time_exponent": float("nan")}
    r0 = float(case["r0"])
    h = max(1e-5, 2e-5 * abs(r0))
    values = [
        float(radial_potential(r0 + offset, case["a"], case["E"], case["Lz"], case["Q"], 0.0))
        for offset in (-h, 0.0, h)
    ]
    rpp = (values[0] - 2.0 * values[1] + values[2]) / (h * h)
    gamma_lam = math.sqrt(max(0.0, 0.5 * rpp))
    dt_dlam_eq = float(
        mino_t_rate(r0, math.pi / 2.0, case["a"], case["E"], case["Lz"])
    )
    gamma_t = gamma_lam / dt_dlam_eq if dt_dlam_eq > 0 else float("nan")
    return {
        "mino_exponent": float(gamma_lam),
        "coordinate_time_exponent": float(gamma_t),
        "radial_potential_second_derivative": float(rpp),
    }


def orbit_diagnostics(case: dict[str, Any], lam: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    r = np.asarray(y[1], dtype=float)
    theta = np.asarray(y[2], dtype=float)
    phi = np.asarray(y[3], dtype=float)
    ptheta = np.asarray(y[5], dtype=float)
    rmin_idx = _turning_indices(r, kind="min")
    thmax_idx = _turning_indices(theta, kind="max")
    radial_period = _period_from_indices(lam, rmin_idx)
    polar_period = _period_from_indices(lam, thmax_idx)
    mean_phi_rate = (
        float((phi[-1] - phi[0]) / (lam[-1] - lam[0])) if lam[-1] > lam[0] else float("nan")
    )
    dt = np.asarray(
        mino_t_rate(r, theta, case["a"], case["E"], case["Lz"]), dtype=float
    )
    photon_instability = photon_radial_instability(case)
    if case["particle_type"] == "photon":
        mean_dt = float(np.nanmean(dt))
        if mean_dt > 0 and np.isfinite(photon_instability["mino_exponent"]):
            photon_instability["coordinate_time_exponent"] = (
                photon_instability["mino_exponent"] / mean_dt
            )
    poincare_theta = theta[rmin_idx] if rmin_idx.size else np.asarray([], dtype=float)
    poincare_ptheta = ptheta[rmin_idx] if rmin_idx.size else np.asarray([], dtype=float)
    return {
        "r_min": float(np.nanmin(r)),
        "r_max": float(np.nanmax(r)),
        "theta_min": float(np.nanmin(theta)),
        "theta_max": float(np.nanmax(theta)),
        "radial_period_mino": radial_period,
        "polar_period_mino": polar_period,
        "mean_phi_rate_mino": mean_phi_rate,
        "mean_dt_dlambda": float(np.nanmean(dt)),
        "poincare_theta": poincare_theta,
        "poincare_ptheta": poincare_ptheta,
        "photon_instability": photon_instability,
    }


def oblate_xyz(r: Any, theta: Any, phi: Any, a: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r_arr = np.asarray(r, dtype=float)
    th = np.asarray(theta, dtype=float)
    ph = np.asarray(phi, dtype=float)
    rho = np.sqrt(np.maximum(r_arr * r_arr + a * a, 0.0))
    return (
        rho * np.sin(th) * np.cos(ph),
        rho * np.sin(th) * np.sin(ph),
        r_arr * np.cos(th),
    )


def result_summary(result: dict[str, Any]) -> dict[str, Any]:
    case = result["case"]
    diag = result["diagnostics"]
    instability = diag["photon_instability"]
    return {
        "schema": MODEL_SCHEMA,
        "particle_type": case["particle_type"],
        "spin": case["a"],
        "inclination_deg": case["inclination_deg"],
        "E": case["E"],
        "Lz": case["Lz"],
        "Q": case["Q"],
        "status": result["status"],
        "nfev": result["nfev"],
        "first_integral_residual_max": result["residuals"]["combined_max"],
        "r_min": diag["r_min"],
        "r_max": diag["r_max"],
        "radial_period_mino": diag["radial_period_mino"],
        "polar_period_mino": diag["polar_period_mino"],
        "mean_phi_rate_mino": diag["mean_phi_rate_mino"],
        "photon_radial_instability_mino": instability["mino_exponent"],
        "photon_radial_instability_coordinate_time": instability["coordinate_time_exponent"],
    }


def run_refinement_pair(config: KerrOrbitConfig) -> dict[str, Any]:
    loose = KerrOrbitConfig(
        spin=config.spin,
        inclination_deg=config.inclination_deg,
        particle_type=config.particle_type,
        periapsis=config.periapsis,
        apoapsis=config.apoapsis,
        lam_max=min(config.lam_max, 12.0),
        samples=min(config.samples, 1600),
        rtol=max(config.rtol * 100.0, 1e-7),
        atol=max(config.atol * 100.0, 1e-9),
        horizon_pad=config.horizon_pad,
    )
    tight = KerrOrbitConfig(
        spin=config.spin,
        inclination_deg=config.inclination_deg,
        particle_type=config.particle_type,
        periapsis=config.periapsis,
        apoapsis=config.apoapsis,
        lam_max=min(config.lam_max, 12.0),
        samples=min(config.samples, 1600),
        rtol=min(config.rtol, 1e-10),
        atol=min(config.atol, 1e-12),
        horizon_pad=config.horizon_pad,
    )
    a = integrate_case(loose)
    b = integrate_case(tight)
    sa, sb = result_summary(a), result_summary(b)
    keys = ("r_min", "r_max", "mean_phi_rate_mino")
    deltas = {}
    for key in keys:
        av, bv = float(sa[key]), float(sb[key])
        deltas[key] = abs(av - bv)
    return {
        "loose": sa,
        "tight": sb,
        "absolute_deltas": deltas,
        "tight_residual": sb["first_integral_residual_max"],
    }
