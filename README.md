# Physical Lab v0.5.0 — Content Quality Upgrade

Physical Lab is a unified macOS desktop shell for the computational-physics projects and scientific runtime/build tools maintained in the `lord-navy-crypto` GitHub account.

## v0.5.0 — Scientific content reinforcement

This release upgrades **experiment content quality** inside the Advanced Experiment Suite. Upstream Lab solvers remain intact; Physical Lab adds stronger research workflows on top.

### Ising Monte Carlo — Finite-size scaling

- New **Finite-size scaling** tab measures χ-peak height versus lattice size.
- Reports an observed γ/ν from a log–log fit and compares it with the 2D Onsager ratio γ/ν = 1.75.
- Tracks finite-size movement of T(χ peak) against the exact Onsager Tc when dimension=2 and h≈0.

### Radiation Platform — Linewidth & harmonic ladder

- New **Linewidth & harmonic ladder** tab builds the ideal odd-harmonic energy ladder E_n = n E_1.
- Shows the finite-N relative-bandwidth estimate ΔE/E ≈ 1/(nN) with absolute linewidths.
- Remains an ideal design reference; Full-mode RADIA/V11 physics is unchanged.

### Oscillation & Integration — PyChrono cross-check

- New **PyChrono cross-check** tab is the first real adapter that consumes a discovered PyChrono runtime.
- Compares the Lab RK4 force-free oscillator against analytic motion and, when available, against `PHYSICAL_LAB_PYCHRONO_PYTHON`.
- PyChrono stays optional: Safe/Full Lab solve paths do not require it.

### All Labs — Content Validation Battery

- Every Lab now exposes a one-click **Content Validation Battery** under the advanced suite.
- Runs short deterministic checks against analytic references (Onsager Tc, undulator γ² scaling, force-free oscillator, power-law fit recovery, conservative energy drift, etc.).
- Exports a JSON report for bug reports and reproducibility notes.

### Product metadata

- App version bumped to **0.5.0** (`package.json`, `Cargo.toml`, `tauri.conf.json`, UI footer).
- Module/dependency notes updated so Oscillation advertises the optional PyChrono adapter accurately.

---

## v0.1 module set

Physics labs:
- Numerical Error Analysis
- Ising Monte Carlo Lab
- Random Walk & Monte Carlo
- Nonlinear Dynamics & Chaos
- Oscillation & Numerical Integration
- RADIA Magnet Studio
- Radiation Platform

Runtime/build tools:
- RADIA Universal2 Runtime installer
- Chrono::Modal Universal2 Builder
- VAMPIRE Apple Silicon Builder

`radiaition-study` is intentionally not included. Sentinel, Openguin and Knowledge Explorer remain separate products.

## How v0.4.1 works

Physical Lab does not duplicate the ten repositories inside its own source tree. Instead, it ships a versioned module manifest and provides a native Module Manager:

1. Choose a lab or runtime inside Physical Lab.
2. Physical Lab downloads that repository from GitHub into its macOS Application Support directory.
3. Every Lab gets an isolated `.venv`. Physical Lab enforces the module's minimum Python version and filters known development-only packages from runtime installation.
4. Streamlit labs run headless on localhost and are displayed inside Physical Lab's own embedded lab view.
5. Runtime/build modules run their existing trusted launcher from inside the app and report task output to Task Center.
6. After package installation, Physical Lab runs `pip check`, imports each critical package, and writes `physical-lab-lock.txt` from `pip freeze --all`.
7. RADIA-dependent Labs verify an actual `import radia` + `ObjRecMag` smoke test inside that Lab venv. If the existing extension is missing or ABI-incompatible, Physical Lab rebuilds RADIA with the same base Python minor version.
8. Runtime Builders perform architecture/system-tool preflight. VAMPIRE is explicitly unavailable on Intel; Chrono::Modal checks for Xcode Command Line Tools and CMake instead of failing halfway through a build.

This keeps the original repositories independent while presenting them to users as one application.


## Local Runtime Reuse

Physical Lab now distinguishes **PyChrono** from the **Chrono::Modal C++ SDK**.

