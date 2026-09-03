#!/usr/bin/env python3
"""Physical Lab research CLI for the shared digital-twin scientific core."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(CORE_DIR))

from physical_lab_digital_twin import (
    analyze_beam_phase_space,
    compare_field_series,
    fit_linear_calibration,
    fit_model_affine,
    suggest_residual_measurement_points,
)


def read_columns(path: Path, names: list[str]) -> dict[str, list[float]]:
    if not path.is_file():
        raise SystemExit(f"Dataset not found: {path}")
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    out = {name: [] for name in names}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        missing = [name for name in names if name not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit("Missing column(s): " + ", ".join(missing))
        for row in reader:
            for name in names:
                try:
                    out[name].append(float(row[name]))
                except (TypeError, ValueError):
                    out[name].append(float("nan"))
    return out


def emit(payload: dict, output: str | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(output)
    else:
        print(text, end="")


def main() -> int:
    parser = argparse.ArgumentParser(description="Physical Lab digital-twin CSV tools")
    parser.add_argument("--output", help="optional JSON output path")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("calibrate", help="fit reference = slope*raw + offset")
    p.add_argument("csv"); p.add_argument("--raw", required=True); p.add_argument("--reference", required=True)

    p = sub.add_parser("field-compare", help="compare measured and model field columns")
    p.add_argument("csv"); p.add_argument("--position", required=True); p.add_argument("--measured", required=True); p.add_argument("--model", required=True)

    p = sub.add_parser("inverse-affine", help="fit measured ≈ scale*model + offset")
    p.add_argument("csv"); p.add_argument("--measured", required=True); p.add_argument("--model", required=True)

    p = sub.add_parser("phase-space", help="compute x/px and y/py RMS emittance/Twiss statistics")
    p.add_argument("csv"); p.add_argument("--x", required=True); p.add_argument("--px", required=True); p.add_argument("--y", required=True); p.add_argument("--py", required=True); p.add_argument("--beta-gamma", type=float)

    p = sub.add_parser("suggest-points", help="residual-guided measurement locations")
    p.add_argument("csv"); p.add_argument("--position", required=True); p.add_argument("--measured", required=True); p.add_argument("--model", required=True); p.add_argument("--count", type=int, default=3)

    args = parser.parse_args()
    path = Path(getattr(args, "csv"))

    if args.command == "calibrate":
        c = read_columns(path, [args.raw, args.reference])
        payload = {"schema":"physical-lab-calibration-result-v1", "result": fit_linear_calibration(c[args.raw], c[args.reference]).to_dict()}
    elif args.command == "field-compare":
        c = read_columns(path, [args.position, args.measured, args.model])
        payload = {"schema":"physical-lab-field-comparison-v1", "result": compare_field_series(c[args.position], c[args.measured], c[args.model]).to_dict()}
    elif args.command == "inverse-affine":
        c = read_columns(path, [args.measured, args.model])
        payload = {"schema":"physical-lab-affine-inverse-v1", "result": fit_model_affine(c[args.measured], c[args.model]).to_dict()}
    elif args.command == "phase-space":
        c = read_columns(path, [args.x, args.px, args.y, args.py])
        payload = {"schema":"physical-lab-beam-phase-space-v1", "result": analyze_beam_phase_space(c[args.x], c[args.px], c[args.y], c[args.py], beta_gamma=args.beta_gamma).to_dict()}
    else:
        c = read_columns(path, [args.position, args.measured, args.model])
        payload = {
            "schema":"physical-lab-residual-guided-sampling-v1",
            "result": suggest_residual_measurement_points(c[args.position], c[args.measured], c[args.model], count=max(1, args.count)),
            "boundary":"Transparent residual heuristic; not Bayesian information gain or globally optimal experimental design.",
        }
    emit(payload, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
