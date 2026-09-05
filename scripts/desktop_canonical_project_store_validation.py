\
#!/usr/bin/env python3
"""Acceptance checks for the alias-free desktop canonical Project store."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri/resources/ui"
sys.path.insert(0, str(UI))

import physical_lab_project_discovery as discovery
import physical_lab_project_kernel as projects


def compact(text: str) -> str:
    return "".join(text.split())


def function_block(text: str, name: str) -> str:
    marker = f"fn {name}("
    start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError(name)


def main() -> int:
    facade = (ROOT / "src-tauri/src/research.rs").read_text(encoding="utf-8")
    legacy = (ROOT / "src-tauri/src/research_legacy_impl.rs").read_text(encoding="utf-8")
    assert '#[path = "research_runtime_support.rs"]' in facade
    assert '#[path = "research_legacy_impl.rs"]' not in facade
    assert "mod runtime_support;" in facade
    assert "mod legacy;" not in facade
    assert len(legacy) > 25_000

    create_block = compact(function_block(facade, "create_workspace"))
    for needle in (
        '"project_version":PROJECT_VERSION',
        '"project_id":project_id',
        '"created_at":now',
        '"updated_at":now',
        '"experiments":{}',
        '"jobs":{}',
        '"results":{}',
        '"reports":[]',
        '"migration":{"current_version":PROJECT_VERSION,"history":[]}',
        'legacy_root_path(&app)',
    ):
        assert needle in create_block, needle
    for retired in (
        'create_alias',
        'ensure_alias_for_id',
        'legacy_root(&app)',
        '"id":&id',
        '"createdAt":&now',
        '"updatedAt":&now',
    ):
        assert retired not in create_block, retired
    assert "fn create_alias(" not in facade
    assert "fn ensure_alias_for_id(" not in facade
    assert "fn legacy_root(" not in facade

    conf = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    assert "resources/ui/physical_lab_workspace_aliases.py" not in resources
    assert not (UI / "physical_lab_workspace_aliases.py").exists()
    assert "resources/ui/physical_lab_project_discovery.py" in resources
    assert "resources/ui/physical_lab_canonical_discovery_patch.py" in resources
    assert "resources/ui/physical_lab_project_unification.py" in resources

    startup = (UI / "sitecustomize.py").read_text(encoding="utf-8")
    assert "ensure_workspace_aliases" not in startup
    assert "physical_lab_workspace_aliases" not in startup
    assert "physical_lab_canonical_discovery_patch" in startup

    old_data = os.environ.get("PHYSICAL_LAB_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="physical-lab-alias-free-store-") as td:
            root = Path(td)
            os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)

            canonical_path, canonical_doc = projects.create_project(
                "Alias-free canonical fixture",
                slug="alias-free-fixture",
                research_question="Can canonical project discovery operate without workspace aliases?",
            )
            assert canonical_path.parent == root / "projects"
            assert not (root / "workspaces").exists()
            rows = discovery.discover_projects()
            assert len(rows) == 1
            assert rows[0]["source"] == "canonical"
            assert rows[0]["project_id"] == canonical_doc["project_id"]
            assert rows[0]["path"].resolve() == canonical_path.resolve()
            assert not (root / "workspaces").exists()

            real_legacy = root / "workspaces/legacy-owned.physlab"
            real_legacy.mkdir(parents=True)
            legacy_doc = {
                "schema": "physical-lab-project-v1",
                "id": "legacy-owned",
                "name": "Real legacy project",
                "createdAt": "2026-01-01T00:00:00+00:00",
                "updatedAt": "2026-01-02T00:00:00+00:00",
            }
            legacy_bytes = json.dumps(legacy_doc, sort_keys=True).encode("utf-8")
            (real_legacy / "project.json").write_bytes(legacy_bytes)
            rows = discovery.discover_projects()
            assert [row["source"] for row in rows] == ["canonical", "legacy"]
            assert rows[1]["id"] == "legacy-owned"
            assert (real_legacy / "project.json").read_bytes() == legacy_bytes

            historical_alias = root / "workspaces" / canonical_path.name
            historical_alias.symlink_to(canonical_path, target_is_directory=True)
            rows = discovery.discover_projects()
            assert len(rows) == 2
            assert sum(row["source"] == "canonical" for row in rows) == 1
            assert sum(row["source"] == "legacy" for row in rows) == 1
            assert (real_legacy / "project.json").read_bytes() == legacy_bytes

            malformed = root / "projects/not-canonical.physlab"
            malformed.mkdir(parents=True)
            (malformed / "project.json").write_text(
                '{"schema":"physical-lab-project-v1","id":"wrong-shape"}',
                encoding="utf-8",
            )
            canonical_only = discovery.discover_projects(include_legacy=False)
            assert len(canonical_only) == 1
            assert canonical_only[0]["project_id"] == canonical_doc["project_id"]
    finally:
        if old_data is None:
            os.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
        else:
            os.environ["PHYSICAL_LAB_DATA_DIR"] = old_data

    print("Physical Lab desktop canonical Project store: PASS")
    print("- new projects live only under projects/*.physlab")
    print("- compatibility alias module/resource retired")
    print("- canonical discovery needs no workspaces directory")
    print("- genuine legacy workspace fallback preserved byte-for-byte")
    print("- historical alias deduplication preserved for upgraded installs")
    print("- explicit Project Kernel bridge remains packaged")
    print("Boundary: alias retirement changes storage plumbing only; it does not reinterpret runs, datasets, results, measurements, or claims.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
