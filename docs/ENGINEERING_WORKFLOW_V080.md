# Physical Lab v0.8 Engineering Workflow

Physical Lab v0.8 extends the existing V&V/UQ layer into a requirement-driven engineering workflow. The goal is not to add unrelated Labs; it is to make the existing computational-physics stack answer engineering questions such as **which design should be built, how sensitive is it, what happens under tolerance, how does a measured field differ from the model, and how does that discrepancy propagate into the downstream physics?**

## Engineering chain

```text
requirement
   ↓
parameterized design
   ↓
solver / field model
   ↓
sensitivity + tolerance ensemble
   ↓
robust-design screening
   ↓
measurement / calibration
   ↓
model residual
   ↓
trajectory / radiation propagation
   ↓
engineering decision + evidence
```

For the accelerator path this becomes:

```text
magnet geometry
→ RADIA / field model
→ B(x,y,z)
→ measured-field residual
→ electron trajectory
→ radiation observables
→ requirement margin / design comparison
```

## 1. Requirement-driven verification

`physical_lab_engineering_workflow.evaluate_requirements` evaluates named metrics against lower and/or upper bounds. An optional symmetric entered uncertainty expands the nominal value into a screening interval.

- **PASS**: the complete entered interval stays inside the requirement.
- **REVIEW**: the nominal value is inside, but the interval crosses a requirement boundary.
- **FAIL**: the nominal value itself violates a requirement.

These are project screening labels, not certification labels.

## 2. Design optimization and Pareto screening

The new workflow computes non-dominated designs for explicit `min` / `max` objective columns. This supports comparisons such as performance versus cost, field quality versus magnet volume, or photon-energy objective versus steering penalty.

Pareto membership means only that another entered design does not improve every selected objective simultaneously. It is not a global optimum claim.

## 3. Sensitivity and robust-design screening

One-at-a-time finite-difference cases can be ranked by absolute local sensitivity `|Δy/Δx|`.

Finite solver/manufacturing ensembles can be grouped by design and summarized with:

- mean;
- sample standard deviation;
- minimum / maximum;
- p05 / median / p95 descriptive percentiles;
- finite-sample requirement pass fraction.

The pass fraction is deliberately called a **finite-ensemble screening result**. It is not automatically a manufacturing yield, confidence interval, or certified probability of failure.

## 4. Measured-field residuals

Co-registered model and measured field series can be compared with:

- MAE;
- RMSE;
- maximum absolute residual;
- RMSE relative to model RMS;
- model and measured field integrals;
- integral difference;
- uncertainty-normalized residual RMS when pointwise standard uncertainty is actually supplied;
- fraction of normalized residuals inside `±2u`.

The normalized statistic is not labeled chi-square because Physical Lab does not infer independent Gaussian residual assumptions from the data.

## 5. Clean-macOS measurement-like propagation acceptance

Full-mode CI now creates two regular three-dimensional field maps on the same grid:

1. a nominal `0.05 T`, `20 mm` sinusoidal planar map;
2. a deterministic **synthetic measurement-like** map with a small amplitude change and weak third harmonic.

Both maps are propagated through the pinned Radiation Platform field-map worker. `scripts/measured_field_radiation_validation.py` then records the field residual and the resulting changes in fundamental frequency, photon energy and transverse excursion.

This proves that the software path

```text
field discrepancy → trajectory/radiation discrepancy
```

is active on clean macOS. The CI fixture is intentionally synthetic and must not be described as experimental magnet validation.

## 6. Closed-loop calibration / control foundation

`bounded_calibration_update` computes one bounded model-based parameter update from:

- current parameter;
- measured response;
- target response;
- local response sensitivity;
- update gain;
- optional parameter bounds.

The function performs no hardware I/O. A future hardware-in-the-loop layer must add a device-specific safety boundary before any command can reach physical equipment.

## 7. Lightweight multiphysics coupling

`undulator_thermal_coupling` provides a first-order transparent screening model:

```text
ΔT
→ linear thermal expansion of period
→ optional user-entered fractional field-temperature coefficient
→ K change
→ resonance-wavelength change
→ photon-energy change
```

It assumes uniform temperature and linear coefficients. It does not replace thermal/structural FEA or a temperature-dependent magnet material model.

## 8. Batch / HPC foundation

`build_batch_plan` creates deterministic case fingerprints, chunks and a minimum scheduling-wave estimate for a requested worker count. This gives Physical Lab a resumable cache/scheduler boundary without blindly parallelizing external solvers that may be non-thread-safe, memory-heavy or license-constrained.

Actual concurrent execution remains adapter-specific.

## Deterministic reference validation

`scripts/engineering_workflow_reference_validation.py` verifies the software definitions above against a committed snapshot:

`docs/engineering-workflow-reference-validation.json`

Source Integrity requires the snapshot to remain synchronized with the implementation.

## Scientific boundary

v0.8 improves engineering structure and traceability. It does **not** by itself claim:

- ASME/NIST certification;
- experimentally validated magnet performance;
- manufacturing yield;
- true probability of failure;
- globally optimal design;
- thermal/structural FEA fidelity;
- safe physical hardware control.

Those claims require evidence beyond software functionality and synthetic CI fixtures.
