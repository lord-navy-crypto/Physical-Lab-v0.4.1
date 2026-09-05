# Physical Lab Requirements & Traceability Layer v1

## Purpose

Physical Lab now carries engineering evidence through simulation/measurement, credibility review, decisions, operations, quality/reliability, and risk/economic context. Requirements & Traceability Layer v1 adds the missing systems-engineering structure that connects those records to explicit requirements.

The intended chain becomes:

`Stakeholder / Engineering Requirement → Verification Plan → Project Evidence + Engineering Records → Human Review → Decisions / Follow-up Work`

This layer does not replace domain verification or validation. It organizes what requirement is being addressed, where it came from, how verification is planned, and which current Project records support review.

## Public systems-engineering basis

### NASA Systems Engineering Handbook

NASA's Systems Engineering Handbook includes guidance on writing requirements, requirements validation, requirements verification matrices, validation requirements matrices, and bidirectional requirements flowdown.

- Handbook appendix: https://www.nasa.gov/reference/system-engineering-handbook-appendix/

The handbook's Requirements Verification Matrix guidance states that requirements should have unique identifiers, definitive source information, and an identified verification approach. The V&V-plan guidance also describes system-requirements flowdown and bidirectional traceability.

NASA software-engineering requirements guidance likewise describes maintaining bidirectional traceability between software requirements and higher-level requirements, managing requirement changes, and using verification matrices to reveal inconsistencies.

- Requirements validation guidance: https://swehb.nasa.gov/spaces/7150/pages/16449673/SWE-055+-+Requirements+Validation
- NPR 7150.2 traceability material: https://nodis3.gsfc.nasa.gov/displayAll.cfm?Internal_ID=N_PR_7150_0002_&page_name=all

Physical Lab uses these public sources as terminology and process-design context only. It does **not** claim NASA process compliance, NASA certification, NASA endorsement, or equivalence to an official NASA requirements-management system.

### ABET systems-engineering context

ABET's 2025–2026 Systems and Similarly Named Engineering Program Criteria include requirements engineering alongside decision analysis, risk analysis, trade-off analysis, optimization, modeling/simulation, and sensitivity analysis.

- Criteria: https://www.abet.org/accreditation/accreditation-criteria/criteria-for-accrediting-engineering-programs-2025-2026/

Physical Lab uses this only to support the engineering rationale for connecting requirements to decision, risk, and modeling evidence. It does **not** claim ABET accreditation or compliance.

## Requirement record v1

Each requirement stores:

- deterministic internal `requirement_id`;
- human-readable unique `requirement_key`, e.g. `SYS-001`;
- requirement statement;
- source;
- engineering level / allocation label;
- zero or more parent requirement IDs;
- planned verification method;
- planned verification criteria;
- explicit raw Project evidence references;
- optional engineering-record links;
- rationale;
- intended use;
- registration-time fingerprints.

## Verification-planning vocabulary

v1 supports these planned verification-method labels:

- `analysis`;
- `inspection`;
- `demonstration`;
- `test`;
- `other`.

A method label is planning metadata. It does not mean that the verification activity was performed or passed.

A requirement can be registered before its verification plan is complete. In that case it remains `UNPLANNED` rather than being silently forced into a completed state.

## Raw evidence references

Requirements reuse the same explicit Project evidence vocabulary already used by Claims and Cross-Checks:

- experiment;
- job;
- result;
- measurement;
- calibration.

At registration, Physical Lab snapshots each referenced evidence fingerprint. Later evaluation compares the current Project record with that snapshot.

## Engineering-record links

Requirements can also link to eight higher-level engineering record types:

- Claim;
- Cross-Check;
- Engineering Decision Study;
- Operations Plan;
- Quality Study;
- Reliability Event Study;
- Risk Study;
- Engineering Economics Study.

Each linked record is resolved through its own Project API and deterministic fingerprint at registration time. A free-text identifier that cannot be resolved is rejected rather than treated as valid traceability.

This is how Physical Lab turns the earlier engineering layers into one system-level evidence chain.

## Requirement flowdown

A requirement may reference previously registered parent requirements.

The child snapshots the parent's deterministic fingerprint. Traceability Matrix v1 also reconstructs child counts from parent links, providing bidirectional matrix visibility:

- child → parent through stored `parent_requirement_ids`;
- parent → children through the generated matrix.

Top-level requirements are allowed to have zero parents. A zero-parent requirement is not automatically labeled an orphan because system/stakeholder-level requirements may legitimately be roots.

## Review states

v1 deliberately avoids `VERIFIED` and `VALIDATED` states.

The available states are:

### `UNPLANNED`

The planned verification method or criteria are not fully declared.

### `EVIDENCE_MISSING`

The requirement has no explicit raw Project evidence, or one or more registered evidence references no longer resolve.

### `LINK_MISSING`

A parent requirement or linked engineering record no longer resolves.

### `STALE`

A registered evidence, parent requirement, or engineering-record fingerprint changed after the requirement was registered.

### `READY_FOR_REVIEW`

The verification method and criteria are declared, raw evidence is explicitly linked, and all registered evidence/traceability fingerprints are current.

`READY_FOR_REVIEW` means only that the evidence package and planning metadata are ready for human/domain review. It does **not** mean:

- verified;
- validated;
- compliant;
- accepted;
- safe;
- certified.

## Traceability Matrix v1

The generated matrix includes per requirement:

- requirement key / internal ID;
- statement;
- source;
- level;
- review state;
- planned verification method;
- parent count;
- child count;
- raw evidence-reference count;
- engineering-link count;
- requirement fingerprint;
- evaluation fingerprint.

The matrix also summarizes counts by review state.

There is no aggregate compliance score or completion percentage that hides individual requirement evidence.

## Change/freshness semantics

Physical Lab treats engineering evidence as mutable over a Project lifecycle.

Examples:

- a result file is regenerated;
- a measurement is replaced;
- an Operations Plan changes capacity or task assumptions;
- a Risk Study changes probability/consequence assumptions;
- a Decision Study changes its declared alternatives or metrics.

If a requirement was registered against an earlier fingerprint, its state becomes `STALE`. Physical Lab does not silently transfer the earlier review readiness to the new record.

## Relation to the other engineering layers

Requirements & Traceability is the structural layer that closes the loop among the existing capabilities:

- **Physics / Measurement** provides model and experimental outputs;
- **Evidence Center** tracks provenance, freshness, claims and cross-checks;
- **Engineering Decisions** compares explicit alternatives and constraints;
- **Operations** models execution resources and queues;
- **Quality & Reliability** summarizes variation and observed event evidence;
- **Risk & Economics** adds explicit uncertainty consequences and time-valued economic assumptions;
- **Requirements** records what the system is expected to satisfy and links those engineering records into a reviewable chain.

This is the key Systems Engineering connection: engineering analysis is organized around traceable requirements rather than accumulating as disconnected plots and reports.

## v1 boundary

Requirements & Traceability Layer v1 is a planning, evidence-readiness, and traceability system. It does not perform official verification, validation, compliance determination, acceptance, safety approval, accreditation, standards certification, or product certification.
