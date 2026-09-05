#!/usr/bin/env python3
"""Acceptance checks for canonical-native Rust run/pipeline writes."""
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

    for helper in (
        "modules_root_for_research",
        "touch_project_after_direct_write",
        "pipeline_template_value",
        "record_run_snapshot_to_dir",
        "save_pipeline_to_dir",
    ):
        assert f"fn {helper}(" in source, helper

    for command, helper in (
        ("record_run_snapshot", "record_run_snapshot_to_dir"),
        ("save_pipeline", "save_pipeline_to_dir"),
    ):
        block = compact(function_block(source, command))
        assert "resolve_project_dir" in block
        assert helper in block
        assert "ensure_alias_for_id" not in block
        assert "legacy::" not in block

    templates = compact(function_block(source, "pipeline_templates"))
    assert "pipeline_template_value" in templates
    assert "legacy::" not in templates

    run_new = compact(function_block(source, "record_run_snapshot_to_dir"))
    run_old = compact(function_block(legacy, "record_run_snapshot"))
    for token in (
        '"physical-lab-run-v1"',
        '"createdAt"',
        '"moduleId"',
        '"parameters"',
        '"results"',
        '"sourceCommit"',
        '"python"',
        '"pipFreeze"',
        '"pip","freeze","--all"',
        '"rev-parse","HEAD"',
    ):
        assert token in run_new, token
        assert token in run_old, token

    pipeline_new = compact(function_block(source, "pipeline_template_value"))
    pipeline_old = compact(function_block(legacy, "default_pipeline_value"))
    for token in (
        '"accelerator-measurement"',
        '"MeasuredField→RADIA→Radiation"',
        '"oscillation-modal"',
        '"Oscillation→Chrono::ModalComparison"',
        '"atomistic-magnetism"',
        '"MaterialInputs→VAMPIRE→ResultImport"',
        '"Measurement→Validation"',
        '"physical-lab-pipeline-v1"',
        '"adapter-boundary"',
        '"schema-ready"',
    ):
        assert token in pipeline_new, token
        assert token in pipeline_old, token

    touch = compact(function_block(source, "touch_project_after_direct_write"))
    assert 'project["updated_at"]' in touch
    assert 'object.remove("updatedAt")' in touch
    assert 'project["updatedAt"]' in touch

    save = compact(function_block(source, "save_pipeline_to_dir"))
    assert 'project_dir.join("pipelines")' in save
    assert "touch_project_after_direct_write" in save

    assert 'Projectmetadataandprovenanceindexonly' in compact(source)
    print("Physical Lab Rust canonical run/pipeline writes: PASS")
    print("- run snapshot: direct canonical/legacy resolver, no alias")
    print("- run schema + provenance fields preserved")
    print("- pipeline templates/save share one canonical helper")
    print("- pipeline contracts preserved")
    print("- canonical updated_at / legacy updatedAt behavior preserved")
    print("Boundary: desktop run snapshots remain workflow/provenance artifacts and are not automatically canonical scientific Results.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
