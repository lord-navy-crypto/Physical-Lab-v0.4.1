"""Cross-model refinement analyses for Physical Lab's newest scientific models.

This module intentionally sits above the existing solver/workflow modules.  It
adds deeper *interpretation and diagnostic* analyses without changing the
underlying equations of motion or widening Compute Engine execution privileges.

Scientific boundary
-------------------
- Kerr: frequency-ratio / low-order rational proximity diagnostics describe an
  integrable geodesic benchmark.  Near-rational ratios are not chaos claims.
- Sun-Jupiter-Saturn: the 5:2 phase uses projected geometric longitudes as a
  finite-window commensurability proxy.  It is not a canonical resonant angle.
- Honeycomb: group velocity is the path-projected derivative of the reduced-unit
  harmonic Bloch dispersion.  It is not a calibrated material velocity.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, replace
from fractions import Fraction
from typing import Any, Mapping

import numpy as np

REFINEMENT_SCHEMA = "physical-lab-new-model-refinement-v1"
EVIDENCE_SCHEMA = "physical-lab-model-evidence-v1"

KERR_VARIANT = "kerr-geodesic"
SOLAR_VARIANT = "sun-jupiter-saturn-dynamics"
LATTICE_VARIANT = "multilayer-honeycomb-lattice"


def _plain(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, np.generic):
        return _plain(value.item())
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _sha256_json(value: Mapping[str, Any]) -> str:
    raw = json.dumps(_plain(value), sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _nearest_rational(value: float | None, max_denominator: int = 12) -> dict[str, Any] | None:
    if value is None or not math.isfinite(float(value)):
        return None
    frac = Fraction(float(value)).limit_denominator(max(1, int(max_denominator)))
    approx = frac.numerator / frac.denominator
    return {
        "ratio": float(value),
        "nearest_low_order": f"{frac.numerator}:{frac.denominator}",
        "numerator": int(frac.numerator),
        "denominator": int(frac.denominator),
        "approximation": float(approx),
        "absolute_detuning": abs(float(value) - float(approx)),
        "max_denominator": int(max_denominator),
    }


def kerr_frequency_refinement(config: Any, *, result: Mapping[str, Any] | None = None, scan: bool = True) -> dict[str, Any]:
    """Add frequency-ratio and bounded near-resonance diagnostics to Kerr."""
    from physical_lab_kerr_geodesics import integrate_case, result_summary

    base = dict(result) if isinstance(result, Mapping) else integrate_case(config)
    summary = result_summary(base)
    diag = base["diagnostics"]

    tr = float(diag.get("radial_period_mino", float("nan")))
    tt = float(diag.get("polar_period_mino", float("nan")))
    omega_r = 2.0 * math.pi / tr if math.isfinite(tr) and tr > 0 else None
    omega_theta = 2.0 * math.pi / tt if math.isfinite(tt) and tt > 0 else None
    omega_phi = float(diag.get("mean_phi_rate_mino", float("nan")))
    if not math.isfinite(omega_phi):
        omega_phi = None

    ratio_r_theta = (omega_r / omega_theta) if omega_r is not None and omega_theta not in (None, 0.0) else None
    ratio_phi_theta = (omega_phi / omega_theta) if omega_phi is not None and omega_theta not in (None, 0.0) else None
    ratio_phi_r = (omega_phi / omega_r) if omega_phi is not None and omega_r not in (None, 0.0) else None

    ratios = {
        "omega_r_over_omega_theta": _nearest_rational(ratio_r_theta),
        "omega_phi_over_omega_theta": _nearest_rational(ratio_phi_theta),
        "omega_phi_over_omega_r": _nearest_rational(ratio_phi_r),
    }

    scan_rows: list[dict[str, Any]] = []
    if scan:
        base_dict = asdict(config)
        variants = [
            ("base", float(config.spin), float(config.inclination_deg)),
            ("spin-low", max(0.0, float(config.spin) - 0.08), float(config.inclination_deg)),
            ("spin-high", min(0.98, float(config.spin) + 0.08), float(config.inclination_deg)),
            ("inclination-low", float(config.spin), max(0.0, float(config.inclination_deg) - 8.0)),
            ("inclination-high", float(config.spin), min(85.0, float(config.inclination_deg) + 8.0)),
        ]
        for label, spin, inclination in variants:
            try:
                variant = type(config)(**{
                    **base_dict,
                    "spin": spin,
                    "inclination_deg": inclination,
                    "lam_max": min(max(float(config.lam_max), 16.0 if config.particle_type == "massive" else 4.0), 30.0),
                    "samples": min(max(int(config.samples), 1000), 1800),
                })
                vres = integrate_case(variant)
                vdiag = vres["diagnostics"]
                vr = float(vdiag.get("radial_period_mino", float("nan")))
                vt = float(vdiag.get("polar_period_mino", float("nan")))
                wr = 2.0 * math.pi / vr if math.isfinite(vr) and vr > 0 else None
                wt = 2.0 * math.pi / vt if math.isfinite(vt) and vt > 0 else None
                wp = float(vdiag.get("mean_phi_rate_mino", float("nan")))
                wp = wp if math.isfinite(wp) else None
                ratio = wr / wt if wr is not None and wt not in (None, 0.0) else None
                rational = _nearest_rational(ratio)
                scan_rows.append({
                    "case": label,
                    "spin_a_over_M": spin,
                    "inclination_deg": inclination,
                    "omega_r_mino": wr,
                    "omega_theta_mino": wt,
                    "omega_phi_mino": wp,
                    "r_over_theta": rational,
                    "first_integral_residual_max": float(result_summary(vres)["first_integral_residual_max"]),
                    "status": str(vres.get("status") or "unknown"),
                })
            except Exception as exc:
                scan_rows.append({"case": label, "spin_a_over_M": spin, "inclination_deg": inclination, "error": f"{type(exc).__name__}: {exc}"})

    return {
        "schema": REFINEMENT_SCHEMA,
        "model_variant": KERR_VARIANT,
        "frequency_definition": "Mino-time frequencies estimated from turning-point periods and mean azimuthal rate",
        "omega_r_mino": omega_r,
        "omega_theta_mino": omega_theta,
        "omega_phi_mino": omega_phi,
        "ratios": ratios,
        "local_frequency_scan": scan_rows,
        "base_summary": _plain(summary),
        "boundary": (
            "Standard unperturbed Kerr geodesics remain integrable. A ratio close to a low-order rational is a frequency-commensurability diagnostic, "
            "not evidence of chaos, capture, astrophysical resonance occupation, or self-force evolution."
        ),
    }


def _dominant_uniform_spectrum(t: np.ndarray, signal: np.ndarray, *, count: int = 5) -> list[dict[str, float]]:
    t = np.asarray(t, dtype=float)
    y = np.asarray(signal, dtype=float)
    if t.size < 16 or y.size != t.size:
        return []
    dt = float(np.mean(np.diff(t)))
    if dt <= 0 or np.max(np.abs(np.diff(t) - dt)) > 1e-6 * max(1.0, abs(dt)):
        return []
    x = t - float(np.mean(t))
    coef = np.polyfit(x, y, 1)
    detrended = y - np.polyval(coef, x)
    amp = np.abs(np.fft.rfft(detrended * np.hanning(len(detrended))))
    freq = np.fft.rfftfreq(len(detrended), d=dt)
    if len(amp) <= 1:
        return []
    order = np.argsort(amp[1:])[::-1][: max(1, int(count))] + 1
    return [{"frequency_per_year": float(freq[i]), "amplitude": float(amp[i])} for i in order]


def solar_commensurability_refinement(result: Mapping[str, Any]) -> dict[str, Any]:
    """Analyze a finite-window 5:2 geometric commensurability phase proxy."""
    t = np.asarray(result["time_years"], dtype=float)
    r = np.asarray(result["positions_AU"], dtype=float)
    if r.ndim != 3 or r.shape[1:] != (3, 3):
        raise ValueError("expected Sun/Jupiter/Saturn trajectory positions")
    rel_j = r[:, 1] - r[:, 0]
    rel_s = r[:, 2] - r[:, 0]
    lambda_j = np.unwrap(np.arctan2(rel_j[:, 1], rel_j[:, 0]))
    lambda_s = np.unwrap(np.arctan2(rel_s[:, 1], rel_s[:, 0]))
    raw_phase = 2.0 * lambda_j - 5.0 * lambda_s
    wrapped = np.angle(np.exp(1j * raw_phase))
    phase_unwrapped = np.unwrap(wrapped)

    if len(t) >= 2 and float(t[-1]) > float(t[0]):
        slope, intercept = np.polyfit(t - t[0], phase_unwrapped, 1)
        fitted = slope * (t - t[0]) + intercept
        residual_rms = float(np.sqrt(np.mean((phase_unwrapped - fitted) ** 2)))
    else:
        slope, residual_rms = float("nan"), float("nan")
    concentration = float(abs(np.mean(np.exp(1j * wrapped)))) if wrapped.size else float("nan")
    beat_period = 2.0 * math.pi / abs(float(slope)) if math.isfinite(float(slope)) and abs(float(slope)) > 1e-12 else None

    d = result["diagnostics"]
    ratio = np.asarray(d["period_ratio_saturn_over_jupiter"], dtype=float)
    j_e = np.asarray(d["jupiter"]["e"], dtype=float)
    s_e = np.asarray(d["saturn"]["e"], dtype=float)

    return {
        "schema": REFINEMENT_SCHEMA,
        "model_variant": SOLAR_VARIANT,
        "phase_definition": "psi = 2*lambda_J(projected) - 5*lambda_S(projected)",
        "phase_wrapped_rad": wrapped,
        "phase_unwrapped_rad": phase_unwrapped,
        "phase_drift_rad_per_year": float(slope),
        "phase_drift_cycles_per_year": float(slope / (2.0 * math.pi)) if math.isfinite(float(slope)) else None,
        "finite_window_circular_concentration": concentration,
        "phase_linear_residual_rms_rad": residual_rms,
        "beat_period_years_from_phase_drift": beat_period,
        "period_ratio_mean": float(np.mean(ratio)),
        "period_ratio_std": float(np.std(ratio)),
        "period_ratio_mean_deviation_from_5_2": float(np.mean(ratio) - 2.5),
        "jupiter_eccentricity_spectrum": _dominant_uniform_spectrum(t, j_e),
        "saturn_eccentricity_spectrum": _dominant_uniform_spectrum(t, s_e),
        "time_years": t,
        "boundary": (
            "This is a projected-geometric 5:2 commensurability phase proxy chosen because the rebuilt model starts nearly circular, where apsidal angles can be ill-defined. "
            "It is not a canonical disturbing-function resonant argument and finite-window phase concentration alone does not prove resonance capture."
        ),
    }


def _path_group_velocity(dispersion: Mapping[str, Any]) -> np.ndarray:
    x = np.asarray(dispersion["path_coordinate"], dtype=float)
    f = np.asarray(dispersion["frequencies_cycles_per_time"], dtype=float)
    if len(x) < 3:
        return np.zeros_like(f)
    vg = np.empty_like(f)
    for branch in range(f.shape[1]):
        # omega = 2*pi*f, so d(omega)/dq has reduced length/time units.
        vg[:, branch] = 2.0 * math.pi * np.gradient(f[:, branch], x, edge_order=1)
    # Direction changes at high-symmetry corners; do not use those one-sided
    # path derivatives as a global transport maximum.
    for tick in np.asarray(dispersion["tick_positions"], dtype=float)[1:-1]:
        idx = int(np.argmin(np.abs(x - tick)))
        for j in range(max(0, idx - 1), min(len(x), idx + 2)):
            vg[j, :] = np.nan
    return vg


def _dispersion_gap_summary(dispersion: Mapping[str, Any]) -> dict[str, Any]:
    x = np.asarray(dispersion["path_coordinate"], dtype=float)
    f = np.asarray(dispersion["frequencies_cycles_per_time"], dtype=float)
    if f.shape[1] < 2:
        return {"minimum_adjacent_gap": None, "minimum_positive_adjacent_gap": None}
    gaps = np.maximum(f[:, 1:] - f[:, :-1], 0.0)
    flat = int(np.argmin(gaps))
    qi, bi = np.unravel_index(flat, gaps.shape)
    positive_mask = gaps > 1e-8
    positive = gaps[positive_mask]
    positive_min = float(np.min(positive)) if positive.size else None
    if positive_min is not None:
        candidates = np.argwhere(np.isclose(gaps, positive_min, rtol=1e-10, atol=1e-12))
        pqi, pbi = map(int, candidates[0])
    else:
        pqi, pbi = qi, bi
    return {
        "minimum_adjacent_gap": float(gaps[qi, bi]),
        "minimum_gap_branch_pair": [int(bi), int(bi + 1)],
        "minimum_gap_path_coordinate": float(x[qi]),
        "minimum_positive_adjacent_gap": positive_min,
        "minimum_positive_gap_branch_pair": [int(pbi), int(pbi + 1)] if positive_min is not None else None,
        "minimum_positive_gap_path_coordinate": float(x[pqi]) if positive_min is not None else None,
        "boundary": "Adjacent-branch gap minima identify degeneracy/near-crossing locations only; they do not by themselves establish an avoided crossing or interaction mechanism.",
    }


def lattice_transport_refinement(config: Any, *, points_per_segment: int = 36, strain_sweep: bool = True) -> dict[str, Any]:
    """Add path-projected group velocity, branch-gap and strain diagnostics."""
    from physical_lab_lattice_phonons import phonon_dispersion

    dispersion = phonon_dispersion(config, points_per_segment=int(points_per_segment))
    vg = _path_group_velocity(dispersion)
    finite = np.abs(vg[np.isfinite(vg)])
    global_max = float(np.max(finite)) if finite.size else None
    branch_max = []
    for branch in range(vg.shape[1]):
        vals = np.abs(vg[:, branch])
        vals = vals[np.isfinite(vals)]
        branch_max.append(float(np.max(vals)) if vals.size else None)
    gaps = _dispersion_gap_summary(dispersion)

    strain_rows: list[dict[str, Any]] = []
    if strain_sweep:
        for offset in (-0.04, -0.02, 0.0, 0.02, 0.04):
            strain = min(0.20, max(-0.20, float(config.strain_x) + offset))
            scfg = replace(config, strain_x=strain)
            sdisp = phonon_dispersion(scfg, points_per_segment=18)
            svg = _path_group_velocity(sdisp)
            vals = np.abs(svg[np.isfinite(svg)])
            sgap = _dispersion_gap_summary(sdisp)
            strain_rows.append({
                "strain_x": strain,
                "frequency_max": float(np.max(np.asarray(sdisp["frequencies_cycles_per_time"], dtype=float))),
                "max_abs_path_group_velocity": float(np.max(vals)) if vals.size else None,
                "minimum_positive_adjacent_gap": sgap.get("minimum_positive_adjacent_gap"),
                "gamma_zero_mode_count": int(sdisp["gamma_zero_mode_count"]),
                "negative_eigenvalue_magnitude_max": float(sdisp["negative_eigenvalue_magnitude_max"]),
            })

    return {
        "schema": REFINEMENT_SCHEMA,
        "model_variant": LATTICE_VARIANT,
        "group_velocity_reduced": vg,
        "max_abs_path_group_velocity": global_max,
        "max_abs_path_group_velocity_by_branch": branch_max,
        "gap_diagnostics": gaps,
        "strain_sweep": strain_rows,
        "dispersion_summary": {
            "branch_count": int(dispersion["branch_count"]),
            "gamma_zero_mode_count": int(dispersion["gamma_zero_mode_count"]),
            "hermiticity_residual_max": float(dispersion["hermiticity_residual_max"]),
            "negative_eigenvalue_magnitude_max": float(dispersion["negative_eigenvalue_magnitude_max"]),
            "path_coordinate": np.asarray(dispersion["path_coordinate"], dtype=float),
            "tick_positions": np.asarray(dispersion["tick_positions"], dtype=float),
            "tick_labels": list(dispersion["tick_labels"]),
        },
        "boundary": (
            "Group velocity is d(omega)/dq projected along the chosen Gamma-K-M-Gamma path in reduced units. Values at path corners are excluded from maxima. "
            "They are not SI material velocities, and localized defects/anharmonic transport are outside this harmonic bulk derivative."
        ),
    }


_MODEL_BOUNDARIES = {
    KERR_VARIANT: {
        "fidelity_level": "exact Kerr background / test-particle geodesic equations with numerical constants-of-motion solving",
        "supports": [
            "dimensionless Kerr geodesic trajectory studies",
            "Carter first-integral verification",
            "spherical-photon local radial instability",
            "Mino-time frequency commensurability diagnostics",
        ],
        "does_not_support": [
            "self-force or radiation reaction",
            "binary black-hole dynamics",
            "astrophysical parameter inference",
            "generic chaos claims for unperturbed Kerr geodesics",
        ],
    },
    SOLAR_VARIANT: {
        "fidelity_level": "barycentric Newtonian Sun-Jupiter-Saturn point masses with optional central-Sun 1PN approximation",
        "supports": [
            "long-term reduced solar-system orbital dynamics",
            "barycenter/momentum/energy/angular-momentum verification in the Newtonian baseline",
            "finite-time sensitivity indicators",
            "5:2 period and geometric commensurability diagnostics",
        ],
        "does_not_support": [
            "full Solar System ephemeris reproduction",
            "full Einstein-Infeld-Hoffmann N-body 1PN",
            "physical spin-orbit or gravitational-wave reaction from the legacy toy terms",
            "proof of canonical resonance capture from a projected phase proxy",
        ],
    },
    LATTICE_VARIANT: {
        "fidelity_level": "reduced-unit central-spring multilayer honeycomb dynamics with pristine harmonic Bloch bulk reference",
        "supports": [
            "periodic honeycomb topology and equilibrium-force verification",
            "finite-supercell normal modes",
            "harmonic Bloch dispersion and normalized DOS",
            "reduced path-projected group-velocity and branch-gap diagnostics",
        ],
        "does_not_support": [
            "ab-initio graphene phonons",
            "calibrated van-der-Waals interlayer physics",
            "SI thermal conductivity or material group velocity",
            "localized-defect Bloch periodicity without a dedicated supercell Bloch treatment",
        ],
    },
}


def build_model_evidence_contract(
    model_variant: str,
    *,
    manifest: Mapping[str, Any] | None = None,
    campaign: Mapping[str, Any] | None = None,
    refinement: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if model_variant not in _MODEL_BOUNDARIES:
        raise ValueError(f"unsupported new model variant: {model_variant}")
    boundary = _MODEL_BOUNDARIES[model_variant]
    screening = (campaign or {}).get("screening") if isinstance(campaign, Mapping) else None
    if isinstance(screening, Mapping):
        screening_status = str(screening.get("status") or "REVIEW")
    else:
        screening_status = "NOT-RUN"
    uncertainty = (manifest or {}).get("uncertainty") if isinstance(manifest, Mapping) else None
    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "model_variant": model_variant,
        "experiment_sha256": (manifest or {}).get("experiment_sha256") if isinstance(manifest, Mapping) else None,
        "computational_screening": screening_status,
        "fidelity_level": boundary["fidelity_level"],
        "supported_claims": list(boundary["supports"]),
        "unsupported_claims": list(boundary["does_not_support"]),
        "uncertainty_class": _plain(uncertainty) if isinstance(uncertainty, Mapping) else None,
        "refinement_schema": (refinement or {}).get("schema") if isinstance(refinement, Mapping) else None,
        "refinement_boundary": (refinement or {}).get("boundary") if isinstance(refinement, Mapping) else None,
        "reproducibility": {
            "manifest_fingerprint_present": bool((manifest or {}).get("experiment_sha256")) if isinstance(manifest, Mapping) else False,
            "campaign_result_present": bool(campaign),
            "refinement_result_present": bool(refinement),
        },
        "authority_boundary": "Solver outputs and registered measurements remain authoritative. This contract organizes computational evidence; it is not experimental validation, certification, or an AI-generated physics result.",
    }
    evidence["evidence_sha256"] = _sha256_json(evidence)
    return evidence


def render_refinement_report_markdown(evidence: Mapping[str, Any], refinement: Mapping[str, Any]) -> str:
    lines = [
        "# Physical Lab · New Model Refinement Evidence",
        "",
        f"- Model variant: `{evidence.get('model_variant')}`",
        f"- Experiment SHA-256: `{evidence.get('experiment_sha256') or 'not registered'}`",
        f"- Evidence SHA-256: `{evidence.get('evidence_sha256')}`",
        f"- Computational screening: **{evidence.get('computational_screening')}**",
        "",
        "## Fidelity level",
        "",
        str(evidence.get("fidelity_level") or ""),
        "",
        "## Supported claims",
        "",
    ]
    lines.extend(f"- {item}" for item in evidence.get("supported_claims") or [])
    lines += ["", "## Unsupported claims", ""]
    lines.extend(f"- {item}" for item in evidence.get("unsupported_claims") or [])
    lines += [
        "",
        "## Refinement result",
        "",
        "```json",
        json.dumps(_plain(refinement), ensure_ascii=False, indent=2, allow_nan=False),
        "```",
        "",
        "## Authority boundary",
        "",
        str(evidence.get("authority_boundary") or ""),
        "",
    ]
    return "\n".join(lines)