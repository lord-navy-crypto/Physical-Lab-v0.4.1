#!/usr/bin/env python3
"""CLI for Physical Lab cross-checks and evidence snapshots/diffs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_cross_checks as cross_checks
import physical_lab_evidence_diff as evidence_diff


def emit(value: object) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Physical Lab Evidence Review CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    matrix = sub.add_parser("cross-check-matrix", help="Evaluate all registered cross-checks")
    matrix.add_argument("project")

    evaluate = sub.add_parser("cross-check", help="Evaluate one cross-check")
    evaluate.add_argument("project")
    evaluate.add_argument("cross_check_id")

    snapshot = sub.add_parser("snapshot", help="Write a project evidence snapshot")
    snapshot.add_argument("project")
    snapshot.add_argument("--label", default="")

    diff = sub.add_parser("diff", help="Compare two saved evidence snapshots")
    diff.add_argument("before")
    diff.add_argument("after")
    diff.add_argument("--markdown", action="store_true")

    args = parser.parse_args()
    if args.command == "cross-check-matrix":
        emit(cross_checks.cross_check_matrix(args.project))
    elif args.command == "cross-check":
        emit(cross_checks.evaluate_cross_check(args.project, args.cross_check_id))
    elif args.command == "snapshot":
        path, value = evidence_diff.write_evidence_snapshot(args.project, label=args.label)
        emit({"path": str(path), "snapshot": value})
    elif args.command == "diff":
        before = evidence_diff.load_evidence_snapshot(args.before)
        after = evidence_diff.load_evidence_snapshot(args.after)
        value = evidence_diff.diff_evidence_snapshots(before, after)
        if args.markdown:
            print(evidence_diff.render_evidence_diff_markdown(value))
        else:
            emit(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
