#!/usr/bin/env python3
"""Acceptance checks for canonical-native desktop measurement file import."""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src-tauri/src/research.rs"
LEGACY = ROOT / "src-tauri/src/research_legacy_impl.rs"

def compact(value: str) -> str:
    return "".join(value.split())

def function_block(text: str, name: str) -> str:
    marker = f"fn {name}("
    start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{": depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0: return text[start:index + 1]
    raise AssertionError(name)

def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")

    command = compact(function_block(source, "import_measurement_dataset"))
    assert "resolve_project_dir" in command
    assert "import_measurement_dataset_to_dir" in command
    assert "ensure_alias_for_id" not in command
    assert "legacy::" not in command
    assert "ifcanonical" in command
    assert "register_desktop_measurement" in command

    new_import = compact(function_block(source, "import_measurement_dataset_to_dir"))
    old_import = compact(function_block(legacy, "import_measurement_dataset"))
    for token in (
        'source.is_file()',
        '["csv","tsv","json","h5","hdf5"]',
        '"Supportedmeasurementformats:CSV,TSV,JSON,HDF5"',
        'project_dir.join("datasets")',
        'format!("data.{extension}")',
        'fs::copy(&source,&stored)',
        '"physical-lab-dataset-v1"',
        '"calibration":calibration',
        '"sourceFile":source.to_string_lossy()',
        '"storedFile":stored.to_string_lossy()',
        '"sha256":&digest',
        '"createdAt":&created_at',
        '"measurement":true',
        'touch_project_after_direct_write(project_dir,canonical)',
    ):
        assert token in new_import, token

    for token in (
        'src.is_file()',
        '["csv","tsv","json","h5","hdf5"]',
        '"Supportedmeasurementformats:CSV,TSV,JSON,HDF5"',
        'dir.join("datasets")',
        'format!("data.{ext}")',
        'fs::copy(&src,&stored)',
        '"physical-lab-dataset-v1"',
        '"calibration":&calibration',
        '"sourceFile":src.to_string_lossy()',
        '"storedFile":stored.to_string_lossy()',
        '"sha256":&hash',
        '"createdAt":&created',
        '"measurement":true',
    ):
        assert token in old_import, token

    new_hash = compact(function_block(source, "sha256_file"))
    old_hash = compact(function_block(legacy, "sha256"))
    for token in ('"/usr/bin/shasum"', '"-a","256"', 'split_whitespace()'):
        assert token in new_hash, token
        assert token in old_hash, token

    registration = compact(function_block(source, "register_desktop_measurement"))
    for token in (
        '"physical-lab-measurement-v1"',
        '"source_type":"desktop-data-bridge"',
        '"sha256":digest',
        'Calibrationstatus,sensoraccuracy,traceabilityandexperimentalvalidationmustbeestablishedseparately.',
    ):
        assert token in registration, token

    assert 'ifcanonical' in command
    print("Physical Lab Rust canonical measurement import: PASS")
    print("- CSV/TSV/JSON/HDF5 import formats preserved")
    print("- project-local dataset copy + SHA-256 metadata preserved")
    print("- canonical/legacy direct resolver, no compatibility alias")
    print("- canonical import registers Measurement Evidence")
    print("- genuine legacy fallback does not fabricate canonical evidence")
    print("Boundary: file integrity and project registration do not establish calibration accuracy, traceability, or experimental validation.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
