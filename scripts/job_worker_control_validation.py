#!/usr/bin/env python3
"""Acceptance checks for Physical Lab persistent-job campaign control.

This validation isolates the queue control plane from the scientific solvers. It
checks that generic campaigns publish heartbeats, persist a result atomically,
and can be cancelled promptly while the CPU-bound child is still running.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))


def load_worker():
    path = UI / "physical_lab_job_worker.py"
    spec = importlib.util.spec_from_file_location("physical_lab_job_worker_control_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


worker = load_worker()
worker._GENERIC_CAMPAIGN_POLL_S = 0.01
worker._GENERIC_CAMPAIGN_HEARTBEAT_S = 0.02
worker._GENERIC_CAMPAIGN_GRACE_S = 0.5

SUCCESS_SNIPPET = r"""
import json
import os
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
time.sleep(0.08)
result = {
    "schema": "physical-lab-model-campaign-v1",
    "profile": sys.argv[2],
    "preset": sys.argv[3],
    "metrics": {"control_probe": 1.0},
    "cases": [{"probe": "success"}],
}
temp = path.with_suffix(path.suffix + ".child-tmp")
temp.write_text(json.dumps(result), encoding="utf-8")
os.replace(temp, path)
"""

SLOW_SNIPPET = r"""
import time
while True:
    time.sleep(1.0)
"""


def make_job(root: Path, job_id: str) -> Path:
    job_dir = root / job_id
    job_dir.mkdir()
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "id": job_id,
                "status": "running",
                "stage": "campaign-starting",
                "progress": 0.25,
                "pid": 12345,
            }
        ),
        encoding="utf-8",
    )
    return job_dir


def assert_no_campaign_temp(job_dir: Path) -> None:
    assert not (job_dir / "generic-campaign-result.tmp.json").exists()
    assert not (job_dir / "generic-campaign-result.tmp.json.child-tmp").exists()


def test_success(root: Path) -> None:
    job_dir = make_job(root, "success")
    worker._GENERIC_CAMPAIGN_SNIPPET = SUCCESS_SNIPPET
    result = worker._run_generic_campaign_subprocess(
        job_dir,
        "numerical-methods",
        "compact",
    )
    assert result["metrics"]["control_probe"] == 1.0
    checkpoint = json.loads((job_dir / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["stage"] == "campaign-running"
    assert checkpoint["payload"]["progress_mode"] == "indeterminate"
    assert_no_campaign_temp(job_dir)
    print("PASS generic campaign success + heartbeat + cleanup")


def test_cancel(root: Path) -> None:
    job_dir = make_job(root, "cancel")
    worker._GENERIC_CAMPAIGN_SNIPPET = SLOW_SNIPPET

    def request_cancel() -> None:
        time.sleep(0.08)
        (job_dir / "cancel.requested").write_text("cancel", encoding="utf-8")

    thread = threading.Thread(target=request_cancel, daemon=True)
    thread.start()
    started = time.monotonic()
    try:
        worker._run_generic_campaign_subprocess(
            job_dir,
            "ising-monte-carlo",
            "standard",
        )
    except SystemExit as exc:
        assert int(exc.code) == 130
    else:
        raise AssertionError("generic campaign ignored queued cancellation")
    elapsed = time.monotonic() - started
    thread.join(timeout=1.0)

    record = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert record["status"] == "cancelled"
    assert record["stage"] == "cancelled"
    assert record["pid"] is None
    assert elapsed < 1.5, f"cancellation took too long: {elapsed:.3f}s"
    assert_no_campaign_temp(job_dir)
    print(f"PASS generic campaign cancellation latency={elapsed:.3f}s")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="physical-lab-job-control-") as temp:
        root = Path(temp)
        test_success(root)
        test_cancel(root)
    print("PASS persistent job-worker generic campaign control")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
