# Physical Lab v0.8.0 — Reproducible Computational Physics & Engineering for macOS

[![Source Integrity](https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/actions/workflows/source-integrity.yml/badge.svg)](https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/actions/workflows/source-integrity.yml)

**Physical Lab is a native macOS research workbench that turns seven computational-physics projects into one reproducible engineering workflow: requirement → model → run → validate → compare → optimize → measure → calibrate → decide.**

It combines numerical-error analysis, Monte Carlo/statistical physics, nonlinear dynamics, oscillation/integration, and a RADIA-backed **magnet → electron trajectory → radiation** workflow. Physical Lab adds the research-software and engineering layer around those solvers: isolated environments, pinned source revisions, ABI-aware native-engine checks, Safe/Full execution, measurement provenance, scientific smoke tests, run comparison, V&V/UQ, requirement screening, robust-design summaries, measured-field residual analysis, batch planning, and reproducibility exports.

## 30-second overview

| Question | Physical Lab answer |
|---|---|
| What physics does it cover? | Numerical error, Ising/Monte Carlo, random walk/QMC, chaos/Lyapunov analysis, oscillators/integration, RADIA magnetics, undulator radiation |
| What is the representative deep workflow? | **RADIA Magnet Studio → realized magnetic field → measured/model residual → electron trajectory → Radiation Platform → analytic/reference comparison** |
| What engineering questions can it answer? | Requirement margin, sensitivity ranking, finite-ensemble robustness, Pareto design comparison, measured-field discrepancy, bounded calibration updates, lightweight thermal coupling, resumable batch planning |
| How is correctness treated? | Analytic/reference comparisons, bounded scientific smoke tests, uncertainty metrics, explicit model limitations, Safe/Full separation |
| How is software reliability handled? | Per-Lab `.venv`, PEP 440 compatibility checks, `pip check`, import tests, CPython ABI checks, pinned GitHub revisions, cancellable tasks |
| Can experiment data enter the platform? | Yes. CSV/TSV/JSON/HDF5 provenance plus bounded Arduino-style serial measurement capture |
| Can results be reproduced? | Projects preserve parameters, source revision, Python/package state, measurements, runs and exportable provenance |

## Representative research path: accelerator physics

Physical Lab's clearest end-to-end example is the accelerator-physics path:

```text
Engineering requirement
        ↓
Undulator / magnet geometry
        ↓
RADIA Magnet Studio (Full mode)
        ↓
realized B(x,y,z), harmonics, field integrals, manufacturing-error ensemble
        ↓
measured-field comparison / residual
        ↓
electron trajectory / phase behavior
        ↓
Radiation Platform
        ↓
resonance / spectrum-oriented analysis
        ↓
analytic reference + requirement margin + design decision
```

Safe mode keeps a clearly labeled analytical ideal-undulator fallback available when RADIA is unavailable; it is not presented as a replacement for 3-D magnetic-field solving.

## What I built in Physical Lab

Physical Lab is **not a claim that every upstream physics engine was authored here**. The project separates three contribution layers:

1. **Original physics projects and analysis layers** — the seven linked Lab repositories and the Physical Lab advanced experiment suite, including numerical reliability studies, finite-size/statistical diagnostics, QMC comparisons, Lyapunov/stability analysis, integration/error diagnostics, RADIA tolerance ensembles, radiation sensitivity/reference workflows, and the v0.8 engineering-design layer.
2. **Research-software engineering** — the Tauri/Rust macOS shell, Module/Runtime/Dependency/Task/Integrity centers, isolated environments, Safe/Full engine policy, source pinning, ABI/runtime discovery, scientific smoke tests, cancellation, workspaces, run provenance and reproducibility export.
3. **Third-party scientific engines** — RADIA, Project Chrono/Chrono::Modal and VAMPIRE retain their own authorship and licenses. RADIA is currently consumed by real Labs; Chrono::Modal and VAMPIRE remain optional adapter boundaries and are intentionally not advertised as active solvers.

See [`docs/ORIGINAL_CONTRIBUTIONS.md`](docs/ORIGINAL_CONTRIBUTIONS.md) for the detailed boundary.

## Seven validated Lab interfaces

