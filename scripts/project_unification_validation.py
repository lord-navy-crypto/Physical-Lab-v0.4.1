#!/usr/bin/env python3
"""Deterministic acceptance for legacy desktop workspace -> canonical Project Kernel bridge."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_measurement_registry as measurements
import physical_lab_project_kernel as projects
import physical_lab_project_unification as bridge


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_legacy(root: Path) -> tuple[Path, bytes]:
    workspace = root / "workspaces" / "undulator-study.physlab"
    for child in ("datasets/hall-scan-01", "runs/run-001", "campaigns", "pipelines", "figures", "exports", "provenance"):
        (workspace / child).mkdir(parents=True, exist_ok=True)
    write_json(
        workspace / "project.json",
        {
            "schema": "physical-lab-project-v1",
            "id": "undulator-study",
            "name": "Undulator Measurement Study",
            "createdAt": "2026-08-01T12:00:00+00:00",
            "updatedAt": "2026-08-02T12:00:00+00:00",
            "description": "Legacy desktop workspace fixture",
            "measurementBridge": {"enabled": True},
            "provenance": {"policy": "legacy fixture"},
        },
    )
    csv = b"z_mm,Bz_mT\n0,101.2\n1,99.8\n2,98.1\n"
    (workspace / "datasets/hall-scan-01/data.csv").write_bytes(csv)
    write_json(
        workspace / "datasets/hall-scan-01/metadata.json",
        {
            "schema": "physical-lab-dataset-v1",
            "id": "hall-scan-01",
            "name": "Hall scan 01",
            "quantity": "Magnetic field Bz",
            "unit": "mT",
            "sensor": "Hall probe",
            "calibration": "legacy note only; no accreditation claim",
            "format": "csv",
            "storedFile": str(workspace / "datasets/hall-scan-01/data.csv"),
            "sha256": sha256(csv),
            "createdAt": "2026-08-01T13:00:00+00:00",
            "measurement": True,
        },
    )
    write_json(
        workspace / "runs/run-001/run.json",
        {
            "schema": "physical-lab-run-v1",
            "id": "run-001",
            "createdAt": "2026-08-01T14:00:00+00:00",
            "moduleId": "radia-magnet-studio",
            "mode": "safe",
            "parameters": {"gap_mm": 12.0},
            "results": {"peak_B_T": 1.01},
            "provenance": {"sourceCommit": "0123456789abcdef0123456789abcdef01234567"},
        },
    )
    write_json(workspace / "campaigns/gap-scan.json", {"schema": "legacy-campaign", "parameter": "gap_mm"})
    write_json(workspace / "pipelines/default-measurement-validation.json", {"schema": "legacy-pipeline", "id": "measurement-validation"})
    (workspace / "figures/plot.txt").write_text("legacy figure placeholder", encoding="utf-8")
    (workspace / "exports/report.txt").write_text("legacy export placeholder", encoding="utf-8")
    return workspace, csv


def main() -> int:
    old = os.environ.get("PHYSICAL_LAB_DATA_DIR")
    with tempfile.TemporaryDirectory(prefix="physical-lab-project-unification-") as td:
        data_root = Path(td)
        os.environ["PHYSICAL_LAB_DATA_DIR"] = str(data_root)
        workspace, csv = build_legacy(data_root)
        legacy_before = (workspace / "project.json").read_bytes()

        legacy_doc = json.loads(legacy_before)
        assert bridge.classify_project_document(legacy_doc) == "legacy-shell"
        canonical_fixture = projects.new_project_document("Canonical fixture", project_id="plproj-canonical-fixture")
        assert bridge.classify_project_document(canonical_fixture) == "canonical"
        assert bridge.classify_project_document({"schema": "physical-lab-project-v1"}) == "unknown"

        first = bridge.synchronize_legacy_workspaces()
        assert first["discovered"] == 1
        assert first["created"] == 1
        assert first["changed"] == 1
        assert first["measurements_imported"] == 1
        assert not first["errors"]
        canonical_path = Path(first["projects"][0]["canonical_path"])
        assert canonical_path.parent == data_root / "projects"
        assert canonical_path.is_dir()

        canonical = projects.open_project(canonical_path)
        assert canonical["schema"] == projects.PROJECT_SCHEMA
        assert canonical["project_version"] == projects.PROJECT_VERSION
        assert str(canonical["project_id"]).startswith("plproj-legacy-")
        assert "id" not in canonical
        assert canonical["experiments"] == {}
        assert canonical["jobs"] == {}
        assert canonical["results"] == {}, "legacy run must not be promoted to a canonical result"
        assert canonical["research_question"] == ""

        rows = measurements.list_measurements(canonical_path)
        assert len(rows) == 1
        assert rows[0]["sha256"] == sha256(csv)
        assert rows[0]["quantity"] == "Magnetic field Bz"
        assert rows[0]["unit"] == "mT"
        assert rows[0]["instrument"] == "Hall probe"
        assert rows[0]["source_type"] == "user-upload"
        assert "legacy desktop dataset hall-scan-01" in rows[0]["notes"]

        bridge_record = json.loads((canonical_path / "provenance/legacy-workspace-bridge.json").read_text(encoding="utf-8"))
        assert bridge_record["schema"] == bridge.BRIDGE_SCHEMA
        assert bridge_record["dataset_count"] == 1
        assert bridge_record["inventory_counts"]["runs"] == 1
        assert bridge_record["inventory_counts"]["campaigns"] == 1
        assert bridge_record["inventory_counts"]["pipelines"] == 1
        assert "not promoted" in bridge_record["boundary"]
        assert (workspace / "project.json").read_bytes() == legacy_before, "legacy source must remain byte-for-byte unchanged"

        # Canonical user edits belong to the canonical project and must survive later bridge syncs.
        projects.update_project_metadata(canonical_path, research_question="How does measured Bz compare with the model?")
        second = bridge.synchronize_legacy_workspaces()
        assert second["created"] == 0
        assert second["changed"] == 0
        assert second["unchanged"] == 1
        assert second["measurements_imported"] == 0
        assert projects.open_project(canonical_path)["research_question"].startswith("How does measured Bz")
        assert len(measurements.list_measurements(canonical_path)) == 1

        # Add new legacy evidence: same canonical project, one new measurement, no reinterpretation.
        folder = workspace / "datasets/hall-scan-02"
        folder.mkdir(parents=True)
        csv2 = b"z_mm,Bz_mT\n0,102.0\n1,100.1\n"
        (folder / "data.csv").write_bytes(csv2)
        write_json(
            folder / "metadata.json",
            {
                "schema": "physical-lab-dataset-v1",
                "id": "hall-scan-02",
                "name": "Hall scan 02",
                "quantity": "Magnetic field Bz",
                "unit": "mT",
                "sensor": "Hall probe",
                "format": "csv",
                "sha256": sha256(csv2),
                "createdAt": "2026-08-03T13:00:00+00:00",
                "measurement": True,
            },
        )
        third = bridge.synchronize_legacy_workspaces()
        assert third["created"] == 0
        assert third["changed"] == 1
        assert third["measurements_imported"] == 1
        assert len(measurements.list_measurements(canonical_path)) == 2
        assert projects.open_project(canonical_path)["results"] == {}
        assert (workspace / "project.json").read_bytes() == legacy_before

        conf = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
        resources = (conf.get("bundle") or {}).get("resources") or {}
        assert "resources/ui/physical_lab_project_unification.py" in resources
        surface = (UI / "physical_lab_project_surface_patch.py").read_text(encoding="utf-8")
        assert "synchronize_legacy_workspaces" in surface
        assert "LEGACY_SYNC_SESSION_KEY" in surface

        print("Physical Lab Project Kernel unification bridge: PASS")
        print("- reused-schema shape discrimination: PASS")
        print("- non-destructive legacy source preservation: PASS")
        print("- deterministic canonical project creation: PASS")
        print("- legacy dataset -> measurement SHA-256 evidence: PASS")
        print("- legacy run/campaign/pipeline -> provenance inventory only: PASS")
        print("- idempotent re-sync + canonical edit preservation: PASS")
        print("- incremental new measurement sync: PASS")
        print("- Tauri/shared-Lab wiring: PASS")
        print("Boundary: compatibility migration only; legacy run payloads are never declared canonical experiments/results or validation evidence.")

    if old is None:
        os.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
    else:
        os.environ["PHYSICAL_LAB_DATA_DIR"] = old
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
