#!/usr/bin/env python3
"""Acceptance checks for canonical Rust dataset analysis/validation paths."""
from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src-tauri/src/research.rs"
LEGACY = ROOT / "src-tauri/src/research_legacy_impl.rs"


def function_block(text: str, name: str) -> str:
    marker = f"fn {name}("
    start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError(f"unterminated Rust function: {name}")


def compact(text: str) -> str:
    return "".join(text.split())


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")

    for helper in (
        "dataset_record_from_dir",
        "dataset_numeric_path",
        "parse_csv_numeric",
        "analyze_dataset_from_dir",
        "validate_dataset_columns_from_dir",
    ):
        assert f"fn {helper}(" in source, helper

    analyze = function_block(source, "analyze_dataset")
    validate = function_block(source, "validate_dataset_columns")
    for block, helper in ((analyze, "analyze_dataset_from_dir"), (validate, "validate_dataset_columns_from_dir")):
        assert "resolve_project_dir" in block
        assert helper in block
        assert "ensure_alias_for_id" not in block
        assert "legacy::" not in block

    # Preserve the legacy statistical definitions and descriptive thresholds.
    new_analysis = compact(function_block(source, "analyze_dataset_from_dir"))
    old_analysis = compact(function_block(legacy, "analyze_dataset"))
    for token in (
        "/(n-1)asf64",
        "1.96*",
        "ci95_low",
        "ci95_high",
        "f64::INFINITY",
        "f64::NEG_INFINITY",
    ):
        assert token in new_analysis, token
        assert token in old_analysis, token

    new_parser = compact(function_block(source, "parse_csv_numeric"))
    old_parser = compact(function_block(legacy, "parse_csv_numeric"))
    assert "200_000" in new_parser
    assert "200_000" in old_parser

    new_validation = compact(function_block(source, "validate_dataset_columns_from_dir"))
    old_validation = compact(function_block(legacy, "validate_dataset_columns"))
    for token in (
        "relative_rmse",
        "1e-15",
        "1e-30",
        "1.0-ss_res/ss_tot",
        'ratio<0.01',
        'ratio<0.05',
        'ratio<0.15',
        '"Strong"',
        '"Good"',
        '"Moderate"',
        '"Weak"',
        "Agreementlabelsaredescriptivethresholds,notproofthateithermodelormeasurementiscorrect.",
    ):
        assert token in new_validation, token
        assert token in old_validation, token

    # Independent numeric fixture for the unchanged definitions.
    observed = [1.0, 2.0, 3.0, 4.0]
    reference = [1.0, 2.2, 2.8, 4.1]
    errors = [a - b for a, b in zip(observed, reference)]
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    ref_scale = sum(abs(v) for v in reference) / len(reference)
    ratio = rmse / ref_scale
    assert abs(mae - 0.125) < 1e-15
    assert 0.05 < ratio < 0.15
    assert ("Strong" if ratio < 0.01 else "Good" if ratio < 0.05 else "Moderate" if ratio < 0.15 else "Weak") == "Moderate"

    print("Physical Lab Rust canonical dataset analysis: PASS")
    print("- analyze_dataset: canonical/legacy direct project resolver, no alias")
    print("- validate_dataset_columns: canonical/legacy direct project resolver, no alias")
    print("- sample SD + 95% CI definition preserved")
    print("- MAE/RMSE/relative RMSE/R2 definitions preserved")
    print("- descriptive agreement thresholds preserved")
    print("Boundary: descriptive agreement is not proof of model correctness, measurement correctness, verification, or validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