- **Numerical Error Analysis** — Taylor evaluation, cancellation, floating-point reliability and convergence diagnostics.
- **Ising Monte Carlo Lab** — 1-D/2-D Ising systems, samplers, autocorrelation/ESS, Binder-style finite-size analysis and critical behavior.
- **Random Walk & Monte Carlo** — random-walk scaling, first-passage/ensemble analysis, Monte Carlo and scrambled Sobol QMC comparisons.
- **Nonlinear Dynamics & Chaos** — driven/double pendula, Lyapunov divergence, stability/flip maps and Poincaré-oriented analysis.
- **Oscillation & Numerical Integration** — linear/damped/driven/nonlinear oscillators, Euler/Symplectic/RK2/RK4/DOP853 comparisons and energy-work closure.
- **RADIA Magnet Studio** — 3-D magnet geometry, actual RADIA field solving, harmonics, field integrals, trajectory/phase metrics and manufacturing-error ensembles.
- **Radiation Platform** — magnet-to-trajectory-to-radiation workflow, scan intelligence and ideal-reference comparisons.

All module downloads are pinned to explicit Git commit revisions in `src-tauri/resources/modules.json`; `physical-lab-source.json` records the revision actually requested for each managed checkout.

## v0.8.0 engineering workflow

Physical Lab v0.8 extends the existing Engineering V&V/UQ panel into a unified **Engineering Design Workflow** available inside the Lab research UI.

### Requirement-driven verification

Named response metrics can be checked against lower and/or upper limits with an explicitly entered symmetric uncertainty interval:

- **PASS** — the whole entered interval stays inside the requirement;
- **REVIEW** — nominal is inside, but the entered interval crosses a limit;
- **FAIL** — nominal itself violates a limit.

These are engineering-screening labels, not certification claims.

### Design optimization / Pareto screening

Candidate designs can be compared with explicit `min` / `max` objectives. The workflow identifies the non-dominated Pareto subset without pretending that a finite candidate table proves a global optimum.

### Sensitivity and robust design

One-at-a-time finite-difference cases can be ranked by `|Δy/Δx|`. Solver/manufacturing ensembles can be grouped by design and summarized with mean, sample standard deviation, min/max, p05/median/p95, and finite-sample requirement pass fractions.

Finite-sample pass fractions are descriptive screening results; they are not automatically manufacturing yield or certified probabilities of failure.

### Measured-field validation layer

Co-registered field series can be compared using MAE, RMSE, maximum absolute residual, model-relative RMSE, field-integral difference, and uncertainty-normalized residual statistics when pointwise standard uncertainty is actually supplied.

The workflow does not infer missing uncertainty or distributional assumptions, and it does not label the normalized statistic as chi-square.

### Closed-loop calibration/control foundation

A bounded model-based update computes the next parameter from current parameter, measured response, target response, local response sensitivity and gain. It performs **no hardware I/O**. Any future hardware-in-the-loop adapter must add a device-specific safety boundary before sending commands to physical equipment.

### Lightweight multiphysics coupling

A transparent undulator thermal screen propagates uniform linear expansion and an optional user-entered fractional field-temperature coefficient into period, `K`, resonance wavelength and photon energy. It is a first-order engineering screen, not structural/thermal FEA.

### Batch / HPC foundation

Physical Lab can create deterministic case fingerprints, resumable chunks and minimum scheduling-wave estimates for a requested worker count. Actual concurrent solver execution remains adapter-specific so native engines are not blindly parallelized.

See [`docs/ENGINEERING_WORKFLOW_V080.md`](docs/ENGINEERING_WORKFLOW_V080.md).

## Project Workspace

A `.physlab` project owns:

```text
project.json
├── datasets/
├── measurements/
├── runs/
├── figures/
├── exports/
├── provenance/
├── pipelines/
└── campaigns/
```

Runs can preserve model parameters, Safe/Full mode, source revision, Python/package state and results, then be compared field-by-field.

### Measurement bridge

Physical Lab can preserve CSV, TSV, JSON and HDF5 measurements with quantity, unit, sensor, calibration notes, timestamp and SHA-256 provenance. The native macOS build can discover `/dev/cu.*` / `/dev/tty.*` serial devices and perform bounded numeric capture for Arduino-style sensors. This is data acquisition, not arbitrary device control or firmware flashing.

### Integrity Center

Dependency presence and scientific readiness are deliberately separate:

- requirement compatibility is checked **inside each Lab's own `.venv`** using PEP 440 semantics;
- global packages do not make a Lab green;
- repair targets only the selected managed Lab environment;
- scientific smoke tests perform small deterministic calculations instead of stopping at `import` success.

### Results & validation

For numeric datasets, Physical Lab can report N, mean, sample standard deviation, 95% CI, min/max, and observed/reference metrics including MAE, RMSE, relative RMSE, maximum absolute error and R². Agreement labels are descriptive only; they do not prove which model is physically correct.

### Reproducibility

