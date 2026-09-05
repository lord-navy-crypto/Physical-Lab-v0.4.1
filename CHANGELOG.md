# Changelog

All notable Physical Lab changes are recorded here. Version numbers follow SemVer (`MAJOR.MINOR.PATCH`).

## [Unreleased]

### Added — Research Model Builder MVP
- Added a native **Model Builder** creation surface for trusted local Python research models without turning the Builder into an eleventh built-in physics Lab.
- Added static AST inspection for top-level functions, candidate parameters/outputs, imports, source SHA-256 and execution-risk warnings; static analysis does not import or execute the selected source.
- Added human-reviewed `physical-lab-model-spec-v1` metadata with explicit labels, units, controls, defaults and user-confirmed slider ranges.
- Added wrapper-not-rewrite generation of `original_model.py`, `adapter.py`, `model.json`, `ui.json`, `tests.json` and `provenance.json` with deterministic fingerprints.
- Added deterministic ModelSpec rendering for number, slider, toggle, dropdown and text controls plus scalar, numeric-array, automatic x-y and structured-JSON preview output.
- Added explicit trusted local Preview and original↔adapter equivalence checks with timeout/output bounds; adapter equivalence compares output shape/type signatures and numeric paths/values.
- Added canonical `.physlab` Project model storage under `models/<bundle-id>/` plus `models/index.json`; legacy workspaces must be migrated before Builder bundles can be registered.
- Added deterministic and wiring validations proving Analyze/Generate do not execute student source and that execution remains an explicit local action.

### Model Builder boundary
Research Model Builder automates the interface around a student model, not the scientific judgment inside it. It does not silently rewrite source equations, infer authoritative units/ranges, establish scientific correctness, provide a security sandbox for arbitrary untrusted Internet code, or establish experimental validation, safety, compliance or certification. Public/server arbitrary-Python execution, publishing, model-library/fork services and browser/WASM execution remain deferred.

### Restored — first-class bundled scientific Labs
- Restored **Kerr Black Hole Geodesics**, **Sun–Jupiter–Saturn Dynamics**, and **Multilayer Honeycomb Lattice** as top-level launcher Labs instead of hiding them under nonlinear-chaos / oscillation profiles.
- The three Labs reuse the already strengthened solver, workflow, UI, verification and Model Refinement implementations shipped inside Physical Lab; no scientific equations were rewritten for this restoration.
- Added a bundled-Lab installation path that creates an isolated per-Lab Python environment and launcher wrapper without downloading or maintaining a second solver repository.
- Added a regression contract requiring **10 Labs + 3 runtime/builders** so these model families cannot silently disappear from the catalog again.

### Boundary
This restoration changes product identity, navigation and environment preparation. Existing numerical/model validity boundaries remain unchanged; first-class visibility does not imply experimental validation, calibrated material properties, astrophysical truth, safety approval or certification.

## [0.10.0] - 2026-09-05

### Added — Evidence-First Engineering Systems
- **Credibility Passport + Evidence Graph** with explicit PRESENT / PARTIAL / MISSING factors and no aggregate credibility score.
- **Claim-to-Evidence Matrix** and evidence freshness states, without machine truth/proof verdicts.
- **Cross-Checks + Evidence Snapshots/Diff** for declared method/source corroboration and review-state change detection.
- **Engineering Decision Layer** with explicit constraints, feasibility, Pareto non-dominance and human decision rationale.
- **Operations Layer** with finite resource capacity, task precedence, queue wait, utilization, makespan and transparent dispatch-policy comparison.
- **Quality & Reliability Layer** with descriptive variation, pooled replicate repeatability, factor contrasts, specification context and observed reliability-event/exposure evidence.
- **Risk & Engineering Economics Layer** with user-declared probabilities/consequences and explicit signed cash-flow present-worth arithmetic.
- **Requirements & Verification Planning** with normative `shall` requirements, source/upstream trace identifiers, test/analysis/inspection/demonstration methods, success criteria, evidence freshness and human review notes.
- Shared nine-tab Evidence Center using the same canonical `.physlab` Project state across all engineering-review layers.

### Changed — Project / desktop architecture
- Unified new desktop projects on canonical `projects/*.physlab` storage.
- Retired compatibility workspace-alias creation while preserving genuine legacy workspace discovery/bridge behavior.
- Moved Rust project read, analysis, write, campaign, measurement, serial-capture and reproducibility-export paths to direct canonical/legacy resolvers rather than symlink aliases.
- Separated non-project desktop runtime support from frozen `research_legacy_impl.rs`; the legacy implementation remains a regression/compatibility fixture rather than an active runtime module.

### Release hardening
- Added `scripts/v010_release_readiness_validation.py` and `docs/V010_RELEASE_READINESS.md`.
- README now describes the actual Evidence-First Engineering Systems architecture instead of only the v0.9 campaign milestone.
- Self-check now requires all Decision / Operations / Quality & Reliability / Risk & Economics / Requirements & Verification core and UI modules, Tauri resources, and Evidence Center tabs.
- The release-hardening branch intentionally remains version `0.9.0`; version metadata advances only in a dedicated release PR after all contracts are green.

### Scientific / professional boundary
These additions organize engineering evidence, planning, trade studies and human review. They do not establish scientific truth, experimental validation of every model, process capability, field reliability, calibrated risk, financial advice, formal product verification/validation, qualification, acceptance, safety approval, standards compliance, NASA endorsement, ABET accreditation, or certification.

## [0.9.0] - 2026-09-04

