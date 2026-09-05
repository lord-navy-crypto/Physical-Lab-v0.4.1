# Research Model Builder MVP

## Purpose

Research Model Builder turns a trusted local Python research model into a reviewable Physical Lab model bundle without silently rewriting the student's scientific implementation.

The MVP implements the bounded chain:

```text
Trusted local .py source
        ↓
Static AST analysis (no import / no execution)
        ↓
Candidate entry function + parameters + outputs + dependencies
        ↓
Human parameter review (labels / units / controls / ranges)
        ↓
ModelSpec v1
        ↓
Generated adapter + deterministic UI spec
        ↓
Explicit local Preview
        ↓
Original ↔ adapter equivalence check
        ↓
Save bundle into canonical .physlab Project
```

The product philosophy is **wrapper, not rewrite**. Generation copies a source snapshot into the model bundle for provenance and creates an adapter around it. The selected original file is not overwritten.

## Model bundle

A generated bundle contains:

- `original_model.py` — immutable snapshot copy used by the generated adapter;
- `adapter.py` — generated bridge exposing `physical_lab_run(parameters)`;
- `model.json` — `physical-lab-model-spec-v1`;
- `ui.json` — deterministic control/output description;
- `tests.json` — adapter-equivalence settings plus user-declared scientific tests;
- `provenance.json` — source, adapter and ModelSpec fingerprints plus generation policy.

Saving a bundle to a canonical Project copies these files into `models/<bundle-id>/` and updates `models/index.json`. Project membership is provenance only; it does not certify the model.

## ModelSpec v1

The MVP schema includes:

- `metadata` — name, description, source file, SHA-256;
- `compute` — entry function and calling convention;
- `parameters` — name, label, type, unit, default, control, explicit range when applicable;
- `outputs` — named output candidates;
- `visualizations` — deterministic renderer hints;
- `assumptions`;
- `validation` — user-confirmed reference/sanity tests;
- `documentation`.

Supported MVP controls:

- `slider` — requires explicit min and max;
- `number`;
- `toggle`;
- `dropdown`;
- `text`.

The analyzer does **not** invent slider bounds. Unknown units remain unknown until the user supplies or confirms them.

## Static analysis boundary

`Analyze` uses Python's AST parser only. It does not import or execute the selected model. It extracts top-level function signatures, imports, defaults and return-shape candidates.

Imports associated with process, network, native-memory or filesystem mutation are surfaced as execution-risk warnings. A warning does not prove that the source is malicious; it tells the user that explicit local execution deserves review.

## Execution boundary

`Preview` and `Validate Adapter` are separate explicit actions. The desktop bridge requires the user to confirm that they trust the local source before execution. Physical Lab:

- launches Python directly, never through a shell;
- uses a fixed execution timeout;
- caps captured output;
- disables stdin;
- does not execute the source during analysis or generation.

This is a local desktop trust model, not a sandbox strong enough for arbitrary untrusted Internet code. Public/server execution of uploaded Python is deliberately out of scope for this MVP.

## Adapter equivalence is not scientific validation

The MVP comparison runs the same parameter object through:

1. the selected source snapshot's entry function;
2. the generated Physical Lab adapter.

It compares normalized output structure and finite numeric values under explicit tolerances. Passing this check establishes **interface equivalence for that case**, not correctness of equations, assumptions, numerical method, units, calibration, physical interpretation or reference truth.

## Deterministic UI renderer

The desktop Model Builder renders parameter controls from ModelSpec rather than generating arbitrary HTML/JavaScript for each student model. Preview output uses safe deterministic components:

- scalar value cards;
- numeric-array summaries/sparklines;
- an automatic x-y line view when two compatible numeric arrays are available;
- structured JSON fallback for unsupported output shapes.

Custom frontend code generation is not required for MVP.

## Explicitly deferred

The following belong to later phases:

- Local-AI suggestion cards for semantic units/ranges/visualizations;
- notebook and paper import;
- browser/Pyodide execution;
- dependency resolution beyond the available local Python environment;
- public publishing and accounts;
- model library and attribution service;
- Fork Model ancestry/version graph;
- unrestricted custom widgets;
- remote execution.

These are compatible with the ModelSpec/bundle architecture but should not weaken the current execution and scientific-review boundaries.