A reproducibility export packages project state with machine/runtime information, source revisions and per-Lab package freezes. See [`docs/RESEARCH_WORKSPACE.md`](docs/RESEARCH_WORKSPACE.md).

## Optional Local AI Assistant

Physical Lab can use a **local-only, read-only AI explanation layer** without making AI part of the scientific solver. The assistant discovers either the private OpenPenguin/Ollama runtime at `127.0.0.1:11435` or an existing Ollama service at `127.0.0.1:11434`, sends a bounded structured snapshot of the current Lab state, and can explain parameters, units, assumptions, diagnostics and possible next experiments. It cannot modify parameters, download models, execute model-generated code, or contact a cloud endpoint. Physical Lab remains fully functional when no local model is running.

For RADIA Magnet Studio Full mode, the **RADIA Measurement Adapter** can evaluate the current managed magnet model at explicit measurement coordinates and write lineage-tracked `Bx/By/Bz/Bperp` columns into a derived `.physlab` dataset. A bounded one-parameter profile can repeatedly run the real RADIA forward model over explicit `gap_mm`, `br_t`, or `z_offset_mm` candidates. The best result means only the lowest RMSE on that finite grid; it is not presented as a posterior distribution or global optimum.

## Measurement Digital Twin

Physical Lab has a shared **measurement → calibration → model → comparison → update** scientific core instead of treating sensor data as a generic file attachment. `physical_lab_digital_twin.py` provides deterministic definitions for linear sensor calibration, measured/model field residuals and field integrals, affine model-discrepancy fitting, transverse beam phase-space/RMS-emittance statistics, and transparent residual-guided remeasurement priorities.

The project-level **Measurement Digital Twin** view is injected into the accelerator/dynamics research layer and reads CSV/TSV datasets directly from `.physlab` workspaces. Calibration results can create lineage-tracked derived datasets; comparison, inverse-fit, phase-space and remeasurement outputs are written back to project provenance. Units and coordinate conventions are never silently inferred.

The same core is exposed through `scripts/physical_lab_digital_twin_cli.py`, so GUI and scripted workflows share the same mathematical definitions. See [`docs/DIGITAL_TWIN_CORE.md`](docs/DIGITAL_TWIN_CORE.md).

## Native Full-mode acceptance

Source CI keeps RADIA outside the deterministic source-only reference snapshot. Separately, `.github/workflows/full-mode-acceptance.yml` runs on a clean macOS runner, builds a **pinned RADIA Universal2** revision, verifies `arm64 + x86_64`, evaluates a real native magnetic field with `radia.Fld`, checks symmetry/sanity conditions, reruns the deterministic reference cores, and uploads JSON evidence artifacts.

The same acceptance workflow exercises the cross-engine boundary: a regular 3-D field map is converted through the pinned Radiation Platform `FieldMapInsertionDevice` path and propagated into finite trajectory/radiation observables. This validates the interface and runtime boundary; it does **not** claim validation of a specific manufactured undulator, beam, detector, or radiation experiment.

### Independent accelerator resonance benchmark

For the deliberately simple planar case `B0 = 0.05 T`, `lambda_u = 20 mm`, `gamma = 80`, Physical Lab computes the closed-form on-axis undulator resonance and requires the clean-macOS field-map solver's fundamental frequency and photon energy to agree within a declared `5e-4` relative-error bound. The same check verifies `E = h f` consistency and that the solver-reported frequency residual matches the independently computed residual. See [`docs/ACCELERATOR_REFERENCE_BENCHMARK.md`](docs/ACCELERATOR_REFERENCE_BENCHMARK.md).

### v0.8 measured-field-to-radiation acceptance

Full-mode CI now creates a second deterministic **synthetic measurement-like** field map on the exact nominal grid. It contains a small field-amplitude perturbation and a weak third harmonic. Both nominal and perturbed maps are run through the pinned Radiation Platform worker, then `scripts/measured_field_radiation_validation.py` records:

- model ↔ measurement-like field RMSE / integral discrepancy;
- uncertainty-normalized residual screening;
- fundamental-frequency change;
- photon-energy change;
- maximum transverse-excursion change.

This proves the software path **field discrepancy → trajectory/radiation discrepancy** is executable on clean macOS. The CI field is synthetic and must not be described as a real magnet measurement.

## Reproducible reference validation

Source CI runs deterministic reference checks against committed snapshots. The current set includes Taylor-series error, harmonic-oscillator RK4 return error, exact random-walk MSD, the exact 2-D zero-field Ising critical-temperature reference, an ideal-undulator first-harmonic reference, the Measurement Digital Twin reference core, the dedicated planar-undulator accelerator benchmark, and the v0.8 Engineering Design Workflow definitions.

