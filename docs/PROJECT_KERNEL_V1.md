# Physical Lab `.physlab` Project Kernel v1

## Purpose

Physical Lab now has three persistence layers with distinct responsibilities:

1. **Experiment Kernel** owns stable scientific experiment identity (`experiment_sha256`).
2. **Compute Engine** owns durable execution state, checkpoints, logs and result files.
3. **Project Kernel** owns project membership, research context, references and report provenance.

The Project Kernel is intentionally an **index and source-of-truth layer**, not a second solver store. Large field maps, trajectories, spectra and Monte Carlo arrays remain in their native result stores and are referenced by path + SHA-256.

## Directory contract

```text
$PHYSICAL_LAB_DATA_DIR/projects/<slug>.physlab/
├── project.json
├── experiments/
│   └── exp-<fingerprint-prefix>/
│       └── manifest.json
├── jobs/
├── results/
│   └── <job-id>.json          # small result reference/summary only
├── measurements/
├── calibration/
├── reports/
│   └── project-report-*.md
└── provenance/
```

`measurements/`, `calibration/` and `provenance/` are reserved now so future measurement/digital-twin work does not require another project format change.

## Project schema

Current schema:

```text
physical-lab-project-v1
```

`project.json` stores:

- stable `project_id`
- name / slug
- research question and description
- participating Lab profiles
- experiment index
- compute-job index
- result-reference index
- report provenance
- migration history
- explicit scientific boundary

## Scientific identity

Project identity does **not** replace experiment identity.

```text
Project
  └── Experiment
        └── experiment_sha256
```

The same scientific manifest registered twice produces the same `exp-...` project entry. A changed scientific parameter produces a changed Experiment Kernel fingerprint and therefore a new experiment entry.

This lets a project contain a design history without pretending two different parameter sets are one run.

## Compute Engine synchronization

The Project Kernel scans the existing Compute Engine store and matches jobs through `experiment_sha256`.

```text
registered experiment fingerprint
            ↓
Compute Engine job fingerprint
            ↓
match
            ↓
project job reference
            ↓
completed result reference + result SHA-256
```

This architecture has two important properties:

- jobs can continue to be owned by the Compute Engine;
- reopening the project can rebuild/synchronize references after a UI restart.

The Project Kernel does not need to own the worker lifecycle.

## Result non-duplication

A project result entry contains only small metadata:

- job ID
- experiment ID
- result path
- result SHA-256
- bounded scalar summary
- update timestamp

It deliberately does **not** copy large scientific arrays into `project.json`.

This is important for future RADIA field maps, trajectories, spectra and large UQ campaigns.

## Project report v1

The built-in Markdown report currently includes:

- project identity
- research question
- description
- experiment identities/fingerprints
- compute jobs and statuses
- result references and fingerprints
- reproducibility/V&V boundary

This is the first report layer, not the final publication system. Future versions can add selected figures, measurement/calibration evidence, uncertainty budgets and engineering requirement tables while continuing to source those sections from canonical project references.

## UI behavior

Every Lab Engineering workspace now exposes a compact `.physlab Project` expander.

The user can:

- create a project;
- select an existing project;
- edit project research context;
- register the current Lab experiment;
- synchronize matching compute jobs/results;
- generate/download a Markdown project report.

The two existing Lab application modes remain unchanged:

```text
Mathematical Tool
Physics Scenario
```

`.physlab` is a project/persistence layer, not a third scientific mode.

## Migration boundary

v1 supports an explicit metadata-only migration path from the prototype schema:

```text
physical-lab-project-v0
→
physical-lab-project-v1
```

Migration may add/rebuild indexes and metadata fields, but it must not reinterpret solver output or silently alter scientific parameters.

## CI contract

`project_kernel_validation.py` deterministically checks:

- `.physlab` structure and schema;
- experiment-manifest fingerprint preservation;
- idempotent experiment registration;
- Compute Engine job matching;
- completed result reference hashing;
- non-duplication of large result arrays;
- legacy metadata migration;
- project discovery/summary;
- report generation;
- Tauri packaging and Engineering facade integration.

## Next Project Kernel phases

The project layout is intentionally prepared for the next major Physical Lab work:

1. **measurement assets** with calibration/provenance records;
2. **native RADIA/Radiation worker references**;
3. **unified UQ propagation campaigns**;
4. **DOE/optimization campaign groups**;
5. **HTML/PDF research report generation**;
6. **Local AI project query API** over canonical project metadata rather than Streamlit session state.

## Boundary

A `.physlab` project improves reproducibility and traceability. It does not make a simulation experimentally validated, manufacture-ready or certified. Those claims require separate measurement, calibration, model-form uncertainty and applicable engineering evidence.
