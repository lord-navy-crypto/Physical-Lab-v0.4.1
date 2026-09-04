# RADIA → Trajectory → Radiation Tolerance Propagation

Physical Lab v0.70 extends engineering tolerance analysis beyond magnetic-field envelopes. The same explicit RADIA manufacturing-error model can be propagated through a real 3-D field map into the pinned Radiation Platform single-electron trajectory/radiation solver.

## Engineering chain

```text
RADIA Magnet Studio parameters
        ↓
nominal 3-D RADIA solve
        +
seeded manufacturing realizations
        ↓
sample_3d B(x,y,z)
        ↓
regular SI field-map evidence
        ↓
Radiation Platform isolated .venv
        ↓
FieldMapInsertionDevice
        ↓
run_sim_scalar
        ↓
trajectory + radiation observables
        ↓
finite-ensemble engineering comparison
```

## Why the worker is a separate process

Physical Lab intentionally gives every managed Lab its own `.venv`. RADIA Magnet Studio must not silently import Radiation Platform dependencies from another environment. The propagation bridge therefore writes a temporary compressed field-map evidence package and launches `physical_lab_radiation_worker.py` with the managed Radiation Platform interpreter.

The worker verifies/uses the pinned Radiation Platform source and returns JSON observables. This preserves dependency isolation while making the cross-model boundary explicit and auditable.

Pinned Radiation Platform revision:

`6d19b36304c9d30f9b608214f7cfb9fcbaf941d4`

Pinned RADIA Magnet Studio revision:

`3bceb02a5195a6eb14d01458cc44f7206ed6b40a`

## Field-map convention

RADIA Magnet Studio `sample_3d` returns a field tensor with shape:

`(Nz, Ny, Nx, 3)`

where coordinates are millimetres and field values are tesla. The Radiation Platform field-map device uses SI coordinates and a regular `(Nx, Ny, Nz)` component grid. The worker performs the explicit axis transpose and millimetre → metre conversion before constructing the pinned V11 field-map device.

The bridge never estimates a field from a screenshot or a plotting interpolation.

## Propagated observables

Depending on the pinned Radiation Platform result, Physical Lab records finite values including:

- fundamental frequency `f0`;
- photon energy;
- Larmor/radiated-power observable;
- relative spectral linewidth;
- circular-polarization observable;
- maximum transverse trajectory excursion;
- period-to-period orbit repeatability;
- orbit phase-error RMS;
- exit x/y steering angles;
- frequency residual against the model's analytic reference when available.

The nominal field map is calculated with manufacturing errors disabled. Each manufacturing member is then rebuilt with the entered error magnitudes and an explicit seed.

## What the percentiles mean

The 5th, median and 95th percentiles are descriptive statistics of the finite set of solver realizations that was actually run.

They are **not** automatically:

- 90% confidence intervals;
- production-yield predictions;
- tolerance-process capability (`Cp`, `Cpk`);
- experimental uncertainty intervals;
- certification evidence.

Those stronger interpretations require a justified manufacturing/process distribution, adequate sample design and, where appropriate, experimental data.

## Requirement screening

A user may enter a lower, upper, or two-sided engineering bound for a propagated observable. Physical Lab reports how many sampled realizations satisfy it.

`PASS` means every **sampled** propagated realization met the entered bound.

`REVIEW` means at least one sampled realization did not.

Neither result makes a claim about unsampled manufactured units.

## Target-B0 calibration boundary

Manufacturing propagation refuses to run while target-B0 calibration is enabled. Re-fitting remanence for each manufacturing seed could artificially force random realizations back toward the same target field and hide the variation being studied.

Recommended sequence:

1. calibrate the nominal design if needed;
2. freeze the calibrated `Br`;
3. disable target-B0 calibration;
4. enter justified manufacturing-error magnitudes;
5. run the nonlinear field ensemble;
6. run field → trajectory → radiation propagation.

## Radiation-model boundary

The pinned Radiation Platform is a single-electron model. This propagation does not add capabilities the upstream solver does not have. In particular it does not represent:

- bunch emittance;
- beam energy spread;
- coherent bunch effects;
- beamline optics;
- detector response;
- experimental apparatus uncertainty.

Those should be added as explicit later model layers rather than silently folded into the current result.

## Validation layers

Physical Lab uses separate evidence layers:

1. **deterministic source validation** checks aggregation, requirement logic and file/config boundaries without needing native RADIA;
2. **native RADIA Full-mode acceptance** checks a real RADIA extension and field calculation on clean macOS;
3. **cross-engine acceptance** executes a small regular 3-D field map through the pinned Radiation Platform field-map device and `run_sim_scalar` on clean macOS;
4. user research runs supply the actual geometry, manufacturing-error model and scientific interpretation.

The CI acceptance map is deliberately small and synthetic. It validates the interface, not a specific magnet or experiment.
