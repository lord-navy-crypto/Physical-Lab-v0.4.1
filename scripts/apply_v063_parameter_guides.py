#!/usr/bin/env python3
"""One-time patch: expand Local AI parameter semantics across all seven Labs."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "src-tauri/resources/ui/physical_lab_local_ai.py"
VALIDATION = ROOT / "scripts/local_ai_reference_validation.py"
DOC = ROOT / "docs/LOCAL_AI_TUTOR.md"

advanced_guides = r'''

# Advanced Physical Lab controls are defined by the injected research suites.
# Keep their metadata separate from upstream/core controls so a local model can
# distinguish the original Lab state from Physical Lab's additional experiment
# orchestration. Every key below comes from an actual Streamlit widget key in
# physical_lab_advanced.py; units are explicit where the UI/equation defines one.
ADVANCED_PARAMETER_GUIDES: dict[str, dict[str, dict[str, str]]] = {
    "numerical-methods": {
        "pl_n_xmax": {"unit": "rad", "meaning": "Maximum |x| used when mapping the sine-evaluation reliability frontier."},
        "pl_n_points": {"unit": "scan points", "meaning": "Number of x samples in the reliability-frontier scan."},
        "pl_n_dtype": {"unit": "arithmetic type", "meaning": "Floating-point arithmetic used by the frontier comparison (float32 or float64)."},
        "pl_n_at_method": {"unit": "method choice", "meaning": "Taylor evaluation strategy used by the cancellation atlas: raw or range-reduced."},
        "pl_n_at_dtype": {"unit": "arithmetic type", "meaning": "Floating-point arithmetic used by the cancellation atlas."},
        "pl_n_at_xmax": {"unit": "rad", "meaning": "Maximum input magnitude represented on the cancellation atlas."},
        "pl_n_at_grid": {"unit": "grid samples/axis", "meaning": "Resolution used for both input magnitude and Taylor-term sampling in the cancellation atlas."},
        "pl_n_at_terms": {"unit": "Taylor terms", "meaning": "Maximum fixed Taylor-series term count explored by the cancellation atlas."},
        "pl_n_micro_x": {"unit": "rad", "meaning": "Single input x inspected term-by-term in the numerical error microscope."},
        "pl_n_micro_dtype": {"unit": "arithmetic type", "meaning": "Floating-point arithmetic used by the term-by-term microscope."},
        "pl_n_micro_n": {"unit": "Taylor terms", "meaning": "Maximum term count inspected in the term-by-term error microscope."},
    },
    "ising-monte-carlo": {
        "pl_i_tmin": {"unit": "model temperature", "meaning": "Lower temperature bound of the coarse critical-region scan."},
        "pl_i_tmax": {"unit": "model temperature", "meaning": "Upper temperature bound of the coarse critical-region scan."},
        "pl_i_cn": {"unit": "temperature points", "meaning": "Number of coarse temperature samples before adaptive refinement."},
        "pl_i_rn": {"unit": "temperature points", "meaning": "Number of samples used in the refined critical-region window."},
        "pl_i_method": {"unit": "sampler choice", "meaning": "Monte Carlo update method used for the adaptive critical scan."},
        "pl_i_peak_seeds": {"unit": "independent RNG seeds", "meaning": "Number of independent repetitions used to audit critical-peak location stability."},
        "pl_i_peak_eq": {"unit": "equilibration cycles/seed", "meaning": "Thermalization budget for each independent critical-peak audit run."},
        "pl_i_peak_mc": {"unit": "measurement cycles/seed", "meaning": "Sampling budget for each independent critical-peak audit run."},
        "pl_i_sizes": {"unit": "lattice-size list", "meaning": "Comma-separated linear lattice sizes L used for the Binder-cumulant finite-size probe."},
        "pl_i_bmin": {"unit": "model temperature", "meaning": "Lower temperature bound of the Binder-cumulant scan."},
        "pl_i_bmax": {"unit": "model temperature", "meaning": "Upper temperature bound of the Binder-cumulant scan."},
        "pl_i_bpoints": {"unit": "temperature points", "meaning": "Number of temperature samples per lattice size in the Binder analysis."},
        "pl_i_dist_L": {"unit": "lattice sites/side", "meaning": "Linear lattice size used by the magnetization-distribution microscope."},
        "pl_i_dist_T": {"unit": "model temperature", "meaning": "Temperature used to sample the magnetization distribution."},
        "pl_i_eff_t": {"unit": "model temperature", "meaning": "Temperature at which compatible Monte Carlo samplers are compared by effective samples per work unit."},
    },
    "random-walk-monte-carlo": {
        "pl_rw_s_dim": {"unit": "dimensions", "meaning": "Spatial dimension used by the diffusion-scaling scan."},
        "pl_rw_s_walkers": {"unit": "walkers/scan point", "meaning": "Ensemble size used at each step-count value in the diffusion-scaling scan."},
        "pl_rw_s_nmin": {"unit": "steps/walker", "meaning": "Minimum random-walk length in the log-spaced diffusion-scaling scan."},
        "pl_rw_s_nmax": {"unit": "steps/walker", "meaning": "Maximum random-walk length in the log-spaced diffusion-scaling scan."},
        "pl_rw_s_points": {"unit": "scan points", "meaning": "Number of log-spaced walk lengths used to fit diffusion exponents."},
        "pl_rw_d_max": {"unit": "dimensions", "meaning": "Highest spatial dimension included in the dimension-concentration study."},
        "pl_rw_d_steps": {"unit": "steps/walker", "meaning": "Walk length held fixed while dimension is scanned."},
        "pl_rw_d_walkers": {"unit": "walkers/dimension", "meaning": "Ensemble size used at each dimension in the concentration study."},
        "pl_rw_q_powers": {"unit": "powers of two", "meaning": "Comma-separated exponents p defining matched sample budgets N=2^p for MC versus scrambled Sobol QMC."},
        "pl_rw_q_reps": {"unit": "independent replicates", "meaning": "Number of pseudorandom trials or independently scrambled Sobol replicates per sample budget."},
        "pl_rw_r_horizons": {"unit": "steps", "meaning": "Comma-separated finite observation horizons used for return-to-origin probability."},
        "pl_rw_r_dims": {"unit": "dimensions", "meaning": "Comma-separated spatial dimensions included in the recurrence-horizon study."},
        "pl_rw_r_trials": {"unit": "trials/point", "meaning": "Independent random-walk trials used for each dimension/horizon recurrence estimate."},
    },
    "nonlinear-chaos": {
        "pl_c_pair_dur": {"unit": "s", "meaning": "Integration duration for the nearby twin-trajectory divergence experiment."},
        "pl_c_pair_dt": {"unit": "s/step", "meaning": "Integrator time step used for the paired-trajectory divergence experiment."},
        "pl_c_pair_pert": {"unit": "log10(rad)", "meaning": "Base-10 exponent of the initial theta1 angular perturbation between the twin trajectories."},
        "pl_c_ly_dur": {"unit": "s", "meaning": "Finite observation duration used for the largest-Lyapunov-exponent estimate."},
        "pl_c_ly_dt": {"unit": "s/step", "meaning": "Integrator time step used by the finite-time Lyapunov calculation."},
        "pl_c_ly_ren": {"unit": "s", "meaning": "Time interval between perturbation renormalizations in the Benettin-style Lyapunov estimate."},
        "pl_c_at_span": {"unit": "rad", "meaning": "Symmetric initial-angle span sampled on each axis of the flip-time stability atlas."},
        "pl_c_at_res": {"unit": "initial conditions/axis", "meaning": "Grid resolution of the two-angle initial-condition stability atlas."},
        "pl_c_at_tmax": {"unit": "s", "meaning": "Finite maximum observation time for detecting a flip in the stability atlas."},
        "pl_c_at_dt": {"unit": "s/step", "meaning": "Integrator time step used by the flip-time atlas."},
        "pl_c_d_amin": {"unit": "model drive amplitude", "meaning": "Lower drive-amplitude bound of the driven Poincare scan."},
        "pl_c_d_amax": {"unit": "model drive amplitude", "meaning": "Upper drive-amplitude bound of the driven Poincare scan."},
        "pl_c_d_points": {"unit": "amplitude points", "meaning": "Number of drive-amplitude values in the stroboscopic response scan."},
        "pl_c_d_periods": {"unit": "drive periods", "meaning": "Number of forcing periods simulated at each drive amplitude."},
        "pl_c_d_gamma": {"unit": "model damping parameter", "meaning": "Damping parameter used by the driven-pendulum Poincare experiment."},
        "pl_c_d_freq": {"unit": "model angular-frequency convention", "meaning": "Drive frequency passed to the upstream driven-pendulum model."},
    },
    "oscillation-integration": {
        "pl_o_gmax": {"unit": "s^-1", "meaning": "Maximum damping coefficient gamma included in the linear damping-versus-drive atlas."},
        "pl_o_rmin": {"unit": "Omega/omega0", "meaning": "Minimum drive-to-natural-frequency ratio in the response atlas."},
        "pl_o_rmax": {"unit": "Omega/omega0", "meaning": "Maximum drive-to-natural-frequency ratio in the response atlas."},
        "pl_o_res": {"unit": "grid samples/axis", "meaning": "Resolution of the damping-versus-frequency-ratio response atlas."},
        "pl_o_force": {"unit": "N", "meaning": "Drive-force amplitude F0 used by the linear steady-state response atlas."},
        "pl_o_dtmin": {"unit": "s/step", "meaning": "Smallest integration time step included in the solver-convergence comparison."},
        "pl_o_dtmax": {"unit": "s/step", "meaning": "Largest integration time step included in the solver-convergence comparison."},
        "pl_o_dtpts": {"unit": "dt points", "meaning": "Number of geometrically spaced time-step values used to estimate integrator error/order."},
        "pl_o_e_gamma": {"unit": "s^-1", "meaning": "Damping coefficient used for the energy-flow audit."},
        "pl_o_e_force": {"unit": "N", "meaning": "External drive-force amplitude used for the energy-flow audit."},
        "pl_o_e_freq": {"unit": "rad/s", "meaning": "Drive angular frequency used for the energy-flow audit."},
        "pl_o_e_dt": {"unit": "s/step", "meaning": "RK4 integration step used for the energy-flow audit."},
    },
    "radia-magnet-studio": {
        "pl_m_seeds": {"unit": "independent RNG seeds", "meaning": "Number of manufacturing-error realizations in the RADIA seed ensemble."},
        "pl_m_axis": {"unit": "on-axis samples/seed", "meaning": "Number of longitudinal field samples used to analyze each manufacturing-error realization."},
        "pl_m_seed0": {"unit": "integer RNG seed", "meaning": "First manufacturing-error seed; subsequent ensemble runs increment from this value."},
    },
    "radiation-platform": {
        "pl_rad_gmin": {"unit": "Lorentz factor gamma", "meaning": "Minimum electron Lorentz factor in the ideal resonance sensitivity atlas."},
        "pl_rad_gmax": {"unit": "Lorentz factor gamma", "meaning": "Maximum electron Lorentz factor in the ideal resonance sensitivity atlas."},
        "pl_rad_kmin": {"unit": "dimensionless K", "meaning": "Minimum undulator-strength parameter K in the ideal resonance sensitivity atlas."},
        "pl_rad_kmax": {"unit": "dimensionless K", "meaning": "Maximum undulator-strength parameter K in the ideal resonance sensitivity atlas."},
        "pl_rad_period": {"unit": "mm", "meaning": "Undulator period lambda_u used by the ideal two-parameter sensitivity atlas."},
        "pl_rad_theta": {"unit": "mrad", "meaning": "Observation-angle magnitude used by the ideal resonance sensitivity atlas."},
        "pl_rad_harmonic": {"unit": "harmonic number", "meaning": "Odd ideal undulator harmonic used in the resonance calculation."},
        "pl_rad_res": {"unit": "grid samples/axis", "meaning": "Resolution of the gamma-versus-K ideal sensitivity atlas."},
        "pl_rad_inv_ev": {"unit": "eV", "meaning": "Target photon energy for the inverse ideal-resonance design calculation."},
        "pl_rad_inv_k": {"unit": "dimensionless K", "meaning": "Design K assumed while solving the ideal resonance relation backward for gamma."},
        "pl_rad_inv_h": {"unit": "harmonic number", "meaning": "Odd harmonic assumed by the inverse ideal-resonance design calculation."},
        "pl_rad_inv_angle": {"unit": "mrad", "meaning": "Observation angle assumed by the inverse ideal-resonance design calculation."},
        "pl_rad_inv_period": {"unit": "mm", "meaning": "Undulator period assumed by the inverse ideal-resonance design calculation."},
        "pl_rad_rep_axis": {"unit": "data-column choice", "meaning": "Numeric scan column treated as the independent variable for representative-point selection."},
        "pl_rad_rep_obs": {"unit": "data-column choice", "meaning": "Numeric observable used to identify feature-rich or representative scan locations."},
        "pl_rad_cmp_axis": {"unit": "data-column choice", "meaning": "Numeric upstream scan column used as the horizontal axis in analytic-reference comparison."},
        "pl_rad_cmp_sem": {"unit": "axis semantics", "meaning": "Physical interpretation assigned to the selected comparison axis: gamma, K, or observation angle."},
        "pl_rad_cmp_q": {"unit": "quantity choice", "meaning": "Analytic reference quantity displayed in comparison: photon energy or wavelength."},
        "pl_rad_cmp_gamma": {"unit": "Lorentz factor gamma", "meaning": "Fixed gamma used when the selected comparison axis is not gamma."},
        "pl_rad_cmp_k": {"unit": "dimensionless K", "meaning": "Fixed K used when the selected comparison axis is not K."},
        "pl_rad_cmp_period": {"unit": "mm", "meaning": "Reference undulator period used by the analytic comparison curve."},
        "pl_rad_cmp_obs": {"unit": "data-column choice", "meaning": "Optional upstream observable overlaid on the ideal analytic reference."},
    },
}
'''

text = AI.read_text(encoding="utf-8")
if "ADVANCED_PARAMETER_GUIDES:" not in text:
    anchor = "\n_RESULT_KEYS = ("
    if text.count(anchor) != 1:
        raise SystemExit("Local AI _RESULT_KEYS anchor missing or ambiguous")
    text = text.replace(anchor, advanced_guides + anchor, 1)

old = '''def _parameter_guide(profile: str, session_state: Mapping[str, Any] | None) -> dict[str, Any]:\n    guide = PARAMETER_GUIDES.get(profile, {})\n    if not guide or session_state is None:\n        return dict(guide)\n    present = {str(key) for key in session_state.keys()}\n    visible = {key: value for key, value in guide.items() if key in present}\n    return visible or dict(guide)\n'''
new = '''def _parameter_guide(profile: str, session_state: Mapping[str, Any] | None) -> dict[str, Any]:\n    guide: dict[str, dict[str, str]] = {}\n    guide.update(PARAMETER_GUIDES.get(profile, {}))\n    guide.update(ADVANCED_PARAMETER_GUIDES.get(profile, {}))\n    if not guide or session_state is None:\n        return dict(guide)\n    present = {str(key) for key in session_state.keys()}\n    visible = {key: value for key, value in guide.items() if key in present}\n    return visible or dict(guide)\n'''
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("Local AI parameter-guide function anchor missing")
AI.write_text(text, encoding="utf-8")

validation = VALIDATION.read_text(encoding="utf-8")
block = r'''

# Every supported research Lab now has an explicit advanced-control guide. This
# protects the Tutor from falling back to variable-name guessing for Physical
# Lab's own experiment controls.
expected_profiles = {
    "numerical-methods", "ising-monte-carlo", "random-walk-monte-carlo",
    "nonlinear-chaos", "oscillation-integration", "radia-magnet-studio",
    "radiation-platform",
}
assert expected_profiles <= set(mod.ADVANCED_PARAMETER_GUIDES)
for profile in expected_profiles:
    entries = mod.ADVANCED_PARAMETER_GUIDES[profile]
    assert len(entries) >= 3, (profile, len(entries))
    for key, meta in entries.items():
        assert key.startswith("pl_"), (profile, key)
        assert isinstance(meta.get("unit"), str) and meta["unit"].strip(), (profile, key, "unit")
        assert isinstance(meta.get("meaning"), str) and meta["meaning"].strip(), (profile, key, "meaning")

merged = mod._parameter_guide(
    "numerical-methods",
    {"pl_n_xmax": 100.0, "pl_n_micro_n": 50},
)
assert merged["pl_n_xmax"]["unit"] == "rad"
assert "Taylor" in merged["pl_n_micro_n"]["meaning"]

merged_rad = mod._parameter_guide(
    "radia-magnet-studio",
    {"cfg_gap_mm": 12.0, "pl_m_seeds": 4},
)
assert merged_rad["cfg_gap_mm"]["unit"] == "mm"
assert merged_rad["pl_m_seeds"]["unit"] == "independent RNG seeds"

print("Seven-Lab advanced parameter guide coverage: PASS")
'''
if "Seven-Lab advanced parameter guide coverage: PASS" not in validation:
    validation += block
VALIDATION.write_text(validation, encoding="utf-8")

doc = DOC.read_text(encoding="utf-8")
section = r'''

## Seven-Lab parameter semantics

The Tutor carries explicit metadata not only for upstream/core controls but also for Physical Lab's advanced research-suite widgets. The advanced guide is keyed by the actual Streamlit control IDs used by the seven Labs, including numerical reliability/cancellation controls, Ising critical and Binder scans, random-walk scaling/QMC/recurrence controls, nonlinear-chaos Lyapunov and stability-atlas controls, oscillation solver/energy audits, RADIA manufacturing-seed ensembles, and radiation resonance/sensitivity controls.

Metadata is merged only for controls that are present in the current session. Each documented advanced control has a non-empty `unit` and `meaning`; controls that are not explicitly documented remain visible as raw session state but are not assigned an invented unit.
'''
if "## Seven-Lab parameter semantics" not in doc:
    doc += section
DOC.write_text(doc, encoding="utf-8")

print("v0.63 seven-Lab parameter guide patch: APPLIED")
