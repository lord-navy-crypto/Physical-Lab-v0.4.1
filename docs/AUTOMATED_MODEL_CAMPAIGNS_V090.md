# Physical Lab v0.9.0 — Automated Multi-Model Engineering Campaigns

Physical Lab v0.9.0 turns the five non-accelerator engineering profiles introduced in v0.8.1 into executable, one-click computational campaigns.

The objective is not to add more disconnected simulation panels. It is to make each existing model answer an engineering question through a repeatable chain:

```text
model configuration
      ↓
automated refinement / replicate campaign
      ↓
canonical numerical or statistical diagnostics
      ↓
Engineering V&V / UQ
      ↓
Engineering Design Workflow
      ↓
model-specific requirement scorecard
      ↓
PASS / REVIEW / FAIL screening decision
```

A campaign result is computational evidence. It is not experimental validation, certification, manufacturing yield, or a guarantee that a physical apparatus will meet the same limits.

## Shared campaign contract

`src-tauri/resources/ui/physical_lab_model_campaigns.py` implements the common contract for:

- `numerical-methods`
- `ising-monte-carlo`
- `random-walk-monte-carlo`
- `nonlinear-chaos`
- `oscillation-integration`

Every campaign returns:

- the profile and resolved preset;
- the full bounded configuration;
- individual case records;
- canonical scorecard metrics;
- a deterministic SHA-256 campaign fingerprint derived from profile + preset + configuration;
- model-specific scientific boundary notes.

The UI adds descriptive observed runtime separately; runtime is deliberately excluded from the deterministic fingerprint because it depends on machine state.

Two presets are shipped:

- **Compact** — interactive engineering checks and deterministic CI acceptance.
- **Standard** — a deeper but still bounded numerical/stochastic study.

The campaign is rendered before the existing Engineering V&V/UQ layer. Its canonical metrics are published into Streamlit session state and are then discovered by the v0.8.1 model-specific scorecard using the same metric names and requirement logic as manually supplied results.

## Numerical Error — accuracy / cost campaign

The numerical campaign evaluates the Taylor series for `sin(x)` across `[-π, π]` at multiple term counts.

For each refinement case it records:

- maximum absolute error;
- RMS error;
- scan pass fraction against the configured tolerance;
- an evaluation-count work proxy;
- descriptive wall-clock runtime.

The final Taylor case publishes:

- `max_normalized_error`
- `pass_fraction`

Observed convergence order is intentionally measured by a separate centered finite-difference derivative refinement at `h = 0.2, 0.1, 0.05, 0.025`, rather than pretending that Taylor term count is the same kind of grid refinement. The centered difference should approach second-order behavior in its asymptotic regime and publishes:

- `convergence_order`

The NumPy/libm double-precision sine value is the reference for this bounded campaign. This is a numerical verification reference, not arbitrary-precision proof for all inputs.

## Ising Monte Carlo — multi-chain sampling campaign

The Ising campaign runs independent periodic two-dimensional zero-field Metropolis chains.

For each chain it records:

- mean energy per spin;
- mean absolute magnetization;
- autocorrelation-based effective sample sizes for energy and `|M|`.

Across chains it computes the classical between/within-chain variance form of R-hat. It also compares the first and second halves of the retained burn trace using a sigma-scaled drift diagnostic.

The scorecard receives:

- `rhat_max`
- `effective_samples_min`
- `equilibration_drift_sigma`

### Exact 4×4 checkpoint

A separate reference checkpoint enumerates every state of a periodic 4×4 Ising lattice:

```text
2^(4×4) = 65,536 states
```

At `T = 3.0`, the exact canonical energy per spin is calculated by direct partition-function weighting and compared with independent Monte Carlo chains. The relative discrepancy publishes:

- `exact_reference_relative_error`

R-hat, ESS and finite burn diagnostics are evidence about the finite chains actually run. They are not mathematical proof of convergence to the target distribution.

## Random Walk / Monte Carlo — multi-seed estimator campaign

The stochastic campaign uses independent deterministic seeds for a two-dimensional unbiased nearest-neighbor lattice walk with unit step length.

For this explicitly selected model:

```text
E[r²] = N
```

so the expected MSD log-log exponent is one and the expected final `MSD/N` ratio is one.

The campaign evaluates several step counts, fits the MSD exponent across the aggregate response, and calculates a final diffusion-scale estimate for each seed.

