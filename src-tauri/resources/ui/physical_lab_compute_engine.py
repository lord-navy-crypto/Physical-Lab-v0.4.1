"""Persistent local Job / Compute Engine for Physical Lab.

The engine consumes Experiment Kernel manifests and runs allow-listed worker
operations in child Python processes.  Queue state lives under
PHYSICAL_LAB_DATA_DIR so a Streamlit rerun is not the computation lifecycle.

v1 provides durable queue records, bounded local concurrency, cancellation,
logs, stage-level checkpoints, retry/requeue and result publication.  Native
RADIA/Radiation solver extraction remains intentionally separate; those profiles
can already produce/validate manifests but are not falsely advertised as worker-
native solvers yet.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Mapping

from physical_lab_experiment_kernel import (
    PROFILE_CONTRACTS,
    build_session_manifest,
    estimate_resources,
    manifest_summary,
    plain,
    utc_now,
    validate_manifest,
)

JOB_SCHEMA = "physical-lab-job-v1"
TERMINAL_STATES = {"succeeded", "failed", "cancelled"}
ACTIVE_STATES = {"queued", "running"}
RUNNERS = {"manifest-validate", "model-campaign"}
MAX_PARALLEL_HARD_LIMIT = 4


def _data_root() -> Path | None:
    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
    if not raw:
        return None
    root = Path(raw) / "compute-jobs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _job_dir(job_id: str) -> Path:
    root = _data_root()
    if root is None:
        raise RuntimeError("PHYSICAL_LAB_DATA_DIR is not configured")
    if not job_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in job_id):
        raise ValueError("invalid job id")
    return root / job_id


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(plain(dict(value)), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _record_path(job_id: str) -> Path:
    return _job_dir(job_id) / "job.json"


def read_job(job_id: str) -> dict[str, Any] | None:
    return _read_json(_record_path(job_id))


def write_job(record: Mapping[str, Any]) -> None:
    job_id = str(record.get("id") or "")
    _atomic_json(_record_path(job_id), dict(record))


def _pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def submit_job(
    manifest: Mapping[str, Any],
    *,
    runner: str,
    runner_config: Mapping[str, Any] | None = None,
    priority: int = 50,
) -> dict[str, Any]:
    check = validate_manifest(manifest)
    if not check["valid"]:
        raise ValueError("invalid experiment manifest: " + "; ".join(check["errors"]))
    if runner not in RUNNERS:
        raise ValueError(f"runner is not allow-listed: {runner}")
    profile = str(manifest["profile"])
    if runner == "model-campaign" and "model-campaign" not in PROFILE_CONTRACTS[profile]["worker_capabilities"]:
        raise ValueError(f"{profile} does not yet expose worker-native model-campaign capability")
    config = plain(dict(runner_config or {}))
    if runner == "model-campaign":
        if str(config.get("profile") or profile) != profile:
            raise ValueError("runner profile must match experiment profile")
        preset = str(config.get("preset") or "compact")
        if preset not in {"compact", "standard"}:
            raise ValueError("model-campaign preset must be compact or standard")
        config["profile"] = profile
        config["preset"] = preset
    job_id = f"job-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:10]}"
    directory = _job_dir(job_id)
    directory.mkdir(parents=True, exist_ok=False)
    _atomic_json(directory / "manifest.json", dict(manifest))
    record = {
        "schema": JOB_SCHEMA,
        "id": job_id,
        "profile": profile,
        "experiment_sha256": manifest.get("experiment_sha256"),
        "runner": runner,
        "runner_config": config,
        "status": "queued",
        "progress": 0.0,
        "stage": "queued",
        "priority": max(0, min(int(priority), 100)),
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "pid": None,
        "attempt": 0,
        "resource_estimate": estimate_resources(profile, manifest.get("execution") or config),
        "checkpoint": None,
        "error": None,
        "result_path": None,
        "log_path": str(directory / "worker.log"),
        "boundary": "Local process scheduling and deterministic persistence; resource estimates are hints, not guarantees.",
    }
    write_job(record)
    return record


def list_jobs(*, limit: int = 100, profile: str | None = None) -> list[dict[str, Any]]:
    root = _data_root()
    if root is None:
        return []
    rows: list[dict[str, Any]] = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        record = _read_json(path / "job.json")
        if not record or record.get("schema") != JOB_SCHEMA:
            continue
        if profile and record.get("profile") != profile:
            continue
        rows.append(record)
    rows.sort(key=lambda row: (str(row.get("created_at") or ""), str(row.get("id") or "")), reverse=True)
    return rows[: max(1, min(int(limit), 500))]


def reconcile_jobs() -> list[dict[str, Any]]:
    """Mark orphaned running jobs interrupted; never infer success from a dead PID."""
    changed: list[dict[str, Any]] = []
    for record in list_jobs(limit=500):
        if record.get("status") != "running":
            continue
        if _pid_alive(record.get("pid")):
            continue
        latest = read_job(str(record["id"])) or record
        if latest.get("status") == "running":
            latest.update({
                "status": "interrupted",
                "stage": "interrupted",
                "updated_at": utc_now(),
                "finished_at": utc_now(),
                "pid": None,
                "error": latest.get("error") or "worker process exited before writing a terminal state",
            })
            write_job(latest)
            changed.append(latest)
    return changed


def _worker_path() -> Path:
    return Path(__file__).resolve().parent / "physical_lab_job_worker.py"


def _start_job(record: Mapping[str, Any]) -> dict[str, Any]:
    job_id = str(record["id"])
    directory = _job_dir(job_id)
    log_path = directory / "worker.log"
    worker = _worker_path()
    if not worker.exists():
        raise RuntimeError(f"Physical Lab job worker is missing: {worker}")
    log_handle = open(log_path, "ab", buffering=0)
    try:
        process = subprocess.Popen(
            [sys.executable, str(worker), "--job", str(directory)],
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
            start_new_session=True,
            close_fds=True,
        )
    finally:
        log_handle.close()
    latest = read_job(job_id) or dict(record)
    latest.update({
        "status": "running",
        "stage": "starting-worker",
        "progress": max(float(latest.get("progress") or 0.0), 0.02),
        "started_at": latest.get("started_at") or utc_now(),
        "updated_at": utc_now(),
        "finished_at": None,
        "pid": int(process.pid),
        "attempt": int(latest.get("attempt") or 0) + 1,
        "error": None,
    })
    write_job(latest)
    return latest


def start_queued_jobs(*, max_parallel: int = 1) -> list[dict[str, Any]]:
    reconcile_jobs()
    limit = max(1, min(int(max_parallel), MAX_PARALLEL_HARD_LIMIT))
    jobs = list_jobs(limit=500)
    running = [row for row in jobs if row.get("status") == "running" and _pid_alive(row.get("pid"))]
    slots = max(0, limit - len(running))
    if slots <= 0:
        return []
    queued = [row for row in jobs if row.get("status") == "queued"]
    queued.sort(key=lambda row: (-int(row.get("priority") or 0), str(row.get("created_at") or "")))
    started: list[dict[str, Any]] = []
    for record in queued[:slots]:
        try:
            started.append(_start_job(record))
        except Exception as exc:
            failed = read_job(str(record["id"])) or dict(record)
            failed.update({
                "status": "failed",
                "stage": "worker-launch",
                "finished_at": utc_now(),
                "updated_at": utc_now(),
                "error": f"worker launch failed: {exc}",
                "pid": None,
            })
            write_job(failed)
    return started


def cancel_job(job_id: str) -> dict[str, Any]:
    record = read_job(job_id)
    if not record:
        raise FileNotFoundError(job_id)
    status = str(record.get("status") or "")
    if status in TERMINAL_STATES:
        return record
    directory = _job_dir(job_id)
    (directory / "cancel.requested").write_text(utc_now(), encoding="utf-8")
    pid = record.get("pid")
    if status == "running" and _pid_alive(pid):
        try:
            os.killpg(int(pid), signal.SIGTERM)
        except Exception:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except Exception:
                pass
    record.update({
        "status": "cancelled",
        "stage": "cancelled",
        "progress": float(record.get("progress") or 0.0),
        "updated_at": utc_now(),
        "finished_at": utc_now(),
        "pid": None,
        "error": None,
    })
    write_job(record)
    return record


def requeue_job(job_id: str) -> dict[str, Any]:
    record = read_job(job_id)
    if not record:
        raise FileNotFoundError(job_id)
    if record.get("status") not in {"failed", "interrupted", "cancelled"}:
        raise ValueError("only failed, interrupted or cancelled jobs can be requeued")
    directory = _job_dir(job_id)
    try:
        (directory / "cancel.requested").unlink()
    except FileNotFoundError:
        pass
    record.update({
        "status": "queued",
        "stage": "queued-for-retry",
        "progress": 0.0,
        "updated_at": utc_now(),
        "started_at": None,
        "finished_at": None,
        "pid": None,
        "error": None,
        "result_path": None,
    })
    write_job(record)
    return record


def read_result(job_id: str) -> dict[str, Any] | None:
    record = read_job(job_id)
    if not record:
        return None
    path = record.get("result_path")
    if not path:
        candidate = _job_dir(job_id) / "result.json"
    else:
        candidate = Path(str(path))
    return _read_json(candidate) if candidate.exists() else None


def tail_log(job_id: str, *, max_chars: int = 12000) -> str:
    path = _job_dir(job_id) / "worker.log"
    if not path.exists():
        return ""
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return data[-max(1000, min(int(max_chars), 100000)) :]


def queue_summary() -> dict[str, int]:
    summary = {"queued": 0, "running": 0, "succeeded": 0, "failed": 0, "cancelled": 0, "interrupted": 0}
    for row in list_jobs(limit=500):
        state = str(row.get("status") or "")
        if state in summary:
            summary[state] += 1
    return summary


def render_compute_workspace(st: Any, profile: str, namespace: Mapping[str, Any] | None = None) -> None:
    """Render the first kernel-native compute workspace without replacing legacy UI."""
    root = _data_root()
    st.markdown("---")
    st.markdown("## Physical Lab · Experiment Kernel & Compute")
    st.caption(
        "Kernel-native experiment identity plus a durable local child-process queue. "
        "This separates computation lifecycle from Streamlit reruns."
    )
    if root is None:
        st.info("Compute Engine needs PHYSICAL_LAB_DATA_DIR from the desktop shell. Interactive Lab execution remains available.")
        return

    reconcile_jobs()
    control_left, control_right = st.columns([2, 1])
    max_parallel = control_right.select_slider(
        "Local worker limit", options=[1, 2, 3, 4], value=1,
        key=f"pl_compute_parallel_{profile}",
        help="Bounded local process concurrency. Heavy native solvers are not yet migrated into this queue.",
    )
    start_queued_jobs(max_parallel=int(max_parallel))

    source_commit = None
    try:
        source_commit = os.environ.get("PHYSICAL_LAB_SOURCE_COMMIT") or None
    except Exception:
        pass
    manifest = build_session_manifest(profile, namespace or {}, st.session_state, source_commit=source_commit)
    summary = manifest_summary(manifest)
    control_left.write({
        "profile": summary["profile"],
        "experiment_sha256": summary["experiment_sha256"],
        "parameters": summary["parameter_count"],
        "adapter_capabilities": PROFILE_CONTRACTS[profile]["worker_capabilities"],
        "resource_estimate": summary["resource_estimate"],
    })

    a, b, c = st.columns(3)
    if a.button("Queue manifest validation", key=f"pl_compute_manifest_{profile}", width="stretch"):
        submit_job(manifest, runner="manifest-validate", priority=60)
        st.success("Experiment manifest queued.")
        st.rerun()

    can_campaign = "model-campaign" in PROFILE_CONTRACTS[profile]["worker_capabilities"]
    preset = b.selectbox(
        "Queued campaign depth", ["compact", "standard"], index=0,
        disabled=not can_campaign, key=f"pl_compute_preset_{profile}",
    )
    if c.button(
        "Queue model campaign", type="primary", width="stretch", disabled=not can_campaign,
        key=f"pl_compute_campaign_{profile}",
    ):
        campaign_manifest = build_session_manifest(
            profile, namespace or {}, st.session_state,
            execution={"mode": "model-campaign", "preset": preset},
            source_commit=source_commit,
        )
        submit_job(
            campaign_manifest, runner="model-campaign",
            runner_config={"profile": profile, "preset": preset}, priority=70,
        )
        st.success("Kernel-native campaign queued in a child worker.")
        st.rerun()
    if not can_campaign:
        st.caption(PROFILE_CONTRACTS[profile].get("migration_note", "Worker-native solver adapter is not available yet."))

    jobs = list_jobs(limit=40)
    state = queue_summary()
    cols = st.columns(6)
    for col, key in zip(cols, ("queued", "running", "succeeded", "failed", "cancelled", "interrupted")):
        col.metric(key.title(), state[key])

    if not jobs:
        st.caption("No compute jobs yet.")
        return
    import pandas as pd
    table = pd.DataFrame([
        {
            "id": row.get("id"),
            "profile": row.get("profile"),
            "runner": row.get("runner"),
            "status": row.get("status"),
            "progress": row.get("progress"),
            "stage": row.get("stage"),
            "attempt": row.get("attempt"),
            "created_at": row.get("created_at"),
        }
        for row in jobs
    ])
    st.dataframe(table, width="stretch", hide_index=True)

    ids = [str(row["id"]) for row in jobs]
    selected = st.selectbox("Inspect compute job", ids, key=f"pl_compute_inspect_{profile}")
    record = read_job(selected) or {}
    j1, j2, j3 = st.columns(3)
    if j1.button("Refresh queue", key=f"pl_compute_refresh_{profile}", width="stretch"):
        st.rerun()
    if j2.button(
        "Cancel job", key=f"pl_compute_cancel_{profile}", width="stretch",
        disabled=str(record.get("status")) not in ACTIVE_STATES,
    ):
        cancel_job(selected)
        st.rerun()
    if j3.button(
        "Requeue job", key=f"pl_compute_retry_{profile}", width="stretch",
        disabled=str(record.get("status")) not in {"failed", "interrupted", "cancelled"},
    ):
        requeue_job(selected)
        st.rerun()

    st.write({
        "status": record.get("status"),
        "stage": record.get("stage"),
        "progress": record.get("progress"),
        "pid": record.get("pid"),
        "attempt": record.get("attempt"),
        "checkpoint": record.get("checkpoint"),
        "error": record.get("error"),
    })
    result = read_result(selected)
    if result:
        with st.expander("Job result", expanded=False):
            st.json(result)
        if record.get("runner") == "model-campaign" and record.get("profile") == profile:
            if st.button("Publish campaign result to this Lab", key=f"pl_compute_publish_{profile}", type="primary"):
                campaign = result.get("result") if isinstance(result.get("result"), Mapping) else result
                st.session_state[f"pl_model_campaign_result_{profile}"] = campaign
                if isinstance(campaign, Mapping) and isinstance(campaign.get("metrics"), Mapping):
                    st.session_state[f"pl_model_campaign_metrics_{profile}"] = dict(campaign["metrics"])
                st.success("Queued campaign result published to the current Lab scorecard state.")
                st.rerun()
    log = tail_log(selected)
    if log:
        with st.expander("Worker log", expanded=False):
            st.code(log, language="text")
