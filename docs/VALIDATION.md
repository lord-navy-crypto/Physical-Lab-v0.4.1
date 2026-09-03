# Physical Lab Validation Policy

Physical Lab separates four questions that are often incorrectly collapsed into one:

1. **Can the software run?** — dependencies, imports, ABI/architecture and bounded smoke tests.
2. **Does the numerical method converge?** — step/grid/sample refinement and reference-error behavior.
3. **Does the implementation reproduce a known reference?** — analytic solutions, exact special cases or independently defined reference data.
4. **Is the model physically adequate for the real system?** — assumptions, omitted effects, measurement uncertainty and experimental comparison.

Passing an earlier layer does not prove a later one.

## Current reference checks

- Numerical Error Analysis: high-precision/reference evaluation and explicit cancellation/reliability diagnostics.
- Random Walk: exact MSD for the symmetric axis-aligned walk; asymptotic mean-radius references are labeled as asymptotic rather than exact finite-N laws.
- Oscillation: analytic force-free response, observed numerical convergence order and energy/input-work/damping-work closure.
- Ising: exact 2-D zero-field critical-temperature reference is used only under the assumptions where it applies; Binder/finite-size results remain finite-size estimates.
- Chaos: finite-time Lyapunov/Benettin diagnostics are not described as proof of a global strange attractor.
- RADIA Magnet Studio: Full mode uses solved field data; remanent induction is not substituted for solved `B0`; field integrals/harmonics/trajectory/phase metrics come from sampled fields.
- Radiation Platform: ideal undulator relations are references/fallbacks, not replacements for a realized 3-D magnetic field.

## Measurement comparison

The v0.5 Results Center can compare observed and reference datasets with MAE, RMSE, relative RMSE, maximum absolute error and R². These statistics describe agreement; they do not identify which side is physically correct. Sensor calibration, units, coordinate conventions and provenance remain part of the scientific record.

## Scientific smoke tests

Smoke tests are deliberately small. Their purpose is to detect broken runtime/solver paths, not to certify a research conclusion. Expensive production scans are never run automatically as a dependency check.

## Reproducibility

Physical Lab pins module source revisions, records managed-source provenance, isolates Lab Python environments and can export run/environment provenance. A reproducible run should state model, parameters, units, random seed where relevant, solver mode, source revision, runtime/package state and any measurement provenance.
