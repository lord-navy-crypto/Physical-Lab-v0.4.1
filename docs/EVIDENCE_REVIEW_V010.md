# Physical Lab Evidence Review v1

## Product role

Physical Lab is moving toward an **Evidence-First Engineering Physics Workbench** rather than competing with established commercial platforms on solver count alone.

The Evidence Review layer extends the existing Credibility Passport and Claim-to-Evidence Matrix with two capabilities:

1. **Evidence-linked Cross-Checks** — compare the same scalar observable through two user-declared distinct method paths and bind the comparison to explicit project evidence.
2. **Evidence Diff** — compare two project evidence snapshots and explain what changed in factor readiness, graph artifacts, claim readiness, and cross-check readiness.

The design vocabulary is informed by public NASA modeling-and-simulation credibility guidance and by VVUQ practice, but Physical Lab does not claim NASA-STD-7009 compliance, ASME compliance, accreditation, certification, or regulatory acceptance.

## Cross-Check contract

A cross-check stores:

- an observable name and unit;
- a primary scalar value;
- a comparison scalar value;
- an absolute or relative tolerance;
- a `method_family` and `source_identity` for each path;
- explicit references to project evidence such as results, jobs, experiments, measurements, or calibrations;
- SHA-256 evidence snapshots captured when the cross-check is registered.

Evaluation states are intentionally conservative:

- `AGREES_WITHIN_TOLERANCE` — the declared-distinct paths are current and agree numerically within the registered tolerance;
- `DISAGREES` — the declared-distinct paths are current but exceed the tolerance;
- `NOT_DISTINCT` — the two paths do not declare different method families and source identities;
- `STALE` — at least one supporting evidence fingerprint changed after registration;
- `EVIDENCE_MISSING` — at least one supporting evidence reference no longer resolves.

### Important boundary

`AGREES_WITHIN_TOLERANCE` is **not** a verification, validation, truth, or certification verdict.

Different strings in `method_family` and `source_identity` are only user-declared evidence that the paths are intended to be different. Physical Lab cannot prove statistical, mathematical, organizational, or software independence from those strings alone.

This distinction matters because two implementations can share the same hidden assumptions, equations, libraries, or source data and therefore fail in correlated ways.

## Evidence snapshots

An evidence snapshot combines the current project state of:

- Credibility Passport factors;
- Evidence Graph nodes/fingerprints;
- Claim-to-Evidence Matrix evaluations;
- Cross-Check Matrix evaluations.

The stable content receives a deterministic SHA-256 fingerprint. Generated timestamps are not part of the fingerprint, so identical scientific/evidence state produces the same snapshot identity.

## Evidence Diff

Evidence Diff compares two snapshots from the same project and reports:

- credibility-factor status transitions;
- added and resolved factor gaps;
- evidence graph nodes that were added, removed, or changed;
- claims that were added, removed, or changed readiness/fingerprint;
- cross-checks that were added, removed, or changed readiness/fingerprint;
- whether the Passport, Evidence Graph, Claim Matrix, or Cross-Check Matrix fingerprints changed.

A typical review transition is:

`AGREES_WITHIN_TOLERANCE -> STALE`

when a result or calibration referenced by the cross-check changes after the comparison was registered.

Evidence Diff does not infer that the underlying scientific conclusion became true or false. It says that the evidence state changed and identifies where a human/domain review should look.

## Why this is useful

A normal results dashboard usually preserves the newest values and plots. It may not make it obvious that a sentence in an older report was based on a result or calibration that has since changed.

Physical Lab's Evidence Review model treats scientific statements and corroborating comparisons as **versioned consumers of evidence**. That gives the project an explicit mechanism for detecting evidence drift.

The intended workflow is:

`Simulation / Measurement -> Verification & UQ -> Evidence Graph -> Credibility Passport -> Claims / Cross-Checks -> Evidence Snapshot -> Evidence Diff -> Human Review`

## CLI

The packaged CLI entry point is `scripts/physical_lab_evidence_review_cli.py`.

Supported operations:

- `cross-check-matrix <project>`
- `cross-check <project> <cross_check_id>`
- `snapshot <project> --label <label>`
- `diff <before.json> <after.json> [--markdown]`

## Acceptance test

`python scripts/evidence_review_validation.py`

The deterministic CI fixture constructs a complete synthetic `.physlab` evidence chain, verifies:

- an agreement within tolerance between declared-distinct paths;
- a `NOT_DISTINCT` same-method guard;
- an out-of-tolerance disagreement;
- a result fingerprint change causing `STALE`;
- Evidence Diff detecting the cross-check readiness transition and graph change;
- absence of machine truth/proof/verification verdicts.

## Next UI step

The native desktop **Evidence Center** should present the same core contracts rather than reimplementing them in UI state. The UI should read Passport, Claims, Cross-Checks, snapshots, and diffs from the deterministic project-level APIs so CLI, CI, and desktop behavior remain aligned.
