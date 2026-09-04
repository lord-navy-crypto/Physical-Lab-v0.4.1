"""Unified Run & Diagnostics Log for Physical Lab.

This module is intentionally platform-level. It provides a small structured event
contract that can be called from compute workers, project/evidence workflows and
UI exception boundaries without coupling scientific solvers to Streamlit.

Events are stored as JSON Lines under ``PHYSICAL_LAB_DATA_DIR/diagnostics``.
The log is diagnostic evidence, not scientific result data. Support-bundle export
redacts common secret-like values and never exports the process environment.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

EVENT_SCHEMA = "physical-lab-diagnostic-event-v1"
BUNDLE_SCHEMA = "physical-lab-support-bundle-v1"
SEVERITIES = ("INFO", "WARNING", "ERROR")
_SEVERITY_ORDER = {"INFO": 10, "WARNING": 20, "ERROR": 30}
_MAX_LOG_BYTES = 12 * 1024 * 1024

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*)([^\s,;]+)"),
    re.compile(r"(?i)((?:api[_-]?key|token|password|secret)\s*[=:]\s*)([^\s,;]+)"),
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9._~+/=-]+)"),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _diagnostics_root() -> Path | None:
    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
    if not raw:
        return None
    root = Path(raw) / "diagnostics"
    root.mkdir(parents=True, exist_ok=True)
    return root


def diagnostics_path() -> Path | None:
    root = _diagnostics_root()
    return None if root is None else root / "events.jsonl"


def redact_text(value: Any) -> str:
    text = str(value if value is not None else "")
    home = str(Path.home())
    if home and home != "/":
        text = text.replace(home, "~")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: match.group(1) + "<redacted>", text)
    return text


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Path):
        return redact_text(str(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(item) for item in value]
    return redact_text(repr(value))


def normalize_severity(severity: str) -> str:
    value = str(severity or "INFO").strip().upper()
    aliases = {"WARN": "WARNING", "FATAL": "ERROR", "CRITICAL": "ERROR", "ERR": "ERROR"}
    value = aliases.get(value, value)
    if value not in SEVERITIES:
        value = "INFO"
    return value


def _rotate_if_needed(path: Path) -> None:
    try:
        if path.exists() and path.stat().st_size >= _MAX_LOG_BYTES:
            rotated = path.with_name(f"events-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
            os.replace(path, rotated)
    except OSError:
        # Diagnostics must never be allowed to break a scientific run.
        pass


def emit_event(
    severity: str,
    source: str,
    message: str,
    *,
    kind: str = "system",
    profile: str | None = None,
    job_id: str | None = None,
    run_id: str | None = None,
    experiment_sha256: str | None = None,
    code: str | None = None,
    detail: Any = None,
    persist: bool = True,
) -> dict[str, Any]:
    event = {
        "schema": EVENT_SCHEMA,
        "id": f"evt-{uuid.uuid4().hex[:16]}",
        "timestamp": utc_now(),
        "severity": normalize_severity(severity),
        "kind": str(kind or "system"),
        "source": str(source or "physical-lab"),
        "profile": str(profile) if profile else None,
        "job_id": str(job_id) if job_id else None,
        "run_id": str(run_id) if run_id else None,
        "experiment_sha256": str(experiment_sha256) if experiment_sha256 else None,
        "code": str(code) if code else None,
        "message": redact_text(message),
        "detail": _plain(detail) if detail is not None else None,
    }
    if not persist:
        return event
    path = diagnostics_path()
    if path is None:
        return event
    try:
        _rotate_if_needed(path)
        line = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass
    return event


def record_exception(
    source: str,
    exc: BaseException,
    *,
    profile: str | None = None,
    job_id: str | None = None,
    code: str | None = None,
    detail: Any = None,
) -> dict[str, Any]:
    payload = {
        "exception_type": type(exc).__name__,
        "exception": str(exc),
    }
    if detail is not None:
        payload["context"] = detail
    return emit_event(
        "ERROR",
        source,
        f"{type(exc).__name__}: {exc}",
        kind="exception",
        profile=profile,
        job_id=job_id,
        code=code,
        detail=payload,
    )


def classify_log_line(line: str) -> str:
    text = str(line or "").strip().lower()
    if not text:
        return "INFO"
    error_tokens = ("traceback", "exception", "fatal", "failed", "failure", "error:", " error ")
    warning_tokens = ("warning", "warn:", "deprecated", "retrying", "interrupted")
    if any(token in text for token in error_tokens):
        return "ERROR"
    if any(token in text for token in warning_tokens):
        return "WARNING"
    return "INFO"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    value = json.loads(line)
                except Exception:
                    continue
                if isinstance(value, dict) and value.get("schema") == EVENT_SCHEMA:
                    rows.append(value)
    except OSError:
        return []
    return rows


def list_events(
    *,
    limit: int = 500,
    severities: Iterable[str] | None = None,
    profile: str | None = None,
    source_contains: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    root = _diagnostics_root()
    if root is None:
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("events*.jsonl")):
        rows.extend(_read_jsonl(path))
    allowed = {normalize_severity(item) for item in severities} if severities else None
    needle = str(search or "").strip().lower()
    source_needle = str(source_contains or "").strip().lower()
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if allowed and row.get("severity") not in allowed:
            continue
        if profile and row.get("profile") not in {profile, None}:
            continue
        if source_needle and source_needle not in str(row.get("source") or "").lower():
            continue
        if needle:
            haystack = " ".join(
                str(row.get(key) or "")
                for key in ("timestamp", "severity", "kind", "source", "profile", "job_id", "code", "message")
            ).lower()
            if needle not in haystack:
                continue
        filtered.append(row)
    filtered.sort(key=lambda row: (str(row.get("timestamp") or ""), str(row.get("id") or "")), reverse=True)
    return filtered[: max(1, min(int(limit), 5000))]


def severity_summary(events: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    summary = {"INFO": 0, "WARNING": 0, "ERROR": 0}
    for row in events:
        severity = normalize_severity(str(row.get("severity") or "INFO"))
        summary[severity] += 1
    return summary


def _job_event(record: Mapping[str, Any]) -> dict[str, Any]:
    status = str(record.get("status") or "unknown")
    if status in {"failed", "interrupted"}:
        severity = "ERROR"
    elif status in {"cancelled"}:
        severity = "WARNING"
    else:
        severity = "INFO"
    message = f"Compute job {status}: {record.get('runner') or 'runner'}"
    if record.get("error"):
        message += f" — {record.get('error')}"
    return {
        "schema": EVENT_SCHEMA,
        "id": f"job-state-{record.get('id')}",
        "timestamp": record.get("updated_at") or record.get("created_at") or "",
        "severity": severity,
        "kind": "compute-job",
        "source": "compute-engine",
        "profile": record.get("profile"),
        "job_id": record.get("id"),
        "run_id": None,
        "experiment_sha256": record.get("experiment_sha256"),
        "code": f"JOB_{status.upper()}",
        "message": redact_text(message),
        "detail": {
            "status": status,
            "stage": record.get("stage"),
            "progress": record.get("progress"),
            "attempt": record.get("attempt"),
        },
    }


def collect_events_with_compute(
    compute_engine: Any | None,
    *,
    limit: int = 1000,
    profile: str | None = None,
    include_worker_lines: bool = True,
    worker_lines_per_job: int = 40,
) -> list[dict[str, Any]]:
    rows = list_events(limit=limit, profile=profile)
    if compute_engine is None:
        return rows[:limit]
    try:
        jobs = compute_engine.list_jobs(limit=200, profile=profile)
    except Exception:
        jobs = []
    for record in jobs:
        rows.append(_job_event(record))
        if not include_worker_lines:
            continue
        try:
            raw = compute_engine.tail_log(str(record.get("id") or ""), max_chars=24000)
        except Exception:
            raw = ""
        if not raw:
            continue
        lines = [line for line in raw.splitlines() if line.strip()][-max(1, min(int(worker_lines_per_job), 200)) :]
        for index, line in enumerate(lines):
            rows.append({
                "schema": EVENT_SCHEMA,
                "id": f"worker-{record.get('id')}-{index}",
                "timestamp": record.get("updated_at") or record.get("created_at") or "",
                "severity": classify_log_line(line),
                "kind": "worker-log",
                "source": f"worker:{record.get('runner') or 'unknown'}",
                "profile": record.get("profile"),
                "job_id": record.get("id"),
                "run_id": None,
                "experiment_sha256": record.get("experiment_sha256"),
                "code": None,
                "message": redact_text(line),
                "detail": None,
            })
    rows.sort(
        key=lambda row: (
            str(row.get("timestamp") or ""),
            _SEVERITY_ORDER.get(normalize_severity(str(row.get("severity") or "INFO")), 0),
            str(row.get("id") or ""),
        ),
        reverse=True,
    )
    return rows[: max(1, min(int(limit), 5000))]


def build_support_bundle(
    events: Iterable[Mapping[str, Any]],
    *,
    jobs: Iterable[Mapping[str, Any]] | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    safe_events = [_plain(dict(row)) for row in events]
    safe_jobs: list[dict[str, Any]] = []
    for row in jobs or []:
        safe_jobs.append(
            _plain({
                key: row.get(key)
                for key in (
                    "id", "profile", "experiment_sha256", "runner", "status", "progress", "stage",
                    "priority", "created_at", "updated_at", "started_at", "finished_at", "attempt", "error",
                )
            })
        )
    return {
        "schema": BUNDLE_SCHEMA,
        "generated_at": utc_now(),
        "profile_filter": profile,
        "summary": severity_summary(safe_events),
        "events": safe_events,
        "jobs": safe_jobs,
        "privacy_boundary": (
            "Support bundle includes diagnostic events and bounded job metadata only. "
            "Process environment, credentials and scientific result payloads are not exported; common secret-like text is redacted."
        ),
    }


def render_diagnostics_workspace(st: Any, profile: str | None = None, compute_engine: Any | None = None) -> None:
    st.markdown("---")
    st.markdown("## Physical Lab · Run & Diagnostics Log")
    st.caption(
        "Unified platform timeline for runs, background jobs, INFO, WARNING and ERROR events. "
        "This is diagnostic evidence; it does not replace scientific provenance or validation results."
    )

    scope = st.radio(
        "Log scope",
        ["All Labs", "Current Lab"],
        horizontal=True,
        key=f"pl_diag_scope_{profile or 'global'}",
    )
    active_profile = profile if scope == "Current Lab" else None
    max_events = st.select_slider(
        "Entries",
        options=[100, 250, 500, 1000, 2000],
        value=500,
        key=f"pl_diag_limit_{profile or 'global'}",
    )
    rows = collect_events_with_compute(
        compute_engine,
        limit=int(max_events),
        profile=active_profile,
        include_worker_lines=True,
    )
    summary = severity_summary(rows)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Entries", len(rows))
    m2.metric("INFO", summary["INFO"])
    m3.metric("WARNING", summary["WARNING"])
    m4.metric("ERROR", summary["ERROR"])

    f1, f2 = st.columns([2, 1])
    query = f1.text_input("Search log", key=f"pl_diag_search_{profile or 'global'}", placeholder="job id, module, message, error…")
    selected_levels = f2.multiselect(
        "Severity",
        list(SEVERITIES),
        default=list(SEVERITIES),
        key=f"pl_diag_levels_{profile or 'global'}",
    )
    needle = query.strip().lower()
    visible = []
    for row in rows:
        if selected_levels and normalize_severity(str(row.get("severity") or "INFO")) not in selected_levels:
            continue
        if needle:
            haystack = " ".join(
                str(row.get(key) or "")
                for key in ("timestamp", "severity", "kind", "source", "profile", "job_id", "code", "message")
            ).lower()
            if needle not in haystack:
                continue
        visible.append(row)

    if summary["ERROR"]:
        st.error(f"Diagnostics contains {summary['ERROR']} error event(s) in the current view.")
    elif summary["WARNING"]:
        st.warning(f"Diagnostics contains {summary['WARNING']} warning event(s) in the current view.")
    else:
        st.success("No warning/error events in the current view.")

    table_rows = [
        {
            "time": row.get("timestamp"),
            "level": row.get("severity"),
            "source": row.get("source"),
            "profile": row.get("profile"),
            "job": row.get("job_id"),
            "message": row.get("message"),
        }
        for row in visible
    ]
    if table_rows:
        st.dataframe(table_rows, width="stretch", hide_index=True)
        event_ids = [str(row.get("id") or index) for index, row in enumerate(visible)]
        selected_id = st.selectbox(
            "Inspect event",
            event_ids,
            key=f"pl_diag_event_{profile or 'global'}",
        )
        selected = next((row for row in visible if str(row.get("id")) == selected_id), None)
        if selected:
            st.json(_plain(selected))
    else:
        st.caption("No events match the current filters.")

    jobs = []
    if compute_engine is not None:
        try:
            jobs = compute_engine.list_jobs(limit=200, profile=active_profile)
        except Exception:
            jobs = []
    bundle = build_support_bundle(visible, jobs=jobs, profile=active_profile)
    b1, b2 = st.columns(2)
    b1.download_button(
        "Export diagnostics bundle",
        data=json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False),
        file_name=f"physical-lab-diagnostics-{time.strftime('%Y%m%d-%H%M%S')}.json",
        mime="application/json",
        width="stretch",
        key=f"pl_diag_export_{profile or 'global'}",
    )
    if b2.button("Refresh diagnostics", width="stretch", key=f"pl_diag_refresh_{profile or 'global'}"):
        st.rerun()
