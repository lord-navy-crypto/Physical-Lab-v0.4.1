# Accelerator Reference Benchmark

Physical Lab uses a deliberately simple planar-undulator case as an independent analytic benchmark for the accelerator-physics workflow.

## Reference case

The committed reference uses:

- sinusoidal planar magnetic field peak amplitude: `B0 = 0.05 T`;
- period: `lambda_u = 20 mm`;
- electron Lorentz factor: `gamma = 80`;
- on-axis observation.

For this restricted case,

```text
K = e B0 lambda_u / (2 pi m_e c)

lambda_1 = lambda_u (1 + K^2/2) / (2 gamma^2)

f_1 = c / lambda_1

E_1 = h f_1
```

The committed deterministic snapshot is `docs/accelerator-reference-benchmark.json` and is regenerated/checked by `scripts/accelerator_reference_benchmark.py`.

## Cross-engine acceptance

The clean-macOS Full-mode workflow constructs the same regular sinusoidal 3-D field map, sends it through the pinned Radiation Platform `FieldMapInsertionDevice` and scalar single-electron solver, then compares the resulting fundamental frequency and photon energy with the independent analytic reference.

The acceptance requires both resonance observables to remain within a bounded relative-error threshold and also checks that the reported photon energy is internally consistent with `E = h f`.

This strengthens the acceptance test from “the solver returned finite values” to “the solver returned the expected resonance scale for a case with a known analytic result.”

## What passing means

Passing supports a narrow statement: the field-map interface, unit conversion, trajectory/radiation execution path, and fundamental-resonance scale agree for this simple reference case within the declared numerical threshold.

It does **not** establish:

- validation of a specific manufactured undulator;
- production yield or process capability;
- bunch emittance or energy-spread effects;
- coherent radiation effects;
- beamline optics or detector response;
- agreement with experimental measurements.

Those remain separate validation layers.
