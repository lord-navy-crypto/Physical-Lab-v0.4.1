"""Sun-Jupiter-Saturn orbital dynamics core for Physical Lab.

The model is a controlled rebuild of the user's long-duration 3-D orbital study.
It separates a physically interpretable barycentric Newtonian baseline from
optional approximations and phenomenological perturbations.

Scientific boundaries
---------------------
- Baseline dynamics are point-mass Newtonian gravity in AU, year, solar-mass
  units with G = 4*pi^2.
- ``solar_1pn`` adds only the standard test-particle-like central-Sun 1PN
  acceleration, with an equal-and-opposite recoil bookkeeping term. It is NOT a
  complete Einstein-Infeld-Hoffmann N-body 1PN implementation.
- ``velocity_cross`` and ``radial_drag`` are explicitly phenomenological legacy
  perturbations retained for controlled sensitivity experiments. They are not
  claimed to be physical spin-orbit coupling or gravitational-wave reaction.
- Retarded-gravity history from the original standalone script is intentionally
  not reproduced: mutating a deque inside an adaptive ODE RHS is not a valid DDE
  integrator and makes rejected/internal solver stages contaminate history.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

PROFILE = "nonlinear-chaos"
MODEL_SCHEMA = "physical-lab-solar-system-dynamics-v1"
MODEL_VARIANT = "sun-jupiter-saturn-dynamics"
MODEL_TITLE = "Sun–Jupiter–Saturn Orbital Dynamics"

G = 4.0 * math.pi ** 2  # AU^3 / (yr^2 M_sun)
C_AU_PER_YR = 63241.0
M_SUN = 1.0
M_JUPITER = 0.00095
M_SATURN = 0.0002857
R_JUPITER_AU = 5.2
R_SATURN_AU = 9.5
TWO_PI = 2.0 * math.pi


@dataclass(frozen=True)
class SolarSystemConfig:
    duration_years: float = 80.0
    samples: int = 2400
    inclination_jupiter_deg: float = 10.0
    saturn_inclination_factor: float = 0.25
    saturn_backreaction: bool = True
    solar_1pn: bool = False
    velocity_cross: bool = False
    radial_drag: bool = False
    velocity_cross_strength: float = 1e-4
    radial_drag_strength: float = 1e-8
    omega_z_per_year: float = 0.1
    rtol: float = 1e-10
    atol: float = 1e-12
    max_step_years: float = 0.03

    def validate(self) -> None:
        if not (0.05 <= float(self.duration_years) <= 1000.0):
            raise ValueError("duration_years must be in [0.05, 1000]")
        if not (100 <= int(self.samples) <= 50000):
            raise ValueError("samples must be in [100, 50000]")
        if not (0.0 <= float(self.inclination_jupiter_deg) <= 60.0):
            raise ValueError("inclination_jupiter_deg must be in [0, 60]")
        if not (0.0 <= float(self.saturn_inclination_factor) <= 1.0):
            raise ValueError("saturn_inclination_factor must be in [0, 1]")
        if not (0.0 <= float(self.velocity_cross_strength) <= 1e-2):
            raise ValueError("velocity_cross_strength must be in [0, 1e-2]")
        if not (0.0 <= float(self.radial_drag_strength) <= 1e-5):
            raise ValueError("radial_drag_strength must be in [0, 1e-5]")
        if not (0.0 <= float(self.omega_z_per_year) <= 10.0):
            raise ValueError("omega_z_per_year must be in [0, 10]")
        if not (1e-13 <= float(self.rtol) <= 1e-5):
            raise ValueError("rtol must be in [1e-13, 1e-5]")
        if not (1e-15 <= float(self.atol) <= 1e-7):
            raise ValueError("atol must be in [1e-15, 1e-7]")
        if not (1e-4 <= float(self.max_step_years) <= 1.0):
            raise ValueError("max_step_years must be in [1e-4, 1]")


def masses(config: SolarSystemConfig) -> np.ndarray:
    """Return [Sun, Jupiter, Saturn] masses in solar masses.

    When Saturn backreaction is disabled, Saturn remains a massless tracer so the
    trajectory can still be compared while its force on Sun/Jupiter is removed.
    """
    return np.asarray(
        [M_SUN, M_JUPITER, M_SATURN if config.saturn_backreaction else 0.0],
        dtype=float,
    )


def _pack(r: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.concatenate([np.asarray(r, dtype=float).reshape(-1), np.asarray(v, dtype=float).reshape(-1)])


def _unpack(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    arr = np.asarray(y, dtype=float)
    if arr.size != 18:
        raise ValueError("solar-system state must contain 18 scalars")
    return arr[:9].reshape(3, 3), arr[9:].reshape(3, 3)


def initial_state(config: SolarSystemConfig) -> np.ndarray:
    """Construct circular heliocentric guesses and shift them to a barycentric frame."""
    config.validate()
    inc_j = math.radians(float(config.inclination_jupiter_deg))
    inc_s = inc_j * float(config.saturn_inclination_factor)

    r = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [R_JUPITER_AU, 0.0, 0.0],
            [R_SATURN_AU, 0.0, 0.0],
        ],
        dtype=float,
    )
    vj = math.sqrt(G * M_SUN / R_JUPITER_AU)
    vs = math.sqrt(G * M_SUN / R_SATURN_AU)
    v = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [0.0, vj * math.cos(inc_j), vj * math.sin(inc_j)],
            [0.0, vs * math.cos(inc_s), vs * math.sin(inc_s)],
        ],
        dtype=float,
    )

    m = masses(config)
    m_total = float(np.sum(m))
    if m_total <= 0:
        raise ValueError("total gravitating mass must be positive")
    r_cm = np.sum(m[:, None] * r, axis=0) / m_total
    v_cm = np.sum(m[:, None] * v, axis=0) / m_total
    r -= r_cm
    v -= v_cm
    return _pack(r, v)


def _newtonian_acceleration(r: np.ndarray, m: np.ndarray) -> np.ndarray:
    a = np.zeros((3, 3), dtype=float)
    for i in range(3):
        for j in range(3):
            if i == j or m[j] == 0.0:
                continue
            delta = r[i] - r[j]
            dist2 = float(np.dot(delta, delta))
            if dist2 <= 1e-18:
                raise FloatingPointError("body separation became singular")
            inv_r3 = dist2 ** -1.5
            a[i] += -G * m[j] * delta * inv_r3
    return a


def _solar_1pn_pair(relative_r: np.ndarray, relative_v: np.ndarray) -> np.ndarray:
    """Approximate central-Sun 1PN acceleration for one orbiting body.

    Formula: GM/(c^2 r^3) * [(4GM/r-v^2) r + 4(r.v) v].
    This is useful for a controlled precession comparison but is not full N-body
    post-Newtonian dynamics.
    """
    rnorm = float(np.linalg.norm(relative_r))
    if rnorm <= 1e-12:
        return np.zeros(3, dtype=float)
    v2 = float(np.dot(relative_v, relative_v))
    rv = float(np.dot(relative_r, relative_v))
    mu = G * M_SUN
    factor = mu / (C_AU_PER_YR ** 2 * rnorm ** 3)
    return factor * ((4.0 * mu / rnorm - v2) * relative_r + 4.0 * rv * relative_v)


def _add_recoil(acc: np.ndarray, body_index: int, body_mass: float, extra: np.ndarray) -> None:
    """Apply an extra acceleration to a planet plus equal/opposite linear-momentum bookkeeping."""
    acc[body_index] += extra
    if M_SUN > 0.0 and body_mass > 0.0:
        acc[0] -= (body_mass / M_SUN) * extra


def acceleration(r: np.ndarray, v: np.ndarray, config: SolarSystemConfig) -> np.ndarray:
    m = masses(config)
    a = _newtonian_acceleration(r, m)
    omega = np.asarray([0.0, 0.0, float(config.omega_z_per_year)], dtype=float)

    for i in (1, 2):
        if i == 2 and not config.saturn_backreaction:
            body_mass = 0.0
        else:
            body_mass = float(m[i])
        rel_r = r[i] - r[0]
        rel_v = v[i] - v[0]

        if config.solar_1pn:
            _add_recoil(a, i, body_mass, _solar_1pn_pair(rel_r, rel_v))

        if config.velocity_cross:
            # Legacy toy term formerly labelled spin-orbit coupling. Since
            # (Omega x v).v = 0, this term performs no instantaneous work.
            extra = float(config.velocity_cross_strength) * np.cross(omega, rel_v)
            _add_recoil(a, i, body_mass, extra)

        if config.radial_drag:
            rnorm = float(np.linalg.norm(rel_r))
            if rnorm > 1e-12:
                vnorm = float(np.linalg.norm(rel_v))
                extra = -float(config.radial_drag_strength) * (vnorm ** 3) * rel_r / rnorm
                _add_recoil(a, i, body_mass, extra)
    return a


def rhs(_t: float, y: np.ndarray, config: SolarSystemConfig) -> np.ndarray:
    r, v = _unpack(y)
    a = acceleration(r, v, config)
    return _pack(v, a)


def integrate_case(config: SolarSystemConfig) -> dict[str, Any]:
    config.validate()
    y0 = initial_state(config)
    t_eval = np.linspace(0.0, float(config.duration_years), int(config.samples))
    sol = solve_ivp(
        lambda t, y: rhs(t, y, config),
        (0.0, float(config.duration_years)),
        y0,
        method="DOP853",
        t_eval=t_eval,
        rtol=float(config.rtol),
        atol=float(config.atol),
        max_step=float(config.max_step_years),
    )
    if not sol.success:
        raise RuntimeError(f"orbital integration failed: {sol.message}")
    states = np.asarray(sol.y.T, dtype=float)
    r = states[:, :9].reshape(-1, 3, 3)
    v = states[:, 9:].reshape(-1, 3, 3)
    diagnostics = trajectory_diagnostics(config, np.asarray(sol.t, dtype=float), r, v)
    return {
        "schema": MODEL_SCHEMA,
        "config": config,
        "time_years": np.asarray(sol.t, dtype=float),
        "positions_AU": r,
        "velocities_AU_per_yr": v,
        "status": "completed",
        "solver_message": str(sol.message),
        "nfev": int(sol.nfev),
        "diagnostics": diagnostics,
    }


def orbital_elements(relative_r: np.ndarray, relative_v: np.ndarray, mu: float) -> dict[str, float]:
    r = np.asarray(relative_r, dtype=float)
    v = np.asarray(relative_v, dtype=float)
    rnorm = float(np.linalg.norm(r))
    vnorm = float(np.linalg.norm(v))
    h = np.cross(r, v)
    hnorm = float(np.linalg.norm(h))
    if rnorm <= 0 or hnorm <= 0:
        return {"a_AU": float("nan"), "e": float("nan"), "inclination_deg": float("nan")}
    evec = np.cross(v, h) / mu - r / rnorm
    ecc = float(np.linalg.norm(evec))
    denom = 2.0 / rnorm - vnorm * vnorm / mu
    semi = 1.0 / denom if abs(denom) > 1e-15 else float("inf")
    cos_i = float(np.clip(h[2] / hnorm, -1.0, 1.0))
    return {
        "a_AU": float(semi),
        "e": ecc,
        "inclination_deg": math.degrees(math.acos(cos_i)),
    }


def _newtonian_energy(r: np.ndarray, v: np.ndarray, m: np.ndarray) -> float:
    kinetic = 0.5 * float(np.sum(m[:, None] * v * v))
    potential = 0.0
    for i in range(3):
        for j in range(i + 1, 3):
            if m[i] == 0.0 or m[j] == 0.0:
                continue
            dist = float(np.linalg.norm(r[i] - r[j]))
            potential += -G * m[i] * m[j] / max(dist, 1e-15)
    return kinetic + potential


def _angular_momentum(r: np.ndarray, v: np.ndarray, m: np.ndarray) -> np.ndarray:
    return np.sum(m[:, None] * np.cross(r, v), axis=0)


def _linear_momentum(v: np.ndarray, m: np.ndarray) -> np.ndarray:
    return np.sum(m[:, None] * v, axis=0)


def trajectory_diagnostics(
    config: SolarSystemConfig,
    t: np.ndarray,
    r: np.ndarray,
    v: np.ndarray,
) -> dict[str, Any]:
    m = masses(config)
    gravitating_mass = float(np.sum(m))
    energy = np.asarray([_newtonian_energy(rr, vv, m) for rr, vv in zip(r, v)], dtype=float)
    ang = np.asarray([_angular_momentum(rr, vv, m) for rr, vv in zip(r, v)], dtype=float)
    momentum = np.asarray([_linear_momentum(vv, m) for vv in v], dtype=float)
    bary = np.asarray([np.sum(m[:, None] * rr, axis=0) / gravitating_mass for rr in r], dtype=float)

    e0 = float(energy[0])
    l0 = ang[0]
    p0 = momentum[0]
    relative_energy_drift = float(np.max(np.abs(energy - e0)) / max(abs(e0), 1e-30))
    relative_l_drift = float(np.max(np.linalg.norm(ang - l0, axis=1)) / max(float(np.linalg.norm(l0)), 1e-30))
    momentum_drift = float(np.max(np.linalg.norm(momentum - p0, axis=1)))
    barycenter_drift = float(np.max(np.linalg.norm(bary - bary[0], axis=1)))

    rel_j_r = r[:, 1] - r[:, 0]
    rel_j_v = v[:, 1] - v[:, 0]
    rel_s_r = r[:, 2] - r[:, 0]
    rel_s_v = v[:, 2] - v[:, 0]
    mu_j = G * (M_SUN + M_JUPITER)
    mu_s = G * (M_SUN + (M_SATURN if config.saturn_backreaction else 0.0))
    j_elements = [orbital_elements(rr, vv, mu_j) for rr, vv in zip(rel_j_r, rel_j_v)]
    s_elements = [orbital_elements(rr, vv, mu_s) for rr, vv in zip(rel_s_r, rel_s_v)]
    a_j = np.asarray([row["a_AU"] for row in j_elements], dtype=float)
    a_s = np.asarray([row["a_AU"] for row in s_elements], dtype=float)
    e_j = np.asarray([row["e"] for row in j_elements], dtype=float)
    e_s = np.asarray([row["e"] for row in s_elements], dtype=float)
    i_j = np.asarray([row["inclination_deg"] for row in j_elements], dtype=float)
    i_s = np.asarray([row["inclination_deg"] for row in s_elements], dtype=float)

    period_j = TWO_PI * np.sqrt(np.maximum(a_j, 1e-15) ** 3 / mu_j)
    period_s = TWO_PI * np.sqrt(np.maximum(a_s, 1e-15) ** 3 / mu_s)
    ratio = period_s / period_j
    resonance_deviation_5_2 = ratio - 2.5
    separation = np.linalg.norm(r[:, 1] - r[:, 2], axis=1)

    invariants_expected = not (config.solar_1pn or config.velocity_cross or config.radial_drag)
    return {
        "newtonian_energy": energy,
        "angular_momentum": ang,
        "linear_momentum": momentum,
        "barycenter_AU": bary,
        "relative_energy_drift": relative_energy_drift,
        "relative_angular_momentum_drift": relative_l_drift,
        "absolute_linear_momentum_drift": momentum_drift,
        "barycenter_position_drift_AU": barycenter_drift,
        "invariants_expected": invariants_expected,
        "jupiter": {"a_AU": a_j, "e": e_j, "inclination_deg": i_j, "period_years": period_j},
        "saturn": {"a_AU": a_s, "e": e_s, "inclination_deg": i_s, "period_years": period_s},
        "period_ratio_saturn_over_jupiter": ratio,
        "resonance_deviation_5_2": resonance_deviation_5_2,
        "jupiter_saturn_separation_AU": separation,
        "minimum_separation_AU": float(np.min(separation)),
        "maximum_separation_AU": float(np.max(separation)),
        "final_period_ratio": float(ratio[-1]),
        "final_resonance_deviation_5_2": float(resonance_deviation_5_2[-1]),
        "time_years": np.asarray(t, dtype=float),
    }


def result_summary(result: dict[str, Any]) -> dict[str, Any]:
    d = result["diagnostics"]
    j = d["jupiter"]
    s = d["saturn"]
    return {
        "schema": MODEL_SCHEMA,
        "status": result["status"],
        "nfev": result["nfev"],
        "relative_energy_drift": d["relative_energy_drift"],
        "relative_angular_momentum_drift": d["relative_angular_momentum_drift"],
        "absolute_linear_momentum_drift": d["absolute_linear_momentum_drift"],
        "barycenter_position_drift_AU": d["barycenter_position_drift_AU"],
        "invariants_expected": d["invariants_expected"],
        "minimum_separation_AU": d["minimum_separation_AU"],
        "maximum_separation_AU": d["maximum_separation_AU"],
        "final_period_ratio": d["final_period_ratio"],
        "final_resonance_deviation_5_2": d["final_resonance_deviation_5_2"],
        "jupiter_final_a_AU": float(j["a_AU"][-1]),
        "jupiter_final_e": float(j["e"][-1]),
        "jupiter_final_inclination_deg": float(j["inclination_deg"][-1]),
        "saturn_final_a_AU": float(s["a_AU"][-1]),
        "saturn_final_e": float(s["e"][-1]),
        "saturn_final_inclination_deg": float(s["inclination_deg"][-1]),
    }


def run_refinement_pair(config: SolarSystemConfig) -> dict[str, Any]:
    span = min(float(config.duration_years), 20.0)
    loose = replace(
        config,
        duration_years=span,
        samples=min(int(config.samples), 900),
        rtol=max(float(config.rtol) * 100.0, 1e-8),
        atol=max(float(config.atol) * 100.0, 1e-10),
        max_step_years=min(max(float(config.max_step_years) * 2.0, 0.02), 0.08),
    )
    tight = replace(
        config,
        duration_years=span,
        samples=min(int(config.samples), 900),
        rtol=min(float(config.rtol), 1e-11),
        atol=min(float(config.atol), 1e-13),
        max_step_years=min(float(config.max_step_years), 0.02),
    )
    a = result_summary(integrate_case(loose))
    b = result_summary(integrate_case(tight))
    keys = (
        "jupiter_final_a_AU",
        "jupiter_final_e",
        "saturn_final_a_AU",
        "saturn_final_e",
        "final_period_ratio",
    )
    rel = {}
    for key in keys:
        av, bv = float(a[key]), float(b[key])
        rel[key] = abs(av - bv) / max(1.0, abs(bv))
    return {"loose": a, "tight": b, "relative_changes": rel, "max_relative_change": max(rel.values())}


def _normalized_phase(y: np.ndarray) -> np.ndarray:
    r, v = _unpack(y)
    return np.concatenate([r.reshape(-1), (v / TWO_PI).reshape(-1)])


def _phase_delta_to_state(delta: np.ndarray) -> np.ndarray:
    arr = np.asarray(delta, dtype=float)
    out = arr.copy()
    out[9:] *= TWO_PI
    return out


def finite_time_lyapunov_indicator(
    config: SolarSystemConfig,
    *,
    d0: float = 1e-8,
    segment_years: float = 2.0,
    max_years: float = 30.0,
) -> dict[str, Any]:
    """Benettin-style finite-time phase-space divergence indicator.

    The phase norm uses 1 AU for position and 2*pi AU/yr for velocity. This is a
    bounded finite-time diagnostic, not an asymptotic proof of chaos.
    """
    config.validate()
    if d0 <= 0 or segment_years <= 0 or max_years <= 0:
        raise ValueError("FTLE parameters must be positive")
    total = min(float(config.duration_years), float(max_years))
    ref = initial_state(config)
    twin = ref.copy()
    m = masses(config)
    # Preserve center of mass when seeding the perturbation.
    twin[3] += d0  # Jupiter x in flattened position block
    twin[0] -= (m[1] / max(m[0], 1e-30)) * d0
    initial_sep = float(np.linalg.norm(_normalized_phase(twin) - _normalized_phase(ref)))
    if initial_sep <= 0:
        raise RuntimeError("failed to seed FTLE perturbation")
    # Normalize exactly to d0.
    delta_norm = (_normalized_phase(twin) - _normalized_phase(ref)) * (d0 / initial_sep)
    twin = ref + _phase_delta_to_state(delta_norm)

    elapsed = 0.0
    logs: list[float] = []
    times: list[float] = []
    separations: list[float] = []
    while elapsed < total - 1e-12:
        dt = min(float(segment_years), total - elapsed)
        end = elapsed + dt
        kwargs = dict(
            method="DOP853",
            rtol=max(float(config.rtol), 1e-10),
            atol=max(float(config.atol), 1e-12),
            max_step=min(float(config.max_step_years), 0.05),
            t_eval=[end],
        )
        sol_a = solve_ivp(lambda t, y: rhs(t, y, config), (elapsed, end), ref, **kwargs)
        sol_b = solve_ivp(lambda t, y: rhs(t, y, config), (elapsed, end), twin, **kwargs)
        if not (sol_a.success and sol_b.success):
            raise RuntimeError("FTLE segment integration failed")
        ref = np.asarray(sol_a.y[:, -1], dtype=float)
        twin_end = np.asarray(sol_b.y[:, -1], dtype=float)
        delta = _normalized_phase(twin_end) - _normalized_phase(ref)
        sep = float(np.linalg.norm(delta))
        if not math.isfinite(sep) or sep <= 0:
            raise RuntimeError("FTLE separation became invalid")
        logs.append(math.log(sep / d0))
        elapsed = end
        times.append(elapsed)
        separations.append(sep)
        delta *= d0 / sep
        twin = ref + _phase_delta_to_state(delta)

    rate = float(np.sum(logs) / max(elapsed, 1e-30))
    return {
        "finite_time_rate_per_year": rate,
        "elapsed_years": elapsed,
        "segment_years": float(segment_years),
        "renormalizations": len(logs),
        "times_years": np.asarray(times, dtype=float),
        "pre_renormalization_separation": np.asarray(separations, dtype=float),
        "phase_normalization": "position/1 AU; velocity/(2*pi AU/yr)",
        "boundary": "Finite-time Benettin-style sensitivity indicator; not an asymptotic proof of chaos.",
    }