**RADIA Full mode is deliberately kept separate from source-only CI** because native 3-D solving is validated by the clean-macOS Full-mode acceptance workflow.

See [`docs/REFERENCE_VALIDATION.md`](docs/REFERENCE_VALIDATION.md), [`docs/reference-validation.json`](docs/reference-validation.json), [`docs/accelerator-reference-benchmark.json`](docs/accelerator-reference-benchmark.json), and [`docs/engineering-workflow-reference-validation.json`](docs/engineering-workflow-reference-validation.json).

## Validation philosophy

Physical Lab follows a simple rule: **a simulation result is not automatically a physical result**.

The project therefore distinguishes:

- numerical convergence from physical validity;
- finite-time chaos indicators from global claims;
- finite QMC comparisons from universal superiority claims;
- remanent induction from solved undulator field amplitude;
- analytical Safe-mode references from RADIA Full-mode field solutions;
- synthetic measurement-like CI fixtures from real experimental measurements;
- finite-ensemble pass fractions from manufacturing yield/probability claims;
- Pareto non-dominance from proof of global optimality;
- optional detected runtimes from engines actually consumed by a Lab.

See [`docs/VALIDATION.md`](docs/VALIDATION.md) and [`docs/RESEARCH_NOTE_RADIATION.md`](docs/RESEARCH_NOTE_RADIATION.md).

## Build on macOS

```bash
chmod +x RUN_SOURCE_SELF_CHECK.command BUILD_PHYSICAL_LAB.command
./RUN_SOURCE_SELF_CHECK.command
./BUILD_PHYSICAL_LAB.command
```

The release builder targets a Universal2 macOS application (`arm64` + `x86_64`). Release version metadata is anchored by `VERSION` and checked against `package.json`, `src-tauri/Cargo.toml`, and `src-tauri/tauri.conf.json`. The Universal2 CI derives artifact names from that version instead of hard-coding a DMG version.

A packaged public DMG should still be treated separately from source correctness; signing/notarization must be validated on the exact release artifact.

## Source integrity CI

`.github/workflows/source-integrity.yml` checks repository structure, release-version consistency, JSON manifests, Python syntax, JavaScript syntax, deterministic reference snapshots and the project's source self-check on every push/PR. The accelerator analytic snapshot and Engineering Design Workflow snapshot are included in these deterministic checks. This does **not** substitute for real-macOS runtime acceptance tests of RADIA or hardware/serial paths.

## Current scope

- macOS desktop application built with Tauri 2 / Rust.
- Seven current computational-physics Labs.
- One shared engineering-design workflow layered across the Labs instead of an eighth disconnected Lab.
- RADIA is the only fragile native physics engine currently consumed by a real Lab.
- Chrono::Modal and VAMPIRE remain optional future adapter boundaries; they are not part of the project's primary external description until a validated Lab consumes them.
- The old `radiaition-study` / Radiation Study project is intentionally excluded.

## Documentation

- [`docs/ORIGINAL_CONTRIBUTIONS.md`](docs/ORIGINAL_CONTRIBUTIONS.md) — authorship and integration boundary.
- [`docs/VALIDATION.md`](docs/VALIDATION.md) — scientific/numerical validation policy.
- [`docs/RESEARCH_NOTE_RADIATION.md`](docs/RESEARCH_NOTE_RADIATION.md) — reproducible accelerator-physics validation protocol.
- [`docs/RESEARCH_WORKSPACE.md`](docs/RESEARCH_WORKSPACE.md) — workspace/data/reproducibility architecture.
- [`docs/RADIA_RADIATION_TOLERANCE_PROPAGATION.md`](docs/RADIA_RADIATION_TOLERANCE_PROPAGATION.md) — field → trajectory → radiation tolerance propagation boundary.
- [`docs/ACCELERATOR_REFERENCE_BENCHMARK.md`](docs/ACCELERATOR_REFERENCE_BENCHMARK.md) — analytic resonance benchmark and clean-macOS comparison boundary.
- [`docs/ENGINEERING_SIMULATION.md`](docs/ENGINEERING_SIMULATION.md) — V&V/UQ terminology and original engineering-screening layer.
- [`docs/ENGINEERING_WORKFLOW_V080.md`](docs/ENGINEERING_WORKFLOW_V080.md) — requirement → design → robustness → measurement → decision workflow.
- [`docs/DEPENDENCY_AUDIT.md`](docs/DEPENDENCY_AUDIT.md) — dependency/runtime policy.

## License

Physical Lab source is MIT-licensed. Linked or downloaded third-party projects retain their own licenses and attribution requirements.
