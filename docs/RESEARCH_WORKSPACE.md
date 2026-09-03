# Physical Lab v0.5.0 Research Workspace

## Design rule

Physical Lab coordinates scientific work without replacing the validated solvers inside the individual Labs. A project records measurements, parameters, results, versions, source commits and handoffs so a result can be inspected and reproduced later.

## Project layout

A project is a Finder-visible directory ending in `.physlab`:

```text
Undulator-Measurement-Study.physlab/
├── project.json
├── datasets/
├── measurements/
├── runs/
├── figures/
├── exports/
├── provenance/
├── pipelines/
└── campaigns/
```

Dataset metadata records physical quantity, units, sensor, calibration notes, source path, stored path, timestamp and SHA-256. Run snapshots record module, Safe/Full mode, parameter/result JSON, source commit, Python version and a package freeze when a managed Lab environment is available.

## Data Bridge

Supported project imports:

- CSV
- TSV
- JSON
- HDF5 (`.h5` / `.hdf5`)

CSV/TSV receive direct numeric summary/validation support. JSON/HDF5 are preserved with provenance for Lab-specific readers instead of being flattened incorrectly by the shell.

### Arduino / serial capture

The macOS app scans `/dev/cu.*` and `/dev/tty.*`. A bounded capture configures the selected serial port with `stty`, reads numeric lines without PySerial, and writes a timestamp/value CSV into the project. The final field of a comma-separated serial line may also be numeric.

This is a data-acquisition bridge, not firmware flashing or arbitrary device control.

## Integrity Center

The compatibility matrix reads each installed Lab's own requirements file and checks versions inside that Lab's managed `.venv`. PEP 440 comparison uses `packaging.specifiers.SpecifierSet` / `packaging.version.Version`, with pip's vendored packaging as a fallback.

A package found globally does not make a Lab green. Repair acts only on the selected Lab `.venv`.

Scientific smoke tests are intentionally small and bounded. They test a deterministic numerical operation appropriate to each Lab family and are separate from expensive research runs.

## Pipelines

Current templates include:

1. Measured magnetic field → field validation → RADIA → trajectory handoff → Radiation Platform.
2. Oscillation result → mass/stiffness/damping interchange → Chrono::Modal adapter boundary → comparison.
3. Material/lattice/temperature/field interchange → VAMPIRE adapter boundary → magnetization result import.
4. Generic measurement → statistics → observed/reference validation.

Chrono::Modal and VAMPIRE are not presented as active Lab solvers. Their interchange contracts exist so a later validated adapter has an explicit boundary instead of silently changing current models.

## Campaigns

A campaign stores a bounded linear parameter grid, persistent jobs, queue state and `maxParallel` resource budget. Pause/resume/retry/reset update the queue metadata. Current Streamlit Labs still own their parameter controls; Physical Lab does not pretend to auto-drive a Lab without a module-specific parameter adapter.

## Results & validation

For numeric CSV/TSV columns Physical Lab reports:

- N
- mean
- sample standard deviation
- normal-approximation 95% confidence interval for the mean
- minimum / maximum

Observed/reference comparisons report MAE, RMSE, maximum absolute error, relative RMSE and R². The agreement label is descriptive only and does not establish which dataset/model is correct.

## Reproducibility export

A project export adds machine/version provenance and creates a ZIP outside the project directory to avoid self-inclusion. For installed Labs it records source commit, Python version and `pip freeze --all`.

## Task cancellation

Downloads and subprocess-backed install/build stages now check a user cancellation token. Physical Lab can terminate a cancellable child process or stop an active download. Completed artifacts may remain and are intentionally repairable/retryable rather than silently deleted.
