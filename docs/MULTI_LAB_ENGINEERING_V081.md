# Physical Lab v0.8.1 — Multi-Lab Engineering Profiles

Physical Lab v0.8.1 extends the shared engineering layer beyond the accelerator-physics path. The five non-accelerator Labs keep their native scientific models and diagnostics, while Physical Lab adds a domain-specific engineering scorecard that turns those outputs into explicit questions about accuracy, convergence, repeatability, computational cost, and requirement margin.

This layer does **not** replace each upstream Lab and does not pretend that one generic engineering formula fits every physics problem. Each profile uses quantities that make sense for that model.

## Shared engineering structure

Every supported profile can use three common engineering views:

1. **Domain scorecard** — editable lower/upper targets with PASS / REVIEW / FAIL uncertainty-margin screening. Missing metrics are REVIEW, never silently treated as zero or passing.
2. **Convergence / cost** — a two-level observed convergence-order estimate plus a cost-versus-error non-dominated frontier for supplied design points.
3. **Replicate robustness** — descriptive finite-replicate mean, sample standard deviation, coefficient of variation, p05/median/p95, range, and extrema.

The thresholds shipped with Physical Lab are starting defaults for screening and can be edited by the user. They are not external standards or certification criteria.

## Numerical Error Analysis

Engineering emphasis: **accuracy budget and precision/cost design**.

Default scorecard quantities:

- worst normalized numerical error;
- fraction of scan points satisfying the selected error allowance;
- observed convergence order.

The cost/accuracy panel can compare choices such as float32 versus float64, raw versus range-reduced evaluation, Taylor order, reference precision, or scan density. A smaller final Taylor term by itself is not accepted as proof of an accurate result; the Lab's independent/high-precision reference remains the stronger validation path.

## Ising Monte Carlo Lab

Engineering emphasis: **sampling quality, equilibration, finite-size behavior, and work efficiency**.

Default scorecard quantities:

- worst multi-chain R-hat;
- minimum effective sample size;
- relative discrepancy against an available exact/reference result;
- equilibration mean-drift statistic.

The existing autocorrelation, effective-sample-size, multi-chain, finite-size, and exact-observable tools remain the scientific source. The engineering layer asks whether a result has enough independent information and convergence evidence for the intended decision. Raw Monte Carlo sweeps are not treated as equivalent to independent samples.

## Random Walk & Monte Carlo

Engineering emphasis: **estimator accuracy, scaling-law agreement, replicate stability, and work-versus-precision**.

Default scorecard quantities:

- error in the measured MSD/diffusion scaling exponent relative to the theoretical target used by the study;
- estimator relative error;
- coefficient of variation across finite seed/scramble replicates.

This makes it possible to compare ordinary Monte Carlo, different sample counts, seeds, and QMC/scrambled-QMC runs using both error and computational cost. A finite benchmark cannot establish that one estimator is universally superior.

## Nonlinear Dynamics & Chaos

Engineering emphasis: **robust indicators rather than impossible long-time trajectory matching**.

Default scorecard quantities:

- relative change in the selected chaos/stability indicator under timestep refinement;
- finite-replicate spread of a Lyapunov statistic;
- relative energy/work-balance error where that balance is meaningful for the chosen model.

Chaotic trajectories can separate exponentially even when two numerical solutions are both physically and numerically meaningful. Physical Lab therefore recommends engineering requirements on Lyapunov estimates, Poincare/event statistics, bounded invariants, transition/flip locations, or other finite-window indicators rather than demanding pointwise long-time state agreement.

## Oscillation & Numerical Integration

Engineering emphasis: **dynamic response fidelity and solver convergence**.

Default scorecard quantities:

- frequency relative error;
- amplitude relative error;
- phase error;
- energy/work-balance relative error;
- response change under timestep refinement.

These outputs map naturally to mechanical and controls questions: whether a solver predicts resonance frequency, steady-state amplitude, phase lag, and energy flow within the entered engineering limits. Real apparatus validation still requires measured data, calibration, and a model-form uncertainty assessment.

## Deterministic validation

`src-tauri/resources/ui/physical_lab_model_engineering.py` contains the profile definitions and transparent calculations. `scripts/model_engineering_reference_validation.py --check` regenerates deterministic synthetic reference cases for all five profiles and verifies:

- scorecard completeness and PASS/REVIEW/FAIL behavior;
- observed convergence-order math;
- finite-replicate statistics;
- cost-versus-error non-dominated filtering;
- symmetric relative-change calculation.

The committed snapshot is `docs/model-engineering-reference-validation.json` and is enforced by Source Integrity CI.

## Scientific boundary

v0.8.1 is an engineering **decision layer**, not a claim of experimental certification. In particular:

- editable thresholds are project screening defaults, not standards;
- finite replicate statistics are descriptive and are not automatically confidence intervals, population distributions, failure probabilities, or manufacturing yield;
- finite Ising lattices do not establish the thermodynamic limit without an appropriate finite-size analysis;
- random-walk or Monte Carlo scaling references apply only when the selected stochastic model satisfies the corresponding assumptions;
- long-time chaotic coordinate divergence is not, by itself, a numerical failure;
- simple oscillator models can omit actuator, sensor, structural, nonlinear, thermal, and other apparatus effects;
- real validation still requires appropriate measurements, provenance, uncertainty evidence, and model-form assessment.

The deeper RADIA → measured/model field residual → trajectory → radiation workflow introduced in v0.8.0 remains the representative model-to-measurement path. v0.8.1 closes the engineering-maturity gap for the other five computational-physics Labs without adding a disconnected eighth Lab.
