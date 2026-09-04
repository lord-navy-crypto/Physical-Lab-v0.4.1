#!/usr/bin/env python3
"""Developer/diagnostic CLI for Physical Lab Experiment Kernel + Compute Engine."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_compute_engine as compute  # noqa: E402
import physical_lab_experiment_kernel as kernel  # noqa: E402


def _configure_data_dir(value: str | None) -> None:
    if value:
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(Path(value).expanduser().resolve())
    if not os.environ.get("PHYSICAL_LAB_DATA_DIR"):
        raise SystemExit("PHYSICAL_LAB_DATA_DIR is required (or pass --data-dir)")


def _print(value) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Physical Lab local compute queue")
    parser.add_argument("--data-dir", help="Override PHYSICAL_LAB_DATA_DIR")
    sub = parser.add_subparsers(dest="command", required=True)

    p_manifest = sub.add_parser("manifest", help="Create a minimal kernel manifest")
    p_manifest.add_argument("profile", choices=sorted(kernel.PROFILE_CONTRACTS))
    p_manifest.add_argument("--preset", choices=["compact", "standard"])

    p_submit = sub.add_parser("submit-campaign", help="Queue a migrated model campaign")
    p_submit.add_argument("profile", choices=sorted(kernel.PROFILE_CONTRACTS))
    p_submit.add_argument("--preset", choices=["compact", "standard"], default="compact")
    p_submit.add_argument("--priority", type=int, default=70)

    p_validate = sub.add_parser("submit-validation", help="Queue manifest validation")
    p_validate.add_argument("profile", choices=sorted(kernel.PROFILE_CONTRACTS))

    p_start = sub.add_parser("start", help="Start queued workers")
    p_start.add_argument("--parallel", type=int, default=1)

    p_list = sub.add_parser("list", help="List durable compute jobs")
    p_list.add_argument("--profile", choices=sorted(kernel.PROFILE_CONTRACTS))
    p_list.add_argument("--limit", type=int, default=50)

    p_inspect = sub.add_parser("inspect", help="Inspect one job and optional result")
    p_inspect.add_argument("job_id")

    p_cancel = sub.add_parser("cancel", help="Cancel a queued/running job")
    p_cancel.add_argument("job_id")

    p_requeue = sub.add_parser("requeue", help="Requeue failed/interrupted/cancelled job")
    p_requeue.add_argument("job_id")

    args = parser.parse_args(argv)
    _configure_data_dir(args.data_dir)

    if args.command == "manifest":
        execution = {"mode": "model-campaign", "preset": args.preset} if args.preset else {"mode": "manual"}
        manifest = kernel.build_experiment_manifest(args.profile, execution=execution)
        _print(manifest)
    elif args.command == "submit-campaign":
        manifest = kernel.build_experiment_manifest(
            args.profile,
            execution={"mode": "model-campaign", "preset": args.preset},
            provenance={"capture": "physical_lab_compute_cli"},
        )
        _print(compute.submit_job(
            manifest,
            runner="model-campaign",
            runner_config={"profile": args.profile, "preset": args.preset},
            priority=args.priority,
        ))
    elif args.command == "submit-validation":
        manifest = kernel.build_experiment_manifest(
            args.profile,
            execution={"mode": "manifest-validation"},
            provenance={"capture": "physical_lab_compute_cli"},
        )
        _print(compute.submit_job(manifest, runner="manifest-validate"))
    elif args.command == "start":
        _print({"started": compute.start_queued_jobs(max_parallel=args.parallel)})
    elif args.command == "list":
        compute.reconcile_jobs()
        _print(compute.list_jobs(limit=args.limit, profile=args.profile))
    elif args.command == "inspect":
        _print({
            "job": compute.read_job(args.job_id),
            "result": compute.read_result(args.job_id),
            "log_tail": compute.tail_log(args.job_id),
        })
    elif args.command == "cancel":
        _print(compute.cancel_job(args.job_id))
    elif args.command == "requeue":
        _print(compute.requeue_job(args.job_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
