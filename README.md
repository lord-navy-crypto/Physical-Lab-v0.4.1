# Physical Lab v0.8.1 — Reproducible Computational Physics & Engineering for macOS

[![Source Integrity](https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/actions/workflows/source-integrity.yml/badge.svg)](https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/actions/workflows/source-integrity.yml)

**Physical Lab is a native macOS research workbench that turns seven computational-physics projects into one reproducible engineering workflow: requirement → model → run → validate → compare → optimize → measure → calibrate → decide.**

It combines numerical-error analysis, Monte Carlo/statistical physics, stochastic simulation, nonlinear dynamics, oscillation/integration, and a RADIA-backed **magnet → electron trajectory → radiation** workflow. Physical Lab adds the engineering and research-software layer around those solvers: isolated environments, pinned source revisions, Safe/Full execution, scientific smoke tests, measurement provenance, V&V/UQ, model-specific requirement scorecards, convergence/cost analysis, robust-design summaries, measured/model comparison, batch planning, run provenance, and reproducibility exports.

## 30-second overview

| Question | Physical Lab answer |
|---|---|
| What physics does it cover? | Numerical error, Ising/Monte Carlo, random walk/QMC, chaos/Lyapunov analysis, oscillators/integration, RADIA magnetics, undulator radiation |
| What is the representative deep workflow? | **RADIA Magnet Studio → realized magnetic field → measured/model residual → electron trajectory → Radiation Platform → analytic/reference comparison** |
| Are the other Labs engineered too? | **Yes in v0.8.1.** Numerical, Ising, Random Walk, Chaos, and Oscillation now receive domain-specific engineering scorecards, convergence/cost analysis, and finite-replicate robustness tools |
| What engineering questions can it answer? | Requirement margin, uncertainty budget, sensitivity, convergence, cost↔accuracy tradeoff, finite-ensemble robustness, measured/model discrepancy, Pareto design comparison, bounded calibration, batch planning |
| How is correctness treated? | Analytic/reference comparisons, scientific smoke tests, explicit model limitations, deterministic reference snapshots, Safe/Full separation |
| How is software reliability handled? | Per-Lab `.venv`, PEP 440 checks, `pip check`, import tests, CPython ABI checks, pinned revisions, cancellable tasks, Universal2 builds |
| Can experiment data enter the platform? | Yes. CSV/TSV/JSON/HDF5 provenance plus bounded Arduino-style serial numeric capture |
| Can results be reproduced? | Projects preserve parameters, source revision, Python/package state, measurements, runs and exportable provenance |

## Seven validated Lab interfaces

1. **Numerical Error Analysis** — Taylor evaluation, cancellation, floating-point reliability, reference comparison and convergence diagnostics.
2. **Ising Monte Carlo Lab** — 1-D/2-D Ising systems, multiple samplers, autocorrelation/ESS, multi-chain diagnostics, finite-size analysis and critical behavior.
3. **Random Walk & Monte Carlo** — random-walk scaling, first-passage/ensemble analysis, Monte Carlo and scrambled Sobol QMC comparisons.
4. **Nonlinear Dynamics & Chaos** — driven/double pendula, Lyapunov divergence, stability/flip maps and finite-window chaos diagnostics.
5. **Oscillation & Numerical Integration** — linear/damped/driven/nonlinear oscillators, Euler/Symplectic/RK2/RK4/DOP853 comparisons and energy-work checks.
6. **RADIA Magnet Studio** — 3-D magnet geometry, native RADIA field solving, harmonics, field integrals, trajectory/phase metrics and manufacturing-error ensembles.
7. **Radiation Platform** — magnet-to-trajectory-to-radiation workflow, scan-centric analysis and ideal/reference comparisons.

All managed module downloads are pinned to explicit Git commit revisions in `src-tauri/resources/modules.json`; `physical-lab-source.json` records the revision actually requested for each managed checkout.

## v0.8.1 — model-specific engineering across the other five Labs

v0.8.0 established a shared Engineering Design Workflow. v0.8.1 closes the maturity gap between the accelerator path and the five non-accelerator models by adding a **domain-specific engineering layer** rather than forcing every model into the same generic template.

Each supported Lab receives three common decision views:

- **Domain scorecard** — editable lower/upper targets with PASS / REVIEW / FAIL uncertainty-margin screening. Missing metrics remain REVIEW rather than silently passing.
- **Convergence / cost** — observed two-level convergence order plus a computational-cost-versus-error non-dominated frontier.
- **Replicate robustness** — finite seed/chain/timestep/repeat summaries with mean, sample standard deviation, coefficient of variation, p05/median/p95, range and extrema.

