# Physical Lab — Experiment Kernel & Compute Engine

## Purpose

Physical Lab is moving from a collection of integrated scientific UIs toward a common experiment platform. The first consolidation layer is deliberately split into two parts:

1. **Experiment Kernel v1** — a stable scientific contract for experiment identity, inputs, parameters, execution, provenance, uncertainty and result references.
2. **Compute Engine v1** — a durable local queue that consumes those manifests and runs allow-listed work in child Python processes rather than tying computation lifetime to Streamlit reruns.

This phase does **not** claim that every legacy solver has already been rewritten around the kernel. It provides the contract and real worker execution path first, then permits solver-by-solver migration without breaking existing Labs.

## Experiment Kernel v1

Schema: `physical-lab-experiment-v1`

Every managed Lab has a profile contract:

- Numerical Error Analysis
- Ising Monte Carlo Lab
- Random Walk & Monte Carlo
- Nonlinear Dynamics & Chaos
- Oscillation & Numerical Integration
- RADIA Magnet Studio
- Radiation Platform

A manifest keeps these concerns separate:

```text
Experiment
├── model / profile identity
├── parameters
├── inputs
├── execution configuration
├── requirements
├── uncertainty
├── provenance
├── result reference
└── experiment_sha256
```

`experiment_sha256` is calculated from stable scientific content. Runtime timestamps are intentionally excluded, so the same scientific experiment retains the same identity when captured at a different time. Changing a scientific parameter changes the fingerprint.

Session adapters are transitional: they can capture bounded simple controls from the current Lab while filtering result-like payloads. New native adapters should eventually pass typed parameter/input/result objects directly rather than relying on Streamlit state discovery.

## Capability contracts

The five non-accelerator Labs already expose a deterministic `model-campaign` runner and therefore have:

```text
manifest + model-campaign
```

RADIA Magnet Studio and Radiation Platform currently expose:

```text
manifest
```

only. This is intentional. Their existing native solver lifecycle still lives partly in the legacy UI orchestration. Physical Lab does not label them worker-native until that lifecycle is extracted and validated. They can already be identified, fingerprinted, validated and queued for manifest operations through the same kernel.

## Compute Engine v1

Job schema: `physical-lab-job-v1`

Persistent location:

```text
$PHYSICAL_LAB_DATA_DIR/compute-jobs/<job-id>/
├── job.json
├── manifest.json
├── checkpoint.json
├── result.json
└── worker.log
```

The queue implements:

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`
- `interrupted`

and records:

- PID
- attempt count
- stage
- progress
- resource scheduling hint
- timestamps
- checkpoint
- error
- result path
- worker log

### Worker isolation

A queued job is started with the active Lab Python interpreter as a **child process**. It is therefore no longer dependent on a single Streamlit render call staying alive.

The worker accepts only allow-listed runners:

- `manifest-validate`
- `model-campaign`

It does not execute arbitrary Python strings, model-generated code or arbitrary module/function names.

### Cancellation

Cancellation writes a durable `cancel.requested` marker and terminates the worker process group when a live PID exists. Queued jobs can be cancelled without starting a process.

### Checkpoint / restart boundary

v1 checkpoints **stages**, not arbitrary solver memory. A model campaign records manifest validation, campaign start, campaign completion and result persistence. If a process is interrupted inside a monolithic legacy campaign, retry restarts that computational stage. Future native adapters may add solver-specific checkpoints where scientifically valid.

### Orphan recovery

When the UI returns, `reconcile_jobs()` inspects jobs marked `running`. A dead worker PID is never interpreted as success; the job becomes `interrupted` and can be explicitly requeued.

### Bounded concurrency

The first scheduler supports 1–4 local worker processes with a default of one. Resource classes are transparent scheduling hints rather than measured peak-memory guarantees.

## Current integration

`physical_lab_compute_engine.render_compute_workspace()` provides a Streamlit integration surface that can:

- show the current kernel manifest identity,
- queue manifest validation,
- queue Compact/Standard model campaigns for the five migrated profiles,
- inspect queue state,
- cancel/requeue,
- inspect results/logs,
- publish completed campaign metrics back into the existing Lab scorecard session state.

The modules are bundled in the Tauri application resources so the worker script is present in packaged builds.

## Migration rule

The target architecture is:

```text
Lab UI
  ↓
Experiment Kernel
  ↓
Compute Engine
  ↓
Profile Adapter / Solver
  ↓
Result Store
  ↓
Metrics / V&V / Views / AI
```

Migration should be incremental. Existing direct execution remains available until each solver adapter is proven equivalent or intentionally improved. A solver is not marked worker-native merely because the kernel can describe it.

## Scientific and safety boundaries

- Experiment identity is a reproducibility mechanism, not experimental validation.
- Resource estimates are scheduling hints.
- A completed simulation is not evidence that a physical apparatus is validated.
- Finite stochastic campaigns remain finite-sample evidence.
- No arbitrary worker code execution is exposed.
- Local AI remains advisory and does not receive automatic execution authority through this queue.
