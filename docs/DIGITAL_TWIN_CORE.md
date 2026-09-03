# Physical Lab Digital Twin Core

Physical Lab's next research layer is built around one principle: **measurement, simulation and validation should share the same scientific definitions instead of being separate UI features.**

The initial digital-twin core lives in `src-tauri/resources/ui/physical_lab_digital_twin.py`. It is intentionally independent of Streamlit, Tauri, Arduino hardware models and RADIA so the desktop Data Bridge, managed Labs, CLI/SDK tools and native-engine adapters can call the same validated functions.

## Implemented scientific primitives

### 1. Linear sensor calibration

`fit_linear_calibration(raw, reference)` fits

`reference = slope × raw + offset`

and reports slope, offset, RMSE, R², residual spread and standard errors for the fitted coefficients. This is intended for Hall sensors, voltage/temperature sensors and other classroom/research measurements where an affine calibration is physically justified.

The reported fit uncertainty does **not** include unmodeled sensor drift, hysteresis, temperature response or uncertainty in the reference standard.

### 2. Measured field ↔ model comparison

`compare_field_series(position, measured, model)` compares aligned field samples and reports MAE, RMSE, bias, maximum error, relative RMSE, R², peak-field difference, residual spread and trapezoidal field integrals.

This is the base mathematical layer for the future `Hall sensor → calibrated B(z) → RADIA B(z) → residual` workflow. Coordinate and field units remain dataset metadata; Physical Lab does not silently reinterpret them.

### 3. Affine inverse discrepancy fit

`fit_model_affine(measured, model)` fits

`measured ≈ scale × model + offset`.

This is a deliberately limited first inverse-model step. It can detect a global gain/offset mismatch between measurement and simulation, but it is **not** presented as inference of magnet gap, remanence, alignment or material parameters. Those require a validated RADIA forward-model adapter and explicit parameter bounds.

### 4. Beam phase-space statistics

`analyze_beam_phase_space(x, px, y, py, beta_gamma=...)` computes covariance-based RMS emittance and Twiss α/β/γ in each transverse plane. Normalized emittance is only emitted when `beta×gamma` is supplied explicitly.

The dataset must define whether momentum-like columns are canonical momenta, slopes or normalized coordinates; Physical Lab does not invent those conventions.

### 5. Residual-guided measurement suggestions

`suggest_residual_measurement_points(...)` ranks existing coordinate locations using residual magnitude plus a local residual-gradient term while enforcing minimum spacing.

This is intentionally called **residual-guided sampling**, not Bayesian information gain or optimal experimental design. It is a transparent heuristic that helps decide where an additional measurement may be useful before a more rigorous active-design module is implemented.

## Research CLI

`scripts/physical_lab_digital_twin_cli.py` exposes the same shared core to CSV/TSV data before the desktop GUI wiring is complete. It does not duplicate the equations.

Examples:

```bash
python3 scripts/physical_lab_digital_twin_cli.py calibrate scan.csv --raw adc --reference field_mT
python3 scripts/physical_lab_digital_twin_cli.py field-compare scan.csv --position z_mm --measured measured_Bz --model radia_Bz
python3 scripts/physical_lab_digital_twin_cli.py inverse-affine scan.csv --measured measured_Bz --model radia_Bz
python3 scripts/physical_lab_digital_twin_cli.py phase-space beam.csv --x x --px px --y y --py py --beta-gamma 1000
python3 scripts/physical_lab_digital_twin_cli.py suggest-points scan.csv --position z_mm --measured measured_Bz --model radia_Bz --count 3
```

Every command emits structured JSON with an explicit schema and scientific caveat so the output can be stored in `.physlab` provenance or consumed by a future desktop/SDK adapter.

## Validation

`scripts/digital_twin_reference_validation.py --check` verifies deterministic synthetic cases for all five primitives against `docs/digital-twin-reference-validation.json`.

The Source Integrity workflow runs this check on every push and pull request. A green result means the shared mathematical definitions reproduce the committed deterministic references; it does not claim that a real sensor, magnet or beam has been experimentally validated.

## Full-mode acceptance boundary

`.github/workflows/full-mode-acceptance.yml` runs on a clean macOS runner, checks out a pinned RADIA Universal2 builder revision, compiles the native extension, verifies `arm64 + x86_64`, evaluates a tiny native rectangular-magnet field, checks axial symmetry/transverse suppression, runs the digital-twin reference core, and uploads a JSON evidence artifact.

Passing that job proves a small native RADIA field path works inside Physical Lab's acceptance environment. It does **not** validate a specific undulator, manufacturing model, radiation spectrum or experimental magnet.

## Next integration targets

1. Data Bridge calibration profiles stored inside `.physlab` workspaces.
2. Measured-field/RADIA comparison UI with residual plots and field-integral differences.
3. Bounded RADIA parameter inference with explicit priors/bounds and uncertainty reporting.
4. Beam Dynamics view that consumes trajectory/ensemble data rather than duplicating a new solver.
5. Desktop actions that call the shared core and persist outputs as project provenance.

This keeps Physical Lab centered on a single engineering-physics chain:

`measure → calibrate → model → simulate → compare → update → validate → reproduce`.
