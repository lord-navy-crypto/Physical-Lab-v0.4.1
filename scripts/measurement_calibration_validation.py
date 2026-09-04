#!/usr/bin/env python3
"""Deterministic validation for Physical Lab measurement/calibration evidence v1."""
from __future__ import annotations

import hashlib
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_measurement_registry as evidence  # noqa: E402
import physical_lab_project_kernel as projects  # noqa: E402
import physical_lab_units as units  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def expect_error(fn, message: str) -> None:
    try:
        fn()
    except (ValueError, FileNotFoundError):
        return
    raise AssertionError(message)


def main() -> int:
    # Unit layer: exact simple conversions plus dimensional rejection.
    require(math.isclose(units.convert(10.0, "mm", "m"), 0.01, rel_tol=0, abs_tol=1e-15), "10 mm conversion failed")
    require(math.isclose(units.convert(50.0, "mT", "T"), 0.05, rel_tol=0, abs_tol=1e-15), "50 mT conversion failed")
    require(math.isclose(units.convert(180.0, "deg", "rad"), math.pi, rel_tol=1e-14), "degree conversion failed")
    require(math.isclose(units.canonicalize(1.0, "keV")["canonical_value"], 1.602176634e-16, rel_tol=1e-14), "keV canonicalization failed")
    require(math.isclose(units.convert(1.0, "%", "1"), 0.01, rel_tol=0, abs_tol=1e-15), "percent conversion failed")
    expect_error(lambda: units.convert(1.0, "mm", "eV"), "incompatible dimensions must be rejected")
    expect_error(lambda: units.canonicalize(1.0, "mystery-unit"), "unknown units must be rejected")

    with tempfile.TemporaryDirectory(prefix="physical-lab-measurement-") as temp:
        os.environ["PHYSICAL_LAB_DATA_DIR"] = temp
        project_dir, _ = projects.create_project(
            "Measurement Evidence Validation",
            research_question="Can measurement assets and calibration metadata remain traceable without overstating validation?",
        )

        csv_bytes = (
            b"time_s,position_mm,field_mT\n"
            b"0.0,0.0,49.8\n"
            b"0.1,1.0,50.1\n"
            b"0.2,2.1,50.0\n"
        )
        first = evidence.ingest_measurement_bytes(
            project_dir,
            filename="hall_probe_run.csv",
            data=csv_bytes,
            profile="radia-magnet-studio",
            instrument="Hall probe fixture",
            quantity="magnetic field",
            unit="mT",
            captured_at="fixture-run-1",
            notes="synthetic CI fixture",
        )
        second = evidence.ingest_measurement_bytes(
            project_dir,
            filename="hall_probe_run.csv",
            data=csv_bytes,
            profile="radia-magnet-studio",
            instrument="Hall probe fixture",
            quantity="magnetic field",
            unit="mT",
            captured_at="fixture-run-1",
            notes="synthetic CI fixture",
        )
        require(first["measurement_id"] == second["measurement_id"], "identical asset must be idempotent")
        require(first["sha256"] == hashlib.sha256(csv_bytes).hexdigest(), "measurement SHA-256 mismatch")
        rows = evidence.list_measurements(project_dir)
        require(len(rows) == 1, "identical measurement asset must not duplicate index")
        stored = project_dir / first["asset_path"]
        require(stored.read_bytes() == csv_bytes, "measurement raw asset must round-trip exactly")
        require(first["preview"]["columns"] == ["time_s", "position_mm", "field_mT"], "CSV preview columns mismatch")
        require(len(first["preview"]["preview_rows"]) == 3, "CSV bounded preview row count mismatch")
        require("validation" in first["boundary"].lower(), "measurement scientific boundary missing")

        calibration = evidence.register_calibration(
            project_dir,
            instrument="Hall probe fixture",
            parameter="field scale check",
            nominal_value=50.0,
            unit="mT",
            standard_uncertainty=0.2,
            uncertainty_unit="mT",
            method="comparison fixture",
            reference="CI-SYNTHETIC-NOT-A-CERTIFICATE",
            profile="radia-magnet-studio",
            calibrated_at="2026-09-04",
            related_measurements=[first["measurement_id"]],
            notes="synthetic deterministic fixture",
        )
        require(math.isclose(calibration["nominal"]["canonical_value"], 0.05, rel_tol=0, abs_tol=1e-15), "calibration nominal canonical value mismatch")
        require(math.isclose(calibration["uncertainty"]["canonical_value"], 0.0002, rel_tol=0, abs_tol=1e-15), "calibration uncertainty canonical value mismatch")
        require(calibration["related_measurements"] == [first["measurement_id"]], "calibration measurement linkage mismatch")
        duplicate_calibration = evidence.register_calibration(
            project_dir,
            instrument="Hall probe fixture",
            parameter="field scale check",
            nominal_value=50.0,
            unit="mT",
            standard_uncertainty=0.2,
            uncertainty_unit="mT",
            method="comparison fixture",
            reference="CI-SYNTHETIC-NOT-A-CERTIFICATE",
            profile="radia-magnet-studio",
            calibrated_at="2026-09-04",
            related_measurements=[first["measurement_id"]],
            notes="synthetic deterministic fixture",
        )
        require(duplicate_calibration["calibration_id"] == calibration["calibration_id"], "calibration identity must be deterministic")
        require(len(evidence.list_calibrations(project_dir)) == 1, "same calibration must not duplicate index")

        expect_error(
            lambda: evidence.register_calibration(
                project_dir,
                instrument="fixture",
                parameter="bad uncertainty",
                nominal_value=1.0,
                unit="mm",
                standard_uncertainty=-0.1,
            ),
            "negative uncertainty must be rejected",
        )
        expect_error(
            lambda: evidence.register_calibration(
                project_dir,
                instrument="fixture",
                parameter="dimension mismatch",
                nominal_value=1.0,
                unit="mm",
                standard_uncertainty=1.0,
                uncertainty_unit="eV",
            ),
            "dimension-mismatched uncertainty must be rejected",
        )
        expect_error(
            lambda: evidence.register_calibration(
                project_dir,
                instrument="fixture",
                parameter="unknown link",
                nominal_value=1.0,
                unit="T",
                standard_uncertainty=0.01,
                related_measurements=["meas-does-not-exist"],
            ),
            "unknown measurement linkage must be rejected",
        )

        summary = evidence.evidence_summary(project_dir)
        require(summary["measurement_count"] == 1, "measurement evidence count mismatch")
        require(summary["calibration_count"] == 1, "calibration evidence count mismatch")
        require("csv" in summary["measurement_formats"], "measurement format index missing")
        require("Hall probe fixture" in summary["instruments"], "instrument evidence index missing")

    tauri = (ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8")
    facade = (UI / "physical_lab_engineering.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "source-integrity.yml").read_text(encoding="utf-8")
    require("physical_lab_units.py" in tauri, "unit layer must be bundled")
    require("physical_lab_measurement_registry.py" in tauri, "measurement registry must be bundled")
    require("render_measurement_workspace" in facade, "Engineering facade must render measurement workspace")
    require("measurement_calibration_validation.py" in workflow, "Source Integrity must run measurement/calibration validation")

    print("Physical Lab Measurement/Calibration validation: PASS")
    print("- canonical unit conversions + dimension guards: PASS")
    print("- measurement SHA-256/raw-asset round trip: PASS")
    print("- idempotent evidence indexing: PASS")
    print("- calibration canonicalization + uncertainty linkage: PASS")
    print("- invalid uncertainty/linkage rejection: PASS")
    print("- Tauri/facade/CI integration: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
