"""Physical Lab ↔ RADIA Magnet Studio Full-mode adapter.

This module reuses the *current managed RADIA Magnet Studio* forward-model APIs.
It does not duplicate magnet geometry or field-solving physics. It adds two
Physical Lab capabilities:

1. evaluate the current Magnet Studio model at measurement coordinates; and
2. perform a bounded, transparent one-parameter profile scan against measured
   field data using repeated real RADIA forward solves.

All public operations require PHYSICAL_LAB_ENGINE_MODE=full.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from physical_lab_digital_twin import compare_field_series

RADIA_MAGNET_STUDIO_REVISION = "3bceb02a5195a6eb14d01458cc44f7206ed6b40a"
RADIA_RUNTIME_REVISION = "7ff3b2dc26cbcccfcb0aaf3c4a290ebd83439698"
MAX_FORWARD_POINTS = 20_000
MAX_PROFILE_POINTS = 11
_ALLOWED_COMPONENTS = {"Bx": 0, "By": 1, "Bz": 2, "Bperp": 3}
_ALLOWED_PROFILE_PARAMETERS = {"gap_mm", "br_t", "z_offset_mm"}


def _require_full_mode() -> None:
    mode = os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "").strip().lower()
    if mode != "full":
        raise RuntimeError("The real RADIA forward adapter is available only in Physical Lab Full mode")


def _callable(namespace: Mapping[str, Any], name: str):
    fn = namespace.get(name)
    if not callable(fn):
        raise RuntimeError(f"RADIA Magnet Studio API {name!r} is unavailable in this managed revision")
    return fn


def _finite_positions(values: Iterable[float]) -> list[float]:
    output: list[float] = []
    for value in values:
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("RADIA sampling positions must be finite")
        output.append(value)
    if not output:
        raise ValueError("At least one RADIA sampling position is required")
    if len(output) > MAX_FORWARD_POINTS:
        raise ValueError(f"A single forward evaluation is limited to {MAX_FORWARD_POINTS:,} positions")
    return output


def _field_rows(raw_field: Any, positions: Sequence[float]) -> list[dict[str, float]]:
    if len(raw_field) != len(positions):
        raise RuntimeError("RADIA returned a field array with an unexpected length")
    rows: list[dict[str, float]] = []
    for z, vector in zip(positions, raw_field):
        if len(vector) < 3:
            raise RuntimeError(f"RADIA returned an invalid field vector at z={z!r}: {vector!r}")
        bx, by, bz = (float(vector[0]), float(vector[1]), float(vector[2]))
        if not all(math.isfinite(v) for v in (bx, by, bz)):
            raise RuntimeError(f"RADIA returned a non-finite field vector at z={z!r}")
        rows.append({
            "z_mm": float(z),
            "Bx_T": bx,
            "By_T": by,
            "Bz_T": bz,
            "Bperp_T": math.hypot(bx, by),
        })
    return rows


def _component(rows: Sequence[Mapping[str, float]], component: str) -> list[float]:
    if component not in _ALLOWED_COMPONENTS:
        raise ValueError(f"component must be one of {sorted(_ALLOWED_COMPONENTS)}")
    key = {"Bx": "Bx_T", "By": "By_T", "Bz": "Bz_T", "Bperp": "Bperp_T"}[component]
    return [float(row[key]) for row in rows]


def _cleanup(rad: Any) -> None:
    try:
        if hasattr(rad, "UtiDelAll"):
            rad.UtiDelAll()
    except Exception:
        pass


def _resolved_params(namespace: Mapping[str, Any], rad: Any) -> tuple[dict[str, Any], list[Any]]:
    params = dict(namespace.get("current_params") or {})
    if not params:
        raise RuntimeError("RADIA Magnet Studio did not expose current_params")
    history: list[Any] = []
    if bool(params.get("target_b0_enabled")):
        calibrate_br = _callable(namespace, "calibrate_br")
        calibrated_br, history = calibrate_br(
            rad,
            params.get("device"),
            params,
            float(params.get("target_b0_t")),
            mode=params.get("b0_definition", "Central-period peak B⊥"),
            relax=bool((namespace.get("current_settings") or {}).get("relax", False)),
            precision=float((namespace.get("current_settings") or {}).get("precision", 1e-4)),
            max_iter=int((namespace.get("current_settings") or {}).get("max_iter", 1000)),
        )
        params["br_t"] = float(calibrated_br)
        _cleanup(rad)
    return params, list(history or [])


def _build_solve_sample(namespace: Mapping[str, Any], rad: Any, params: Mapping[str, Any], positions_mm: Sequence[float]) -> list[dict[str, float]]:
    build_device = _callable(namespace, "build_device")
    solve_model = _callable(namespace, "solve_model")
    sample_on_axis = _callable(namespace, "sample_on_axis")
    settings = dict(namespace.get("current_settings") or {})
    model = build_device(rad, params.get("device"), dict(params))
    if not isinstance(model, Mapping) or "obj" not in model:
        raise RuntimeError("RADIA Magnet Studio build_device returned an invalid model")
    solve_model(
        rad,
        model,
        relax=bool(settings.get("relax", False)),
        precision=float(settings.get("precision", 1e-4)),
        max_iter=int(settings.get("max_iter", 1000)),
        method=int(settings.get("method", 4)),
    )
    return _field_rows(sample_on_axis(rad, model["obj"], positions_mm), positions_mm)


def run_current_radia_forward_model(namespace: Mapping[str, Any], positions_mm: Iterable[float]) -> dict[str, Any]:
    """Evaluate the current Magnet Studio model on axis at explicit z positions in mm."""
    _require_full_mode()
    positions = _finite_positions(positions_mm)
    load_radia = _callable(namespace, "load_radia")
    rad = load_radia()
    try:
        _cleanup(rad)
        params, calibration_history = _resolved_params(namespace, rad)
        fields = _build_solve_sample(namespace, rad, params, positions)
        settings = dict(namespace.get("current_settings") or {})
        return {
            "schema": "physical-lab-radia-forward-v1",
            "radiaMagnetStudioRevision": RADIA_MAGNET_STUDIO_REVISION,
            "radiaRuntimeRevision": RADIA_RUNTIME_REVISION,
            "coordinateConvention": "on-axis x=0 mm, y=0 mm; supplied coordinate is z in mm",
            "fieldUnit": "T",
            "positions": len(positions),
            "device": params.get("device"),
            "parameters": params,
            "settings": settings,
            "targetB0CalibrationHistory": calibration_history,
            "fields": fields,
            "boundary": "This is a real RADIA Full-mode field evaluation of the current managed Magnet Studio model. It does not establish that the model geometry/material parameters match a physical magnet.",
        }
    finally:
        _cleanup(rad)


def _paired_measurements(position: Iterable[float], measured: Iterable[float]) -> tuple[list[float], list[float]]:
    z_out: list[float] = []
    m_out: list[float] = []
    for z, value in zip(position, measured):
        try:
            z = float(z); value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(z) and math.isfinite(value):
            z_out.append(z); m_out.append(value)
    if len(z_out) < 3:
        raise ValueError("At least three finite measured field samples are required for a RADIA profile scan")
    if len(z_out) > MAX_FORWARD_POINTS:
        raise ValueError(f"A profile scan is limited to {MAX_FORWARD_POINTS:,} measured samples")
    return z_out, m_out


def run_bounded_radia_parameter_profile(
    namespace: Mapping[str, Any],
    position_mm: Iterable[float],
    measured_field_t: Iterable[float],
    *,
    component: str,
    parameter: str,
    candidate_values: Iterable[float],
) -> dict[str, Any]:
    """Run a bounded one-parameter profile using repeated real RADIA forward solves.

    The result identifies the best *sampled candidate* by RMSE. It is deliberately
    not labeled a posterior, confidence interval, or globally optimal fit.
    """
    _require_full_mode()
    if parameter not in _ALLOWED_PROFILE_PARAMETERS:
        raise ValueError(f"parameter must be one of {sorted(_ALLOWED_PROFILE_PARAMETERS)}")
    if component not in _ALLOWED_COMPONENTS:
        raise ValueError(f"component must be one of {sorted(_ALLOWED_COMPONENTS)}")
    z, measured = _paired_measurements(position_mm, measured_field_t)
    candidates = sorted({float(v) for v in candidate_values})
    if len(candidates) < 3 or len(candidates) > MAX_PROFILE_POINTS:
        raise ValueError(f"Use between 3 and {MAX_PROFILE_POINTS} unique candidate values")
    if not all(math.isfinite(v) for v in candidates):
        raise ValueError("Candidate values must be finite")
    if parameter in {"gap_mm", "br_t"} and min(candidates) <= 0:
        raise ValueError(f"{parameter} candidates must be positive")

    base_params = dict(namespace.get("current_params") or {})
    if not base_params:
        raise RuntimeError("RADIA Magnet Studio did not expose current_params")
    if bool(base_params.get("target_b0_enabled")):
        raise ValueError("Disable target-B0 calibration before a bounded physical-parameter profile so the scanned parameter remains identifiable")
    if bool(base_params.get("errors_enabled")):
        raise ValueError("Disable stochastic manufacturing errors before a bounded parameter profile; fit the deterministic baseline first")

    load_radia = _callable(namespace, "load_radia")
    rad = load_radia()
    rows: list[dict[str, float]] = []
    try:
        for candidate in candidates:
            _cleanup(rad)
            params = dict(base_params)
            sample_z = list(z)
            if parameter == "z_offset_mm":
                sample_z = [value + candidate for value in z]
            else:
                params[parameter] = candidate
            fields = _build_solve_sample(namespace, rad, params, sample_z)
            predicted = _component(fields, component)
            comparison = compare_field_series(z, measured, predicted)
            rows.append({
                "candidate": candidate,
                "rmse_T": float(comparison.rmse),
                "mae_T": float(comparison.mae),
                "bias_T": float(comparison.bias),
                "max_abs_error_T": float(comparison.max_abs_error),
                "field_integral_difference_T_mm": float(comparison.integral_difference),
            })
        best = min(rows, key=lambda item: item["rmse_T"])
        return {
            "schema": "physical-lab-radia-parameter-profile-v1",
            "radiaMagnetStudioRevision": RADIA_MAGNET_STUDIO_REVISION,
            "radiaRuntimeRevision": RADIA_RUNTIME_REVISION,
            "parameter": parameter,
            "component": component,
            "candidateCount": len(rows),
            "measuredSamples": len(z),
            "baselineValue": 0.0 if parameter == "z_offset_mm" else float(base_params.get(parameter)),
            "bestSampledCandidate": best,
            "profile": rows,
            "boundary": "Best candidate means the smallest RMSE among this explicit finite grid. This is a one-parameter deterministic profile, not a posterior distribution, confidence interval, multi-parameter optimum, or proof that the underlying magnet model is complete.",
        }
    finally:
        _cleanup(rad)


# ------------------------------- Streamlit integration -------------------------------

def _write_forward_dataset(workspace: Path, dataset: Mapping[str, Any], headers: Sequence[str], source_rows: Sequence[Mapping[str, str]], valid_indices: Sequence[int], result: Mapping[str, Any]) -> Path:
    from physical_lab_digital_twin_ui import _now, _sha256, _slug

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    parent_id = str(dataset["metadata"].get("id") or dataset["folder"].name)
    dataset_id = f"{_slug(parent_id)}-radia-forward-{stamp}"
    folder = workspace / "datasets" / dataset_id
    folder.mkdir(parents=True, exist_ok=False)
    target = folder / "data.csv"
    model_columns = ["radia_Bx_T", "radia_By_T", "radia_Bz_T", "radia_Bperp_T"]
    output_headers = list(headers) + [name for name in model_columns if name not in headers]
    field_by_index = {index: field for index, field in zip(valid_indices, result["fields"])}
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=output_headers)
        writer.writeheader()
        for index, row in enumerate(source_rows):
            item = dict(row)
            field = field_by_index.get(index)
            if field is not None:
                item["radia_Bx_T"] = f"{float(field['Bx_T']):.17g}"
                item["radia_By_T"] = f"{float(field['By_T']):.17g}"
                item["radia_Bz_T"] = f"{float(field['Bz_T']):.17g}"
                item["radia_Bperp_T"] = f"{float(field['Bperp_T']):.17g}"
            writer.writerow(item)
    meta = {
        "schema": "physical-lab-dataset-v1",
        "id": dataset_id,
        "name": f"{dataset['metadata'].get('name') or parent_id} + RADIA forward field",
        "quantity": "Magnetic field",
        "unit": "T",
        "sensor": dataset["metadata"].get("sensor", ""),
        "calibration": dataset["metadata"].get("calibration", ""),
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
            "operation": "radia-full-mode-forward-model",
            "radiaMagnetStudioRevision": RADIA_MAGNET_STUDIO_REVISION,
            "radiaRuntimeRevision": RADIA_RUNTIME_REVISION,
            "coordinateConvention": result["coordinateConvention"],
            "parameters": result["parameters"],
            "settings": result["settings"],
        },
    }
    (folder / "metadata.json").write_text(json.dumps(meta, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    return folder


def render_radia_forward_workspace(st: Any, namespace: Mapping[str, Any]) -> None:
    """Render Full-mode RADIA forward/parameter-profile tools inside Magnet Studio."""
    st.markdown("---")
    st.markdown("## Physical Lab · RADIA Measurement Adapter")
    st.caption(
        "Use the current Magnet Studio configuration as a real RADIA forward model at coordinates stored in a `.physlab` measurement dataset. "
        "The adapter reuses the managed Magnet Studio solver; it does not contain a second magnet model."
    )
    if os.environ.get("PHYSICAL_LAB_ENGINE_MODE", "").strip().lower() != "full":
        st.info("Switch RADIA Magnet Studio to **Full mode** to use real forward solves and bounded parameter profiles. Safe mode remains an analytic fallback.")
        return

    try:
        from physical_lab_digital_twin_ui import _datasets, _numeric, _persist, _read_table, _workspaces
    except Exception as exc:
        st.error(f"Measurement Digital Twin project layer is unavailable: {exc}")
        return

    workspaces = _workspaces()
    if not workspaces:
        st.info("Create a `.physlab` project and import a CSV/TSV measurement first.")
        return
    workspace_labels = [f"{w['name']} · {w['id']}" for w in workspaces]
    selected_workspace = st.selectbox("RADIA adapter project", workspace_labels, key="pl_radia_adapter_workspace")
    workspace = workspaces[workspace_labels.index(selected_workspace)]
    datasets = _datasets(workspace["path"])
    if not datasets:
        st.info("The selected project has no CSV/TSV datasets.")
        return
    dataset_labels = [f"{d['metadata'].get('name') or d['folder'].name} · {d['metadata'].get('id') or d['folder'].name}" for d in datasets]
    selected_dataset = st.selectbox("Measurement dataset", dataset_labels, key="pl_radia_adapter_dataset")
    dataset = datasets[dataset_labels.index(selected_dataset)]
    try:
        headers, rows = _read_table(dataset["path"])
    except Exception as exc:
        st.error(f"Could not read dataset: {exc}")
        return
    if not headers or not rows:
        st.warning("The selected dataset has no readable rows")
        return

    tab_forward, tab_profile = st.tabs(["Generate RADIA field dataset", "Bounded physical parameter profile"])

    with tab_forward:
        z_col = st.selectbox("On-axis z coordinate column", headers, key="pl_radia_forward_z")
        confirmed = st.checkbox(
            "I confirm this column is on-axis z in millimetres (x=0 mm, y=0 mm); RADIA output will be stored in tesla.",
            key="pl_radia_forward_units",
        )
        if st.button("Run real RADIA forward model", type="primary", disabled=not confirmed, key="pl_radia_forward_run"):
            values = _numeric(rows, z_col)
            valid_indices = [i for i, value in enumerate(values) if math.isfinite(value)]
            positions = [values[i] for i in valid_indices]
            if not positions:
                st.error("No finite z coordinates were found")
            else:
                try:
                    with st.spinner(f"Solving current RADIA model at {len(positions):,} measurement coordinates…"):
                        result = run_current_radia_forward_model(namespace, positions)
                    folder = _write_forward_dataset(workspace["path"], dataset, headers, rows, valid_indices, result)
                    provenance = _persist(
                        workspace["path"],
                        "radia-full-mode-forward-model",
                        dataset,
                        {"positionColumn": z_col, "coordinateConvention": result["coordinateConvention"]},
                        {k: v for k, v in result.items() if k != "fields"},
                        "radia-magnet-studio",
                    )
                    st.session_state["pl_radia_forward_result"] = (result, str(folder), str(provenance))
                except Exception as exc:
                    st.error(f"RADIA forward model failed: {exc}")
        saved = st.session_state.get("pl_radia_forward_result")
        if saved:
            result, folder, provenance = saved
            bperp = [float(row["Bperp_T"]) for row in result["fields"]]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Solved points", f"{result['positions']:,}")
            c2.metric("Peak B⊥", f"{max(bperp):.6g} T")
            c3.metric("Device", str(result.get("device") or "—"))
            c4.metric("RADIA revision", result["radiaRuntimeRevision"][:12])
            st.success(f"Created lineage-tracked model dataset: {Path(folder).name}")
            st.caption(result["boundary"])
            st.code(provenance)

    with tab_profile:
        st.caption(
            "Each candidate below is evaluated with the real RADIA forward model. The result is a finite one-parameter RMSE profile — not a Bayesian posterior or multi-parameter optimizer."
        )
        if bool((namespace.get("current_params") or {}).get("target_b0_enabled")):
            st.warning("Disable target-B0 calibration before parameter profiling so the scanned parameter remains identifiable.")
        if bool((namespace.get("current_params") or {}).get("errors_enabled")):
            st.warning("Disable stochastic manufacturing errors before parameter profiling; fit the deterministic baseline first.")
        c1, c2, c3 = st.columns(3)
        z_col = c1.selectbox("z column (mm)", headers, key="pl_radia_profile_z")
        measured_col = c2.selectbox("Measured field column (T)", headers, index=min(1, len(headers)-1), key="pl_radia_profile_measured")
        component = c3.selectbox("RADIA component", ["Bx", "By", "Bz", "Bperp"], key="pl_radia_profile_component")
        parameter = st.selectbox("Physical parameter", ["gap_mm", "br_t", "z_offset_mm"], key="pl_radia_profile_parameter")
        params = dict(namespace.get("current_params") or {})
        if parameter == "gap_mm":
            center = float(params.get("gap_mm", 12.0)); default_min, default_max = 0.85*center, 1.15*center
        elif parameter == "br_t":
            center = float(params.get("br_t", 1.2)); default_min, default_max = 0.90*center, 1.10*center
        else:
            period = float(params.get("period_mm", 50.0)); default_min, default_max = -0.5*period, 0.5*period
        c4, c5, c6 = st.columns(3)
        lower = c4.number_input("Candidate minimum", value=float(default_min), key=f"pl_radia_profile_min_{parameter}")
        upper = c5.number_input("Candidate maximum", value=float(default_max), key=f"pl_radia_profile_max_{parameter}")
        points = c6.select_slider("Candidate points", options=[3, 5, 7, 9, 11], value=5, key="pl_radia_profile_points")
        confirmed = st.checkbox(
            "I confirm z is in mm and the measured field column is in tesla with the selected component convention.",
            key="pl_radia_profile_units",
        )
        blocked = upper <= lower or not confirmed or bool(params.get("target_b0_enabled")) or bool(params.get("errors_enabled"))
        if st.button("Run bounded RADIA profile", type="primary", disabled=blocked, key="pl_radia_profile_run"):
            import numpy as np
            try:
                candidates = np.linspace(float(lower), float(upper), int(points))
                with st.spinner(f"Running {int(points)} real RADIA forward solves…"):
                    result = run_bounded_radia_parameter_profile(
                        namespace,
                        _numeric(rows, z_col),
                        _numeric(rows, measured_col),
                        component=component,
                        parameter=parameter,
                        candidate_values=candidates,
                    )
                provenance = _persist(
                    workspace["path"],
                    "radia-bounded-parameter-profile",
                    dataset,
                    {"positionColumn": z_col, "measuredColumn": measured_col, "component": component, "parameter": parameter, "candidateMin": float(lower), "candidateMax": float(upper), "candidatePoints": int(points)},
                    result,
                    "radia-magnet-studio",
                )
                st.session_state["pl_radia_profile_result"] = (result, str(provenance))
            except Exception as exc:
                st.error(f"RADIA parameter profile failed: {exc}")
        saved = st.session_state.get("pl_radia_profile_result")
        if saved:
            result, provenance = saved
            best = result["bestSampledCandidate"]
            c1, c2, c3 = st.columns(3)
            c1.metric("Best sampled candidate", f"{best['candidate']:.8g}")
            c2.metric("Best RMSE", f"{best['rmse_T']:.4g} T")
            c3.metric("Candidates", str(result["candidateCount"]))
            st.dataframe(result["profile"], width="stretch", hide_index=True)
            st.warning(result["boundary"])
            st.code(provenance)
