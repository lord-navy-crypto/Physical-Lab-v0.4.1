#!/usr/bin/env python3
"""Headless CLI for Physical Lab .physlab Project Kernel v1."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_project_kernel as projects  # noqa: E402


def _require_data_dir(value: str | None) -> None:
    if value:
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(Path(value).expanduser().resolve())
    if not os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip():
        raise SystemExit("PHYSICAL_LAB_DATA_DIR is required (or pass --data-dir)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Physical Lab .physlab Project Kernel CLI")
    parser.add_argument("--data-dir", help="Physical Lab data directory")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a .physlab project")
    create.add_argument("name")
    create.add_argument("--description", default="")
    create.add_argument("--question", default="")
    create.add_argument("--slug")

    sub.add_parser("list", help="List .physlab projects")

    summary = sub.add_parser("summary", help="Show project summary")
    summary.add_argument("project")

    register = sub.add_parser("register", help="Register an Experiment Kernel manifest")
    register.add_argument("project")
    register.add_argument("manifest")

    sync = sub.add_parser("sync", help="Synchronize matching Compute Engine jobs/results")
    sync.add_argument("project")

    report = sub.add_parser("report", help="Generate Markdown project report")
    report.add_argument("project")
    report.add_argument("--generated-at")

    args = parser.parse_args()
    _require_data_dir(args.data_dir)

    if args.command == "create":
        path, doc = projects.create_project(
            args.name,
            description=args.description,
            research_question=args.question,
            slug=args.slug,
        )
        print(json.dumps({"path": str(path), "project": doc}, indent=2))
        return 0
    if args.command == "list":
        print(json.dumps(projects.list_projects(), indent=2))
        return 0
    if args.command == "summary":
        print(json.dumps(projects.project_summary(args.project), indent=2))
        return 0
    if args.command == "register":
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        entry = projects.register_experiment(args.project, manifest)
        print(json.dumps(entry, indent=2))
        return 0
    if args.command == "sync":
        print(json.dumps(projects.sync_compute_jobs(args.project), indent=2))
        return 0
    if args.command == "report":
        path, _ = projects.write_project_report(args.project, generated_at=args.generated_at)
        print(str(path))
        return 0
    raise SystemExit("unsupported command")


if __name__ == "__main__":
    raise SystemExit(main())
