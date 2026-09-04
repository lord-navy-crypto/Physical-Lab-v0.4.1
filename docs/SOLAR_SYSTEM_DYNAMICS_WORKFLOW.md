# Sun–Jupiter–Saturn Orbital Dynamics · Physical Lab

## Purpose

This model promotes the earlier standalone long-duration Sun/Jupiter/Saturn study into Physical Lab without preserving misleading labels or solver-side global state.

The production architecture is:

```text
interactive parameters
      ↓
SolarSystemConfig
      ↓
barycentric scientific core
      ↓
physical-lab-experiment-v1
      ↓
Persistent Compute Engine
      ↓
verification / sensitivity campaign
      ↓
PASS / REVIEW screening
      ↓
.physlab Project → report / diagnostics / Local AI context
```

The top-level Lab remains **Nonlinear Dynamics & Chaos**. This is a model variant inside that Lab, not a new third application mode.

## Scientific model

### Authoritative baseline

The baseline uses point-mass Newtonian gravity in barycentric Cartesian coordinates.

Units:

- length: AU
- time: year
- mass: solar mass
- gravitational constant: `G = 4π² AU³ yr⁻² M_sun⁻¹`

The state contains all three body positions and velocities:

```text
Sun      r, v
Jupiter  r, v
Saturn   r, v
```

Initial heliocentric circular-orbit guesses are shifted into a zero-center-of-mass / zero-total-momentum barycentric frame before integration.

This is an important improvement over a fixed-Sun three-body display: conservation diagnostics now refer to the actual integrated gravitating state rather than a system where the central body's recoil degree of freedom is omitted.

### Numerical integrator

The production solver uses SciPy `solve_ivp` with `DOP853`.

The ODE right-hand side is pure with respect to integration history. It does not append adaptive internal stages into a global deque.

That matters because adaptive Runge-Kutta methods may evaluate rejected and non-monotonic internal stages. Such calls cannot be treated as an authoritative delay-differential history merely because they happened to be requested by the integrator.

## Mapping from the standalone study

| Earlier control / concept | Physical Lab treatment |
|---|---|
| `SHORT / LONG / ULTRA_LONG` | preserved as 80 / 500 / 1000 yr interactive horizons |
| 0 / 10 / 20 / 30° inclination presets | preserved |
| Saturn switch | represented as Saturn gravitational backreaction on/off; off leaves a massless comparison tracer |
| Newtonian gravity | promoted to barycentric production baseline |
| `ENABLE_RELATIVITY` | replaced by an optional, explicitly approximate central-Sun 1PN correction |
| `ENABLE_SPIN` | retained only as `velocity_cross` phenomenological perturbation |
| `ENABLE_GW` | retained only as `radial_drag` phenomenological perturbation |
| mutable gravitational-delay deque | not promoted to the production ODE solver |
| single twin-trajectory Lyapunov slope | replaced by a periodically renormalized finite-time phase-space divergence indicator |
| fuzzy resonance string classification | replaced by continuous `Ts/Tj` and signed deviation from 5:2 |
| 16 fixed Matplotlib panels | replaced by interactive scientific views plus structured result records |

## Optional central-Sun 1PN approximation

Physical Lab optionally adds the commonly used test-particle-like correction

```text
GM/(c² r³) [(4GM/r - v²) r + 4(r·v)v]
```

for each orbiting body relative to the Sun.

The implementation includes an equal-and-opposite recoil bookkeeping term so the correction does not arbitrarily inject net linear momentum.

This option is useful for a controlled relativistic-precession comparison. It is **not** a complete Einstein–Infeld–Hoffmann N-body 1PN solver and must not be described as one.

When the 1PN option is enabled, Physical Lab does not demand conservation of the baseline Newtonian energy expression as a PASS requirement.

## Legacy phenomenological perturbations

Two terms preserve the experimental intent of the standalone controls while fixing their scientific labels.

### Velocity-cross perturbation

```text
a_extra = ξ (Ω × v)
```

This is not called physical spin-orbit coupling.

It has the useful mathematical property

```text
(Ω × v) · v = 0
```

so it performs no instantaneous work on the same velocity vector. The CI contract checks this property.

### Radial-drag perturbation

```text
a_extra = -σ |v|³ r_hat
```

This is not called gravitational-wave radiation reaction. It is a phenomenological dissipative radial perturbation useful for sensitivity experiments.

A physically calibrated gravitational-wave reaction model would require a separate derivation and validation track.

## Why the old delay switch is not reproduced

The earlier standalone implementation estimated a propagation delay from separation and queried a global history deque from inside the ODE right-hand side.

That approach is not promoted because:

1. `solve_ivp` evaluates adaptive internal stages, not only accepted output times.
2. rejected stages can remain in a mutable history unless explicitly rolled back;
3. ordinary ODE integration does not provide the history semantics required by a delay differential equation;
4. retarded Newtonian forces are not automatically a consistent relativistic theory of gravity.

A future delay/retardation experiment should therefore use a dedicated DDE or field-retardation formulation with an explicit scientific model and validation benchmark.

## Orbital diagnostics

The core computes osculating Sun-relative quantities for Jupiter and Saturn:

- semi-major axis
- eccentricity
- inclination
- Keplerian period estimate
- Saturn/Jupiter period ratio
- signed deviation from 5:2
- Jupiter–Saturn separation

The primary resonance observable is

```text
rho = T_saturn / T_jupiter
Delta_5:2 = rho - 2.5
```

This avoids converting a continuous dynamical quantity into a potentially incorrect string label.

## Conservation and numerical diagnostics

For the pure Newtonian baseline, Physical Lab audits:

- relative total Newtonian energy drift
- relative total angular-momentum-vector drift
- absolute total linear momentum drift
- barycenter position drift
- solver-refinement change in stable observables

The conservation requirements are conditional.

If central-Sun 1PN or phenomenological perturbations are enabled, baseline Newtonian energy/angular momentum are still displayed diagnostically but are not automatically treated as conserved PASS requirements.

## Finite-time divergence indicator

The earlier single twin-trajectory log-slope has been replaced by a Benettin-style finite-time indicator with periodic renormalization.

The phase-space norm uses:

- position scale: 1 AU
- velocity scale: `2π AU/yr`

At each segment:

```text
reference advances
perturbed twin advances
separation is measured
log(separation / d0) is accumulated
the perturbation is renormalized to d0
```

The reported rate is a **finite-time phase-space divergence indicator**.

It is not an asymptotic proof of chaos. A positive finite-time value may depend on observation window, phase-space norm, renormalization interval and transient behavior.

## Experiment Kernel

Model variant:

```text
sun-jupiter-saturn-dynamics
```

The manifest records:

- duration and output sampling
- inclination
- Saturn backreaction mode
- central-Sun 1PN mode
- phenomenological perturbation flags/strengths
- numerical tolerances and max step
- units / frame
- legacy-source mapping
- scientific boundary
- requirements
- deterministic sensitivity boundary
- source / runtime provenance

Any scientific parameter change changes the stable experiment fingerprint.

## Compute Engine campaign

The existing allow-listed `model-campaign` runner routes into this model only when the manifest explicitly carries the solar-system variant.

Worker stages include:

```text
solar-system-base-run
solar-system-refinement
solar-system-finite-time-divergence
solar-system-inclination-sweep
solar-system-model-effect-audit
solar-system-screening
result-persisted
```

The campaign provides two bounded presets.

### compact

Designed for rapid local verification and CI.

### standard

Uses a longer trajectory and deeper finite-time/sweep characterization, while remaining bounded independently from the interactive 500–1000 year horizon.

This separation prevents a UI selection from silently creating an unbounded background campaign.

## Model-effect audit

The campaign compares short, otherwise matched runs of:

1. Newtonian baseline
2. central-Sun 1PN approximation
3. legacy velocity-cross perturbation
4. legacy radial-drag perturbation

The comparison is intended to answer: "How much does this optional modeling assumption move the selected orbital observables?"

It does not imply all four models have equal physical status.

## PASS / REVIEW

Default computational screening checks:

- solver-refinement maximum relative change
- barycenter drift
- linear-momentum drift
- Newtonian energy drift when applicable
- Newtonian angular-momentum drift when applicable

`PASS` means only that the configured numerical screening criteria passed.

It does **not** mean:

- observational validation
- experimental validation
- Solar System ephemeris accuracy
- complete post-Newtonian correctness
- proof of chaos
- certification

## Project and report integration

A solar-system manifest can be registered into the active `.physlab` project.

Compute jobs and successful results are indexed by the same `experiment_sha256` already used by Project Kernel. The project does not duplicate large arrays.

The model-specific Markdown report records:

- experiment fingerprint
- configuration
- verification metrics
- signed PASS/REVIEW margins
- model assumptions
- scientific boundaries

## Next physically meaningful extensions

High-value future work is not "more plots". It is stronger physics and validation:

1. complete barycentric N-body 1PN / EIH equations with literature benchmarks;
2. calibrated Solar System initial conditions / ephemeris import;
3. symplectic long-time Newtonian integrator comparison;
4. proper resonant-angle analysis rather than period ratio alone;
5. secular-frequency extraction;
6. MEGNO / frequency-map analysis for chaos characterization;
7. dedicated delay-differential experiment only if a physically justified retardation model is specified;
8. uncertainty propagation from initial-state covariance / measurement evidence.
