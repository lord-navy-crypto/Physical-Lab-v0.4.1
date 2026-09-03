# Physical Lab v0.1.2 Dependency Audit

## Policy

Physical Lab separates dependency management into three layers:

1. **Per-Lab Python environment** — every physics Lab receives its own `.venv`.
2. **Native runtime / physics engine** — RADIA, Chrono::Modal, and VAMPIRE are managed separately from Python packages.
3. **Apple build toolchain** — Xcode Command Line Tools and selected build utilities are treated as system prerequisites, not Python packages.

After Python packages are installed, Physical Lab runs `pip check`, imports the critical packages for that Lab, and writes a `physical-lab-lock.txt` snapshot using `pip freeze --all`.

## Lab dependency matrix

| Lab | Python | Main runtime packages | External engine |
| --- | --- | --- | --- |
| Numerical Error Analysis | >=3.10 | NumPy, mpmath, pandas, Plotly, Streamlit | None |
| Ising Monte Carlo | >=3.10 | NumPy, SciPy, pandas, Plotly, Streamlit | None |
| Random Walk & Monte Carlo | >=3.11 | NumPy, SciPy, pandas, Matplotlib, Streamlit | None |
| Nonlinear Dynamics & Chaos | >=3.10 | NumPy, SciPy, mpmath, pandas, Plotly, Streamlit | None |
| Oscillation & Integration | >=3.10 | NumPy, SciPy, pandas, Plotly, Streamlit | None |
| RADIA Magnet Studio | >=3.10 | NumPy, pandas, Streamlit, Plotly, h5py, Matplotlib | RADIA (Full mode only; Safe analytical fallback) |
| Radiation Platform | >=3.10 | NumPy 2+, SciPy, pandas, Matplotlib, Streamlit, Plotly, h5py | RADIA (Full mode only; Safe analytical fallback) |

### Runtime-only correction

`Random_Walk_Monte_Carlo_Studio/requirements.txt` currently includes `pytest`, while its `pyproject.toml` does not list pytest as an application dependency. Physical Lab filters `pytest` out of the runtime installation and retains it only as a development/test concern.

## Native runtime matrix

### RADIA Universal2

Status: **fragile Full-mode engine for two accelerator-physics Labs**. Safe mode deliberately avoids RADIA and stays usable when the native extension is unavailable.

Physical Lab does not accept mere file presence as proof of compatibility. It launches the consuming Lab's venv and requires:

- `import radia`
- a small `ObjRecMag` smoke test

If the test fails, the RADIA Universal2 builder is rerun with the Lab venv's base CPython executable so the extension is compiled for the same Python ABI.

Builder prerequisites include Apple Xcode Command Line Tools, clang, make, git, curl, `lipo`, and related macOS utilities. FFTW is handled by the RADIA builder itself.

### Chrono::Modal

Status: **optional / not yet consumed by an existing Lab**.

Chrono::Modal should not be installed automatically when opening Oscillation or Chaos until there is a real provider/interchange path. Its builder requires Xcode Command Line Tools and CMake. Chrono core uses Eigen; Chrono::Modal additionally uses Spectra. The existing builder owns those source/build details.

### VAMPIRE

Status: **optional / not yet consumed by an existing Lab**.

The current builder is Apple-Silicon-only. Physical Lab therefore marks the runtime unsupported on Intel instead of attempting a build that cannot succeed. It should become a dependency only after an Atomistic Magnetism Lab or adapter actually consumes its executable/output.

## What is intentionally NOT globally installed

- NumPy / SciPy / pandas / Streamlit: per-Lab, because version ranges differ.
- mpmath: only Numerical Methods and Nonlinear Chaos need it.
- h5py: only RADIA-oriented applications need it.
- Matplotlib: Random Walk and RADIA-oriented applications need it; several other Labs do not.
- Chrono::Modal and VAMPIRE: optional engines, not current hard dependencies.

## Remaining production hardening

1. **Pin module source refs** to release tags or exact commits instead of `main` for a public Physical Lab release.
2. **Managed CPython**: bundle or securely download a pinned Physical-Lab-owned Python runtime (3.12 is a good common target) so end users do not need their own Python installation.
3. **Wheel cache / wheelhouse**: optionally pre-download architecture-compatible wheels for the core Labs to reduce first-run network dependency.
4. **Portable CMake**: package or on-demand-download an official, pinned CMake distribution for Chrono::Modal so Homebrew/Conda is not required.
5. **Bundle Physical Lab's own adapter/installer scripts**, while continuing to fetch large third-party engine sources from pinned upstream revisions with checksums/commit verification and preserved license notices.


## Existing-runtime reuse (v0.1.2)

Physical Lab prefers verified existing installations before rebuilding:

- RADIA: checks `RADIA_PYTHONPATH`, `RADIA_DEST`, `~/Desktop/Radia-master/cpp/gcc`, and other common local prefixes; it still requires an actual `import radia` + `ObjRecMag` smoke test in the Lab venv.
- Chrono::Modal: checks a Physical Lab build plus common existing builder `release/` folders and optional `PHYSICAL_LAB_CHRONO_SDK` / `CHRONO_MODAL_SDK` paths.
- VAMPIRE: reuses the builder's standard `~/.local/vampire-apple-silicon` installation.

A detected file is not treated as healthy merely because it exists; where a runtime offers an executable/import verification route, Physical Lab verifies it before marking the runtime Ready.


## Local runtime reuse policy (v0.1.3)

PyChrono and Chrono::Modal are tracked separately. A prebuilt PyChrono Conda environment can be used immediately for Python-accessible Chrono features without requiring a CMake rebuild. Chrono::Modal remains an optional C++ SDK and is only considered ready when its SDK/package/provider output is found.

For RADIA, Physical Lab first inspects the CPython ABI tag in an existing extension (for example `radia.cpython-314-darwin.so`) and attempts to select the matching Python minor. A rebuild is only requested when the actual Lab interpreter cannot import and smoke-test that extension.


## v0.1.7 delivery policy

Dependency knowledge is now part of the application UI. Users do not need to inspect repository READMEs to discover prerequisites. The app either manages a dependency, launches an integrated builder, or exposes a single official-source action.


## Fragile-dependency definition

Physical Lab does **not** treat ordinary scientific Python packages as fragile dependencies. NumPy, SciPy, Matplotlib, pandas, Plotly, Streamlit, mpmath and h5py remain normal per-Lab packages and can be used in Safe mode. The Safe/Full split is reserved for external native engines with meaningful ABI, architecture, SDK or compiler risk (currently RADIA; PyChrono/Chrono::Modal/VAMPIRE remain optional until a real Lab adapter consumes them).

## Module source pinning (v0.5.0)

`modules.json` now records an exact Git commit revision for every Lab/runtime source. Physical Lab downloads the pinned codeload archive and writes `physical-lab-source.json` into the managed source tree. `branch` remains human-readable metadata/fallback only. Updating a module revision is therefore an explicit Physical Lab release decision rather than an implicit change whenever upstream `main` moves.