- PyChrono is discovered from common `miniforge3`, `miniconda3`, `anaconda3`, and `mambaforge` `chrono` environments.
- Core PyChrono and optional modules are smoke-tested individually.
- Chrono::Modal remains a separate optional C++ SDK/runtime because a working `pychrono` install does not prove that the Modal SDK/provider exists.
- Python installed from python.org under `/Library/Frameworks/Python.framework/...` is detected even when Physical Lab is launched from Finder.
- RADIA-aware labs prefer the CPython minor encoded in an existing `radia.cpython-XYZ-darwin.so`, so a compatible local RADIA build is reused instead of rebuilt.
- CMake is required only when actually building Chrono::Modal; it is not required merely to use an already-working PyChrono Conda environment.


## Build on macOS

Double-click:

```text
BUILD_PHYSICAL_LAB.command
```

The builder installs both Rust macOS targets and produces a Universal2 `.app` / `.dmg` for Apple Silicon + Intel. The output is placed under:

```text
src-tauri/target/universal-apple-darwin/release/bundle/
```

## v0.1 boundary

The first release is installer-managed rather than fully offline: Python packages and module source are downloaded when first needed. A later release can bundle a pinned Python runtime and a wheelhouse to make the core lab set offline-installable.


## Dependency policy

- **Python scientific packages:** isolated per Lab; never one global environment.
- **Development packages:** excluded when they are not required at runtime (for example `pytest` in Random Walk).
- **RADIA:** fragile external engine used only by Full mode in RADIA Magnet Studio and Radiation Platform. Safe mode remains available without RADIA; Full mode verifies the consuming Lab Python ABI before use.
- **Chrono::Modal:** optional runtime. It is not marked as a dependency of Oscillation/Chaos until a real provider/interchange path exists.
- **VAMPIRE:** optional atomistic-magnetism runtime and currently Apple-Silicon-only. It is not a dependency of the existing Labs.
- **Xcode Command Line Tools:** Apple system prerequisite for native builders; Physical Lab detects it but does not bundle Apple's toolchain.
- **CMake:** required only for Chrono::Modal. The current release detects it in PATH/Homebrew/common Conda locations.
- **Third-party engines:** prefer pinned, checksum/commit-verified on-demand source installation over silently shipping large upstream binaries. User-authored Physical Lab adapter/installer scripts can be bundled in a later offline package.


## Dependency Center

Physical Lab now carries a built-in dependency catalog. Every dependency is classified as one of:

- **Auto-managed** — module-specific Python packages are installed into isolated Lab environments, verified with `pip check` and import smoke tests.
- **Integrated builder** — RADIA, Chrono::Modal and VAMPIRE can be prepared from inside Physical Lab using the existing verified builder repositories.
- **Detect / official source** — Python, PyChrono and CMake are detected first; if missing, Physical Lab provides a single official-source action instead of asking users to search documentation manually.
- **macOS system installer** — missing Xcode Command Line Tools can be requested through the native `xcode-select --install` flow.

The catalog is embedded at `src-tauri/resources/dependencies.json` and shown in the desktop Dependency Center. Runtime readiness is live, not hard-coded to one developer machine.


## Safe / Full engine policy (v0.2.0)

Every physics Lab exposes two launch modes, but **dependency** in this policy means only a fragile external/native engine. Ordinary scientific Python packages such as NumPy, SciPy, Matplotlib, pandas, Plotly, Streamlit, mpmath and h5py are considered normal managed packages and may be used freely in both modes.

- **Safe mode** avoids fragile external engines that are prone to ABI, architecture, SDK or native-build failures.
- **Full mode** enables those engines when the specific Lab genuinely consumes them.
- Labs with no fragile external engine do not maintain a fake duplicate solver: Safe and Full intentionally run the same validated scientific implementation.
- RADIA Magnet Studio Safe mode uses an ideal planar-undulator analytical fallback; Full mode uses RADIA 3-D field solving.
- Radiation Platform Safe mode uses the ideal undulator resonance relation; Full mode uses the RADIA-backed magnet → trajectory → radiation workflow.
- If RADIA preparation fails, installing either RADIA Lab no longer fails as a whole. The Lab is marked **Safe mode ready**, while Full remains unavailable until RADIA passes its ABI/import smoke test.
- PyChrono, Chrono::Modal and VAMPIRE remain discoverable in Dependency Center, but they are not forced into an existing Lab until that Lab has a real adapter that consumes them.

The built-in analytical fallback server is `src-tauri/resources/safe_engine_server.py` and intentionally uses only the Python standard library.

## v0.2.0 maintenance hardening

