# Physical Lab Run & Diagnostics Log

Physical Lab now has a platform-level diagnostic timeline in addition to the per-job `worker.log` files already provided by the Compute Engine.

## Purpose

The Diagnostics Log is designed to answer four practical questions:

1. What ran?
2. What is still running in the background?
3. Did anything produce a warning or error?
4. What compact diagnostic evidence should be exported when reproducing or reporting a problem?

It is **diagnostic evidence**, not scientific result data. A successful diagnostic status does not establish scientific validity, and an uploaded support bundle is not a substitute for experiment/result provenance.

## Event levels

The first contract intentionally uses three user-facing levels:

- `INFO` — normal lifecycle and worker output.
- `WARNING` — cancellation, interruption, retry/deprecation-style messages, or other conditions that merit inspection but are not necessarily failures.
- `ERROR` — failed/interrupted jobs, tracebacks, exceptions, and platform module failures captured by the engineering facade.

The event schema is:

`physical-lab-diagnostic-event-v1`

Core fields include timestamp, severity, kind, source, profile, job ID, run ID, experiment fingerprint, code, message and bounded detail.

## Storage

Persistent platform events are stored as JSON Lines under:

```text
$PHYSICAL_LAB_DATA_DIR/diagnostics/events.jsonl
```

When the active log becomes large it is rotated to a timestamped JSONL file. Diagnostic logging is fail-soft: inability to write diagnostics must never abort a scientific calculation.

Compute Engine worker logs remain stored under their existing job directories:

```text
$PHYSICAL_LAB_DATA_DIR/compute-jobs/<job-id>/worker.log
```

The unified view reads those original logs rather than replacing them.

## Compute integration

The Diagnostics Workspace combines:

- persistent platform diagnostic events,
- current Compute Engine job state,
- job profile / runner / progress / stage / attempt,
- job error field,
- bounded tails of original `worker.log` files.

Worker lifecycle output now uses explicit prefixes such as:

```text
[INFO] ... worker-start
[INFO] ... checkpoint=manifest-validated progress=0.150
[WARNING] ... cancelled
[ERROR] ... ValueError: ...
```

This keeps the raw worker evidence readable while allowing the unified UI to classify messages.

## UI

Every Lab can access **Physical Lab · Run & Diagnostics Log** through the shared engineering workspace.

The first UI supports:

- All Labs vs Current Lab scope,
- INFO / WARNING / ERROR counters,
- text search,
- severity filtering,
- event inspection,
- background job/worker-log correlation,
- manual refresh,
- diagnostics bundle export.

An error counter is intentionally visible rather than silently hiding failures behind a successful plot or completed UI rerun.

## Support bundle

The export schema is:

`physical-lab-support-bundle-v1`

The bundle contains bounded diagnostic events and selected job metadata. It intentionally does **not** export:

- the process environment,
- credentials,
- scientific result payloads,
- complete measurement datasets.

Common token/password/API-key/authorization-like text is redacted, and the user's home path is shortened to `~` where possible.

This export is intended for workflows such as:

```text
Problem occurs
    ↓
Diagnostics shows WARNING / ERROR
    ↓
Export diagnostics bundle
    ↓
Attach/paste bundle for debugging
    ↓
Reproduce → identify source → patch → validate
```

## Current boundary and next expansion

This first platform layer gives strong coverage for kernel-native Compute Engine jobs and exceptions caught at shared platform boundaries. Some legacy interactive Lab calculations still run directly inside existing Streamlit code paths and do not yet emit a dedicated start/finish event for every button press.

The architecture is deliberately ready for those adapters. The next step is to instrument each legacy/physics-scenario run through the same small `emit_event(...)` contract rather than creating Lab-specific logging systems.

## Deterministic validation

`scripts/diagnostics_log_validation.py` verifies:

- persistent JSONL event writing,
- INFO / WARNING / ERROR normalization,
- search/filter-ready event structure,
- warning/error worker-line classification,
- Compute Engine job correlation,
- common secret redaction,
- support-bundle privacy boundary.

The validation is part of Source Integrity CI.
