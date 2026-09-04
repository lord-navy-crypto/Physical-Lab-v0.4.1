"""Bloch-wave harmonic analysis for Physical Lab's honeycomb lattice model.

Scientific boundary
-------------------
This module analyzes the *periodic harmonic bulk reference* associated with the
reduced-unit Multilayer Honeycomb Lattice Dynamics model.  It is intentionally
separate from the time-domain DOP853/Langevin solver.

The implementation provides a primitive-cell Bloch dynamical matrix, a
Gamma-K-M-Gamma reference path, harmonic dispersion, a Brillouin-zone sampled
phonon density of states, and mode polarization/participation diagnostics.

It is not an ab-initio graphene phonon calculation.  Localized defects,
damping, driving, stochastic forcing, and cubic anharmonic coefficients are not
part of the harmonic Bloch eigenproblem.  When affine strain is non-zero, the
fractional K/M points are inherited reference points of the strained reciprocal
basis and need not remain exact crystal-symmetry points.
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Mapping

import numpy as np

from physical_lab_lattice_dynamics import LatticeConfig

PHONON_SCHEMA = "physical-lab-honeycomb-phonon-v1"
DISPERSION_PATH = ("Γ", "K", "M", "Γ")


def bulk_reference_config(config: LatticeConfig) -> LatticeConfig:
    """Return the pristine harmonic bulk reference for Bloch analysis.

    Bulk harmonic analysis deliberately excludes localized defects and all
    time-domain non-conservative controls.  Geometry, masses, stacking, strain,
    and harmonic spring constants remain authoritative.
    """
    return replace(
        config,
        defect_mode="none",
        damping=0.0,
        interlayer_damping=0.0,
        drive_mode="none",
        drive_amplitude=0.0,
        uniform_force_x=0.0,
        stochastic_mode=False,
        temperature_reduced=0.0,
        initial_displacement=0.0,
    )


def _primitive_vectors(config: LatticeConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    b = float(config.bond_length)
    a1 = np.array([math.sqrt(3.0) * b, 0.0], dtype=float)
    a2 = np.array([math.sqrt(3.0) * b / 2.0, 1.5 * b], dtype=float)
    affine = np.array([[1.0 + float(config.strain_x), 0.0], [0.0, 1.0]], dtype=float)
    a1 = affine @ a1
    a2 = affine @ a2
    basis = np.asarray([[0.0, 0.0], [0.0, b]], dtype=float) @ affine.T
    delta = affine @ ((np.array([math.sqrt(3.0) * b, 0.0]) + np.array([math.sqrt(3.0) * b / 2.0, 1.5 * b])) / 3.0)
    return a1, a2, basis, delta


def reciprocal_vectors(config: LatticeConfig) -> tuple[np.ndarray, np.ndarray]:
    a1, a2, _, _ = _primitive_vectors(config)
    amat = np.column_stack([a1, a2])
    bmat = 2.0 * math.pi * np.linalg.inv(amat).T
    return bmat[:, 0], bmat[:, 1]


def _stack_shift(layer: int, stacking: str, delta: np.ndarray) -> np.ndarray:
    if stacking == "AA":
        return np.zeros(2, dtype=float)
    if stacking == "ABA":
        return np.zeros(2, dtype=float) if layer % 2 == 0 else delta.copy()
    return (layer % 3) * delta


def _inplane_bonds(config: LatticeConfig) -> list[tuple[int, int, np.ndarray, np.ndarray]]:
    """Primitive-cell A->B nearest-neighbor bonds.

    Returns (sub_i, sub_j, lattice_translation_R, unit_bond_vector).
    """
    a1, a2, basis, _ = _primitive_vectors(config)
    translations = (np.zeros(2), -a2, a1 - a2)
    out: list[tuple[int, int, np.ndarray, np.ndarray]] = []
    for rcell in translations:
        dr = basis[1] + rcell - basis[0]
        norm = float(np.linalg.norm(dr))
        if norm <= 0:
            raise ValueError("invalid zero-length honeycomb bond")
        out.append((0, 1, np.asarray(rcell, dtype=float), dr / norm))
    return out


def _interlayer_bonds(config: LatticeConfig) -> list[tuple[int, int, int, int, np.ndarray]]:
    """Match each lower-layer basis site to its nearest upper-layer basis site.

    This mirrors the reduced model's registry-matched shear proxy.  The returned
    lattice translation determines the Bloch phase; the harmonic shear block is
    isotropic in x/y and therefore does not use a bond direction.
    """
    a1, a2, basis, delta = _primitive_vectors(config)
    candidates = [(i, j, i * a1 + j * a2) for i in range(-1, 2) for j in range(-1, 2)]
    bonds: list[tuple[int, int, int, int, np.ndarray]] = []
    for layer in range(int(config.layers) - 1):
        lower_shift = _stack_shift(layer, config.stacking, delta)
        upper_shift = _stack_shift(layer + 1, config.stacking, delta)
        chosen_upper: set[tuple[int, int, int]] = set()
        for sub_i in range(2):
            best: tuple[float, int, int, int, np.ndarray] | None = None
            p_i = lower_shift + basis[sub_i]
            for sub_j in range(2):
                for n1, n2, rcell in candidates:
                    dr = upper_shift + basis[sub_j] + rcell - p_i
                    d2 = float(np.dot(dr, dr))
                    key = (sub_j, n1, n2)
                    penalty = 1e-12 if key in chosen_upper else 0.0
                    item = (d2 + penalty, sub_j, n1, n2, rcell)
                    if best is None or item[0] < best[0]:
                        best = item
            assert best is not None
            _, sub_j, n1, n2, rcell = best
            chosen_upper.add((sub_j, n1, n2))
            bonds.append((layer, sub_i, layer + 1, sub_j, np.asarray(rcell, dtype=float)))
    return bonds


def _dof(layer: int, sub: int) -> slice:
    base = 4 * int(layer) + 2 * int(sub)
    return slice(base, base + 2)


def bloch_dynamical_matrix(config: LatticeConfig, q_cart: np.ndarray) -> np.ndarray:
    """Return the mass-weighted Hermitian Bloch dynamical matrix D(q)."""
    cfg = bulk_reference_config(config)
    cfg.validate()
    q = np.asarray(q_cart, dtype=float).reshape(2)
    ndof = 4 * int(cfg.layers)
    dmat = np.zeros((ndof, ndof), dtype=np.complex128)
    mass = float(cfg.mass)

    for layer in range(int(cfg.layers)):
        for sub_i, sub_j, rcell, unit in _inplane_bonds(cfg):
            block = float(cfg.k_in) * np.outer(unit, unit) / mass
            si, sj = _dof(layer, sub_i), _dof(layer, sub_j)
            phase = np.exp(1j * float(np.dot(q, rcell)))
            dmat[si, si] += block
            dmat[sj, sj] += block
            dmat[si, sj] -= block * phase
            dmat[sj, si] -= block * np.conjugate(phase)

    if int(cfg.layers) > 1 and float(cfg.k_inter) > 0:
        block = (float(cfg.k_inter) / mass) * np.eye(2)
        for li, si_idx, lj, sj_idx, rcell in _interlayer_bonds(cfg):
            si, sj = _dof(li, si_idx), _dof(lj, sj_idx)
            phase = np.exp(1j * float(np.dot(q, rcell)))
            dmat[si, si] += block
            dmat[sj, sj] += block
            dmat[si, sj] -= block * phase
            dmat[sj, si] -= block * np.conjugate(phase)
    return dmat


def bloch_eigensystem(config: LatticeConfig, q_cart: np.ndarray) -> dict[str, Any]:
    dmat = bloch_dynamical_matrix(config, q_cart)
    hermitian_residual = float(np.max(np.abs(dmat - dmat.conj().T)))
    eigvals, eigvecs = np.linalg.eigh(0.5 * (dmat + dmat.conj().T))
    order = np.argsort(eigvals)
    eigvals = np.asarray(eigvals[order], dtype=float)
    eigvecs = np.asarray(eigvecs[:, order], dtype=np.complex128)
    frequencies = np.sqrt(np.maximum(eigvals, 0.0)) / (2.0 * math.pi)
    return {
        "dynamical_matrix": dmat,
        "eigenvalues": eigvals,
        "eigenvectors": eigvecs,
        "frequencies_cycles_per_time": frequencies,
        "hermiticity_residual": hermitian_residual,
        "negative_eigenvalue_count": int(np.count_nonzero(eigvals < -1e-9)),
        "most_negative_eigenvalue": float(np.min(eigvals)),
    }


def _fractional_special_points(config: LatticeConfig) -> dict[str, np.ndarray]:
    b1, b2 = reciprocal_vectors(config)
    return {
        "Γ": np.zeros(2, dtype=float),
        "K": (2.0 * b1 + b2) / 3.0,
        "M": (b1 + b2) / 2.0,
    }


def high_symmetry_path(config: LatticeConfig, points_per_segment: int = 40) -> dict[str, Any]:
    if int(points_per_segment) < 4 or int(points_per_segment) > 400:
        raise ValueError("points_per_segment must be between 4 and 400")
    pts = _fractional_special_points(config)
    labels = list(DISPERSION_PATH)
    q_rows: list[np.ndarray] = []
    x_rows: list[float] = []
    ticks: list[float] = [0.0]
    cumulative = 0.0
    for segment in range(len(labels) - 1):
        qa, qb = pts[labels[segment]], pts[labels[segment + 1]]
        count = int(points_per_segment)
        ts = np.linspace(0.0, 1.0, count, endpoint=(segment == len(labels) - 2))
        for idx, t in enumerate(ts):
            q = (1.0 - t) * qa + t * qb
            if q_rows:
                cumulative += float(np.linalg.norm(q - q_rows[-1]))
            q_rows.append(q)
            x_rows.append(cumulative)
        ticks.append(cumulative)
    return {
        "q_cart": np.asarray(q_rows, dtype=float),
        "path_coordinate": np.asarray(x_rows, dtype=float),
        "tick_positions": np.asarray(ticks, dtype=float),
        "tick_labels": labels,
        "special_points": pts,
    }


def phonon_dispersion(config: LatticeConfig, points_per_segment: int = 40) -> dict[str, Any]:
    cfg = bulk_reference_config(config)
    path = high_symmetry_path(cfg, points_per_segment=points_per_segment)
    frequencies: list[np.ndarray] = []
    eigenvalues: list[np.ndarray] = []
    hermitian_max = 0.0
    most_negative = 0.0
    for q in path["q_cart"]:
        eig = bloch_eigensystem(cfg, q)
        frequencies.append(eig["frequencies_cycles_per_time"])
        eigenvalues.append(eig["eigenvalues"])
        hermitian_max = max(hermitian_max, float(eig["hermiticity_residual"]))
        most_negative = min(most_negative, float(eig["most_negative_eigenvalue"]))

    special: dict[str, Any] = {}
    for label, q in path["special_points"].items():
        eig = bloch_eigensystem(cfg, q)
        special[label] = {
            "q_cart": [float(x) for x in q],
            "frequencies_cycles_per_time": [float(x) for x in eig["frequencies_cycles_per_time"]],
            "eigenvalues": [float(x) for x in eig["eigenvalues"]],
        }
    gamma_eig = np.asarray(special["Γ"]["eigenvalues"], dtype=float)
    return {
        "schema": PHONON_SCHEMA,
        "q_cart": path["q_cart"],
        "path_coordinate": path["path_coordinate"],
        "frequencies_cycles_per_time": np.asarray(frequencies, dtype=float),
        "eigenvalues": np.asarray(eigenvalues, dtype=float),
        "tick_positions": path["tick_positions"],
        "tick_labels": path["tick_labels"],
        "special_points": special,
        "branch_count": int(4 * cfg.layers),
        "gamma_zero_mode_count": int(np.count_nonzero(np.abs(gamma_eig) <= 1e-8)),
        "hermiticity_residual_max": float(hermitian_max),
        "negative_eigenvalue_magnitude_max": max(0.0, -float(most_negative)),
        "boundary": "Harmonic Bloch dispersion of the pristine reduced-unit periodic reference. It is not an ab-initio or experimentally calibrated material dispersion.",
        "strain_note": "For non-zero affine strain, K and M are inherited fractional reference points and need not remain exact symmetry points." if abs(float(cfg.strain_x)) > 0 else None,
    }


def phonon_dos(config: LatticeConfig, q_grid: int = 18, bins: int = 80) -> dict[str, Any]:
    cfg = bulk_reference_config(config)
    if not (4 <= int(q_grid) <= 80):
        raise ValueError("q_grid must be between 4 and 80")
    if not (16 <= int(bins) <= 240):
        raise ValueError("bins must be between 16 and 240")
    b1, b2 = reciprocal_vectors(cfg)
    values: list[float] = []
    negative_max = 0.0
    hermitian_max = 0.0
    for i in range(int(q_grid)):
        for j in range(int(q_grid)):
            q = (i / int(q_grid)) * b1 + (j / int(q_grid)) * b2
            eig = bloch_eigensystem(cfg, q)
            values.extend(float(x) for x in eig["frequencies_cycles_per_time"])
            negative_max = max(negative_max, max(0.0, -float(eig["most_negative_eigenvalue"])))
            hermitian_max = max(hermitian_max, float(eig["hermiticity_residual"]))
    arr = np.asarray(values, dtype=float)
    upper = max(float(np.max(arr)) * 1.001, 1e-9)
    counts, edges = np.histogram(arr, bins=int(bins), range=(0.0, upper), density=False)
    widths = np.diff(edges)
    density = counts.astype(float) / max(float(np.sum(counts)), 1.0) / widths
    centers = 0.5 * (edges[:-1] + edges[1:])
    integral = float(np.sum(density * widths))
    return {
        "schema": PHONON_SCHEMA,
        "frequency_centers": centers,
        "density": density,
        "bin_edges": edges,
        "sample_count": int(arr.size),
        "q_grid": int(q_grid),
        "branch_count": int(4 * cfg.layers),
        "normalization_integral": integral,
        "normalization_error": abs(integral - 1.0),
        "zero_frequency_fraction": float(np.mean(arr <= 1e-10)),
        "frequency_min": float(np.min(arr)),
        "frequency_max": float(np.max(arr)),
        "negative_eigenvalue_magnitude_max": float(negative_max),
        "hermiticity_residual_max": float(hermitian_max),
        "boundary": "Histogram DOS from uniform sampling of the primitive reciprocal-cell parallelogram. Reduced-unit harmonic model only.",
    }


def mode_character(config: LatticeConfig, q_cart: np.ndarray, branch_index: int) -> dict[str, Any]:
    cfg = bulk_reference_config(config)
    eig = bloch_eigensystem(cfg, q_cart)
    nbranch = len(eig["eigenvalues"])
    branch = int(branch_index)
    if branch < 0 or branch >= nbranch:
        raise ValueError(f"branch_index must be between 0 and {nbranch - 1}")
    vec = np.asarray(eig["eigenvectors"][:, branch]).reshape(int(cfg.layers), 2, 2)
    amp2 = np.sum(np.abs(vec) ** 2, axis=2)
    layer_participation = np.sum(amp2, axis=1)
    sublattice_participation = np.sum(amp2, axis=0)
    q = np.asarray(q_cart, dtype=float)
    qnorm = float(np.linalg.norm(q))
    longitudinal = None
    if qnorm > 1e-12:
        qhat = q / qnorm
        flat = vec.reshape(-1, 2)
        longitudinal = float(np.sum(np.abs(flat @ qhat) ** 2) / max(np.sum(np.abs(flat) ** 2), 1e-15))
    return {
        "branch_index": branch,
        "frequency_cycles_per_time": float(eig["frequencies_cycles_per_time"][branch]),
        "eigenvalue": float(eig["eigenvalues"][branch]),
        "layer_participation": [float(x) for x in layer_participation],
        "sublattice_participation": [float(x) for x in sublattice_participation],
        "longitudinal_fraction": longitudinal,
        "polarization_boundary": "Longitudinal fraction is defined relative to in-plane q and is undefined at Gamma. Complex eigenvector phase is gauge-dependent; participation magnitudes are gauge-invariant.",
    }


def monolayer_gamma_benchmark(config: LatticeConfig) -> dict[str, Any]:
    cfg = replace(
        bulk_reference_config(config),
        layers=1,
        stacking="AA",
        strain_x=0.0,
        defect_mode="none",
    )
    eig = bloch_eigensystem(cfg, np.zeros(2))
    expected_lambda = 3.0 * float(cfg.k_in) / float(cfg.mass)
    expected_frequency = math.sqrt(expected_lambda) / (2.0 * math.pi)
    observed = np.asarray(eig["eigenvalues"], dtype=float)
    optical = observed[-2:]
    relative_error = float(np.max(np.abs(optical - expected_lambda)) / max(abs(expected_lambda), 1e-15))
    return {
        "expected_gamma_eigenvalues": [0.0, 0.0, expected_lambda, expected_lambda],
        "observed_gamma_eigenvalues": [float(x) for x in observed],
        "expected_optical_frequency_cycles_per_time": expected_frequency,
        "relative_error": relative_error,
        "zero_mode_count": int(np.count_nonzero(np.abs(observed) <= 1e-8)),
        "boundary": "Analytic benchmark for an unstrained monolayer with nearest-neighbor central harmonic springs in the reduced model.",
    }


def compact_phonon_summary(dispersion: Mapping[str, Any], dos: Mapping[str, Any]) -> dict[str, Any]:
    special = dispersion.get("special_points") or {}
    return {
        "branch_count": int(dispersion.get("branch_count") or 0),
        "gamma_zero_mode_count": int(dispersion.get("gamma_zero_mode_count") or 0),
        "hermiticity_residual_max": float(dispersion.get("hermiticity_residual_max") or 0.0),
        "negative_eigenvalue_magnitude_max": float(dispersion.get("negative_eigenvalue_magnitude_max") or 0.0),
        "dos_normalization_error": float(dos.get("normalization_error") or 0.0),
        "dos_frequency_max": float(dos.get("frequency_max") or 0.0),
        "high_symmetry_frequencies": {
            label: list((special.get(label) or {}).get("frequencies_cycles_per_time") or [])
            for label in ("Γ", "K", "M")
        },
        "boundary": "Harmonic periodic bulk-reference analysis in reduced units; localized defects and anharmonic finite-temperature renormalization are outside this result.",
    }
