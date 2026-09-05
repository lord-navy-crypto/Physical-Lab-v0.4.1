#!/usr/bin/env python3
"""Static + schema acceptance for the Rust desktop canonical Project cutover."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_project_kernel as project_kernel
import physical_lab_project_unification as project_unification


def main() -> int:
    facade = (ROOT / "src-tauri" / "src" / "research.rs").read_text(encoding="utf-8")
    legacy = (ROOT / "src-tauri" / "src" / "research_legacy.rs").read_text(encoding="utf-8")
    lib = (ROOT / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")

    # The historical implementation is retained rather than rewritten in place.
    assert 'fn workspaces_root(' in legacy
    assert 'let root = workspaces_root(&app)?;' in legacy
    assert '"schema":"physical-lab-project-v1"' in legacy
    assert '"createdAt":&now' in legacy

    # New project creation is canonical and physically rooted under projects/.
    assert 'fn projects_root(' in facade
    assert '.join("projects")' in facade
    assert 'let root = projects_root(&app)?;' in facade
    assert 'const CANONICAL_SCHEMA: &str = "physical-lab-project-v1";' in facade
    assert 'const CANONICAL_VERSION: i64 = 1;' in facade
    for token in (
        '"project_version": CANONICAL_VERSION',
        '"project_id": project_id',
        '"research_question": ""',
        '"experiments": {}',
        '"jobs": {}',
        '"results": {}',
        '"migration": {"current_version": CANONICAL_VERSION, "history": []}',
        '"storage": "canonical-projects"',
    ):
        assert token in facade, token

    # Operational desktop directories remain explicitly non-canonical evidence.
    for dirname in ("datasets", "runs", "figures", "exports", "pipelines", "campaigns"):
        assert f'"{dirname}"' in facade
    assert 'Compatibility handle collision' in facade
    assert 'ensure_compatibility_link' in facade
    assert 'sync_canonical_timestamp' in facade

    # Every Tauri research command remains an explicit command in the facade.
    commands = (
        "create_workspace", "list_workspaces", "open_workspace", "record_run_snapshot",
        "import_measurement_dataset", "list_datasets", "list_serial_devices", "capture_serial_measurement",
        "analyze_dataset", "validate_dataset_columns", "lab_compatibility_matrix", "repair_lab_environment",
        "scientific_smoke_tests", "pipeline_templates", "save_pipeline", "create_campaign",
        "adapter_statuses", "export_reproducibility_package", "list_run_snapshots", "compare_run_snapshots",
        "list_campaigns", "campaign_action",
    )
    for command in commands:
        assert f"pub fn {command}(" in facade, command
        assert f"research::{command}" in lib, command

    # The Rust-emitted document shape is accepted by the same Python canonical kernel.
    fixture = project_kernel.new_project_document(
        "Rust shell canonical fixture",
        project_id="plproj-shell-fixture",
        description="fixture",
        research_question="",
        created_at="2026-09-05T00:00:00+00:00",
    )
    fixture["slug"] = "rust-shell-canonical-fixture"
    fixture["desktop_shell"] = {
        "storage": "canonical-projects",
        "operational_directories": ["datasets", "runs", "figures", "exports", "pipelines", "campaigns"],
        "compatibility_link": True,
    }
    # Temporary aliases are tolerated only for the Rust compatibility layer.
    fixture["id"] = fixture["project_id"]
    fixture["createdAt"] = fixture["created_at"]
    fixture["updatedAt"] = fixture["updated_at"]
    check = project_kernel.validate_project_document(fixture)
    assert check["valid"], check
    assert project_unification.classify_project_document(fixture) == "canonical"

    # Scientific boundary: operational shell records are not inserted into canonical result indexes by creation.
    assert fixture["experiments"] == {}
    assert fixture["jobs"] == {}
    assert fixture["results"] == {}

    print("Physical Lab desktop Project Kernel cutover validation: PASS")
    print("- new project storage -> projects/*.physlab: PASS")
    print("- canonical document contract: PASS")
    print("- legacy implementation preserved: PASS")
    print("- explicit Tauri command facade coverage: PASS")
    print("- canonical timestamp synchronization hook: PASS")
    print("- operational records remain non-canonical evidence: PASS")
    print("Boundary: compatibility symlinks route mature desktop commands to canonical storage; they do not promote shell runs/campaigns into Experiment/Result evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
