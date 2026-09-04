"""Measurement and calibration evidence registry for Physical Lab .physlab projects.

Raw user measurement assets are copied into the active project with SHA-256
provenance. Calibration records store explicit units plus canonical values through
physical_lab_units. This is an evidence registry, not a claim that an uploaded
file is calibrated, validated or traceable to a metrology standard.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Mapping

import physical_lab_project_kernel as projects
import physical_lab_units as units
from physical_lab_experiment_kernel import plain, utc_now

MEASUREMENT_SCHEMA = "physical-lab-measurement-v1"
CALIBRATION_SCHEMA = "physical-lab-calibration-v1"
MEASUREMENT_INDEX_SCHEMA = "physical-lab-measurement-index-v1"
CALIBRATION_INDEX_SCHEMA = "physical-lab-calibration-index-v1"


def _safe_name(filename: str) -> str:
    base = Path(str(filename or "measurement.dat")).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip("-.")
    return (cleaned or "measurement.dat")[:120]


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(plain(dict(value)), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _measurement_index_path(project_dir: Path) -> Path:
    return project_dir / "measurements" / "index.json"


def _calibration_index_path(project_dir: Path) -> Path:
    return project_dir / "calibration" / "index.json"


def _load_measurement_index(project_dir: Path) -> dict[str, Any]:
    existing = _read_json(_measurement_index_path(project_dir))
    if existing and existing.get("schema") == MEASUREMENT_INDEX_SCHEMA:
        return existing
    return {"schema": MEASUREMENT_INDEX_SCHEMA, "measurements": {}, "updated_at": None}


def _load_calibration_index(project_dir: Path) -> dict[str, Any]:
    existing = _read_json(_calibration_index_path(project_dir))
    if existing and existing.get("schema") == CALIBRATION_INDEX_SCHEMA:
        return existing
    return {"schema": CALIBRATION_INDEX_SCHEMA, "calibrations": {}, "updated_at": None}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _format(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return {
        ".csv": "csv",
        ".tsv": "tsv",
        ".json": "json",
        ".h5": "hdf5",
        ".hdf5": "hdf5",
        ".txt": "text",
    }.get(suffix, suffix.lstrip(".") or "binary")


def _bounded_preview(filename: str, data: bytes) -> dict[str, Any]:
    fmt = _format(filename)
    if fmt in {"csv", "tsv"}:
        try:
            text = data.decode("utf-8-sig")
            dialect_delimiter = "," if fmt == "csv" else "\t"
            reader = csv.reader(io.StringIO(text), delimiter=dialect_delimiter)
            rows = []
            for index, row in enumerate(reader):
                rows.append([str(cell)[:160] for cell in row[:40]])
                if index >= 20:
                    break
            columns = rows[0] if rows else []
            return {
                "format": fmt,
                "columns": columns,
                "preview_rows": rows[1:11] if len(rows) > 1 else [],
                "preview_row_count": max(0, len(rows) - 1),
                "truncated": len(rows) >= 21,
            }
        except Exception as exc:
            return {"format": fmt, "preview_error": str(exc)[:200]}
    if fmt == "json":
        try:
            value = json.loads(data.decode("utf-8"))
            if isinstance(value, Mapping):
                return {"format": fmt, "top_level_type": "object", "keys": [str(k) for k in list(value.keys())[:40]]}
            if isinstance(value, list):
                return {"format": fmt, "top_level_type": "array", "items": len(value)}
            return {"format": fmt, "top_level_type": type(value).__name__}
        except Exception as exc:
            return {"format": fmt, "preview_error": str(exc)[:200]}
    return {"format": fmt, "preview": "opaque asset; content is fingerprinted but not interpreted by the registry"}


def ingest_measurement_bytes(
    project_dir: str | Path,
    *,
    filename: str,
    data: bytes,
    profile: str = "",
    instrument: str = "",
    quantity: str = "",
    unit: str = "",
    captured_at: str = "",
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    if not isinstance(data, (bytes, bytearray)) or len(data) == 0:
        raise ValueError("measurement asset is empty")
    payload = bytes(data)
    digest = _sha256_bytes(payload)
    measurement_id = f"meas-{digest[:20]}"
    safe_name = _safe_name(filename)
    directory = path / "measurements" / measurement_id
    directory.mkdir(parents=True, exist_ok=True)
    asset_path = directory / safe_name
    if asset_path.exists() and _sha256_bytes(asset_path.read_bytes()) != digest:
        raise ValueError("measurement asset path collision")
    asset_path.write_bytes(payload)
    record = {
        "schema": MEASUREMENT_SCHEMA,
        "measurement_id": measurement_id,
        "project_id": projects.open_project(path)["project_id"],
        "profile": str(profile),
        "source_type": "user-upload",
        "file_name": safe_name,
        "asset_path": asset_path.relative_to(path).as_posix(),
        "format": _format(safe_name),
        "size_bytes": len(payload),
        "sha256": digest,
        "instrument": str(instrument),
        "quantity": str(quantity),
        "unit": str(unit),
        "captured_at": str(captured_at),
        "registered_at": utc_now(),
        "notes": str(notes),
        "preview": _bounded_preview(safe_name, payload),
        "boundary": (
            "Uploaded measurement evidence with file-integrity provenance only. Calibration status, sensor accuracy, "
            "traceability and model validation must be established separately."
        ),
    }
    _atomic_json(directory / "measurement.json", record)
    index = _load_measurement_index(path)
    previous = (index.get("measurements") or {}).get(measurement_id)
    # Preserve first registration time for an identical asset while allowing metadata refinement.
    if isinstance(previous, Mapping) and previous.get("registered_at"):
        record["registered_at"] = previous["registered_at"]
        _atomic_json(directory / "measurement.json", record)
    index.setdefault("measurements", {})[measurement_id] = record
    index["updated_at"] = utc_now()
    _atomic_json(_measurement_index_path(path), index)
    return record


def list_measurements(project_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    index = _load_measurement_index(path)
    rows = [dict(v) for v in (index.get("measurements") or {}).values() if isinstance(v, Mapping)]
    rows.sort(key=lambda row: (str(row.get("registered_at") or ""), str(row.get("measurement_id") or "")), reverse=True)
    return rows


def register_calibration(
    project_dir: str | Path,
    *,
    instrument: str,
    parameter: str,
    nominal_value: float,
    unit: str,
    standard_uncertainty: float,
    uncertainty_unit: str | None = None,
    method: str = "",
    reference: str = "",
    profile: str = "",
    calibrated_at: str = "",
    related_measurements: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    if not str(instrument).strip():
        raise ValueError("instrument is required")
    if not str(parameter).strip():
        raise ValueError("calibration parameter is required")
    u = float(standard_uncertainty)
    if not math.isfinite(u) or u < 0:
        raise ValueError("standard uncertainty must be finite and non-negative")
    nominal = units.canonicalize(float(nominal_value), unit)
    u_unit = uncertainty_unit or unit
    uncertainty = units.canonicalize(u, u_unit)
    if nominal["dimension"] != uncertainty["dimension"]:
        raise ValueError("nominal value and uncertainty units must have the same dimension")
    related = sorted({str(item) for item in (related_measurements or []) if item})
    known_measurements = {row["measurement_id"] for row in list_measurements(path)}
    missing = [item for item in related if item not in known_measurements]
    if missing:
        raise ValueError("unknown related measurement IDs: " + ", ".join(missing))
    identity_payload = {
        "project_id": project["project_id"],
        "instrument": str(instrument).strip(),
        "parameter": str(parameter).strip(),
        "nominal": nominal,
        "uncertainty": uncertainty,
        "method": str(method),
        "reference": str(reference),
        "profile": str(profile),
        "calibrated_at": str(calibrated_at),
        "related_measurements": related,
        "notes": str(notes),
    }
    identity_bytes = json.dumps(plain(identity_payload), sort_keys=True, separators=(",", ":")).encode("utf-8")
    calibration_id = f"cal-{hashlib.sha256(identity_bytes).hexdigest()[:20]}"
    record = {
        "schema": CALIBRATION_SCHEMA,
        "calibration_id": calibration_id,
        **identity_payload,
        "registered_at": utc_now(),
        "boundary": (
            "Calibration metadata supplied by the user. Physical Lab does not infer accreditation, traceability, "
            "distribution shape or coverage factor from this record."
        ),
    }
    index = _load_calibration_index(path)
    previous = (index.get("calibrations") or {}).get(calibration_id)
    if isinstance(previous, Mapping) and previous.get("registered_at"):
        record["registered_at"] = previous["registered_at"]
    _atomic_json(path / "calibration" / f"{calibration_id}.json", record)
    index.setdefault("calibrations", {})[calibration_id] = record
    index["updated_at"] = utc_now()
    _atomic_json(_calibration_index_path(path), index)
    return record


def list_calibrations(project_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    index = _load_calibration_index(path)
    rows = [dict(v) for v in (index.get("calibrations") or {}).values() if isinstance(v, Mapping)]
    rows.sort(key=lambda row: (str(row.get("registered_at") or ""), str(row.get("calibration_id") or "")), reverse=True)
    return rows


def evidence_summary(project_dir: str | Path) -> dict[str, Any]:
    measurements = list_measurements(project_dir)
    calibrations = list_calibrations(project_dir)
    return {
        "measurement_count": len(measurements),
        "calibration_count": len(calibrations),
        "measurement_formats": sorted({str(row.get("format") or "") for row in measurements if row.get("format")}),
        "instruments": sorted({str(row.get("instrument") or "") for row in measurements + calibrations if row.get("instrument")}),
        "boundary": "Evidence inventory only; validation requires model-to-measurement comparison with quantified uncertainty.",
    }


def render_measurement_workspace(st: Any, profile: str) -> None:
    active = str(st.session_state.get(projects.ACTIVE_PROJECT_SESSION_KEY) or "")
    if not active:
        return
    project_path = Path(active)
    if not (project_path / "project.json").exists():
        return

    st.markdown("---")
    with st.expander("Physical Lab · Measurement & Calibration Evidence", expanded=False):
        st.caption(
            "Attach real measurement assets and calibration metadata to the active .physlab project. "
            "File integrity and units are recorded explicitly; upload alone is not experimental validation."
        )
        tab_measure, tab_cal, tab_index = st.tabs(["Measurements", "Calibration", "Evidence index"])

        with tab_measure:
            upload = st.file_uploader(
                "Measurement asset",
                type=["csv", "tsv", "json", "h5", "hdf5", "txt"],
                key=f"pl_measure_upload_{profile}",
                help="CSV/TSV/JSON receive bounded metadata previews. HDF5 is retained as an opaque fingerprinted asset in v1.",
            )
            c1, c2, c3 = st.columns(3)
            instrument = c1.text_input("Instrument / source", value="", key=f"pl_measure_instrument_{profile}")
            quantity = c2.text_input("Measured quantity", value="", key=f"pl_measure_quantity_{profile}")
            unit = c3.text_input("Reported unit", value="", key=f"pl_measure_unit_{profile}")
            c4, c5 = st.columns(2)
            captured = c4.text_input("Captured at / run label", value="", key=f"pl_measure_captured_{profile}")
            notes = c5.text_input("Measurement notes", value="", key=f"pl_measure_notes_{profile}")
            if st.button("Register measurement evidence", type="primary", disabled=upload is None, key=f"pl_measure_register_{profile}"):
                record = ingest_measurement_bytes(
                    project_path,
                    filename=upload.name,
                    data=upload.getvalue(),
                    profile=profile,
                    instrument=instrument,
                    quantity=quantity,
                    unit=unit,
                    captured_at=captured,
                    notes=notes,
                )
                st.success(f"Registered {record['measurement_id']} · sha256 {record['sha256'][:12]}…")
                st.rerun()

            rows = list_measurements(project_path)
            if rows:
                st.dataframe([
                    {
                        "id": row.get("measurement_id"),
                        "file": row.get("file_name"),
                        "format": row.get("format"),
                        "instrument": row.get("instrument"),
                        "quantity": row.get("quantity"),
                        "unit": row.get("unit"),
                        "sha256": str(row.get("sha256") or "")[:16],
                    }
                    for row in rows
                ], width="stretch", hide_index=True)
                selected = st.selectbox(
                    "Inspect measurement", [row["measurement_id"] for row in rows], key=f"pl_measure_inspect_{profile}"
                )
                record = next(row for row in rows if row["measurement_id"] == selected)
                st.json(record)
            else:
                st.caption("No measurement evidence registered in this project yet.")

        with tab_cal:
            measurements = list_measurements(project_path)
            c1, c2 = st.columns(2)
            instrument = c1.text_input("Calibration instrument", value="", key=f"pl_cal_instrument_{profile}")
            parameter = c2.text_input("Calibration parameter", value="", key=f"pl_cal_parameter_{profile}")
            c3, c4, c5 = st.columns(3)
            nominal = c3.number_input("Nominal value", value=0.0, format="%.10g", key=f"pl_cal_nominal_{profile}")
            supported = sorted({u for values in units.supported_units().values() for u in values})
            unit = c4.selectbox("Unit", supported, key=f"pl_cal_unit_{profile}")
            uncertainty = c5.number_input("Standard uncertainty u", min_value=0.0, value=0.0, format="%.10g", key=f"pl_cal_unc_{profile}")
            c6, c7 = st.columns(2)
            method = c6.text_input("Method", value="", key=f"pl_cal_method_{profile}")
            reference = c7.text_input("Reference / certificate label", value="", key=f"pl_cal_reference_{profile}")
            related = st.multiselect(
                "Related measurement IDs",
                [row["measurement_id"] for row in measurements],
                key=f"pl_cal_related_{profile}",
            )
            if st.button("Register calibration record", type="primary", key=f"pl_cal_register_{profile}"):
                record = register_calibration(
                    project_path,
                    instrument=instrument,
                    parameter=parameter,
                    nominal_value=float(nominal),
                    unit=unit,
                    standard_uncertainty=float(uncertainty),
                    method=method,
                    reference=reference,
                    profile=profile,
                    related_measurements=related,
                )
                st.success(
                    f"Registered {record['calibration_id']} · {record['nominal']['canonical_value']:.8g} {record['nominal']['canonical_unit']}"
                )
                st.rerun()

            rows = list_calibrations(project_path)
            if rows:
                st.dataframe([
                    {
                        "id": row.get("calibration_id"),
                        "instrument": row.get("instrument"),
                        "parameter": row.get("parameter"),
                        "nominal": f"{row['nominal']['value']} {row['nominal']['unit']}",
                        "standard_u": f"{row['uncertainty']['value']} {row['uncertainty']['unit']}",
                        "canonical": f"{row['nominal']['canonical_value']:.8g} {row['nominal']['canonical_unit']}",
                    }
                    for row in rows
                ], width="stretch", hide_index=True)
            else:
                st.caption("No calibration records registered in this project yet.")

        with tab_index:
            st.json(evidence_summary(project_path))
            st.caption(
                "Next validation phase: map a selected measurement quantity to a simulation observable, combine measurement + simulation + model-form uncertainty, and assess normalized discrepancy."
            )
