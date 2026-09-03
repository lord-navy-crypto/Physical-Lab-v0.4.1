# Physical Lab v0.5.0 — Reproducible Computational Physics for macOS

**Physical Lab is a native macOS research workbench that turns seven computational-physics projects into one reproducible workflow: model → run → validate → compare → export.**

It combines numerical-error analysis, Monte Carlo/statistical physics, nonlinear dynamics, oscillation/integration, and a RADIA-backed **magnet → electron trajectory → radiation** workflow. Physical Lab adds the research-software layer around those solvers: isolated environments, pinned source revisions, ABI-aware native-engine checks, Safe/Full execution, measurement provenance, scientific smoke tests, run comparison, uncertainty analysis, and reproducibility exports.

## 30-second overview

| Question | Physical Lab answer |
|---|---|
| What physics does it cover? | Numerical error, Ising/Monte Carlo, random walk/QMC, chaos/Lyapunov analysis, oscillators/integration, RADIA magnetics, undulator radiation |
| What is the representative deep workflow? | **RADIA Magnet Studio → realized magnetic field → electron trajectory → Radiation Platform → analytic/reference comparison** |
| How is correctness treated? | Analytic/reference comparisons, bounded scientific smoke tests, uncertainty metrics, explicit model limitations, Safe/Full separation |
| How is software reliability handled? | Per-Lab `.venv`, PEP 440 compatibility checks, `pip check`, import tests, CPython ABI checks, pinned GitHub revisions, cancellable tasks |
| Can experiment data enter the platform? | Yes. CSV/TSV/JSON/HDF5 provenance plus bounded Arduino-style serial measurement capture |
| Can results be reproduced? | Projects preserve parameters, source revision, Python/package state, measurements, runs and exportable provenance |

## Representative research path: accelerator physics

Physical Lab's clearest end-to-end example is the accelerator-physics path:

```text
Undulator / magnet geometry
        ↓
RADIA Magnet Studio (Full mode)
        ↓
realized B(x,y,z), harmonics, field integrals, manufacturing-error ensemble
        ↓
electron trajectory / phase behavior
        ↓
Radiation Platform
        ↓
resonance / spectrum-oriented analysis
        ↓
analytic reference + measured-field comparison
```

Safe mode keeps a clearly labeled analytical ideal-undulator fallback available when RADIA is unavailable; it is not presented as a replacement for 3-D magnetic-field solving.

## What I built in Physical Lab

Physical Lab is **not a claim that every upstream physics engine was authored here**. The project separates three contribution layers:

1. **Original physics projects and analysis layers** — the seven linked Lab repositories and the Physical Lab advanced experiment suite, including numerical reliability studies, finite-size/statistical diagnostics, QMC comparisons, Lyapunov/stability analysis, integration/error diagnostics, RADIA tolerance ensembles, and radiation sensitivity/reference workflows.
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

All module downloads are now pinned to explicit Git commit revisions in `src-tauri/resources/modules.json`; `physical-lab-source.json` records the revision actually requested for each managed checkout.

## v0.5.0 research layer

### Project Workspace

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

## Validation philosophy

Physical Lab follows a simple rule: **a simulation result is not automatically a physical result**.

The project therefore distinguishes:

- numerical convergence from physical validity;
- finite-time chaos indicators from global claims;
- finite QMC comparisons from universal superiority claims;
- remanent induction from solved undulator field amplitude;
- analytical Safe-mode references from RADIA Full-mode field solutions;
- optional detected runtimes from engines actually consumed by a Lab.

See [`docs/VALIDATION.md`](docs/VALIDATION.md) and [`docs/RESEARCH_NOTE_RADIATION.md`](docs/RESEARCH_NOTE_RADIATION.md).

## Build on macOS

```bash
chmod +x RUN_SOURCE_SELF_CHECK.command BUILD_PHYSICAL_LAB.command
./RUN_SOURCE_SELF_CHECK.command
./BUILD_PHYSICAL_LAB.command
```

The release builder targets a Universal2 macOS application (`arm64` + `x86_64`). A packaged public DMG should be treated separately from source correctness; signing/notarization must be validated on the exact release artifact.

## Source integrity CI

`docs/source-integrity.example.yml` checks the repository structure, JSON manifests, Python syntax, JavaScript syntax and the project's source self-check on every push/PR. This does **not** substitute for real-macOS runtime acceptance tests of RADIA or hardware/serial paths.

## Current scope

- macOS desktop application built with Tauri 2 / Rust.
- Seven current computational-physics Labs.
- RADIA is the only fragile native physics engine currently consumed by a real Lab.
- Chrono::Modal and VAMPIRE remain optional future adapter boundaries; they are not part of the project's primary external description until a validated Lab consumes them.
- The old `radiaition-study` / Radiation Study project is intentionally excluded.

## Documentation

- [`docs/ORIGINAL_CONTRIBUTIONS.md`](docs/ORIGINAL_CONTRIBUTIONS.md) — authorship and integration boundary.
- [`docs/VALIDATION.md`](docs/VALIDATION.md) — scientific/numerical validation policy.
- [`docs/RESEARCH_NOTE_RADIATION.md`](docs/RESEARCH_NOTE_RADIATION.md) — reproducible accelerator-physics validation protocol.
- [`docs/RESEARCH_WORKSPACE.md`](docs/RESEARCH_WORKSPACE.md) — v0.5 workspace/data/reproducibility architecture.
- [`docs/DEPENDENCY_AUDIT.md`](docs/DEPENDENCY_AUDIT.md) — dependency/runtime policy.

## License

Physical Lab source is MIT-licensed. Linked or downloaded third-party projects retain their own licenses and attribution requirements.