The shipped thresholds are transparent starting defaults and are editable. They are **not standards or certification limits**.

### Numerical Error → accuracy & precision engineering

The Numerical Error profile turns floating-point studies into an accuracy/cost design problem. The default scorecard considers:

- worst normalized numerical error;
- scan pass fraction;
- observed convergence order.

The cost/accuracy view can compare float32/float64, raw/range-reduced algorithms, Taylor order, reference precision or scan density. A small final Taylor term is not treated as proof that the final answer is accurate; independent/high-precision reference comparison remains decisive.

### Ising Monte Carlo → sampling & criticality engineering

The Ising profile uses the Lab's existing statistical diagnostics rather than counting raw sweeps as if they were independent samples. Its default scorecard considers:

- worst multi-chain R-hat;
- minimum effective sample size;
- exact/reference relative discrepancy when a reference exists;
- equilibration drift in sigma units.

This makes autocorrelation, ESS, equilibration, finite-size behavior and computational work part of the engineering decision.

### Random Walk / Monte Carlo → estimator engineering

The stochastic profile focuses on whether the estimator behaves as expected and whether additional computational work actually buys precision. The default scorecard considers:

- MSD/diffusion scaling-exponent error relative to the target theory used by the study;
- estimator relative error;
- finite-replicate coefficient of variation.

It can compare ordinary Monte Carlo, different sample counts/seeds and scrambled-QMC designs on a shared cost↔error plane without claiming universal superiority from one finite benchmark.

### Nonlinear Dynamics & Chaos → robust classification engineering

For chaotic systems, requiring long-time trajectories to remain pointwise identical is usually physically inappropriate. The Chaos profile instead defaults to:

- timestep sensitivity of a selected finite-window indicator;
- finite-replicate spread of a Lyapunov statistic;
- relative energy/work-balance error where such a balance is meaningful.

Engineering requirements should preferentially target Lyapunov estimates, Poincaré/event statistics, bifurcation/flip locations, invariants or other finite-window observables—not raw long-time coordinate agreement.

### Oscillation / Integration → dynamic-system engineering

The Oscillation profile maps solver outputs naturally to mechanical/control-style response requirements:

- frequency relative error;
- amplitude relative error;
- phase error;
- energy/work-balance relative error;
- response change under timestep refinement.

These are useful computational engineering quantities, but real apparatus validation still requires measurements, calibration, and model-form uncertainty evidence.

See [`docs/MULTI_LAB_ENGINEERING_V081.md`](docs/MULTI_LAB_ENGINEERING_V081.md).

## v0.8.0 — shared Engineering Design Workflow

The model-specific profiles sit on top of the common v0.8 engineering foundation rather than replacing it.

### Requirement-driven verification

Named response metrics can be checked against lower and/or upper limits with an explicitly entered symmetric uncertainty interval:

- **PASS** — the full entered interval stays inside the requirement;
- **REVIEW** — nominal is inside, but the entered interval crosses a limit;
- **FAIL** — nominal itself violates a limit.

These are engineering-screening labels, not certification claims.

### Sensitivity, optimization and robust design

Physical Lab supports one-at-a-time finite-difference sensitivity ranking, explicit min/max Pareto non-dominated screening, and finite solver/manufacturing ensemble summaries with mean, sample standard deviation, min/max and p05/median/p95. Finite-sample pass fractions are descriptive screening results, not automatically manufacturing yield or certified probabilities of failure.

### Measured-field validation

Co-registered field series can be compared using MAE, RMSE, maximum residual, model-relative RMSE, field-integral difference and uncertainty-normalized residual statistics when pointwise uncertainty is actually supplied. The workflow does not infer missing uncertainty assumptions or label the normalized statistic as chi-square without the needed statistical assumptions.

### Calibration, lightweight multiphysics and batch planning

A bounded model-based update can calculate a next parameter from response error and local sensitivity, but performs **no hardware I/O**. A first-order undulator thermal screen propagates expansion/field-temperature effects into `K` and resonance energy, explicitly without pretending to be structural/thermal FEA. Deterministic case fingerprints, resumable chunks and scheduling-wave estimates provide a batch/HPC boundary without blindly parallelizing native solvers.

See [`docs/ENGINEERING_WORKFLOW_V080.md`](docs/ENGINEERING_WORKFLOW_V080.md).