### Added
- Automated engineering campaigns for all five non-accelerator Labs, integrated before the existing Engineering V&V/UQ → Engineering Design Workflow → model-specific scorecard chain.
- Compact and Standard campaign presets with explicit configuration, case records, canonical engineering metrics, deterministic SHA-256 campaign fingerprints, scientific boundary notes, and JSON export.
- Numerical Error accuracy/cost refinement across Taylor orders plus an independent centered finite-difference convergence-order check.
- Ising periodic 2-D multi-chain Metropolis campaign with classical R-hat, autocorrelation-based effective sample size, equilibration-drift screening, and an exact periodic 4×4 zero-field checkpoint obtained by enumerating all `2^16` states.
- Random Walk independent-seed campaign for MSD scaling, diffusion-scale estimator error, and finite-replicate coefficient of variation.
- Nonlinear Dynamics driven-Duffing timestep refinement, finite Poincaré-response indicator, tangent-dynamics finite-time Lyapunov estimates with renormalization, and energy/work-balance closure.
- Oscillation RK4 refinement against a closed-form underdamped oscillator reference, including frequency, amplitude, phase, energy/work-balance and timestep-response metrics.
- `src-tauri/resources/ui/physical_lab_model_campaigns.py`, `scripts/model_campaign_reference_validation.py`, and `docs/AUTOMATED_MODEL_CAMPAIGNS_V090.md`.

### Changed
- The engineering UI now renders the automated campaign before V&V/UQ so newly generated canonical metrics are discoverable by the same model-specific scorecards in the same Lab workflow.
- Tauri packaging now includes the model-campaign module.
- Release metadata advanced coherently to `0.9.0` across `VERSION`, npm, Cargo, Tauri, README and CHANGELOG.

### Validation
- Source Integrity compiles the new campaign module and deterministic validator.
- CI executes every Compact campaign and requires all five existing model-specific engineering scorecards to PASS with 100% metric completeness.
- CI also exercises the Standard nonlinear-chaos campaign because finite-time chaotic diagnostics can be especially sensitive to an inappropriate observation window.
- Additional invariants verify numerical refinement direction/cost, the Ising exact-reference checkpoint, random-walk MSD exponent recovery, positive finite-time Duffing sensitivity, oscillator analytic-reference refinement, campaign fingerprints, and canonical session-metric export.

### Scientific boundary
v0.9.0 automates computational verification and finite numerical/stochastic engineering screening. Campaign PASS does not establish experimental validation, product certification, manufacturing yield, population failure probability, global chaos classification, or universal estimator superiority. Ising R-hat/ESS remain finite-sample diagnostics; chaos requirements target finite-window indicators rather than raw long-time coordinate agreement; runtime is descriptive and machine-dependent; and real physical apparatus still requires measurement, calibration and model-form validation.

## [0.8.1] - 2026-09-04

### Added
- Model-specific engineering profiles for all five non-accelerator Labs, layered on top of the shared Engineering V&V/UQ and v0.8 design workflow rather than adding another disconnected Lab.
- A domain scorecard with editable PASS / REVIEW / FAIL screening targets; missing metrics remain REVIEW instead of silently passing.
- Shared observed-convergence-order, computational cost ↔ error non-dominated frontier, and finite replicate/seed stability tools.
- Numerical Error engineering quantities for normalized error, scan pass fraction, convergence order, and accuracy-versus-cost tradeoffs.
- Ising engineering quantities for multi-chain R-hat, effective sample size, exact/reference discrepancy, equilibration drift, and sampling/work quality.
- Random Walk / Monte Carlo engineering quantities for diffusion/MSD scaling, estimator error, finite replicate stability, and cost-versus-precision comparisons.
- Nonlinear Dynamics engineering quantities for timestep sensitivity of finite-window indicators, Lyapunov-statistic replicate spread, and energy/work-balance error. Long-time pointwise trajectory agreement is deliberately not used as a generic chaos requirement.
- Oscillation / Integration engineering quantities for frequency, amplitude, phase, energy/work balance, and timestep sensitivity.
- `src-tauri/resources/ui/physical_lab_model_engineering.py`, `docs/MULTI_LAB_ENGINEERING_V081.md`, and a committed deterministic model-engineering reference snapshot.

### Validation
- Source Integrity now compiles the model-specific engineering module, validates `docs/model-engineering-reference-validation.json`, and runs `scripts/model_engineering_reference_validation.py --check`.
- Deterministic reference evidence covers all five scorecards plus convergence-order math, finite-replicate statistics, symmetric relative-change calculation, and cost/error non-dominated filtering.
- The Tauri resource bundle now includes the model-specific engineering module so the same UI is packaged in the macOS application.

### Scientific boundary
v0.8.1 converts existing research diagnostics into explicit engineering decision quantities; it does not turn editable thresholds into standards or certification. Finite seed/chain/replicate summaries are descriptive rather than automatic failure probabilities or confidence claims, finite Ising lattices still require finite-size reasoning, stochastic scaling references depend on the selected model, chaotic long-time coordinate divergence is not itself a solver failure, and real oscillator/apparatus validation still requires measurements and model-form assessment.

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

[0.10.0]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/compare/Physical-Lab-v0.9.0...Physical-Lab-v0.10.0
[0.9.0]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/compare/Physical-Lab-v0.4.1...HEAD
[0.8.1]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/compare/Physical-Lab-v0.4.1...HEAD
[0.8.0]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/compare/Physical-Lab-v0.4.1...HEAD
[0.7.1]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/compare/Physical-Lab-v0.4.1...HEAD
[0.7.0]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/compare/Physical-Lab-v0.4.1...HEAD
[0.5.0]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/releases/tag/Physical-Lab-v0.4.1
