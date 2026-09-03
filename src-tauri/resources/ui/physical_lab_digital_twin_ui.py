"""Physical Lab project-level Measurement Digital Twin UI.

This view is injected into selected managed Labs but operates on Physical Lab's
`.physlab` workspaces. Scientific math comes only from physical_lab_digital_twin;
this module handles dataset discovery, presentation, derived-data persistence and
provenance.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from physical_lab_digital_twin import (
    analyze_beam_phase_space,
    apply_linear_calibration,
    compare_field_series,
    fit_linear_calibration,
    fit_model_affine,
    suggest_residual_measurement_points,
)

SUPPORTED_PROFILES = {
    "radia-magnet-studio",
    "radiation-platform",
    "oscillation-integration",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text: str) -> str:
    out = []
    for ch in str(text).strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in "-_ " and (not out or out[-1] != "-"):
            out.append("-")
    value = "".join(out).strip("-")
    return value or "result"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _data_root() -> Path | None:
    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser()
    return root if root.exists() else None


def _workspaces() -> list[dict[str, Any]]:
    root = _data_root()
    if root is None:
        return []
    output: list[dict[str, Any]] = []
    for folder in sorted((root / "workspaces").glob("*.physlab")):
        project = folder / "project.json"
        if not project.is_file():
            continue
        try:
            meta = json.loads(project.read_text(encoding="utf-8"))
        except Exception:
            continue
        output.append({
            "id": str(meta.get("id") or folder.stem),
            "name": str(meta.get("name") or folder.stem),
            "path": folder,
        })
    return output


def _datasets(workspace: Path) -> list[dict[str, Any]]:
    root = (workspace / "datasets").resolve()
    output: list[dict[str, Any]] = []
    if not root.is_dir():
        return output
    for folder in sorted(root.iterdir(), reverse=True):
        meta_path = folder / "metadata.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            fmt = str(meta.get("format", "")).lower()
            if fmt not in {"csv", "tsv"}:
                continue
            stored = Path(str(meta.get("storedFile", ""))).expanduser().resolve()
            if not stored.is_file() or not stored.is_relative_to(root):
                continue
            output.append({"folder": folder, "metadata": meta, "path": stored})
        except Exception:
            continue
    return output


def _read_table(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        headers = list(reader.fieldnames or [])
        rows = [dict(row) for _, row in zip(range(200_000), reader)]
    return headers, rows


def _numeric(rows: list[dict[str, str]], column: str) -> list[float]:
    out: list[float] = []
    for row in rows:
        try:
            out.append(float(row.get(column, "")))
        except (TypeError, ValueError):
            out.append(float("nan"))
    return out


def _finite_count(values: list[float]) -> int:
    return sum(1 for value in values if math.isfinite(value))


def _persist(workspace: Path, operation: str, dataset: dict[str, Any], inputs: dict[str, Any], result: Any, profile: str, *, subdir: str = "digital-twin") -> Path:
    root = workspace / "provenance" / subdir
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = root / f"{stamp}-{_slug(operation)}.json"
    payload = {
        "schema": "physical-lab-digital-twin-provenance-v1",
        "createdAt": _now(),
        "operation": operation,
        "profile": profile,
        "dataset": {
            "id": dataset["metadata"].get("id"),
            "name": dataset["metadata"].get("name"),
            "sha256": dataset["metadata"].get("sha256") or _sha256(dataset["path"]),
            "storedFile": str(dataset["path"]),
        },
        "inputs": inputs,
        "result": result,
        "scientificCore": "physical_lab_digital_twin.py",
        "boundary": "This record preserves the calculation and inputs. Interpretation still depends on units, calibration quality, coordinate definitions, model assumptions and measurement uncertainty.",
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    return path


def _write_calibrated_dataset(workspace: Path, dataset: dict[str, Any], headers: list[str], rows: list[dict[str, str]], raw_column: str, output_column: str, slope: float, offset: float, calibration_result: dict[str, Any]) -> Path:
    safe_output = output_column.strip() or f"{raw_column}_calibrated"
    values = apply_linear_calibration(_numeric(rows, raw_column), slope, offset)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_id = str(dataset["metadata"].get("id") or dataset["folder"].name)
    dataset_id = f"{_slug(base_id)}-calibrated-{stamp}"
    folder = workspace / "datasets" / dataset_id
    folder.mkdir(parents=True, exist_ok=False)
    target = folder / "data.csv"
    output_headers = list(headers)
    if safe_output not in output_headers:
        output_headers.append(safe_output)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_headers)
        writer.writeheader()
        for row, value in zip(rows, values):
            item = dict(row)
            item[safe_output] = "" if not math.isfinite(value) else f"{value:.17g}"
            writer.writerow(item)
    meta = {
        "schema": "physical-lab-dataset-v1",
        "id": dataset_id,
        "name": f"{dataset['metadata'].get('name') or base_id} calibrated",
        "quantity": dataset["metadata"].get("quantity", ""),
        "unit": dataset["metadata"].get("unit", ""),
        "sensor": dataset["metadata"].get("sensor", ""),
        "calibration": calibration_result,
        "format": "csv",
        "sourceFile": str(dataset["path"]),
        "storedFile": str(target),
        "sha256": _sha256(target),
        "createdAt": _now(),
        "measurement": True,
        "derived": True,
        "lineage": {
            "parentDatasetId": dataset["metadata"].get("id"),
            "parentSha256": dataset["metadata"].get("sha256") or _sha256(dataset["path"]),
            "operation": "linear-calibration",
            "rawColumn": raw_column,
            "outputColumn": safe_output,
        },
    }
    (folder / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    return folder


def _metric_grid(st, rows: list[tuple[str, str, str]]) -> None:
    cols = st.columns(min(4, max(1, len(rows))))
    for index, (label, value, help_text) in enumerate(rows):
        cols[index % len(cols)].metric(label, value, help=help_text or None)


def render_digital_twin_workspace(st, profile: str) -> None:
    if profile not in SUPPORTED_PROFILES:
        return
    st.markdown("---")
    st.markdown("## Physical Lab · Measurement Digital Twin")
    st.caption(
        "Project-level measurement → calibration → model comparison → inverse discrepancy → beam statistics. "
        "All calculations use Physical Lab's shared validated scientific core and write provenance back to the selected `.physlab` workspace."
    )

    workspaces = _workspaces()
    if not workspaces:
        st.info("Create a `.physlab` project in the Physical Lab desktop **Projects** view, then import a CSV/TSV measurement in **Data Bridge**.")
        return
    labels = [f"{w['name']} · {w['id']}" for w in workspaces]
    selected_label = st.selectbox("Physical Lab project", labels, key=f"pl_dt_workspace_{profile}")
    workspace = workspaces[labels.index(selected_label)]
    datasets = _datasets(workspace["path"])
    if not datasets:
        st.info("This project has no CSV/TSV datasets yet. Import or capture data through Physical Lab Data Bridge first.")
        return
    dataset_labels = [f"{d['metadata'].get('name') or d['folder'].name} · {d['metadata'].get('id') or d['folder'].name}" for d in datasets]
    ds_label = st.selectbox("Project dataset", dataset_labels, key=f"pl_dt_dataset_{profile}")
    dataset = datasets[dataset_labels.index(ds_label)]
    try:
        headers, rows = _read_table(dataset["path"])
    except Exception as exc:
        st.error(f"Could not read dataset: {exc}")
        return
    if not headers or not rows:
        st.warning("The selected dataset has no readable rows.")
        return

    _metric_grid(st, [
        ("Rows", f"{len(rows):,}", "At most 200,000 rows are read in this interactive view"),
        ("Columns", str(len(headers)), "CSV/TSV columns"),
        ("Quantity", str(dataset["metadata"].get("quantity") or "unspecified"), "Dataset metadata"),
        ("Unit", str(dataset["metadata"].get("unit") or "unspecified"), "Physical Lab does not infer units"),
    ])

    tab_cal, tab_field, tab_inverse, tab_phase, tab_sample = st.tabs([
        "Sensor calibration", "Measured ↔ model field", "Inverse discrepancy", "Beam phase space", "Remeasurement priorities"
    ])

    with tab_cal:
        st.markdown("### Linear sensor calibration")
        st.caption("Fits `reference = slope × raw + offset`. Use only when an affine calibration is physically justified.")
        c1, c2, c3 = st.columns(3)
        raw_col = c1.selectbox("Raw sensor column", headers, key=f"pl_dt_cal_raw_{profile}")
        ref_col = c2.selectbox("Reference column", headers, index=min(1, len(headers)-1), key=f"pl_dt_cal_ref_{profile}")
        output_col = c3.text_input("Derived calibrated column", value=f"{raw_col}_calibrated", key=f"pl_dt_cal_out_{profile}")
        if st.button("Fit calibration", type="primary", key=f"pl_dt_cal_run_{profile}"):
            try:
                result = fit_linear_calibration(_numeric(rows, raw_col), _numeric(rows, ref_col))
                payload = result.to_dict()
                path = _persist(workspace["path"], "linear-sensor-calibration", dataset, {"rawColumn": raw_col, "referenceColumn": ref_col}, payload, profile, subdir="calibrations")
                st.session_state[f"pl_dt_cal_result_{profile}"] = (payload, str(path), raw_col, output_col)
            except Exception as exc:
                st.error(str(exc))
        saved = st.session_state.get(f"pl_dt_cal_result_{profile}")
        if saved:
            payload, provenance_path, saved_raw, saved_output = saved
            _metric_grid(st, [
                ("Slope", f"{payload['slope']:.9g}", "Multiplicative calibration coefficient"),
                ("Offset", f"{payload['offset']:.9g}", "Additive calibration coefficient"),
                ("RMSE", f"{payload['rmse']:.3e}", "Fit residual RMSE in reference units"),
                ("R²", f"{payload['r2']:.8g}", "Descriptive linear fit coefficient"),
            ])
            st.caption(payload["caveat"])
            st.code(provenance_path)
            if st.button("Create calibrated derived dataset", key=f"pl_dt_cal_save_{profile}"):
                try:
                    folder = _write_calibrated_dataset(workspace["path"], dataset, headers, rows, saved_raw, saved_output, float(payload["slope"]), float(payload["offset"]), payload)
                    st.success(f"Created derived dataset: {folder.name}. Re-select the project dataset to use it in later comparisons.")
                except Exception as exc:
                    st.error(f"Could not create derived dataset: {exc}")

    with tab_field:
        st.markdown("### Measured field ↔ model field")
        st.caption("Columns must already share the same coordinate convention and field unit. Physical Lab does not silently rescale them.")
        c1, c2, c3 = st.columns(3)
        z_col = c1.selectbox("Position column", headers, key=f"pl_dt_field_z_{profile}")
        measured_col = c2.selectbox("Measured field column", headers, index=min(1, len(headers)-1), key=f"pl_dt_field_m_{profile}")
        model_col = c3.selectbox("Model / RADIA column", headers, index=min(2, len(headers)-1), key=f"pl_dt_field_p_{profile}")
        if st.button("Compare field series", type="primary", key=f"pl_dt_field_run_{profile}"):
            try:
                result = compare_field_series(_numeric(rows, z_col), _numeric(rows, measured_col), _numeric(rows, model_col))
                payload = result.to_dict()
                path = _persist(workspace["path"], "measured-model-field-comparison", dataset, {"positionColumn": z_col, "measuredColumn": measured_col, "modelColumn": model_col}, payload, profile)
                st.session_state[f"pl_dt_field_result_{profile}"] = (payload, str(path), z_col, measured_col, model_col)
            except Exception as exc:
                st.error(str(exc))
        saved = st.session_state.get(f"pl_dt_field_result_{profile}")
        if saved:
            payload, provenance_path, zz, mm, pp = saved
            _metric_grid(st, [
                ("RMSE", f"{payload['rmse']:.4g}", "Measured − model"),
                ("Bias", f"{payload['bias']:.4g}", "Mean measured − model"),
                ("Max |error|", f"{payload['max_abs_error']:.4g}", "Largest paired absolute discrepancy"),
                ("Δ field integral", f"{payload['integral_difference']:.4g}", "Trapezoidal integral difference in inherited field×position units"),
            ])
            try:
                import pandas as pd
                frame = pd.DataFrame({"position": _numeric(rows, zz), "measured": _numeric(rows, mm), "model": _numeric(rows, pp)})
                frame = frame.replace([float("inf"), float("-inf")], float("nan")).dropna()
                st.line_chart(frame.set_index("position")[["measured", "model"]])
                frame["residual"] = frame["measured"] - frame["model"]
                st.line_chart(frame.set_index("position")[["residual"]])
            except Exception:
                pass
            st.caption(payload["caveat"])
            st.code(provenance_path)

    with tab_inverse:
        st.markdown("### Affine model-discrepancy calibration")
        st.caption("Fits `measured ≈ scale × model + offset`. This diagnoses a global gain/offset mismatch; it does not infer physical magnet geometry or material parameters.")
        c1, c2 = st.columns(2)
        measured_col = c1.selectbox("Measured column", headers, key=f"pl_dt_inv_m_{profile}")
        model_col = c2.selectbox("Model column", headers, index=min(1, len(headers)-1), key=f"pl_dt_inv_p_{profile}")
        if st.button("Fit affine discrepancy", type="primary", key=f"pl_dt_inv_run_{profile}"):
            try:
                result = fit_model_affine(_numeric(rows, measured_col), _numeric(rows, model_col))
                payload = result.to_dict()
                path = _persist(workspace["path"], "affine-model-discrepancy", dataset, {"measuredColumn": measured_col, "modelColumn": model_col}, payload, profile)
                st.session_state[f"pl_dt_inv_result_{profile}"] = (payload, str(path))
            except Exception as exc:
                st.error(str(exc))
        saved = st.session_state.get(f"pl_dt_inv_result_{profile}")
        if saved:
            payload, provenance_path = saved
            improvement = payload.get("improvement_fraction")
            _metric_grid(st, [
                ("Scale", f"{payload['scale']:.9g}", "Global multiplicative discrepancy"),
                ("Offset", f"{payload['offset']:.9g}", "Global additive discrepancy"),
                ("RMSE before", f"{payload['rmse_before']:.4g}", "Uncorrected model discrepancy"),
                ("RMSE after", f"{payload['rmse_after']:.4g}", f"Improvement {100*improvement:.2f}%" if improvement is not None else "No finite baseline improvement fraction"),
            ])
            st.warning(payload["caveat"])
            st.code(provenance_path)

    with tab_phase:
        st.markdown("### Transverse beam phase-space statistics")
        st.caption("Computes covariance-based RMS emittance and Twiss statistics. Define the physical meaning and units of momentum-like columns before interpretation.")
        if len(headers) < 4:
            st.info("At least four columns are needed for x, px, y, py analysis.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            x_col = c1.selectbox("x", headers, key=f"pl_dt_phase_x_{profile}")
            px_col = c2.selectbox("px / x′", headers, index=min(1, len(headers)-1), key=f"pl_dt_phase_px_{profile}")
            y_col = c3.selectbox("y", headers, index=min(2, len(headers)-1), key=f"pl_dt_phase_y_{profile}")
            py_col = c4.selectbox("py / y′", headers, index=min(3, len(headers)-1), key=f"pl_dt_phase_py_{profile}")
            bg_text = st.text_input("Optional βγ for normalized emittance", value="", placeholder="e.g. 1000", key=f"pl_dt_phase_bg_{profile}")
            if st.button("Analyze phase space", type="primary", key=f"pl_dt_phase_run_{profile}"):
                try:
                    bg = float(bg_text) if bg_text.strip() else None
                    result = analyze_beam_phase_space(_numeric(rows, x_col), _numeric(rows, px_col), _numeric(rows, y_col), _numeric(rows, py_col), beta_gamma=bg)
                    payload = result.to_dict()
                    path = _persist(workspace["path"], "beam-phase-space", dataset, {"x": x_col, "px": px_col, "y": y_col, "py": py_col, "betaGamma": bg}, payload, profile)
                    st.session_state[f"pl_dt_phase_result_{profile}"] = (payload, str(path))
                except Exception as exc:
                    st.error(str(exc))
            saved = st.session_state.get(f"pl_dt_phase_result_{profile}")
            if saved:
                payload, provenance_path = saved
                xp = payload["x_plane"]; yp = payload["y_plane"]
                _metric_grid(st, [
                    ("εx RMS", f"{xp['rms_emittance']:.6g}", "Geometric RMS emittance in inherited coordinate units"),
                    ("εy RMS", f"{yp['rms_emittance']:.6g}", "Geometric RMS emittance in inherited coordinate units"),
                    ("αx", "—" if xp["twiss_alpha"] is None else f"{xp['twiss_alpha']:.6g}", "Covariance-derived Twiss alpha"),
                    ("βx", "—" if xp["twiss_beta"] is None else f"{xp['twiss_beta']:.6g}", "Covariance-derived Twiss beta"),
                ])
                if payload.get("normalized_x_emittance") is not None:
                    st.caption(f"Normalized εx={payload['normalized_x_emittance']:.6g}, εy={payload['normalized_y_emittance']:.6g} using explicitly supplied βγ={payload['beta_gamma']:.6g}.")
                st.warning(payload["caveat"])
                st.code(provenance_path)

    with tab_sample:
        st.markdown("### Residual-guided remeasurement priorities")
        st.caption("Ranks already sampled coordinates by residual magnitude and local residual gradient. This is a transparent heuristic for where to remeasure/check first — not Bayesian information gain.")
        c1, c2, c3, c4 = st.columns(4)
        z_col = c1.selectbox("Position", headers, key=f"pl_dt_sample_z_{profile}")
        measured_col = c2.selectbox("Measured", headers, index=min(1, len(headers)-1), key=f"pl_dt_sample_m_{profile}")
        model_col = c3.selectbox("Model", headers, index=min(2, len(headers)-1), key=f"pl_dt_sample_p_{profile}")
        count = c4.number_input("Priority points", min_value=1, max_value=12, value=3, key=f"pl_dt_sample_n_{profile}")
        if st.button("Rank remeasurement points", type="primary", key=f"pl_dt_sample_run_{profile}"):
            try:
                result = suggest_residual_measurement_points(_numeric(rows, z_col), _numeric(rows, measured_col), _numeric(rows, model_col), count=int(count))
                path = _persist(workspace["path"], "residual-guided-remeasurement", dataset, {"positionColumn": z_col, "measuredColumn": measured_col, "modelColumn": model_col, "count": int(count)}, result, profile)
                st.session_state[f"pl_dt_sample_result_{profile}"] = (result, str(path))
            except Exception as exc:
                st.error(str(exc))
        saved = st.session_state.get(f"pl_dt_sample_result_{profile}")
        if saved:
            result, provenance_path = saved
            st.dataframe(result, width="stretch", hide_index=True)
            st.info("These are existing coordinates worth rechecking first. A future active-design module can propose unsampled coordinates only after a validated uncertainty/forward-model representation is available.")
            st.code(provenance_path)
