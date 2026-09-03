# Physical Lab Engineering Simulation & VVUQ

Physical Lab is expanding from a computational-physics workbench toward an engineering simulation environment. The engineering layer does **not** treat every difference as one generic “error percentage.” It keeps distinct evidence classes and records what is measured, manufactured, numerically approximated, assumed, or not yet quantified.

## Uncertainty classes

Physical Lab uses explicit labels for:

- **measurement** — sensor calibration, alignment, readout, experimental repeatability;
- **manufacturing** — dimensions, placement, material variation, assembly tolerances;
- **model input** — uncertain operating conditions or physical parameters supplied to a model;
- **numerical** — discretization, finite step size, convergence, roundoff, iterative solve effects;
- **model-form** — discrepancy caused by idealization or omitted physics;
- **sampling** — finite Monte Carlo / ensemble uncertainty.

A zero entry means **not quantified yet** unless the user has independent evidence that the component is exactly zero.

## Engineering calculations in v0.68

### First-order uncertainty propagation

For a response locally approximated by

`y ≈ y0 + Σ c_i δx_i`,

Physical Lab uses the entered local sensitivity `c_i = dy/dx_i` and standard input uncertainty `u(x_i)`. Independent components combine by RSS; the core also accepts a correlation matrix for programmatic use.

The UI reports combined standard uncertainty and `k=2` expanded uncertainty. `k=2` is labeled as an engineering expanded-uncertainty convention and is **not** presented as an automatic 95% guarantee for arbitrary distributions.

### Tolerance stacks

For entered half-width tolerances and local sensitivities, Physical Lab reports both:

- RSS half-width — independent signed-effect screening;
- worst-case half-width — sum of absolute effects.

Neither method replaces a nonlinear tolerance ensemble when interactions, geometric constraints or saturation matter.

### Requirement / design-margin screening

A nominal response can be compared with lower and/or upper requirements using one of the entered uncertainty/tolerance intervals.

- **PASS** — the full entered interval remains inside the limits;
- **REVIEW** — nominal is inside, but the interval crosses a limit;
- **FAIL** — nominal itself violates a limit.

This is an engineering screening rule, not a certification statement.

### Simulation ↔ measurement comparison

Simulation, measurement and model-form standard uncertainties remain separate. Physical Lab reports absolute discrepancy and the discrepancy divided by the entered combined standard-uncertainty scale. It does not infer uncertainty values that were never measured or calculated.

### Linearized Monte Carlo

The first implementation can sample independent normal input perturbations through the same local linear surrogate. This is useful for checking a linear error budget numerically. It is explicitly labeled **linearized Monte Carlo**, not a nonlinear solver ensemble.

Future solver adapters should run the real model for every tolerance sample when nonlinear propagation matters.

## Visualization rules

The Engineering Visualization extension adds:

- model-aware visualization presets;
- session cross-run baseline overlays;
- uncertainty bands only when the authored Plotly trace contains `error_y` data;
- 3D camera and aspect presets;
- 3D trajectory line / marker controls;
- surface opacity and color-scale controls.

These features operate on copied Plotly figures. They do not change solver arrays or measurement data.

Cross-run baselines are session-scoped in v0.68. Run Vault remains the persistent provenance record. A later revision can bind a bounded figure artifact to a saved Run Vault snapshot.

## RADIA / Radiation priority

RADIA Magnet Studio already has manufacturing-error seed ensembles. The next engineering step is to promote those from scalar metric summaries to realized-field envelopes on a common coordinate grid, then propagate selected field ensembles through trajectory and radiation calculations. Those results can create real uncertainty envelopes because every member comes from an actual solver realization.

## Standards-informed terminology

The project uses public ASME/NIST VVUQ and measurement-uncertainty concepts as terminology and design guidance. Physical Lab does not claim compliance or certification merely because it implements similarly named calculations.
