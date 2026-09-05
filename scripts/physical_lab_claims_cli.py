#!/usr/bin/env python3
"""CLI for Physical Lab Claim-to-Evidence records."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_claims as claims


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect Physical Lab claim-to-evidence readiness.")
    sub = parser.add_subparsers(dest="command", required=True)

    matrix = sub.add_parser("matrix", help="Render the project claim-to-evidence matrix")
    matrix.add_argument("project")
    matrix.add_argument("--format", choices=("json", "markdown"), default="json")

    evaluate = sub.add_parser("evaluate", help="Evaluate one claim")
    evaluate.add_argument("project")
    evaluate.add_argument("claim_id")

    args = parser.parse_args(argv)
    project = Path(args.project).expanduser().resolve()
    if args.command == "evaluate":
        print(json.dumps(claims.evaluate_claim(project, args.claim_id), indent=2, sort_keys=True))
    else:
        value = claims.claim_evidence_matrix(project)
        print(claims.render_matrix_markdown(value) if args.format == "markdown" else json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