- Dependency Center now exposes per-dependency red / yellow / green health states.
- Python package discovery scans module virtual environments, python.org Framework installs, Homebrew/PATH interpreters, Conda environments, and known PyChrono environments.
- The catalog checks Python, NumPy, SciPy, pandas, Plotly, Streamlit, Matplotlib, h5py, mpmath, Xcode CLT/toolchain, CMake, FFTW, RADIA, PyChrono, Chrono::Modal, and VAMPIRE.
- Persistent logs are written under Physical Lab's Application Support `logs/` directory. Builder/task output is recorded in `physical-lab.log`; Lab server stdout/stderr is recorded in per-module server log files.
- Task Center can open the persistent log folder and the full Physical Lab data folder.
- Finished task cards can be deleted independently from persistent logs.
- Installed Labs can be deleted from Physical Lab. Deleting a Lab removes its downloaded source and isolated `.venv`.
- Runtime builder downloads can also be removed; externally installed RADIA/Chrono/VAMPIRE runtimes are intentionally left untouched.
- The old `radiaition-study` / Radiation Study repository is hard-excluded from the module catalog and self-check.

## v0.2.0 — Six-model simulation UX enhancement

Physical Lab now applies an embedded simulation UI layer to six primary simulation experiences:

- Numerical Error Analysis
- Ising Monte Carlo
- Random Walk & Monte Carlo
- Nonlinear Dynamics & Chaos
- Oscillation & Numerical Integration
- Unified Radiation Platform

The standalone RADIA Magnet Studio remains available as the Stage-1 magnet tool but is not counted as a separate primary simulation in this UX pass.

### What changes inside the simulations

- wider scientific workspace with a more usable control sidebar;
- responsive control/result columns that wrap instead of squeezing values;
- larger headline metric cards with multiline labels/values;
- compact key-result tables are automatically promoted to responsive result cards;
- one-row scalar summaries become readable KPI grids;
- Plotly charts receive more vertical space, consistent margins, larger hover text, responsive width, and cleaner legends;
- Matplotlib figures receive a larger minimum canvas and constrained layout;
- tabs, expanders, buttons, number inputs, select boxes, and data tables receive more usable spacing;
- model-specific quick presets are available for Numerical, Ising, Random Walk, Chaos, and Oscillation without removing manual control;
- Radiation Safe mode now includes an analytical angle-trend visualization, finite-period linewidth context, and a clearer input → result → model-boundary layout.

The enhancement layer changes presentation and control ergonomics only. It does not replace or silently alter the scientific solver implementation.

## v0.2.0 — Advanced Experiment Suite: Radiation, Ising, Chaos

Physical Lab now injects a research-oriented advanced suite into the managed copies of three priority experiments. The original upstream experiment UI and solver chain remain intact; the advanced suite is appended after the original experiment and is loaded only inside Physical Lab.

### Radiation Platform

- 2D ideal-reference sensitivity atlas over Lorentz factor γ and undulator K.
- Local logarithmic sensitivity map to identify where expensive Full-mode deep analysis is most informative.
- Automatic representative-point selection from an existing scalar scan: minima, maxima, largest local slope, and mid-range reference.
- Explicit user-mapped analytic comparison against an upstream scan. Physical Lab never guesses the scan column units.
- Derived ideal-undulator photon-energy / wavelength reference with clear model-boundary warnings.
- The original field source → device → electron/observer → scalar scan → trajectory → radiation → deep-analysis workflow is unchanged.

### Ising Monte Carlo

- Adaptive coarse → refined temperature scan that concentrates samples around combined susceptibility / specific-heat response.
- Refined estimates of susceptibility-peak and heat-capacity-peak temperatures, with Onsager Tc shown only when the exact 2D zero-field reference is applicable.
- Binder cumulant U4 finite-size scans across user-selected lattice sizes.
- Work-normalized sampler comparison using effective sample size per accumulated work unit.
- Existing autocorrelation, ESS, exact references, finite-size scans, multi-chain diagnostics, and sampler implementations remain available.

### Nonlinear Dynamics & Chaos

- Twin-trajectory initial-condition sensitivity experiment with scaled state-space separation on a logarithmic axis.
- Paired θ1–ω1 phase portraits and conservative-energy drift diagnostics.
- Finite-time Benettin Lyapunov evolution showing local and cumulative exponents instead of only a final scalar.
- A heuristic tail-spread interpretation that avoids claiming a positive finite-time exponent is proof of a global strange attractor.
- Initial-condition flip-time stability atlas with finite-window semantics and the core model's computational safety limit preserved.

