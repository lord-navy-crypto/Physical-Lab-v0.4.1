# Original Contributions and Third-Party Boundaries

Physical Lab is intentionally explicit about authorship. It is a research-software project that orchestrates user-authored computational-physics Labs and external scientific engines without relabeling upstream work as original code.

## Physical Lab desktop/research-software layer

Original project work in this repository includes the Tauri/Rust desktop shell, module/runtime/dependency/task centers, isolated-environment lifecycle, source-revision pinning, Safe/Full engine policy, RADIA ABI/runtime discovery, per-Lab compatibility checks, scientific smoke-test orchestration, project workspaces, measurement provenance, statistical/result validation, run snapshots/comparison, campaign metadata, pipeline contracts, cancellation and reproducibility export.

## Physical Lab advanced experiment layer

The bundled advanced layer augments managed copies of the seven Lab projects while leaving their upstream entrypoints/solver ownership intact. It provides research-oriented workflows such as numerical reliability atlases, Ising finite-size/Binder analysis, random-walk scaling and QMC comparison, Lyapunov/stability analysis, oscillator method/error/energy diagnostics, RADIA engineering/tolerance ensembles and radiation reference/sensitivity analysis.

## User-authored Lab repositories

Physical Lab downloads seven separate computational-physics repositories maintained under the same GitHub account. Their solver code remains in those repositories rather than being duplicated into this desktop repository. `modules.json` pins exact revisions so a Physical Lab release refers to a reproducible source state.

## Third-party engines

- **RADIA**: external magnetic-field engine. Physical Lab does not claim authorship. Full mode in RADIA Magnet Studio and Radiation Platform consumes it after ABI/import validation.
- **FFTW**: external numerical library used in the RADIA build workflow.
- **Project Chrono / Chrono::Modal**: external engine/SDK. Detectable/buildable, but not currently consumed by a validated Lab adapter.
- **VAMPIRE**: external atomistic magnetic simulator. Detectable/buildable on the supported platform, but not currently consumed by a validated Lab adapter.

Third-party projects retain their own licenses. The builder repositories are compatibility/build helpers, not forks claiming ownership of the scientific engines.

## Why the boundary matters

The goal is reproducibility and interoperability, not a larger feature count. An engine appears as a real Lab dependency only when a tested adapter consumes it and the resulting physics can be validated.
