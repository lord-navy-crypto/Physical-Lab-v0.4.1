# Physical Lab Credibility Passport v1

## Product direction

Physical Lab should not compete with established commercial engineering platforms by claiming the largest solver catalog. COMSOL already combines multiphysics modeling, application building, model management/versioning, and uncertainty quantification. Ansys optiSLang provides sensitivity analysis, calibration, optimization, robustness, reliability, and uncertainty workflows. MATLAB/Simulink provides deep requirements-to-design/test/code traceability. LabVIEW is purpose-built for automated test and measurement. Jupyter provides highly flexible reproducible computational documents.

Physical Lab's differentiating product direction is therefore:

> **Evidence-First Engineering Physics Workbench** — do not only produce a simulation result; automatically expose the evidence chain that explains how the result was produced, what supports it, what is missing, and what can be reproduced.

This is a product-positioning choice, not a claim that no other engineering software has provenance, V&V, traceability, or uncertainty features. The differentiation is the combination, the default workflow, the accessibility to individual researchers/students/small teams, and the cross-Lab evidence contract.

## Credibility Passport

The Credibility Passport reads existing `.physlab` project records and reports evidence readiness across eight factor names used in public NASA modeling-and-simulation credibility guidance:

1. Data pedigree
2. Verification
3. Validation
4. Input pedigree
5. Uncertainty characterization
6. Results robustness
7. M&S history
8. M&S process / product management

The passport reports only `PRESENT`, `PARTIAL`, or `MISSING` project evidence for each factor. It also lists the evidence it found and the gaps it detected.

### Important non-goal: no fake overall score

Physical Lab deliberately does **not** compute an `84/100 credibility` number. NASA guidance emphasizes factor-specific assessments and project/intended-use sufficiency thresholds. A generic weighted average would imply a scientific equivalence between unrelated evidence factors that Physical Lab cannot justify.

`PRESENT` means that discoverable project evidence exists for the factor under Physical Lab's evidence-readiness rules. It does not mean that a NASA, ASME, regulatory, accreditation, or certification criterion has been satisfied.

## Evidence Graph

Every passport includes a deterministic evidence graph linking:

`Project -> Experiment -> Job -> Result`

and project evidence:

`Project -> Measurement`

`Project -> Calibration -> Measurement`

Each experiment and result keeps its SHA-256 scientific/result fingerprint. Measurement assets keep their file SHA-256. The graph itself receives a deterministic SHA-256 fingerprint so two evidence states can be compared without relying on UI state.

The graph records traceability relationships only. It does not infer causality or scientific validity from an edge.

## Why this is different from a normal results dashboard

A normal simulation dashboard answers questions such as:

- What value did the solver return?
- What does the curve look like?
- Did a threshold pass?

The Evidence-First workflow additionally asks:

- Which scientific manifest produced the result?
- Which solver/source revision produced it?
- Is numerical verification evidence discoverable?
- Is there actual referent/measurement evidence, rather than simulation-only evidence?
- Is calibration information registered for that measurement?
- Are uncertainty sources represented?
- Was sensitivity, replicate stability, timestep convergence, or another robustness check performed?
- Is there enough prior execution history to compare this result with another run?
- Are logs and result fingerprints retained?
- What evidence is still missing?

## Authoritative design references

Physical Lab uses these references to inform product design and terminology, while making no standards-compliance claim:

- NASA-STD-7009B, *Standard for Models and Simulations*, NASA Technical Standards System.
- NASA-STD-7009A / NASA-HDBK-7009A public credibility-factor guidance.
- ASME Verification, Validation and Uncertainty Quantification (VVUQ) standards and resource guidance.
- NIST work on simulation/digital-twin credibility, verification, validation, and uncertainty quantification.

Commercial-product comparisons should be checked against current vendor documentation because capabilities evolve rapidly.

## Current implementation boundary

Credibility Passport v1 is intentionally evidence-oriented and conservative:

- It detects project-local evidence and gaps; it does not prove scientific truth.
- Measurement upload alone is not validation.
- Calibration metadata supplied by a user is not treated as accredited traceability.
- A successful compute job is not by itself verification.
- A sensitivity study is evidence about robustness only within its sampled/modelled scope.
- A passport fingerprint identifies the evidence state, not the validity of the physical model.

## Next differentiating layers

The natural follow-on roadmap is:

1. **Claim-to-Evidence Matrix** — connect an explicit engineering/scientific claim to requirement, experiment, job, result, measurement, and uncertainty evidence.
2. **Independent Cross-Engine Checks** — allow one invariant/observable to be checked by an independent analytic or solver path.
3. **Reproducibility Capsule** — export a compact manifest of inputs, hashes, environment/source revisions, evidence references, and boundaries.
4. **Evidence-diff Review** — compare two passports and explain which evidence changed, appeared, disappeared, or became stale.
5. **Purpose-specific sufficiency profiles** — user-authored factor thresholds/checklists for a stated intended use, without pretending they are universal standards.

The product principle is simple:

> **Do not just simulate. Show why the result should be trusted — and clearly show why it should not yet be trusted when evidence is missing.**
