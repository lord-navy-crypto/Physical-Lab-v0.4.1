# Changelog

All notable Physical Lab changes are recorded here. Version numbers follow SemVer (`MAJOR.MINOR.PATCH`).

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

[0.7.0]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/compare/Physical-Lab-v0.4.1...HEAD
[0.5.0]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/releases/tag/Physical-Lab-v0.4.1