## Representative deep path: accelerator physics

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

## Research workspace and reproducibility

A `.physlab` project owns structured datasets, measurements, runs, figures, exports, provenance, pipelines and campaigns. Runs preserve model parameters, execution mode, source revision, Python/package state and results so they can be compared and reproduced.

### Measurement bridge

Physical Lab preserves CSV, TSV, JSON and HDF5 measurements with quantity, unit, sensor, calibration notes, timestamp and SHA-256 provenance. The native macOS build can discover `/dev/cu.*` / `/dev/tty.*` serial devices and perform bounded numeric capture for Arduino-style sensors. This is data acquisition, not arbitrary device control or firmware flashing.

### Integrity Center

Dependency presence and scientific readiness are deliberately separate. Requirement compatibility is checked inside each Lab's `.venv`; global packages do not make a Lab green; repair targets only the selected managed environment; and scientific smoke tests perform small calculations rather than stopping at import success.

### Run Vault and exports

The advanced experiment layer preserves parameter fingerprints, package versions, source revision and bounded result snapshots. Reproducibility exports package project state with machine/runtime information and per-Lab package freezes. See [`docs/RESEARCH_WORKSPACE.md`](docs/RESEARCH_WORKSPACE.md).

## Measurement Digital Twin

Physical Lab contains a shared **measurement → calibration → model → comparison → update** core for linear sensor calibration, measured/model field residuals and field integrals, affine discrepancy fitting, transverse beam phase-space/RMS-emittance statistics, and residual-guided remeasurement priorities.

For RADIA Magnet Studio Full mode, the RADIA Measurement Adapter evaluates the current managed magnet model at explicit measurement coordinates and can run a bounded one-parameter profile over `gap_mm`, `br_t`, or `z_offset_mm`. The best finite-grid result is not presented as a global optimum or posterior distribution.

The same mathematical definitions are exposed through `scripts/physical_lab_digital_twin_cli.py`. See [`docs/DIGITAL_TWIN_CORE.md`](docs/DIGITAL_TWIN_CORE.md).

## Optional Local AI Assistant

Physical Lab can use a **local-only, read-only explanation layer** through OpenPenguin/Ollama-compatible localhost services. It receives a bounded structured snapshot and can explain parameters, units, assumptions, diagnostics and possible experiments. It cannot modify Lab parameters, download models, execute model-generated code or contact a cloud endpoint. The scientific workbench remains fully functional without a local model.

## Validation and CI

### Deterministic source validation

Source Integrity validates syntax, manifests, release-version coherence and committed deterministic reference snapshots. Current reference evidence includes numerical-error behavior, oscillator integration, random-walk MSD, exact 2-D Ising critical temperature, ideal-undulator resonance, the Measurement Digital Twin core, the accelerator resonance benchmark, the v0.8 Engineering Design Workflow, and the v0.8.1 five-profile model-engineering layer.

`docs/model-engineering-reference-validation.json` and `scripts/model_engineering_reference_validation.py --check` cover all five non-accelerator scorecards plus convergence-order math, finite-replicate statistics, symmetric relative change and cost/error non-dominated filtering.

### Native Full-mode acceptance

`.github/workflows/full-mode-acceptance.yml` runs separately on clean macOS, builds a pinned RADIA Universal2 revision, verifies `arm64 + x86_64`, evaluates a real native field, exercises the pinned Radiation Platform field-map path, reruns reference cores and uploads JSON evidence.

For the simple planar reference `B0 = 0.05 T`, `lambda_u = 20 mm`, `gamma = 80`, the accelerator benchmark requires field-map-derived frequency and photon energy to agree with closed form within a declared `5e-4` relative-error bound and verifies `E = h f` consistency.

Full-mode CI also creates a deterministic **synthetic measurement-like** perturbed field map, propagates nominal and perturbed fields through Radiation Platform, and records field residuals plus changes in frequency, photon energy and transverse excursion. This proves the software path **field discrepancy → trajectory/radiation discrepancy**; it is not a real magnet measurement.

## Validation philosophy

Physical Lab follows a simple rule: **a simulation result is not automatically a physical result**.

The project distinguishes:

- numerical convergence from physical validity;
- editable engineering screening thresholds from external standards or certification;
- finite seed/chain/ensemble statistics from population failure probabilities or manufacturing yield;
- finite Ising lattices from the thermodynamic limit;
- finite stochastic benchmarks from universal estimator superiority;
- finite-time chaos indicators from global trajectory claims;
- chaotic trajectory divergence from numerical failure;
- analytical Safe-mode references from RADIA Full-mode field solutions;
- synthetic measurement-like CI fixtures from real experiments;
- Pareto non-dominance from proof of global optimality;
- optional runtimes from engines actually consumed by a validated Lab.

