#!/usr/bin/env python3
"""Deterministic validation for Physical Lab Run & Diagnostics Log."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src-tauri" / "resources" / "ui" / "physical_lab_diagnostics.py"


def load_module():
    spec = importlib.util.spec_from_file_location("physical_lab_diagnostics_validation", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load physical_lab_diagnostics.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MockCompute:
    def __init__(self):
        self.jobs = [
            {
                "id": "job-test-ok",
                "profile": "numerical-methods",
                "experiment_sha256": "a" * 64,
                "runner": "manifest-validate",
                "status": "succeeded",
                "progress": 1.0,
                "stage": "complete",
                "attempt": 1,
                "created_at": "2026-09-04T12:00:00Z",
                "updated_at": "2026-09-04T12:00:02Z",
                "started_at": "2026-09-04T12:00:01Z",
                "finished_at": "2026-09-04T12:00:02Z",
                "error": None,
            },
            {
                "id": "job-test-failed",
                "profile": "numerical-methods",
                "experiment_sha256": "b" * 64,
                "runner": "model-campaign",
                "status": "failed",
                "progress": 0.4,
                "stage": "failed",
                "attempt": 2,
                "created_at": "2026-09-04T12:01:00Z",
                "updated_at": "2026-09-04T12:01:04Z",
                "started_at": "2026-09-04T12:01:01Z",
                "finished_at": "2026-09-04T12:01:04Z",
                "error": "ValueError: synthetic failure",
            },
        ]

    def list_jobs(self, *, limit=100, profile=None):
        rows = [row for row in self.jobs if profile is None or row["profile"] == profile]
        return rows[:limit]

    def tail_log(self, job_id: str, *, max_chars=12000):
        if job_id == "job-test-failed":
            return (
                "[INFO] 2026-09-04T12:01:01Z worker-start\n"
                "[WARNING] 2026-09-04T12:01:02Z retrying bounded stage\n"
                "Traceback (most recent call last):\n"
                "ValueError: synthetic failure\n"
            )[-max_chars:]
        return "[INFO] 2026-09-04T12:00:02Z job succeeded\n"[-max_chars:]


def main() -> int:
    diagnostics = load_module()
    with tempfile.TemporaryDirectory(prefix="physical-lab-diagnostics-") as temp:
        old_root = os.environ.get("PHYSICAL_LAB_DATA_DIR")
        os.environ["PHYSICAL_LAB_DATA_DIR"] = temp
        try:
            diagnostics.emit_event(
                "info",
                "validation",
                "normal run",
                kind="run",
                profile="numerical-methods",
                run_id="run-1",
            )
            diagnostics.emit_event(
                "warn",
                "validation",
                "bounded warning",
                kind="run",
                profile="numerical-methods",
            )
            diagnostics.emit_event(
                "error",
                "validation",
                "token=super-secret synthetic error",
                kind="exception",
                profile="numerical-methods",
                detail={"authorization": "Bearer abc123", "password": "hidden"},
            )

            events = diagnostics.list_events(limit=50)
            assert len(events) == 3, events
            summary = diagnostics.severity_summary(events)
            assert summary == {"INFO": 1, "WARNING": 1, "ERROR": 1}, summary
            assert diagnostics.classify_log_line("all good") == "INFO"
            assert diagnostics.classify_log_line("WARNING: retrying") == "WARNING"
            assert diagnostics.classify_log_line("Traceback (most recent call last)") == "ERROR"

            raw_log = diagnostics.diagnostics_path().read_text(encoding="utf-8")
            assert "super-secret" not in raw_log
            assert "token=<redacted>" in raw_log

            compute = MockCompute()
            merged = diagnostics.collect_events_with_compute(
                compute,
                limit=100,
                profile="numerical-methods",
                include_worker_lines=True,
            )
            assert any(row.get("job_id") == "job-test-ok" for row in merged)
            assert any(row.get("job_id") == "job-test-failed" and row.get("severity") == "ERROR" for row in merged)
            assert any(row.get("kind") == "worker-log" and row.get("severity") == "WARNING" for row in merged)
            assert any(row.get("kind") == "worker-log" and row.get("severity") == "ERROR" for row in merged)

            bundle = diagnostics.build_support_bundle(merged, jobs=compute.jobs, profile="numerical-methods")
            assert bundle["schema"] == "physical-lab-support-bundle-v1"
            encoded = json.dumps(bundle, sort_keys=True)
            assert "super-secret" not in encoded
            assert "PHYSICAL_LAB_DATA_DIR" not in encoded
            assert "scientific result payloads are not exported" in bundle["privacy_boundary"]

            event_path = diagnostics.diagnostics_path()
            assert event_path is not None and event_path.exists()
            print("Diagnostics log validation: PASS")
            print(json.dumps({
                "persistent_events": len(events),
                "merged_events": len(merged),
                "summary": diagnostics.severity_summary(merged),
                "log_path": str(event_path),
            }, indent=2, sort_keys=True))
        finally:
            if old_root is None:
                os.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
            else:
                os.environ["PHYSICAL_LAB_DATA_DIR"] = old_root
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
