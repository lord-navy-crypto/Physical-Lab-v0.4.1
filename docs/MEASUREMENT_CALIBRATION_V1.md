# Physical Lab Measurement & Calibration Evidence v1

## Goal

Physical Lab projects can now preserve real measurement assets and calibration metadata as first-class `.physlab` evidence.

This phase establishes the evidence model **before** adding more hardware adapters. Arduino, Hall-probe, photogate, accelerometer, camera-tracking or other acquisition paths can later feed the same registry instead of inventing a new persistence format for each device.

## Project relationship

Measurement evidence belongs to a project, not to temporary UI state:

```text
.physlab Project
├── Experiment manifests
├── Compute jobs/results
├── Measurements
├── Calibration
└── Reports / provenance
```

The registry uses the active `.physlab` project selected by the Project Kernel.

## Measurement asset contract

Supported registration formats in v1:

- CSV
- TSV
- JSON
- HDF5 (`.h5` / `.hdf5`)
- text

Every asset receives:

- content-derived `measurement_id`
- SHA-256
- original/sanitized filename
- size
- project-relative asset path
- Lab profile
- instrument/source label
- measured quantity
- reported unit text
- capture/run label
- notes
- bounded metadata preview
- scientific boundary

The raw bytes are copied into:

```text
measurements/<measurement-id>/<filename>
```

with metadata in:

```text
measurements/<measurement-id>/measurement.json
measurements/index.json
```

The same exact bytes map to the same measurement ID. Re-registering the identical asset therefore does not create duplicate evidence entries.

## Preview policy

CSV/TSV and JSON receive bounded metadata previews so the UI can confirm basic structure without copying an entire dataset into project metadata.

HDF5 remains an opaque fingerprinted asset in v1. That is deliberate: a generic HDF5 reader should not guess which dataset, units or axes are scientifically authoritative. A later HDF5 mapping layer can require the user to select the intended dataset and units explicitly.

## Calibration record contract

Calibration records store:

- instrument
- calibration parameter
- nominal value + original unit
- standard uncertainty + unit
- canonical value/unit
- method
- reference/certificate label
- profile
- calibration date/run label
- related measurement IDs
- notes

Calibration identity is deterministic from this semantic payload. Re-registering the same calibration does not duplicate the index.

A calibration record can only link to measurement IDs already present in the project.

## Canonical unit layer

`physical_lab_units.py` provides a deliberately small, auditable unit allow-list.

Current families include:

- dimensionless / percent
- length
- time
- frequency
- magnetic field
- energy
- angle
- current
- voltage
- mass
- temperature
- force
- pressure
- velocity
- diffusion coefficient

Examples:

```text
10 mm  -> 0.01 m
50 mT  -> 0.05 T
1 keV  -> 1.602176634e-16 J
180 deg -> pi rad
```

Unknown units are rejected rather than silently guessed. Conversions across incompatible dimensions are rejected.

The intended architecture is:

```text
UI / evidence / manifest
        ↓
unit-aware boundary
        ↓
canonical value + unit
        ↓
solver hot path
        ↓
plain float / ndarray
```

This avoids introducing unit-wrapper overhead into numerical loops while still protecting persistence and engineering interfaces from common scale mistakes.

## Uncertainty boundary

Calibration uncertainty is stored as a **standard uncertainty value supplied by the user**. Physical Lab does not infer:

- distribution shape
- coverage probability
- calibration accreditation
- metrological traceability
- sensor resolution
- environmental correction
- model-form uncertainty

Nominal and uncertainty units must be dimensionally compatible.

The existing Engineering V&V layer can later consume these records when a user explicitly maps a measurement quantity to a simulation observable.

## UI

With an active `.physlab` project, every Engineering workspace exposes:

### Measurements

- upload/register evidence
- instrument/source
- quantity/unit label
- capture label/notes
- evidence table
- inspect complete metadata

### Calibration

- instrument and parameter
- nominal value/unit
- standard uncertainty
- method/reference
- link to one or more project measurement IDs
- canonical value display

### Evidence index

- measurement count
- calibration count
- formats
- instruments
- scientific boundary

## What this does not claim

A file upload is not experimental validation.

A calibration record is not automatically an accredited calibration.

A matching unit is not proof that a simulation observable and measurement column represent the same physical quantity.

The next validation layer must explicitly perform:

```text
measurement selection
        ↓
quantity / unit mapping
        ↓
calibration application
        ↓
simulation observable selection
        ↓
measurement uncertainty
+ simulation uncertainty
+ model-form uncertainty
        ↓
residual / normalized discrepancy
        ↓
validation interpretation
```

## Deterministic CI

`measurement_calibration_validation.py` checks:

- engineering unit conversions
- incompatible-unit rejection
- measurement SHA-256
- exact raw-asset round trip
- CSV metadata preview
- idempotent measurement indexing
- canonical calibration values
- standard-uncertainty dimensional consistency
- deterministic calibration identity
- invalid measurement linkage rejection
- evidence summary
- Tauri packaging and Engineering facade integration

The CI fixture is explicitly synthetic and does not represent a physical calibration certificate.

## Future hardware adapters

Future adapters should call the same registry APIs rather than write custom project files. Examples:

- Arduino bounded serial capture
- Hall probe / gaussmeter field scans
- photogate timing
- accelerometer motion traces
- video/object-tracking trajectories
- spectrometer/detector CSV exports

Each adapter should add acquisition metadata but preserve the same raw-asset fingerprint and project evidence model.
