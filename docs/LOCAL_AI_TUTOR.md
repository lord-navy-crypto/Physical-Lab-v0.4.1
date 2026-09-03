# Local AI Physics Tutor

Physical Lab can use an optional **local-only Physics Parameter Tutor** while keeping numerical solvers, imported measurements, validation checks, and project provenance authoritative.

## Runtime discovery

The Tutor checks only loopback endpoints:

- `http://127.0.0.1:11435` — OpenPenguin private Ollama-compatible runtime
- `http://127.0.0.1:11434` — external/standard Ollama runtime

Physical Lab does not download a model, start a cloud request, or require Local AI for any scientific calculation. If neither endpoint is running, every Lab continues to work without the Tutor.

## Structured physics context

The Tutor receives a bounded context containing whichever of these are available for the current Lab:

- current model parameters and solver settings;
- explicit parameter units and meanings for known controls;
- Safe/Full engine mode;
- latest bounded solver/result summary;
- selected UI state that is relevant to the experiment;
- provenance rules distinguishing measured, simulated/model, fitted, visual, and suggested information.

For RADIA Magnet Studio, the guide includes controls such as magnetic period, gap, remanent induction `Br`, material treatment, segmentation, target-field calibration, manufacturing-error scales, field sampling, electron energy, and relaxation settings.

The Tutor must not invent a unit for an unknown control.

## Optional local vision

Physical Lab calls the selected model's local `/api/show` endpoint. Screenshot/plot upload is enabled only when the model explicitly reports the `vision` capability. Physical Lab does not infer vision support from a model name.

A vision-capable model may receive up to **two** user-selected PNG, JPEG, or WebP images, each limited to **8 MB**. The image data is attached to the local `/api/chat` request and is not added to the `.physlab` workspace by the Tutor.

Vision is intentionally supplementary:

- **structured solver values** are authoritative for exact numerical results;
- **visual observations** can describe geometry, plot shape, annotations, visible discontinuities, clipping, unexpected symmetry/asymmetry, or UI state;
- if an image appears inconsistent with the structured result context, the Tutor should identify the discrepancy rather than silently choose one source.

This design avoids reading approximate pixel locations as if they were solver-quality measurements.

## Read-only boundary

The Local AI layer may:

- explain a parameter and its physical role;
- audit assumptions and numerical-resolution risks;
- interpret available results while preserving provenance;
- propose a controlled next scan and state what observation would contradict the expectation;
- discuss a user-supplied screenshot when a local vision model is available.

It may **not**:

- change a parameter;
- press Run or launch a solver;
- execute model-generated code;
- claim a suggested scan has already run;
- relabel simulated output as measured data;
- treat a better fit or converged simulation as experimental validation;
- contact a non-loopback AI endpoint.

## Recommended workflow

1. Configure and run the real Physical Lab model first.
2. Inspect the numerical results and validation status.
3. Open **Local AI Physics Tutor · OpenPenguin / Ollama**.
4. Choose a local model.
5. Use **Explain setup**, **Check assumptions**, **Interpret results**, or **Plan next scan**.
6. If the model reports `vision`, optionally attach a screenshot or plot and ask a visually specific question.
7. Treat the response as advisory reasoning and return to the scientific solver for the next calculation.

## Deterministic validation

`scripts/local_ai_reference_validation.py` tests the Local AI bridge without requiring a running model. CI checks:

- context schema and provenance labels;
- explicit parameter metadata;
- capability-gated vision detection;
- image type/size bounds;
- the Ollama-compatible message shape;
- absence of an `images` field for text-only calls.

The validation is part of the repository's **Source Integrity** workflow.
