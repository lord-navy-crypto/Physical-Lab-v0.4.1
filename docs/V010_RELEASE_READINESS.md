# Physical Lab v0.10 Release Readiness

## Why a hardening phase is required

Physical Lab's implementation has grown beyond the v0.9.0 campaign milestone. The current product now contains a shared Evidence-First Engineering Systems workflow around the seven physics Labs, including:

1. Credibility Passport
2. Claim-to-Evidence Matrix
3. Cross-Checks
4. Engineering Decision Layer
5. Operations Layer
6. Quality & Reliability Layer
7. Risk & Engineering Economics Layer
8. Requirements & Verification Planning
9. Evidence Snapshots & Diff

The purpose of this hardening phase is to make the release contract match that real architecture before the version is advanced.

## Canonical product chain

```text
Simulation / Measurement
        ↓
Project Kernel + Measurement Evidence
        ↓
Verification / UQ / Evidence Graph
        ↓
Claims + Cross-Checks + Evidence Freshness
        ↓
Engineering Decisions
        ↓
Operations Planning
        ↓
Quality & Reliability Evidence
        ↓
Risk & Engineering Economics
        ↓
Requirements & Verification Planning
        ↓
Human Review + Evidence Snapshot / Diff
```

The chain is deliberately evidence-first rather than score-first. Physical Lab does not compute one aggregate credibility, engineering, safety, quality, or compliance score.

## Release blockers addressed by this phase

### 1. Documentation drift

Before release hardening, the README still centered the v0.9 automated-campaign narrative and did not describe the later Engineering Systems layers.

The v0.10 release must describe the actual product architecture rather than only the last numbered release milestone.

### 2. CHANGELOG drift

The existing CHANGELOG ended at v0.9.0 even though major Project Kernel, Evidence, Decision, Operations, Quality, Risk/Economics and Requirements work had been merged afterward.

The hardening phase adds an `Unreleased` section that records these changes before any version bump.

### 3. Self-check coverage gap

The original `scripts/self_check.py` verified the shared Evidence Center but only required the original Passport / Claims / Cross-Checks / Snapshot surface.

The v0.10 hardening contract requires every later engineering layer to be:

- present in source;
- packaged by Tauri;
- wired into the shared Evidence Center;
- explicitly checked by self-check;
- covered by Source Integrity.

### 4. Storage and compatibility boundary

New projects are canonical `projects/*.physlab` stores.

The compatibility alias layer has been retired. Genuine legacy workspaces may still be discovered or bridged explicitly, but new Project operations must not recreate the old alias mechanism.

### 5. Runtime ownership boundary

`research_legacy_impl.rs` is retained only as a frozen compatibility/regression fixture. It must not be compiled as the active desktop runtime module.

## Release-readiness validation

`scripts/v010_release_readiness_validation.py` enforces:

- source version remains `0.9.0` during hardening;
- all nine Evidence Center tabs are wired;
- Decision, Operations, Quality/Reliability, Risk/Economics and Requirements/Verification core + UI modules are packaged;
- self-check explicitly covers those modules and tabs;
- Source Integrity runs all corresponding deterministic validators;
- temporary integration workflows/scripts are absent;
- workspace alias creation cannot return;
- README and CHANGELOG expose the actual architecture.

## Version-bump rule

The hardening PR must merge while the canonical source version is still `0.9.0`.

Only after:

1. Source Integrity is fully green;
2. self-check is green;
3. the release-readiness contract is green;
4. the final diff contains no temporary migration/integration helpers;
5. documentation matches the implementation;

should a separate release PR update:

- `VERSION`
- `package.json`
- `src-tauri/Cargo.toml`
- `src-tauri/tauri.conf.json`
- README release title
- CHANGELOG release heading

This separates product hardening from release metadata and makes the version transition auditable.

## Scientific and professional boundary

Release readiness means the software packaging, architecture, documentation and deterministic regression contracts are coherent.

It does **not** mean:

- experimental validation of all physical models;
- standards compliance;
- engineering certification;
- product qualification;
- safety approval;
- ABET accreditation;
- NASA compliance or endorsement.

Those claims require separate domain evidence and authority beyond this release process.