The scorecard receives:

- `msd_exponent_error`
- `estimator_relative_error`
- `replicate_cv`

The finite seed coefficient of variation is descriptive. It is not a population failure probability and the reference targets do not automatically apply to biased, correlated, continuous, anomalous-diffusion, or other random-walk models.

## Nonlinear Dynamics / Chaos — finite-window robustness campaign

The automated chaos reference is the driven Duffing system

```text
x'' + 0.2 x' - x + x³ = 0.3 cos(1.2 t)
```

integrated with RK4.

The campaign performs three distinct checks.

### 1. Timestep refinement

The selected finite Poincaré-response spread indicator is computed at three timesteps. The scorecard receives the relative change between the two finest responses:

- `indicator_timestep_relative_change`

This tests convergence of a finite-window conclusion rather than requiring two chaotic trajectories to remain pointwise identical indefinitely.

### 2. Finite-time Lyapunov robustness

The variational/tangent equations are integrated alongside the Duffing state. A tangent vector is periodically renormalized and accumulated logarithmic growth produces a finite-time largest-Lyapunov estimate.

Small initial-condition perturbations generate a finite replicate set. Their relative spread publishes:

- `lyapunov_relative_spread`

The value depends on the selected initial state, finite observation window, parameters, timestep and renormalization procedure. It is not a proof of a global strange attractor.

### 3. Energy / work closure

For

```text
E = 1/2 v² - 1/2 x² + 1/4 x⁴
```

the expected instantaneous balance is

```text
dE/dt = -0.2 v² + 0.3 v cos(1.2 t)
```

The integrated mismatch publishes:

- `energy_balance_relative_error`

The Standard preset deliberately uses a tested finite 80-second window. Extending a chaotic finite-time window can materially alter descriptive Lyapunov/indicator statistics even when the numerical solver is working correctly, so window length is treated as part of the experiment definition rather than an automatic notion of “more accurate.”

## Oscillation / Integration — analytic-reference convergence campaign

The oscillator reference is

```text
x'' + 2ζω_n x' + ω_n²x = 0
ω_n = 2 rad/s
ζ = 0.05
x(0) = 1
v(0) = 0
```

The system has a closed-form underdamped solution. RK4 results at several timesteps are compared directly with this analytic reference.

The campaign derives:

- zero-crossing frequency error;
- maximum displacement/amplitude error;
- final phase error in transformed underdamped phase coordinates;
- mechanical-energy loss versus integrated viscous dissipation;
- difference between the two finest final-state responses.

The scorecard receives:

- `frequency_relative_error`
- `amplitude_relative_error`
- `phase_error_rad`
- `energy_balance_relative_error`
- `timestep_relative_change`

This is a strong verification case because an analytic solution exists. It does not validate a real oscillator's mass, stiffness, damping, forcing, sensors or boundary conditions.

## CI acceptance

`scripts/model_campaign_reference_validation.py` is executed by Source Integrity.

It requires:

1. every Compact campaign to execute successfully;
2. every returned canonical metric to be finite;
3. every campaign fingerprint to be a 64-character SHA-256 hex digest;
4. every Compact result to achieve 100% metric completeness in the same model-specific scorecard used by the UI;
5. all five Compact scorecards to report PASS;
6. the Standard nonlinear-chaos preset to report PASS;
7. model-specific physical/numerical invariants, including refinement direction, Ising exact-reference presence, random-walk exponent recovery, positive finite-time Duffing sensitivity, oscillator analytic-reference improvement, and exact session-metric export.

The validator deliberately uses broad engineering/physics invariants rather than storing a brittle exact stochastic-output snapshot tied to one NumPy build.

## Reproducibility boundary

A deterministic campaign fingerprint means the same campaign definition can be identified. It does **not** imply that wall-clock runtime will be identical across machines.

The stochastic campaigns use explicit deterministic seeds in their reference implementations, so CI can repeat the same finite random sequences. That reproducibility does not transform a finite Monte Carlo sample into an exact probability statement.

## v0.9.0 engineering interpretation

v0.8.1 answered:

> What engineering quantities should this model be judged by?

v0.9.0 adds:

> Can Physical Lab automatically generate those quantities through a bounded, reproducible solver campaign and immediately route them into the engineering decision layer?

For all five non-accelerator Labs, the answer is now yes.