### Upgrade architecture

The advanced suite lives in `src-tauri/resources/ui/physical_lab_advanced.py`. On launch, Physical Lab checks its managed checkout of Radiation Platform, Ising, or Chaos and appends one small idempotent hook to the lab entrypoint. The hook imports the bundled advanced suite from Physical Lab's own resource path. This means:

- upstream repository physics code is not rewritten;
- existing managed checkouts gain the upgrade automatically on first launch;
- deleting/re-downloading a module remains safe;
- upstream updates can replace the managed checkout and Physical Lab will re-inject the hook when needed;
- advanced UI renders on every Streamlit rerun while computed results remain cached in session state.


## v0.4.1 — Remaining Lab reinforcement

The Advanced Experiment Suite now covers **all seven physics Labs**. The v0.2.0 Radiation / Ising / Chaos upgrades remain intact, and four additional platforms receive research-oriented capability layers without replacing their upstream physics cores.

### Numerical Error Analysis — Numerical Reliability Observatory

- Reliability-frontier scan comparing range-reduced and raw Taylor evaluation.
- Failure statistics use the existing normalized-error, false-convergence and numerical-reliability diagnostics rather than inventing a new acceptance rule.
- Term-count × input-magnitude heatmaps for normalized error and cancellation amplification.
- Single-point error microscope showing error and cancellation versus fixed Taylor term count.
- Clear distinction between numerical failure and mathematical convergence of the sine Taylor series.

### Random Walk & Monte Carlo — Scaling & Efficiency Suite

- Log-spaced step-count scans recover the empirical mean-radius and MSD scaling exponents.
- Simulation curves are shown against the existing asymptotic mean-radius and exact MSD references.
- Dimension scans expose radial concentration through E[R]/sqrt(E[R²]) and relative radial spread.
- Matched-budget pseudorandom Monte Carlo versus independently scrambled Sobol QMC comparison for the 2-D unit-disk problem.
- QMC uncertainty remains replicate-based; the UI explicitly avoids claiming universal superiority from a finite comparison.

### Oscillation & Numerical Integration — Dynamics Observatory

- Damping × drive-frequency-ratio steady-state response atlas for the linear oscillator.
- Critical damping is shown as a physical reference without replacing transient numerical experiments.
- Cross-method error frontier for Euler, symplectic Euler, RK2 and RK4 against the force-free analytic solution.
- Observed convergence order, finest-grid error and actual time step are reported together.
- Energy-flow microscope separates mechanical-energy change, input work, damping work and the numerical balance residual.

### RADIA Magnet Studio — Magnet Engineering & Tolerance Suite

- Engineering preflight derives device length, nominal block length/count and dimensionless geometry ratios from the requested configuration.
- Target-B0 K is computed only when a target/solved B0 exists; remanent induction Br is never silently substituted for B0.
- Configured manufacturing tolerances are normalized geometrically without pretending they map linearly to field quality.
- The most recent successful full RADIA solve is retained in the advanced audit panel across Streamlit reruns.
- Ideal-vs-error metric deltas are retained when the upstream experiment computed both models.
- Controlled multi-seed manufacturing-error ensemble reruns the actual RADIA build/solve/on-axis analysis and summarizes spread in Bpeak, K, field integrals, harmonics and electron phase error.
- Seed ensembles deliberately skip 2-D/3-D maps to keep the study focused and computationally bounded.

### Injection / compatibility

Physical Lab now injects the advanced hook into all seven managed Lab entrypoints:

- Numerical Error Analysis
- Ising Monte Carlo
- Random Walk & Monte Carlo
- Nonlinear Dynamics & Chaos
- Oscillation & Numerical Integration
- RADIA Magnet Studio
- Radiation Platform

The original upstream UI executes first. Physical Lab's advanced section is appended afterwards and uses the upstream public functions/data already loaded by the Lab. This preserves the original experiment design while allowing Physical Lab to add higher-level research workflows.


## v0.4.1 — Dependency Doctor and action priority

- Dependency Center now classifies every check as Fix now, Auto-managed, Optional/on-demand, or Ready in addition to red/yellow/green health.
- A one-click Dependency Doctor JSON export captures runtime details, resolved locations, versions, module readiness, and per-dependency recommendations for bug reports.
- Re-scan dependencies is available directly inside Dependency Center.
- Optional native engines are not presented as blockers when the current seven Labs do not require them.
