"""Dual-mode mathematical-tool and physics-scenario layer for Physical Lab.

The mathematical Labs remain valid standalone numerical/statistical tools.  This
module adds bounded physics applications without renaming or replacing those
original tools:

- Numerical Error -> optional quantum bound-state numerical verification.
- Ising Monte Carlo -> magnetic phase-transition / criticality study.
- Random Walk / Monte Carlo -> Brownian diffusion and drift transport.

Scenario calculations are deterministic for a fixed configuration and preserve
explicit model boundaries.  They are computational physics demonstrations and
verification studies, not experimental validation.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

APPLICATION_PROFILES = {
    "numerical-methods": {
        "tool_title": "Numerical Error · Mathematical tool",
        "physics_title": "Quantum bound-state numerical verification",
        "research_question": "How do grid spacing and discretization error change a physical eigenenergy?",
    },
    "ising-monte-carlo": {
        "tool_title": "Ising Monte Carlo · Mathematical / sampling tool",
        "physics_title": "Magnetic phase transition & criticality",
        "research_question": "How do thermal fluctuations reorganize magnetization and response near the 2D Ising critical region?",
    },
    "random-walk-monte-carlo": {
        "tool_title": "Random Walk / Monte Carlo · Mathematical tool",
        "physics_title": "Diffusion & stochastic transport",
        "research_question": "Can Brownian trajectories recover the imposed diffusion coefficient and drift velocity?",
    },
}

HBAR_J_S = 1.054_571_817e-34
ELECTRON_MASS_KG = 9.109_383_7139e-31
EV_J = 1.602_176_634e-19
ISING_TC_SQUARE_2D = 2.0 / math.log(1.0 + math.sqrt(2.0))


def _np():
    import numpy as np
    return np


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    try:
        if hasattr(value, "item"):
            return _plain(value.item())
    except Exception:
        pass
    try:
        return [_plain(v) for v in value]
    except Exception:
        return str(value)


def padded_range(values: Any, *, pad_fraction: float = 0.08, clamp: tuple[float | None, float | None] | None = None) -> list[float] | None:
    """Return a tight finite display range so small but meaningful differences stay visible.

    This is display-only.  It never changes scientific values.  Constant traces
    receive a scale-aware finite pad instead of collapsing to a zero-width axis.
    """
    np = _np()
    try:
        arr = np.asarray(values, dtype=float).ravel()
    except Exception:
        return None
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    lo = float(np.min(arr)); hi = float(np.max(arr))
    span = hi - lo
    scale = max(abs(lo), abs(hi), 1.0)
    pad = max(span * max(float(pad_fraction), 0.0), scale * 1e-6)
    if span <= max(scale * 1e-12, 1e-15):
        pad = max(scale * 0.04, 1e-9)
    lo -= pad; hi += pad
    if clamp is not None:
        lower, upper = clamp
        if lower is not None:
            lo = max(lo, float(lower))
        if upper is not None:
            hi = min(hi, float(upper))
    if not (math.isfinite(lo) and math.isfinite(hi) and lo < hi):
        return None
    return [lo, hi]


# ---------------------------------------------------------------------------
# Numerical Error -> quantum verification scenario
# ---------------------------------------------------------------------------

def _quantum_eigensystem(grid_points: int, width_nm: float, states: int) -> dict[str, Any]:
    np = _np()
    n = max(24, min(int(grid_points), 640))
    requested_states = max(1, min(int(states), min(8, n - 2)))
    width_m = float(width_nm) * 1e-9
    if not math.isfinite(width_m) or width_m <= 0:
        raise ValueError("well width must be positive")
    dx = width_m / (n + 1)
    coefficient = HBAR_J_S**2 / (2.0 * ELECTRON_MASS_KG * dx**2)
    diagonal = np.full(n, 2.0 * coefficient, dtype=float)
    off_diagonal = np.full(n - 1, -coefficient, dtype=float)
    backend = "NumPy dense symmetric eigensolver"
    try:
        from scipy.linalg import eigh_tridiagonal  # type: ignore
        eigenvalues, eigenvectors = eigh_tridiagonal(
            diagonal,
            off_diagonal,
            select="i",
            select_range=(0, requested_states - 1),
            check_finite=True,
        )
        backend = "SciPy eigh_tridiagonal"
    except Exception:
        matrix = np.diag(diagonal) + np.diag(off_diagonal, 1) + np.diag(off_diagonal, -1)
        all_values, all_vectors = np.linalg.eigh(matrix)
        eigenvalues = all_values[:requested_states]
        eigenvectors = all_vectors[:, :requested_states]

    exact = np.asarray([
        (index * math.pi * HBAR_J_S) ** 2 / (2.0 * ELECTRON_MASS_KG * width_m**2)
        for index in range(1, requested_states + 1)
    ], dtype=float)
    relative_error = np.abs(eigenvalues - exact) / exact
    interior_x = np.arange(1, n + 1, dtype=float) * dx
    x = np.concatenate(([0.0], interior_x, [width_m]))
    densities = []
    for state_index in range(requested_states):
        vector = np.asarray(eigenvectors[:, state_index], dtype=float)
        norm = math.sqrt(max(float(np.sum(vector * vector) * dx), 1e-300))
        vector = vector / norm
        density_per_m = vector * vector
        density_per_nm = density_per_m * 1e-9
        densities.append(np.concatenate(([0.0], density_per_nm, [0.0])))
    return {
        "grid_points": n,
        "width_nm": float(width_nm),
        "dx_nm": dx * 1e9,
        "backend": backend,
        "energies_eV": eigenvalues / EV_J,
        "exact_energies_eV": exact / EV_J,
        "relative_error": relative_error,
        "x_nm": x * 1e9,
        "probability_density_per_nm": densities,
    }


def quantum_bound_state_verification(
    *,
    grid_points: int = 160,
    width_nm: float = 1.0,
    states: int = 3,
) -> dict[str, Any]:
    """Finite-difference infinite-well study that turns numerical error into energy error."""
    np = _np()
    base = _quantum_eigensystem(grid_points, width_nm, states)
    candidate_grids = sorted(set([40, 80, 160, min(max(int(grid_points), 40), 320)]))
    convergence = []
    for grid in candidate_grids:
        study = _quantum_eigensystem(grid, width_nm, 1)
        convergence.append({
            "grid_points": int(grid),
            "dx_nm": float(study["dx_nm"]),
            "relative_error_E1": float(study["relative_error"][0]),
        })
    h = np.asarray([row["dx_nm"] for row in convergence], dtype=float)
    error = np.asarray([row["relative_error_E1"] for row in convergence], dtype=float)
    mask = (h > 0) & (error > 0)
    observed_order = None
    if int(np.sum(mask)) >= 2:
        observed_order = float(np.polyfit(np.log(h[mask]), np.log(error[mask]), 1)[0])
    energies = []
    for index, (numerical, exact, rel) in enumerate(
        zip(base["energies_eV"], base["exact_energies_eV"], base["relative_error"]), start=1
    ):
        energies.append({
            "state": index,
            "numerical_eV": float(numerical),
            "exact_eV": float(exact),
            "relative_error": float(rel),
        })
    result = {
        "schema": "physical-lab-physics-scenario-v1",
        "profile": "numerical-methods",
        "scenario": "quantum-bound-state-verification",
        "question": APPLICATION_PROFILES["numerical-methods"]["research_question"],
        "inputs": {"grid_points": int(base["grid_points"]), "well_width_nm": float(width_nm), "states": int(states)},
        "backend": base["backend"],
        "energies": energies,
        "convergence": convergence,
        "observed_convergence_order": observed_order,
        "x_nm": [float(v) for v in base["x_nm"]],
        "probability_density_per_nm": [[float(v) for v in density] for density in base["probability_density_per_nm"]],
        "boundary": (
            "One-dimensional infinite square well with Dirichlet boundaries and a second-order centered finite-difference kinetic operator. "
            "The analytic energy levels are a verification reference; this is not a general quantum solver or experimental validation."
        ),
    }
    return _plain(result)


# ---------------------------------------------------------------------------
# Ising -> magnetic criticality scenario
# ---------------------------------------------------------------------------

def _checkerboard_metropolis(spins: Any, beta: float, rng: Any, parity_mask: Any) -> None:
    np = _np()
    for parity in (0, 1):
        neighbors = (
            np.roll(spins, 1, axis=0) + np.roll(spins, -1, axis=0)
            + np.roll(spins, 1, axis=1) + np.roll(spins, -1, axis=1)
        )
        delta_e = 2 * spins * neighbors
        accept = (delta_e <= 0) | (rng.random(spins.shape) < np.exp(-beta * delta_e))
        flip = accept & (parity_mask == parity)
        spins[flip] *= -1


def ising_criticality_study(
    *,
    lattice_size: int = 12,
    temperature_min: float = 1.6,
    temperature_max: float = 3.4,
    temperature_points: int = 11,
    burn_sweeps: int = 160,
    sample_sweeps: int = 280,
    seed: int = 20260904,
) -> dict[str, Any]:
    """Bounded zero-field square-lattice Ising temperature sweep."""
    np = _np()
    L = max(4, min(int(lattice_size), 32))
    points = max(5, min(int(temperature_points), 25))
    t0 = float(temperature_min); t1 = float(temperature_max)
    if not (math.isfinite(t0) and math.isfinite(t1) and 0.2 <= t0 < t1 <= 8.0):
        raise ValueError("temperature range must be finite, positive and increasing")
    burn = max(20, min(int(burn_sweeps), 2000))
    samples = max(40, min(int(sample_sweeps), 3000))
    temperatures = np.linspace(t0, t1, points)
    rng = np.random.default_rng(int(seed))
    ii, jj = np.indices((L, L))
    parity_mask = (ii + jj) & 1
    N = L * L
    rows = []
    for temperature in temperatures:
        spins = rng.choice(np.asarray([-1, 1], dtype=np.int8), size=(L, L))
        beta = 1.0 / float(temperature)
        for _ in range(burn):
            _checkerboard_metropolis(spins, beta, rng, parity_mask)
        energy_samples = []
        magnetization_samples = []
        for _ in range(samples):
            _checkerboard_metropolis(spins, beta, rng, parity_mask)
            energy_per_spin = float(-np.sum(
                spins * (np.roll(spins, 1, axis=0) + np.roll(spins, 1, axis=1))
            ) / N)
            magnetization_per_spin = float(np.mean(spins))
            energy_samples.append(energy_per_spin)
            magnetization_samples.append(magnetization_per_spin)
        energy = np.asarray(energy_samples, dtype=float)
        magnetization = np.asarray(magnetization_samples, dtype=float)
        m2 = float(np.mean(magnetization**2)); m4 = float(np.mean(magnetization**4))
        heat_capacity = float(N * np.var(energy, ddof=1) / (temperature**2))
        susceptibility = float(N * np.var(magnetization, ddof=1) / temperature)
        binder = float(1.0 - m4 / (3.0 * m2 * m2)) if m2 > 0 else 0.0
        rows.append({
            "T_over_JkB": float(temperature),
            "energy_per_spin_J": float(np.mean(energy)),
            "abs_magnetization_per_spin": float(np.mean(np.abs(magnetization))),
            "heat_capacity_per_spin_kB": heat_capacity,
            "susceptibility_per_spin": susceptibility,
            "binder_cumulant": binder,
        })
    cv_peak = max(rows, key=lambda row: row["heat_capacity_per_spin_kB"])
    chi_peak = max(rows, key=lambda row: row["susceptibility_per_spin"])
    return _plain({
        "schema": "physical-lab-physics-scenario-v1",
        "profile": "ising-monte-carlo",
        "scenario": "magnetic-criticality",
        "question": APPLICATION_PROFILES["ising-monte-carlo"]["research_question"],
        "inputs": {
            "lattice_size": L,
            "temperature_range_J_over_kB": [t0, t1],
            "temperature_points": points,
            "burn_sweeps": burn,
            "sample_sweeps": samples,
            "seed": int(seed),
        },
        "rows": rows,
        "infinite_lattice_Tc_over_JkB": ISING_TC_SQUARE_2D,
        "heat_capacity_peak_temperature": cv_peak["T_over_JkB"],
        "susceptibility_peak_temperature": chi_peak["T_over_JkB"],
        "boundary": (
            "Zero-field nearest-neighbor ferromagnetic 2D square Ising model with periodic boundaries and checkerboard Metropolis updates. "
            "Finite lattice and finite sampling shift/broaden response peaks; peak temperatures are pseudo-critical indicators, not a new measurement of the exact infinite-lattice Tc."
        ),
    })


# ---------------------------------------------------------------------------
# Random walk -> Brownian transport scenario
# ---------------------------------------------------------------------------

def brownian_transport_study(
    *,
    diffusion_um2_s: float = 0.8,
    drift_x_um_s: float = 0.25,
    dt_s: float = 0.02,
    steps: int = 240,
    particles: int = 2600,
    seed: int = 20260904,
    representative_trajectories: int = 20,
) -> dict[str, Any]:
    """2D Brownian drift-diffusion with direct recovery of D and mean drift."""
    np = _np()
    D = float(diffusion_um2_s); drift = float(drift_x_um_s); dt = float(dt_s)
    if not (math.isfinite(D) and D > 0):
        raise ValueError("diffusion coefficient must be positive")
    if not math.isfinite(drift):
        raise ValueError("drift velocity must be finite")
    if not (math.isfinite(dt) and dt > 0):
        raise ValueError("time step must be positive")
    n_steps = max(20, min(int(steps), 2500))
    n_particles = max(200, min(int(particles), 20000))
    keep = max(4, min(int(representative_trajectories), min(40, n_particles)))
    rng = np.random.default_rng(int(seed))
    x = np.zeros(n_particles, dtype=float); y = np.zeros(n_particles, dtype=float)
    time_axis = np.arange(n_steps + 1, dtype=float) * dt
    centered_msd = np.zeros(n_steps + 1, dtype=float)
    mean_x = np.zeros(n_steps + 1, dtype=float)
    mean_y = np.zeros(n_steps + 1, dtype=float)
    tracks_x = np.zeros((keep, n_steps + 1), dtype=float)
    tracks_y = np.zeros((keep, n_steps + 1), dtype=float)
    sigma = math.sqrt(2.0 * D * dt)
    for step_index in range(1, n_steps + 1):
        x += drift * dt + sigma * rng.standard_normal(n_particles)
        y += sigma * rng.standard_normal(n_particles)
        mx = float(np.mean(x)); my = float(np.mean(y))
        mean_x[step_index] = mx; mean_y[step_index] = my
        centered_msd[step_index] = float(np.mean((x - mx) ** 2 + (y - my) ** 2))
        tracks_x[:, step_index] = x[:keep]
        tracks_y[:, step_index] = y[:keep]
    fit_mask = time_axis > 0
    diffusion_slope = float(np.polyfit(time_axis[fit_mask], centered_msd[fit_mask], 1)[0])
    drift_fit = float(np.polyfit(time_axis[fit_mask], mean_x[fit_mask], 1)[0])
    estimated_D = diffusion_slope / 4.0
    theoretical_msd = 4.0 * D * time_axis
    theoretical_mean_x = drift * time_axis
    radial_centered = np.sqrt((x - float(np.mean(x))) ** 2 + (y - float(np.mean(y))) ** 2)
    trajectories = [
        {"id": index, "x_um": [float(v) for v in tracks_x[index]], "y_um": [float(v) for v in tracks_y[index]]}
        for index in range(keep)
    ]
    return _plain({
        "schema": "physical-lab-physics-scenario-v1",
        "profile": "random-walk-monte-carlo",
        "scenario": "brownian-drift-diffusion",
        "question": APPLICATION_PROFILES["random-walk-monte-carlo"]["research_question"],
        "inputs": {
            "diffusion_um2_s": D,
            "drift_x_um_s": drift,
            "dt_s": dt,
            "steps": n_steps,
            "particles": n_particles,
            "seed": int(seed),
        },
        "time_s": [float(v) for v in time_axis],
        "centered_msd_um2": [float(v) for v in centered_msd],
        "theoretical_msd_um2": [float(v) for v in theoretical_msd],
        "mean_x_um": [float(v) for v in mean_x],
        "theoretical_mean_x_um": [float(v) for v in theoretical_mean_x],
        "estimated_diffusion_um2_s": estimated_D,
        "estimated_drift_x_um_s": drift_fit,
        "diffusion_relative_error": abs(estimated_D - D) / D,
        "drift_absolute_error_um_s": abs(drift_fit - drift),
        "trajectories": trajectories,
        "final_centered_radius_um": [float(v) for v in radial_centered],
        "boundary": (
            "Two-dimensional independent Gaussian Brownian increments with constant diffusion D and constant x drift. "
            "Centered MSD is compared with 4Dt so deterministic drift is not misidentified as diffusion; finite-particle estimates remain sampling results."
        ),
    })


def _line_figure(x: Any, y: Any, *, title: str, x_title: str, y_title: str, reference: tuple[Any, Any, str] | None = None, y_clamp: tuple[float | None, float | None] | None = None):
    go = __import__("plotly.graph_objects", fromlist=["graph_objects"])
    fig = go.Figure()
    fig.add_scatter(x=x, y=y, mode="lines+markers", name="Simulation")
    if reference is not None:
        rx, ry, label = reference
        fig.add_scatter(x=rx, y=ry, mode="lines", name=label)
    fig.update_layout(title=title, xaxis_title=x_title, yaxis_title=y_title, height=430)
    target = list(y)
    if reference is not None:
        try:
            target += list(reference[1])
        except Exception:
            pass
    yrange = padded_range(target, clamp=y_clamp)
    if yrange is not None:
        fig.update_yaxes(range=yrange)
    return fig


def _render_quantum(st: Any, profile: str) -> None:
    st.caption("Physics scene: an infinite quantum well is used as a controlled verification problem. The numerical object under test remains the discretization error, but the observable is now a physical energy level.")
    c1, c2, c3 = st.columns(3)
    width = c1.number_input("Well width (nm)", min_value=0.2, max_value=10.0, value=1.0, step=0.1, key="pl_scene_quantum_width")
    grid = c2.select_slider("Interior grid points", options=[40, 80, 120, 160, 240, 320], value=160, key="pl_scene_quantum_grid")
    states = c3.select_slider("Bound states", options=[1, 2, 3, 4, 5], value=3, key="pl_scene_quantum_states")
    key = "pl_physics_scene_quantum_result"
    if st.button("Run quantum verification", type="primary", key="pl_scene_quantum_run"):
        st.session_state[key] = quantum_bound_state_verification(grid_points=int(grid), width_nm=float(width), states=int(states))
    result = st.session_state.get(key)
    if not result:
        st.info("Run the physics scene to compare finite-difference eigenenergies with the analytic infinite-well reference.")
        return
    energies = result["energies"]
    a, b, c, d = st.columns(4)
    a.metric("E1 numerical", f"{energies[0]['numerical_eV']:.8g} eV")
    b.metric("E1 analytic", f"{energies[0]['exact_eV']:.8g} eV")
    c.metric("E1 relative error", f"{100.0 * energies[0]['relative_error']:.5g}%")
    order = result.get("observed_convergence_order")
    d.metric("Observed grid order", "—" if order is None else f"{order:.4g}")
    st.caption(f"Backend: {result['backend']}. Second-order centered finite differences should approach order 2 in the resolved regime.")

    go = __import__("plotly.graph_objects", fromlist=["graph_objects"])
    err_fig = go.Figure()
    err_fig.add_bar(x=[f"n={row['state']}" for row in energies], y=[100.0 * row["relative_error"] for row in energies], name="Eigenenergy error")
    err_fig.update_layout(title="Eigenenergy discretization error", xaxis_title="State", yaxis_title="Relative error (%)", height=420)
    yr = padded_range([100.0 * row["relative_error"] for row in energies], clamp=(0.0, None))
    if yr is not None:
        err_fig.update_yaxes(range=yr)
    st.plotly_chart(err_fig, width="stretch")

    conv = result["convergence"]
    conv_fig = go.Figure()
    conv_fig.add_scatter(x=[row["dx_nm"] for row in conv], y=[row["relative_error_E1"] for row in conv], mode="lines+markers", name="E1 error")
    conv_fig.update_layout(title="Grid-refinement convergence", xaxis_title="Grid spacing Δx (nm)", yaxis_title="Relative E1 error", height=430)
    conv_fig.update_xaxes(type="log"); conv_fig.update_yaxes(type="log")
    st.plotly_chart(conv_fig, width="stretch")

    state_index = st.selectbox("Probability-density state", list(range(1, len(energies) + 1)), index=0, key="pl_scene_quantum_density_state")
    density = result["probability_density_per_nm"][int(state_index) - 1]
    density_fig = _line_figure(
        result["x_nm"], density,
        title=f"Probability density · state n={state_index}",
        x_title="Position x (nm)", y_title="|ψ|² (1/nm)", y_clamp=(0.0, None),
    )
    st.plotly_chart(density_fig, width="stretch")
    st.caption(result["boundary"])


def _render_ising(st: Any, profile: str) -> None:
    st.caption("Physics scene: use the Monte Carlo machinery to study a specific statistical-physics question—thermal loss of magnetic order and response near the 2D square-Ising critical region.")
    c1, c2, c3 = st.columns(3)
    L = c1.select_slider("Lattice L×L", options=[6, 8, 12, 16, 24], value=12, key="pl_scene_ising_L")
    points = c2.select_slider("Temperature points", options=[7, 9, 11, 15, 19], value=11, key="pl_scene_ising_points")
    samples = c3.select_slider("Samples / temperature", options=[120, 200, 280, 400, 600], value=280, key="pl_scene_ising_samples")
    c4, c5 = st.columns(2)
    t0 = c4.number_input("T min (J/kB)", min_value=0.5, max_value=6.0, value=1.6, step=0.1, key="pl_scene_ising_tmin")
    t1 = c5.number_input("T max (J/kB)", min_value=0.6, max_value=8.0, value=3.4, step=0.1, key="pl_scene_ising_tmax")
    key = "pl_physics_scene_ising_result"
    if st.button("Run magnetic criticality sweep", type="primary", key="pl_scene_ising_run"):
        st.session_state[key] = ising_criticality_study(
            lattice_size=int(L), temperature_min=float(t0), temperature_max=float(t1),
            temperature_points=int(points), sample_sweeps=int(samples), burn_sweeps=max(100, int(samples // 2)),
        )
    result = st.session_state.get(key)
    if not result:
        st.info("Run the sweep to generate physical observables. Sampling diagnostics in the original Ising tool remain available separately.")
        return
    rows = result["rows"]
    temperatures = [row["T_over_JkB"] for row in rows]
    a, b, c = st.columns(3)
    a.metric("Exact infinite-lattice Tc", f"{result['infinite_lattice_Tc_over_JkB']:.6f} J/kB")
    b.metric("Cv peak T", f"{result['heat_capacity_peak_temperature']:.4g} J/kB")
    c.metric("χ peak T", f"{result['susceptibility_peak_temperature']:.4g} J/kB")
    st.caption("Finite-size response peaks are expected to be broadened/shifted relative to the infinite-lattice reference; that shift is part of the physics, not automatically a solver failure.")

    series = [
        ("abs_magnetization_per_spin", "Magnetic order · |M|", "|M| per spin", (0.0, 1.05)),
        ("energy_per_spin_J", "Energy per spin", "E/J per spin", (-2.1, 0.2)),
        ("heat_capacity_per_spin_kB", "Heat-capacity response", "Cv/kB per spin", (0.0, None)),
        ("susceptibility_per_spin", "Magnetic susceptibility", "χ per spin", (0.0, None)),
        ("binder_cumulant", "Binder cumulant", "U4", (None, 0.72)),
    ]
    left, right = st.columns(2)
    for index, (field, title, ylabel, clamp) in enumerate(series):
        fig = _line_figure(temperatures, [row[field] for row in rows], title=title, x_title="Temperature T (J/kB)", y_title=ylabel, y_clamp=clamp)
        fig.add_vline(x=result["infinite_lattice_Tc_over_JkB"], line_dash="dash", annotation_text="Infinite-lattice Tc")
        target = left if index % 2 == 0 else right
        target.plotly_chart(fig, width="stretch")
    st.caption(result["boundary"])


def _render_transport(st: Any, profile: str) -> None:
    st.caption("Physics scene: interpret the random walk as Brownian transport. Centered MSD isolates diffusion from deterministic drift, so D is not inflated by mean motion.")
    c1, c2, c3 = st.columns(3)
    D = c1.number_input("Diffusion D (µm²/s)", min_value=0.01, max_value=100.0, value=0.8, step=0.05, key="pl_scene_rw_D")
    drift = c2.number_input("x drift (µm/s)", min_value=-20.0, max_value=20.0, value=0.25, step=0.05, key="pl_scene_rw_drift")
    dt = c3.number_input("Δt (s)", min_value=0.001, max_value=1.0, value=0.02, step=0.005, key="pl_scene_rw_dt")
    c4, c5 = st.columns(2)
    steps = c4.select_slider("Time steps", options=[100, 160, 240, 400, 800], value=240, key="pl_scene_rw_steps")
    particles = c5.select_slider("Particles", options=[600, 1200, 2600, 5000, 10000], value=2600, key="pl_scene_rw_particles")
    key = "pl_physics_scene_transport_result"
    if st.button("Run transport study", type="primary", key="pl_scene_rw_run"):
        st.session_state[key] = brownian_transport_study(
            diffusion_um2_s=float(D), drift_x_um_s=float(drift), dt_s=float(dt), steps=int(steps), particles=int(particles),
        )
    result = st.session_state.get(key)
    if not result:
        st.info("Run the transport study to estimate D and drift from the stochastic trajectories.")
        return
    a, b, c, d = st.columns(4)
    a.metric("D input", f"{result['inputs']['diffusion_um2_s']:.6g} µm²/s")
    b.metric("D estimated", f"{result['estimated_diffusion_um2_s']:.6g} µm²/s")
    c.metric("D relative error", f"{100.0 * result['diffusion_relative_error']:.4g}%")
    d.metric("Drift estimated", f"{result['estimated_drift_x_um_s']:.6g} µm/s")

    msd_fig = _line_figure(
        result["time_s"], result["centered_msd_um2"],
        title="Centered mean-squared displacement", x_title="Time (s)", y_title="Centered MSD (µm²)",
        reference=(result["time_s"], result["theoretical_msd_um2"], "Theory · 4Dt"), y_clamp=(0.0, None),
    )
    st.plotly_chart(msd_fig, width="stretch")
    drift_fig = _line_figure(
        result["time_s"], result["mean_x_um"],
        title="Mean drift displacement", x_title="Time (s)", y_title="Mean x (µm)",
        reference=(result["time_s"], result["theoretical_mean_x_um"], "Theory · vt"),
    )
    st.plotly_chart(drift_fig, width="stretch")

    go = __import__("plotly.graph_objects", fromlist=["graph_objects"])
    trajectory_fig = go.Figure()
    for track in result["trajectories"]:
        trajectory_fig.add_scatter(x=track["x_um"], y=track["y_um"], mode="lines", name=f"particle {track['id']}", showlegend=False, opacity=0.55)
    trajectory_fig.update_layout(title="Representative Brownian trajectories", xaxis_title="x (µm)", yaxis_title="y (µm)", height=500)
    trajectory_fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(trajectory_fig, width="stretch")

    radius_fig = go.Figure(go.Histogram(x=result["final_centered_radius_um"], nbinsx=45, histnorm="probability density", name="Final radius"))
    radius_fig.update_layout(title="Final centered radial distribution", xaxis_title="Radius from ensemble mean (µm)", yaxis_title="Probability density", height=430)
    st.plotly_chart(radius_fig, width="stretch")
    st.caption(result["boundary"])


def render_application_mode(st: Any, profile: str, namespace: Mapping[str, Any] | None = None) -> None:
    """Render the explicit Mathematical Tool / Physics Scenario choice for hybrid Labs."""
    if profile not in APPLICATION_PROFILES:
        return
    meta = APPLICATION_PROFILES[profile]
    st.markdown("---")
    st.markdown("## Physical Lab · Application mode")
    st.caption(
        "The original Lab remains a standalone mathematical/numerical instrument. Physics Scenario mode applies that same method to a bounded physical model; it does not replace the tool or hide its numerical diagnostics."
    )
    mode = st.radio(
        "Workspace role",
        ["Mathematical tool", "Physics scenario"],
        horizontal=True,
        key=f"pl_application_mode_{profile}",
    )
    st.session_state[f"pl_application_mode_title_{profile}"] = meta["tool_title"] if mode == "Mathematical tool" else meta["physics_title"]
    if mode == "Mathematical tool":
        st.info(
            f"**{meta['tool_title']}** remains active. Use the existing solver, campaigns, V&V and scorecards as general-purpose numerical/statistical analysis. Switch to Physics scenario when you want the same method attached to a specific physical observable."
        )
        return
    st.markdown(f"### {meta['physics_title']}")
    st.caption(f"Research question: {meta['research_question']}")
    if profile == "numerical-methods":
        _render_quantum(st, profile)
    elif profile == "ising-monte-carlo":
        _render_ising(st, profile)
    elif profile == "random-walk-monte-carlo":
        _render_transport(st, profile)
