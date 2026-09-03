# Research Note — Magnet → Trajectory → Radiation Validation

## Question

How closely does an ideal undulator reference describe the radiation predicted from a realized magnetic field, and how do manufacturing perturbations propagate through field quality, electron trajectory and radiation-oriented observables?

## Why this is the representative Physical Lab workflow

This path connects geometry, a native field solver, numerical post-processing, uncertainty/tolerance studies and a downstream radiation model. It therefore tests both physics modeling and research-software reproducibility.

## Reproducible protocol

1. Define a magnet configuration and record period, geometry, material/remanence inputs and any target field setting.
2. Run **RADIA Magnet Studio Full mode** and preserve the solved field, on-axis sample grid and engineering metrics.
3. Record field integrals, harmonic ratios, solved peak transverse field, derived K, trajectory and phase-related metrics. Never substitute material remanence for solved field amplitude.
4. If studying manufacturing variation, run a bounded multi-seed ensemble with the exact tolerance model and preserve every seed plus aggregate quantiles/intervals.
5. Hand the realized field/trajectory state to the **Radiation Platform**.
6. Compute the ideal undulator resonance reference using the same electron energy, period, K and observation assumptions.
7. Compare realized-field output with the ideal reference and report discrepancy together with model-boundary notes.
8. Export the `.physlab` workspace/reproducibility package so parameters, source revisions, package state and measurement data (if any) travel with the result.

## What would count as evidence

A strong result package contains:

- a field profile and engineering metrics from a real RADIA solve;
- an ideal-vs-realized comparison using explicitly matched units/assumptions;
- a convergence or repeatability check appropriate to the calculation;
- a manufacturing-error ensemble if tolerance sensitivity is claimed;
- a statement of omitted physics and numerical limitations;
- source revision and environment provenance.

## What this note does *not* claim

This repository does not include a precomputed Full-mode result and therefore does not invent one. The analytic relation can serve as a reference, but a publishable claim about a realized device requires an actual RADIA run (and, for experimental validation, calibrated measurement data).

The v0.5 workspace and Results Center are designed so those future outputs can be captured and compared without changing the scientific meaning of the underlying Lab.
