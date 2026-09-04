# Changelog

All notable Physical Lab changes are recorded here. Version numbers follow SemVer (`MAJOR.MINOR.PATCH`).

## [0.8.0] - 2026-09-04

### Added
- Integrated Engineering Design Workflow layered on the existing per-Lab V&V/UQ tools.
- Multi-metric requirement tables with PASS / REVIEW / FAIL screening and explicit uncertainty margins.
- Pareto non-dominated design comparison for explicit minimize/maximize objectives.
- One-at-a-time finite-difference sensitivity ranking.
- Finite-ensemble robust-design summaries with descriptive p05/median/p95 statistics and sample pass fractions.
- Co-registered model ↔ measured-field residual analysis with RMSE, MAE, maximum residual, field-integral difference, and optional uncertainty-normalized residual metrics.
- First-order undulator thermal-expansion / field-temperature coupling into K and resonance photon energy.
- Bounded model-based calibration/control parameter update with no hardware I/O.
- Deterministic resumable batch/HPC planning with stable case fingerprints, chunking, and scheduling-wave estimates.
- `docs/ENGINEERING_WORKFLOW_V080.md` and a committed deterministic engineering-workflow reference snapshot.

### Full-mode engineering validation
- Clean-macOS Full-mode CI now propagates both the nominal synthetic planar field and a deterministic measurement-like perturbed field through the pinned Radiation Platform worker.
- New evidence connects field residuals to changes in fundamental frequency, photon energy and maximum transverse excursion.
- The measurement-like CI fixture is explicitly synthetic and is not presented as experimental magnet validation.

### Changed
- Engineering V&V/UQ UI now exposes the integrated design-workflow tabs directly after the existing error-budget, requirement-margin and simulation↔measurement tools.
- The Tauri bundle now includes the engineering workflow module.
- Source Integrity compiles and validates the new engineering core, reference snapshot and measured-field propagation validator.
- Release metadata advanced coherently to `0.8.0`.

### Scientific boundary
v0.8.0 adds engineering structure and executable evidence, not certification. Finite-ensemble pass fractions are not automatically manufacturing yield or probability of failure; Pareto membership is not a global optimum claim; the thermal model is not FEA; and the synthetic measurement-like Full-mode fixture is not a real experimental validation dataset.

## [0.7.1] - 2026-09-04

### Added
- Independent analytic planar-undulator resonance benchmark for the accelerator-physics path.
- Committed reference snapshot for `B0 = 0.05 T`, `lambda_u = 20 mm`, `gamma = 80`.
- Clean-macOS cross-engine comparison of Radiation Platform fundamental frequency and photon energy against the analytic reference.
- Consistency check between reported photon energy and `E = h f`, plus comparison against the solver-reported frequency residual.

### Validation
- Source Integrity now regenerates/checks the accelerator analytic reference snapshot.
- Full-mode Acceptance now requires the synthetic planar field-map result to agree with the analytic resonance within a declared `5e-4` relative-error bound.
- Full-mode evidence now includes a separate `cross-engine-physics-benchmark.json` artifact.

### Scientific boundary
The new benchmark validates one deliberately simple resonance invariant and the associated field-map/unit/runtime path. It does not validate a manufactured undulator, beam distribution, detector, manufacturing yield, or experimental measurement.

## [0.7.0] - 2026-09-04

### Added
- RADIA → regular 3-D field map → electron trajectory → radiation tolerance propagation.
- Cross-engine clean-macOS acceptance through the pinned Radiation Platform field-map interface.
- Finite-ensemble propagated-observable summaries and engineering-bound screening.
- Canonical `VERSION` file and automated release-version consistency validation.

### Changed
- Unified application, Rust crate, Node package, Tauri bundle, README, and Universal2 artifact metadata on `0.7.0`.
- Universal2 CI now derives DMG and checksum names from the application version instead of hard-coding a release number.
- Source self-check and local DMG packager now consume source-driven version metadata.
- README now describes the v0.7.0 cross-engine acceptance boundary explicitly.

### Validation
- Source Integrity validates version consistency, deterministic reference checks, syntax, manifests, and the Physical Lab self-check.
- Full-mode Acceptance validates a pinned native RADIA Universal2 build and a small cross-engine field-map → trajectory/radiation path on clean macOS.
- macOS Universal2 Build verifies that the packaged executable contains both `arm64` and `x86_64` architectures.

### Scientific boundary
The v0.7.0 tolerance pipeline reports finite solver-ensemble behavior. It does not by itself establish manufacturing yield, confidence intervals, detector response, beam emittance/energy-spread effects, or experimental validation.

## [0.5.0] - 2026-09-02

### Added
- Seven-Lab reproducible research workspace.
- Measurement/provenance bridge, isolated Lab environments, scientific smoke tests, run comparison, and reproducibility export.
- Universal2 macOS packaging and public v0.4.1-era release infrastructure migrated toward the research-workbench architecture.

[0.8.0]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/compare/Physical-Lab-v0.4.1...HEAD
[0.7.1]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/compare/Physical-Lab-v0.4.1...HEAD
[0.7.0]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/compare/Physical-Lab-v0.4.1...HEAD
[0.5.0]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/releases/tag/Physical-Lab-v0.4.1
