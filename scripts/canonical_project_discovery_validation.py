#!/usr/bin/env python3
"""Acceptance checks for canonical-first Python project discovery."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_canonical_discovery_patch as discovery_patch
import physical_lab_digital_twin_ui as digital_twin_ui
import physical_lab_project_discovery as discovery
import physical_lab_project_kernel as projects


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    old_data = os.environ.get("PHYSICAL_LAB_DATA_DIR")
    original_workspaces = digital_twin_ui._workspaces
    had_flag = hasattr(digital_twin_ui, "_physical_lab_canonical_discovery_patched")
    old_flag = getattr(digital_twin_ui, "_physical_lab_canonical_discovery_patched", None)
    try:
        with tempfile.TemporaryDirectory(prefix="physical-lab-project-discovery-") as td:
            root = Path(td)
            os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)

            canonical_path, canonical_doc = projects.create_project(
                "Canonical direct discovery",
                slug="canonical-direct",
                research_question="Can Python surfaces discover the canonical project without a workspace alias?",
            )
            dataset_dir = canonical_path / "datasets" / "field-scan"
            dataset_dir.mkdir(parents=True)
            data_path = dataset_dir / "data.csv"
            data_path.write_text("z,B_measured,B_model\n0,1.0,0.98\n1,1.1,1.08\n", encoding="utf-8")
            write_json(dataset_dir / "metadata.json", {
                "schema": "physical-lab-dataset-v1",
                "id": "field-scan",
                "name": "Field scan",
                "quantity": "magnetic field",
                "unit": "T",
                "sensor": "fixture",
                "format": "csv",
                "sourceFile": str(data_path),
                "storedFile": str(data_path),
                "sha256": "fixture",
                "createdAt": "2026-09-05T00:00:00+00:00",
                "measurement": True,
            })

            # The core requirement: no legacy directory or symlink is needed.
            assert not (root / "workspaces").exists()
            rows = discovery.discover_projects()
            assert len(rows) == 1
            assert rows[0]["source"] == "canonical"
            assert rows[0]["project_id"] == canonical_doc["project_id"]
            assert rows[0]["path"].resolve() == canonical_path.resolve()

            digital_twin_ui._physical_lab_canonical_discovery_patched = False
            discovery_patch.install()
            patched = digital_twin_ui._workspaces()
            assert len(patched) == 1
            assert patched[0]["source"] == "canonical"
            assert patched[0]["path"].resolve() == canonical_path.resolve()
            datasets = digital_twin_ui._datasets(patched[0]["path"])
            assert len(datasets) == 1
            assert datasets[0]["metadata"]["id"] == "field-scan"
            assert datasets[0]["path"].resolve() == data_path.resolve()
            assert not (root / "workspaces").exists(), "Digital Twin discovery must not create compatibility aliases"

            # A genuine legacy workspace remains visible as fallback.
            legacy = root / "workspaces" / "legacy-real.physlab"
            legacy.mkdir(parents=True)
            write_json(legacy / "project.json", {
                "schema": "physical-lab-project-v1",
                "id": "legacy-real",
                "name": "Legacy real",
                "createdAt": "2025-01-01T00:00:00+00:00",
                "updatedAt": "2025-01-02T00:00:00+00:00",
            })
            rows = discovery.discover_projects()
            assert [row["source"] for row in rows] == ["canonical", "legacy"]
            assert rows[1]["id"] == "legacy-real"

            # A compatibility symlink is plumbing, not a duplicate project.
            alias = root / "workspaces" / canonical_path.name
            alias.symlink_to(canonical_path, target_is_directory=True)
            rows = discovery.discover_projects()
            assert len(rows) == 2
            assert sum(row["source"] == "canonical" for row in rows) == 1
            assert sum(row["source"] == "legacy" for row in rows) == 1

            # Wrong-shape documents never enter canonical discovery.
            malformed = root / "projects" / "malformed.physlab"
            malformed.mkdir(parents=True)
            write_json(malformed / "project.json", {
                "schema": "physical-lab-project-v1",
                "id": "wrong-shape",
                "createdAt": "2026-01-01T00:00:00+00:00",
                "updatedAt": "2026-01-01T00:00:00+00:00",
            })
            canonical_only = discovery.discover_projects(include_legacy=False)
            assert len(canonical_only) == 1
            assert canonical_only[0]["project_id"] == canonical_doc["project_id"]

            summary = discovery.discovery_summary()
            assert summary["canonical"] == 1
            assert summary["legacy"] == 1

    finally:
        digital_twin_ui._workspaces = original_workspaces
        if had_flag:
            digital_twin_ui._physical_lab_canonical_discovery_patched = old_flag
        elif hasattr(digital_twin_ui, "_physical_lab_canonical_discovery_patched"):
            delattr(digital_twin_ui, "_physical_lab_canonical_discovery_patched")
        if old_data is None:
            os.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
        else:
            os.environ["PHYSICAL_LAB_DATA_DIR"] = old_data

    startup = (UI / "sitecustomize.py").read_text(encoding="utf-8")
    assert "physical_lab_canonical_discovery_patch" in startup
    assert "ensure_workspace_aliases" not in startup
    conf = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    assert "resources/ui/physical_lab_project_discovery.py" in resources
    assert "resources/ui/physical_lab_canonical_discovery_patch.py" in resources

    print("Physical Lab canonical Python Project discovery: PASS")
    print("- canonical project visible with no workspaces directory: PASS")
    print("- Digital Twin direct canonical discovery + dataset read: PASS")
    print("- genuine legacy fallback: PASS")
    print("- compatibility symlink deduplication: PASS")
    print("- malformed canonical-shape rejection: PASS")
    print("- startup alias creation no longer required: PASS")
    print("Boundary: discovery changes project lookup only; it does not migrate or reinterpret scientific records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
