#!/usr/bin/env python3
"""Deterministic validation for Experiment Kernel v1 + local Compute Engine v1."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_experiment_kernel as kernel  # noqa: E402
import physical_lab_compute_engine as compute  # noqa: E402
import physical_lab_job_worker as worker  # noqa: E402

EXPECTED = {
    "numerical-methods", "ising-monte-carlo", "random-walk-monte-carlo",
    "nonlinear-chaos", "oscillation-integration", "radia-magnet-studio",
    "radiation-platform",
}
assert EXPECTED == set(kernel.PROFILE_CONTRACTS)
assert all("manifest" in item["worker_capabilities"] for item in kernel.PROFILE_CONTRACTS.values())
assert all(
    "model-campaign" in kernel.PROFILE_CONTRACTS[p]["worker_capabilities"]
    for p in EXPECTED - {"radia-magnet-studio", "radiation-platform"}
)
assert kernel.PROFILE_CONTRACTS["radia-magnet-studio"]["worker_capabilities"] == ["manifest"]
assert kernel.PROFILE_CONTRACTS["radiation-platform"]["worker_capabilities"] == ["manifest"]

# Scientific identity is stable across timestamps and changes when parameters change.
a = kernel.build_experiment_manifest(
    "numerical-methods",
    parameters={"x": 1.0, "terms": 11},
    execution={"mode": "model-campaign", "preset": "compact"},
    provenance={"engine_mode": "safe", "source_commit": "abc123"},
    created_at="2026-01-01T00:00:00+00:00",
)
b = kernel.build_experiment_manifest(
    "numerical-methods",
    parameters={"x": 1.0, "terms": 11},
    execution={"mode": "model-campaign", "preset": "compact"},
    provenance={"engine_mode": "safe", "source_commit": "abc123"},
    created_at="2026-02-01T00:00:00+00:00",
)
assert a["experiment_sha256"] == b["experiment_sha256"]
c = kernel.build_experiment_manifest(
    "numerical-methods",
    parameters={"x": 1.0, "terms": 13},
    execution={"mode": "model-campaign", "preset": "compact"},
    provenance={"engine_mode": "safe", "source_commit": "abc123"},
)
assert c["experiment_sha256"] != a["experiment_sha256"]
assert kernel.validate_manifest(a)["valid"] is True
assert len(a["experiment_sha256"]) == 64

# Session adapter excludes result-like payloads while retaining simple inputs.
session_manifest = kernel.build_session_manifest(
    "oscillation-integration",
    {"frequency_result": 1.23, "helper": object()},
    {"gamma": 0.1, "pl_o_force": 0.5, "scan_result": [1, 2, 3], "__private": 5},
)
assert session_manifest["parameters"]["gamma"] == 0.1
assert session_manifest["parameters"]["pl_o_force"] == 0.5
assert "scan_result" not in session_manifest["parameters"]
assert "__private" not in session_manifest["parameters"]
assert session_manifest["result_reference"]["frequency_result"] == 1.23

# Resource estimates are explicit hints and bounded.
for profile in EXPECTED:
    estimate = kernel.estimate_resources(profile, {"preset": "compact"})
    assert estimate["resource_class"] in {"light", "medium", "heavy"}
    assert 1 <= estimate["cpu_slots"] <= 2
    assert estimate["memory_mb_hint"] >= 512

old_data = os.environ.get("PHYSICAL_LAB_DATA_DIR")
try:
    with tempfile.TemporaryDirectory() as td:
        os.environ["PHYSICAL_LAB_DATA_DIR"] = td

        # Durable queued manifest-validation job.
        queued = compute.submit_job(a, runner="manifest-validate", priority=70)
        assert queued["status"] == "queued"
        assert compute.read_job(queued["id"])["status"] == "queued"
        job_dir = Path(td) / "compute-jobs" / queued["id"]
        assert (job_dir / "manifest.json").exists()
        output = worker.execute_job(job_dir)
        finished = compute.read_job(queued["id"])
        assert finished["status"] == "succeeded"
        assert finished["progress"] == 1.0
        assert finished["checkpoint"]["stage"] == "result-persisted"
        assert output["result"]["valid"] is True
        assert compute.read_result(queued["id"])["experiment_sha256"] == a["experiment_sha256"]

        # Real model campaign executes outside Streamlit through the allow-listed worker.
        campaign_manifest = kernel.build_experiment_manifest(
            "numerical-methods",
            parameters={"validation_fixture": True},
            execution={"mode": "model-campaign", "preset": "compact"},
            provenance={"engine_mode": "safe"},
        )
        campaign_job = compute.submit_job(
            campaign_manifest,
            runner="model-campaign",
            runner_config={"profile": "numerical-methods", "preset": "compact"},
        )
        campaign_dir = Path(td) / "compute-jobs" / campaign_job["id"]
        campaign_output = worker.execute_job(campaign_dir)
        campaign_record = compute.read_job(campaign_job["id"])
        assert campaign_record["status"] == "succeeded"
        assert campaign_output["result"]["schema"] == "physical-lab-model-campaign-v1"
        assert campaign_output["result"]["profile"] == "numerical-methods"
        assert campaign_output["result"]["metrics"]["pass_fraction"] >= 0.99

        # Queue policy refuses arbitrary code execution and unsupported native migration claims.
        try:
            compute.submit_job(a, runner="python-eval")
        except ValueError:
            pass
        else:
            raise AssertionError("arbitrary runner must be rejected")

        radia = kernel.build_experiment_manifest("radia-magnet-studio")
        try:
            compute.submit_job(
                radia, runner="model-campaign",
                runner_config={"profile": "radia-magnet-studio", "preset": "compact"},
            )
        except ValueError:
            pass
        else:
            raise AssertionError("RADIA worker-native campaign must not be falsely advertised")

        # Cancellation and explicit requeue are durable state transitions.
        cancelled_job = compute.submit_job(a, runner="manifest-validate")
        cancelled = compute.cancel_job(cancelled_job["id"])
        assert cancelled["status"] == "cancelled"
        assert (Path(td) / "compute-jobs" / cancelled_job["id"] / "cancel.requested").exists()
        requeued = compute.requeue_job(cancelled_job["id"])
        assert requeued["status"] == "queued"
        assert not (Path(td) / "compute-jobs" / cancelled_job["id"] / "cancel.requested").exists()

        summary = compute.queue_summary()
        assert summary["succeeded"] == 2
        assert summary["queued"] == 1
finally:
    if old_data is None:
        os.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
    else:
        os.environ["PHYSICAL_LAB_DATA_DIR"] = old_data

print("PASS Experiment Kernel v1: seven-Lab contracts, stable scientific fingerprints, bounded session adapters")
print("PASS Compute Engine v1: durable queue, allow-listed child-worker execution, checkpoints, cancellation and requeue")
print("PASS kernel-native numerical model campaign outside Streamlit UI lifecycle")
print("Boundary: RADIA/Radiation are manifest-ready but native worker solver migration is intentionally not claimed yet")