See [`docs/VALIDATION.md`](docs/VALIDATION.md).

## What Physical Lab contributes

Physical Lab does **not** claim that every upstream scientific engine was authored here. Its contribution boundary has three layers:

1. **Original physics projects and analysis layers** — seven linked Lab repositories plus Physical Lab's advanced experiment, V&V/UQ, digital-twin and engineering-decision layers.
2. **Research-software engineering** — Tauri/Rust macOS shell, Module/Runtime/Dependency/Task/Integrity centers, isolated environments, Safe/Full policy, source pinning, ABI/runtime discovery, scientific smoke tests, cancellation, workspaces, provenance and reproducibility export.
3. **Third-party scientific engines** — RADIA, Project Chrono/Chrono::Modal and VAMPIRE retain their own authorship/licenses. RADIA is currently consumed by real Labs; Chrono::Modal and VAMPIRE remain optional adapter boundaries rather than advertised active solvers.

See [`docs/ORIGINAL_CONTRIBUTIONS.md`](docs/ORIGINAL_CONTRIBUTIONS.md).

## Build on macOS

```bash
chmod +x RUN_SOURCE_SELF_CHECK.command BUILD_PHYSICAL_LAB.command
./RUN_SOURCE_SELF_CHECK.command
./BUILD_PHYSICAL_LAB.command
```

The release builder targets a Universal2 macOS application (`arm64` + `x86_64`). Release metadata is anchored by `VERSION` and checked against `package.json`, `src-tauri/Cargo.toml`, `src-tauri/tauri.conf.json`, README and CHANGELOG. CI derives artifact names from the canonical version.

A packaged public DMG should still be treated separately from source correctness; Developer ID signing and notarization must be validated on the exact public release artifact.

## Current scope

- Native macOS desktop application built with Tauri 2 / Rust.
- Seven computational-physics Labs.
- Shared Engineering V&V/UQ and Engineering Design Workflow.
- Five domain-specific non-accelerator engineering profiles in v0.8.1.
- RADIA is the only fragile native physics engine currently consumed by a real Lab.
- Chrono::Modal and VAMPIRE remain optional future adapter boundaries.
- The old `radiaition-study` / Radiation Study project is intentionally excluded.

## Documentation

- [`docs/MULTI_LAB_ENGINEERING_V081.md`](docs/MULTI_LAB_ENGINEERING_V081.md) — v0.8.1 model-specific engineering profiles.
- [`docs/ENGINEERING_WORKFLOW_V080.md`](docs/ENGINEERING_WORKFLOW_V080.md) — shared requirement → design → robustness → measurement → decision workflow.
- [`docs/ENGINEERING_SIMULATION.md`](docs/ENGINEERING_SIMULATION.md) — V&V/UQ terminology and engineering-screening layer.
- [`docs/ORIGINAL_CONTRIBUTIONS.md`](docs/ORIGINAL_CONTRIBUTIONS.md) — authorship and integration boundary.
- [`docs/VALIDATION.md`](docs/VALIDATION.md) — scientific/numerical validation policy.
- [`docs/RESEARCH_NOTE_RADIATION.md`](docs/RESEARCH_NOTE_RADIATION.md) — accelerator-physics validation protocol.
- [`docs/RESEARCH_WORKSPACE.md`](docs/RESEARCH_WORKSPACE.md) — workspace/data/reproducibility architecture.
- [`docs/RADIA_RADIATION_TOLERANCE_PROPAGATION.md`](docs/RADIA_RADIATION_TOLERANCE_PROPAGATION.md) — field → trajectory → radiation tolerance propagation.
- [`docs/ACCELERATOR_REFERENCE_BENCHMARK.md`](docs/ACCELERATOR_REFERENCE_BENCHMARK.md) — analytic accelerator reference benchmark.
- [`docs/DIGITAL_TWIN_CORE.md`](docs/DIGITAL_TWIN_CORE.md) — measurement digital-twin definitions.
- [`docs/DEPENDENCY_AUDIT.md`](docs/DEPENDENCY_AUDIT.md) — dependency/runtime policy.

## License

Physical Lab source is MIT-licensed. Linked or downloaded third-party projects retain their own licenses and attribution requirements.
