#!/usr/bin/env python3
"""Command-line access to Physical Lab evidence-first Credibility Passports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_credibility as credibility


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a Physical Lab Credibility Passport for a .physlab project.")
    parser.add_argument("project", help="Path to a .physlab project directory")
    parser.add_argument("--experiment", dest="experiment_id", help="Optional experiment ID scope")
    parser.add_argument("--job", dest="job_id", help="Optional job ID scope")
    parser.add_argument("--format", choices=("summary", "json", "markdown"), default="summary")
    parser.add_argument("--write", action="store_true", help="Persist JSON + Markdown passport inside the project")
    args = parser.parse_args(argv)

    project = Path(args.project).expanduser().resolve()
    if args.write:
        json_path, markdown_path, passport = credibility.write_credibility_passport(
            project,
            experiment_id=args.experiment_id,
            job_id=args.job_id,
        )
        print(f"wrote_json={json_path}")
        print(f"wrote_markdown={markdown_path}")
    else:
        passport = credibility.build_credibility_passport(
            project,
            experiment_id=args.experiment_id,
            job_id=args.job_id,
        )

    if args.format == "json":
        print(json.dumps(passport, indent=2, sort_keys=True))
    elif args.format == "markdown":
        print(credibility.render_passport_markdown(passport))
    else:
        print(json.dumps(credibility.passport_summary(passport), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
