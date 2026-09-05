# Physical Lab Requirements & Verification Planning v1

## Purpose

Physical Lab now connects engineering evidence to explicit requirements planning inside the same canonical `.physlab` Project.

The layer is intentionally conservative. It records:

- normative requirement statements;
- unique requirement identifiers;
- declared source document and source locator;
- declared upstream trace identifiers;
- one planned verification method;
- verification activity;
- explicit success criteria;
- Project evidence references and freshness;
- human evidence-sufficiency / plan-revision review notes.

It does **not** automatically declare a requirement verified, compliant, accepted, qualified, certified, safe, or validated for stakeholder use.

## Engineering rationale

### NASA systems-engineering verification planning

NASA's Systems Engineering Handbook materials distinguish product verification from product validation and describe verification as showing compliance with requirements, commonly through test, analysis, inspection, or demonstration. Validation instead addresses whether the product satisfies its intended purpose in its intended environment.

NASA's Requirements Verification Matrix guidance also says that only normative `shall` requirements should be included in the matrix and that each requirement should have a unique identifier and a definitive source.

Physical Lab adopts this planning vocabulary as methodology context only.

It does not claim NASA compliance, NASA endorsement, qualification, acceptance, certification, or formal verification authority.

### Broader engineering / systems-engineering connection

Requirements engineering closes an important gap in the Evidence-First Engineering chain:

```text
Physics / Measurement
        ↓
Project Evidence
        ↓
Claims / Cross-Checks / Evidence Freshness
        ↓
Engineering Decisions
        ↓
Operations / Quality / Reliability / Risk / Economics
        ↓
Requirements & Verification Planning
```

The layer makes it possible to ask a more complete engineering question:

> What requirement is being addressed, where did it come from, how is it planned to be checked, what evidence supports that review, and is that evidence still current?

This is especially relevant to systems engineering, software/hardware integration, mechanical/electrical test planning, experiment qualification planning, and multidisciplinary design reviews.

### ABET context

Current ABET engineering criteria identify requirements engineering as one of the systems design/analysis topics that may appear in systems-engineering curricula. ABET software-engineering criteria also explicitly include requirements analysis, verification, and validation.

Physical Lab uses these public curriculum criteria only as evidence that the feature maps to recognized engineering practice areas. It does not claim ABET accreditation or institutional endorsement.

## Data model

Schema:

`physical-lab-requirement-verification-plan-v1`

Each requirement stores:

- `requirement_id`
- `statement`
- `normative_keyword = shall`
- `source_document`
- `source_locator`
- `rationale`
- `level`
- `owner`
- `upstream_requirement_ids`
- `verification_method`
- `verification_activity`
- `success_criteria`
- `intended_use`
- explicit Project evidence references
- evidence fingerprint snapshots
- human review history

Allowed verification methods in v1:

- `test`
- `analysis`
- `inspection`
- `demonstration`

## Evidence states

### `READY_FOR_REVIEW`

All explicitly referenced Project evidence still exists and matches its stored fingerprint.

This means only:

> the evidence bundle is available and current enough to enter a human project review.

It does **not** mean:

- VERIFIED
- PASS
- requirement satisfied
- compliant
- accepted
- qualified
- certified
- safe
- validated for stakeholder use

### `STALE`

At least one referenced evidence object still exists but its current fingerprint differs from the snapshot stored when the requirement plan was registered or updated.

### `EVIDENCE_MISSING`

The requirement has no explicit evidence references or one or more referenced Project evidence objects no longer resolve.

## Human review outcomes

v1 permits only these review notes:

- `EVIDENCE_SUFFICIENT_FOR_PROJECT_REVIEW`
- `MORE_EVIDENCE_NEEDED`
- `PLAN_REVISION_NEEDED`

Even the first state means only that a human reviewer considers the evidence bundle sufficient to proceed with a project review.

It is intentionally not named `VERIFIED`, `PASS`, `COMPLIANT`, or `ACCEPTED`.

A stale or missing evidence bundle cannot be marked evidence-sufficient.

## Traceability boundary

`upstream_requirement_ids` are declared trace identifiers.

Physical Lab does not infer that the referenced upstream requirements really exist in an external requirements-management system, nor does it fabricate bidirectional traceability.

A future integration may resolve external requirement objects explicitly, but v1 stores only the user's declared trace relationship.

## Why this improves the broader Engineering integration

Before this layer, Physical Lab could answer:

- what model or measurement was run;
- what evidence exists;
- whether evidence changed;
- what engineering alternatives were compared;
- how operations, quality, reliability, risk, and economics were summarized.

With Requirements & Verification Planning, it can additionally organize those artifacts around explicit engineering obligations and planned verification methods.

This makes Physical Lab closer to an **Evidence-First Engineering Systems Workbench** rather than only a physics simulation collection.

## Scientific and professional boundary

Physical Lab v1 does not establish:

- formal product verification;
- product validation;
- requirement compliance;
- qualification;
- acceptance testing status;
- safety approval;
- standards compliance;
- certification;
- regulatory approval.

Those conclusions require domain-specific procedures, authorities, configuration control, acceptance criteria, and review processes beyond the scope of this software layer.
