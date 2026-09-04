#!/usr/bin/env python3
"""Child-process worker for Physical Lab's persistent compute queue."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import traceback
from pathlib import Path
from typing import Any, Mapping

from physical_lab_experiment_kernel import plain, utc_now, validate_manifest

_CANCELLED = False


def _signal_cancel(_signum, _frame):
    global _CANCELLED
    _CANCELLED = True


for _sig in (signal.SIGTERM, signal.SIGINT):
    try:
        signal.signal(_sig, _signal_cancel)
    except Exception:
        pass


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(plain(dict(value)), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _cancel_requested(job_dir: Path) -> bool:
    return _CANCELLED or (job_dir / "cancel.requested").exists()


def _update(job_dir: Path, **changes: Any) -> dict[str, Any]:
    path = job_dir / "job.json"
    record = _read_json(path)
    record.update(changes)
    record["updated_at"] = utc_now()
    _atomic_json(path, record)
    return record


def _checkpoint(job_dir: Path, stage: str, progress: float, payload: Mapping[str, Any] | None = None) -> None:
    value = {
        "schema": "physical-lab-job-checkpoint-v1",
        "stage": stage,
        "progress": float(progress),
        "updated_at": utc_now(),
        "payload": plain(dict(payload or {})),
    }
    _atomic_json(job_dir / "checkpoint.json", value)
    _update(job_dir, stage=stage, progress=float(progress), checkpoint=value)


def _fail_if_cancelled(job_dir: Path) -> None:
    if _cancel_requested(job_dir):
        _update(
            job_dir,
            status="cancelled",
            stage="cancelled",
            finished_at=utc_now(),
            pid=None,
            error=None,
        )
        raise SystemExit(130)


def execute_job(job_dir: Path) -> dict[str, Any]:
    job_dir = job_dir.resolve()
    record = _read_json(job_dir / "job.json")
    manifest = _read_json(job_dir / "manifest.json")
    runner = str(record.get("runner") or "")
    config = record.get("runner_config") or {}

    _update(
        job_dir,
        status="running",
        stage="validating-manifest",
        progress=max(float(record.get("progress") or 0.0), 0.05),
        pid=os.getpid(),
        started_at=record.get("started_at") or utc_now(),
        finished_at=None,
        error=None,
    )
    _fail_if_cancelled(job_dir)

    check = validate_manifest(manifest)
    if not check["valid"]:
        raise ValueError("invalid experiment manifest: " + "; ".join(check["errors"]))
    _checkpoint(job_dir, "manifest-validated", 0.15, {"experiment_sha256": manifest.get("experiment_sha256")})
    _fail_if_cancelled(job_dir)

    if runner == "manifest-validate":
        output = {
            "schema": "physical-lab-job-result-v1",
            "runner": runner,
            "profile": manifest.get("profile"),
            "experiment_sha256": manifest.get("experiment_sha256"),
            "validation": check,
            "result": {
                "valid": True,
                "parameter_count": len(manifest.get("parameters") or {}),
                "input_count": len(manifest.get("inputs") or {}),
            },
            "completed_at": utc_now(),
        }
    elif runner == "model-campaign":
        profile = str(config.get("profile") or manifest.get("profile") or "")
        preset = str(config.get("preset") or "compact")
        _checkpoint(job_dir, "campaign-starting", 0.25, {"profile": profile, "preset": preset})
        _fail_if_cancelled(job_dir)
        from physical_lab_model_campaigns import run_campaign
        campaign = run_campaign(profile, preset)
        _fail_if_cancelled(job_dir)
        _checkpoint(job_dir, "campaign-computed", 0.90, {"campaign_sha256": campaign.get("campaign_sha256")})
        output = {
            "schema": "physical-lab-job-result-v1",
            "runner": runner,
            "profile": profile,
            "experiment_sha256": manifest.get("experiment_sha256"),
            "result": campaign,
            "completed_at": utc_now(),
        }
    else:
        raise ValueError(f"runner is not allow-listed: {runner}")

    result_path = job_dir / "result.json"
    _atomic_json(result_path, output)
    _checkpoint(job_dir, "result-persisted", 0.98, {"result_path": str(result_path)})
    final = _update(
        job_dir,
        status="succeeded",
        stage="complete",
        progress=1.0,
        finished_at=utc_now(),
        pid=None,
        error=None,
        result_path=str(result_path),
    )
    print(f"Physical Lab job {final.get('id')} succeeded: {runner}", flush=True)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, help="Physical Lab compute job directory")
    args = parser.parse_args(argv)
    job_dir = Path(args.job).resolve()
    try:
        execute_job(job_dir)
        return 0
    except SystemExit as exc:
        return int(exc.code or 1)
    except Exception as exc:
        try:
            _update(
                job_dir,
                status="failed",
                stage="failed",
                finished_at=utc_now(),
                pid=None,
                error=f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            pass
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
