# Physical Lab dual-mode application architecture

Physical Lab keeps a deliberate distinction between **mathematical/numerical tools** and **physics scenarios**.

A tool does not become more scientific merely by being renamed after a physics topic. The tool remains useful on its own. Physics Scenario mode supplies a specific physical model, units, observables, references and interpretation boundaries while retaining the original numerical diagnostics.

## Hybrid Labs

### Numerical Error

**Mathematical tool mode**

- floating-point and truncation error
- approximation order
- grid/refinement studies
- cancellation and conditioning
- accuracy/cost scorecards

**Physics Scenario mode: quantum bound-state numerical verification**

The infinite square well is used as a controlled benchmark. A centered finite-difference approximation turns the kinetic-energy operator into a symmetric matrix eigenproblem. The numerical eigenenergy can then be compared with the analytic energy level.

This does **not** mean Numerical Error and quantum mechanics are the same subject. The relationship is that a numerical quantum calculation inherits numerical-analysis errors: grid spacing, domain truncation, finite-difference order, eigensolver tolerance and floating-point effects can all change the reported physical energy.

The current scenario deliberately uses the infinite well because it has an analytic reference. It is therefore a verification scene, not a claim that Physical Lab already contains a general-purpose quantum package.

### Ising Monte Carlo

**Mathematical / sampling tool mode** retains chains, equilibration, autocorrelation, effective sample size, replicate stability and exact finite-lattice checks.

**Physics Scenario mode: magnetic phase transition & criticality** adds a temperature sweep for the zero-field nearest-neighbor ferromagnetic square-lattice Ising model and reports:

- energy per spin
- absolute magnetization per spin
- heat capacity per spin
- magnetic susceptibility per spin
- Binder cumulant
- the exact infinite-square-lattice critical-temperature reference

Finite-size response peaks are labeled pseudo-critical indicators. A finite simulation is not presented as a new measurement of the infinite-lattice critical temperature.

### Random Walk / Monte Carlo

**Mathematical tool mode** retains estimator error, replicate variation and asymptotic scaling.

**Physics Scenario mode: diffusion & stochastic transport** interprets the walk as two-dimensional Brownian motion with optional constant drift. It reports:

- centered mean-squared displacement
- theoretical `4 D t` reference
- recovered diffusion coefficient
- mean drift displacement
- recovered drift velocity
- representative trajectories
- final centered radial distribution

Centered MSD is intentional: deterministic drift is removed before estimating diffusion so mean motion is not misidentified as stochastic spreading.

## Physics-first Labs

Oscillation / Integration and Nonlinear Dynamics / Chaos already have explicit physical models, so they are not forced into the hybrid selector merely for symmetry. RADIA Magnet Studio and Radiation Platform are also physics-first.

## Visualization contract

Physics Scenario charts follow these rules:

1. Stored scientific values are never altered to improve appearance.
2. Quantities with different units receive separate axes/plots instead of being compressed onto one arbitrary scale.
3. A tight padded display range may be used when values share a large common offset and meaningful differences would otherwise be visually compressed.
4. Theory/reference traces remain on the same physical scale as the simulated trace.
5. Signed quantities are not silently passed through ordinary logarithmic scaling.
6. Representative stochastic trajectories are bounded; ensemble statistics carry the scientific result.
7. Phase/trajectory geometry uses equal spatial scaling when unequal axes would distort shape.

## Dependency policy

The first dual-mode implementation adds **no new hard scientific dependency**.

- NumPy remains the guaranteed numerical backend.
- SciPy is used opportunistically for the tridiagonal quantum eigenproblem when present; the scenario has a NumPy symmetric-eigensolver fallback.
- Numba is a future optional acceleration backend for update-heavy Monte Carlo/transport workloads, not a physics authority.
- Astropy Units is a future optional unit-validation/conversion layer, especially useful for radiation and accelerator quantities; solver arrays should still be converted to canonical numeric units at the compute boundary.
- QuTiP should be considered only when Physical Lab grows into time-dependent/open-system quantum dynamics. It is unnecessary for the current bound-state verification scene.

## Scientific boundary

These scenarios are computational physics studies. Analytic references and convergence checks provide **verification** of selected numerical models. They do not constitute experimental validation, instrument calibration, product certification or evidence that omitted model-form effects are negligible.
