#!/usr/bin/env python3
"""Acceptance checks for the desktop-shell canonical Project Kernel cutover."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_project_kernel as projects
import physical_lab_workspace_aliases as aliases


def main() -> int:
    facade = (ROOT / "src-tauri/src/research.rs").read_text(encoding="utf-8")
    legacy = (ROOT / "src-tauri/src/research_legacy_impl.rs").read_text(encoding="utf-8")

    # The mature pre-cutover implementation is retained rather than manually
    # duplicated or partly deleted during storage migration.
    assert '#[path = "research_legacy_impl.rs"]' in facade
    assert len(legacy) > 25_000
    for needle in (
        "pub fn create_workspace(",
        "pub fn import_measurement_dataset(",
        "pub fn create_campaign(",
        "pub fn export_reproducibility_package(",
        "pub fn compare_run_snapshots(",
    ):
        assert needle in legacy, f"legacy implementation lost: {needle}"

    create_start = facade.index("pub fn create_workspace(")
    create_end = facade.index("pub fn list_workspaces(", create_start)
    create_block = facade[create_start:create_end]
    assert 'join("projects")' in facade
    assert 'join("workspaces")' in facade
    assert '"project_version": PROJECT_VERSION' in create_block
    assert '"project_id": project_id' in create_block
    assert '"created_at": now' in create_block
    assert '"updated_at": now' in create_block
    assert '"experiments": {}' in create_block
    assert '"jobs": {}' in create_block
    assert '"results": {}' in create_block
    assert '"reports": []' in create_block
    assert '"migration": {"current_version": PROJECT_VERSION, "history": []}' in create_block
    assert 'create_alias(&alias, &dir)?' in create_block
    assert '"id":&id' not in create_block
    assert '"createdAt":&now' not in create_block
    assert '"updatedAt":&now' not in create_block

    # Desktop writes that still use the proven legacy implementation are wrapped
    # so canonical updated_at and Measurement Evidence stay in the shared kernel.
    for needle in (
        "touch_canonical_after_write",
        "register_desktop_measurement",
        '"physical-lab-measurement-index-v1"',
        '"physical-lab-measurement-v1"',
        '"source_type": "desktop-data-bridge"',
        "Calibration status, sensor accuracy, traceability and experimental validation must be established separately.",
    ):
        assert needle in facade, needle

    # Existing legacy workspaces are explicitly preserved; only absent paths can
    # become compatibility aliases to a canonical project.
    assert "A real legacy workspace wins during the compatibility period" in facade
    assert "alias.symlink_metadata().is_ok()" in facade
    assert "metadata.file_type().is_symlink()" in facade

    conf = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    assert "resources/ui/physical_lab_workspace_aliases.py" in resources
    startup = (UI / "sitecustomize.py").read_text(encoding="utf-8")
    assert "ensure_workspace_aliases" in startup
    assert startup.index("ensure_workspace_aliases") < startup.index("physical_lab_sitecustomize_base")

    old_data = os.environ.get("PHYSICAL_LAB_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="physical-lab-desktop-store-") as td:
            root = Path(td)
            os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)

            canonical_path, canonical_doc = projects.create_project(
                "Canonical shell fixture",
                slug="canonical-shell-fixture",
                research_question="Does the canonical project remain discoverable by legacy readers?",
            )
            first = aliases.ensure_workspace_aliases()
            alias = root / "workspaces/canonical-shell-fixture.physlab"
            assert first["canonical"] == 1
            assert first["created"] == 1
            assert not first["errors"]
            assert alias.is_symlink()
            assert alias.resolve() == canonical_path.resolve()
            alias_doc = json.loads((alias / "project.json").read_text(encoding="utf-8"))
            assert alias_doc["project_id"] == canonical_doc["project_id"]
            assert alias_doc["project_version"] == 1

            second = aliases.ensure_workspace_aliases()
            assert second["created"] == 0
            assert second["preserved_legacy"] >= 1
            assert alias.resolve() == canonical_path.resolve()

            # Same-name real legacy directory must win; alias creation must not
            # delete, rename or replace it.
            real_legacy = root / "workspaces/legacy-owned.physlab"
            real_legacy.mkdir(parents=True)
            legacy_project = {
                "schema": "physical-lab-project-v1",
                "id": "legacy-owned",
                "name": "Real legacy project",
                "createdAt": "2026-01-01T00:00:00+00:00",
                "updatedAt": "2026-01-01T00:00:00+00:00",
            }
            legacy_bytes = json.dumps(legacy_project, sort_keys=True).encode("utf-8")
            (real_legacy / "project.json").write_bytes(legacy_bytes)
            projects.create_project("Canonical shadow", slug="legacy-owned")
            third = aliases.ensure_workspace_aliases()
            assert not real_legacy.is_symlink()
            assert (real_legacy / "project.json").read_bytes() == legacy_bytes
            assert third["canonical"] == 2
            assert third["preserved_legacy"] >= 2

            # Alias layer must ignore malformed/noncanonical folders under projects/.
            malformed = root / "projects/not-canonical.physlab"
            malformed.mkdir(parents=True)
            (malformed / "project.json").write_text('{"schema":"physical-lab-project-v1","id":"wrong-shape"}', encoding="utf-8")
            fourth = aliases.ensure_workspace_aliases()
            assert fourth["canonical"] == 2
            assert not (root / "workspaces/not-canonical.physlab").exists()

    finally:
        if old_data is None:
            os.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
        else:
            os.environ["PHYSICAL_LAB_DATA_DIR"] = old_data

    print("Physical Lab desktop canonical Project store: PASS")
    print("- legacy Rust implementation frozen and delegated: PASS")
    print("- new project schema contract -> canonical Project Kernel: PASS")
    print("- projects/ primary storage + workspaces/ compatibility path: PASS")
    print("- canonical updated_at write-through contract: PASS")
    print("- desktop dataset -> Measurement Evidence contract: PASS")
    print("- compatibility alias creation + idempotence: PASS")
    print("- existing real legacy workspace preservation: PASS")
    print("- malformed project alias rejection: PASS")
    print("- Tauri/startup packaging order: PASS")
    print("Boundary: desktop run/campaign artifacts remain workflow/provenance records unless separately registered through the Experiment/Compute/Evidence kernels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
