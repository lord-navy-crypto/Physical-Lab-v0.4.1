"""Engineering visualization extensions for Physical Lab.

Adds session cross-run baselines, authored uncertainty bands and 3D/trajectory
view controls. The wrapper receives figures before the v0.67 display transform,
so an uncertainty array is never silently rescaled independently of its data.
No solver arrays are modified.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import math
from typing import Any


PRESETS = {
    "Model default": {
        "uncertainty_style": "As authored", "overlay": False,
        "camera": "Respect model", "aspect": "Respect model",
        "surface_opacity": 1.0, "show_colorbar": True,
        "trajectory_line_width": 3, "trajectory_marker_size": 4,
    },
    "Engineering review": {
        "uncertainty_style": "Band from authored error_y", "overlay": True,
        "camera": "Isometric", "aspect": "Data",
        "surface_opacity": 0.85, "show_colorbar": True,
        "trajectory_line_width": 4, "trajectory_marker_size": 5,
    },
    "Publication": {
        "uncertainty_style": "Band from authored error_y", "overlay": False,
        "camera": "Isometric", "aspect": "Data",
        "surface_opacity": 0.95, "show_colorbar": True,
        "trajectory_line_width": 3, "trajectory_marker_size": 4,
    },
    "Dense trajectory": {
        "uncertainty_style": "As authored", "overlay": False,
        "camera": "Isometric", "aspect": "Data",
        "surface_opacity": 0.55, "show_colorbar": False,
        "trajectory_line_width": 2, "trajectory_marker_size": 2,
    },
    "Uncertainty review": {
        "uncertainty_style": "Band from authored error_y", "overlay": True,
        "camera": "Respect model", "aspect": "Respect model",
        "surface_opacity": 0.8, "show_colorbar": True,
        "trajectory_line_width": 3, "trajectory_marker_size": 4,
    },
}

CAMERAS = {
    "Isometric": {"eye": {"x": 1.55, "y": 1.55, "z": 1.25}},
    "Front": {"eye": {"x": 0.0, "y": 0.0, "z": 2.2}},
    "Side": {"eye": {"x": 2.2, "y": 0.0, "z": 0.0}},
    "Top": {"eye": {"x": 0.0, "y": 2.2, "z": 0.0}},
}


def _title(fig: Any) -> str:
    try:
        return str(fig.layout.title.text or "Untitled chart")
    except Exception:
        return "Untitled chart"


def _bounded_seq(value: Any, limit: int = 4000) -> list[Any] | None:
    try:
        seq = list(value)
    except Exception:
        return None
    if len(seq) > limit:
        stride = max(1, int(math.ceil(len(seq) / limit)))
        seq = seq[::stride]
        if seq and seq[-1] != list(value)[-1]:
            try:
                seq.append(list(value)[-1])
            except Exception:
                pass
    return seq


def _capture_figure(fig: Any) -> dict[str, Any]:
    traces = []
    for tr in getattr(fig, "data", ()):
        t = str(getattr(tr, "type", ""))
        if t not in {"scatter", "scattergl", "scatter3d"}:
            continue
        x = _bounded_seq(getattr(tr, "x", None)); y = _bounded_seq(getattr(tr, "y", None))
        if x is None or y is None:
            continue
        item = {"type": t, "name": str(getattr(tr, "name", "") or "trace"), "x": x, "y": y}
        if t == "scatter3d":
            z = _bounded_seq(getattr(tr, "z", None))
            if z is None:
                continue
            item["z"] = z
        traces.append(item)
        if len(traces) >= 12:
            break
    return {"title": _title(fig), "traces": traces}


def _apply_baseline(fig: Any, baseline: list[dict[str, Any]]) -> int:
    try:
        import plotly.graph_objects as go
    except Exception:
        return 0
    title = _title(fig)
    match = next((b for b in baseline if b.get("title") == title), None)
    if not match:
        return 0
    added = 0
    for tr in match.get("traces", [])[:12]:
        name = f"Baseline · {tr.get('name', 'trace')}"
        if tr.get("type") == "scatter3d":
            fig.add_trace(go.Scatter3d(x=tr.get("x"), y=tr.get("y"), z=tr.get("z"), mode="lines", name=name, opacity=0.42, line={"dash": "dash", "width": 3}))
        else:
            fig.add_trace(go.Scatter(x=tr.get("x"), y=tr.get("y"), mode="lines", name=name, opacity=0.48, line={"dash": "dot", "width": 2}))
        added += 1
    return added


def _error_arrays(trace: Any) -> tuple[list[float], list[float]] | None:
    err = getattr(trace, "error_y", None)
    if err is None:
        return None
    arr = getattr(err, "array", None)
    if arr is None:
        return None
    try:
        plus = [abs(float(v)) for v in list(arr)]
    except Exception:
        return None
    arr_minus = getattr(err, "arrayminus", None)
    if arr_minus is None:
        minus = plus
    else:
        try:
            minus = [abs(float(v)) for v in list(arr_minus)]
        except Exception:
            return None
    return plus, minus


def _add_uncertainty_bands(fig: Any) -> int:
    try:
        import plotly.graph_objects as go
    except Exception:
        return 0
    bands = []
    for trace in list(getattr(fig, "data", ())):
        if str(getattr(trace, "type", "")) not in {"scatter", "scattergl"}:
            continue
        arrays = _error_arrays(trace)
        if arrays is None:
            continue
        try:
            x = list(trace.x); y = [float(v) for v in list(trace.y)]
        except Exception:
            continue
        plus, minus = arrays
        n = min(len(x), len(y), len(plus), len(minus))
        if n < 2:
            continue
        x = x[:n]; y = y[:n]; plus = plus[:n]; minus = minus[:n]
        lower = [y[i] - minus[i] for i in range(n)]
        upper = [y[i] + plus[i] for i in range(n)]
        base_name = str(getattr(trace, "name", "") or "trace")
        bands.append(go.Scatter(x=x, y=lower, mode="lines", line={"width": 0}, hoverinfo="skip", showlegend=False, legendgroup=f"uq-{base_name}"))
        bands.append(go.Scatter(x=x, y=upper, mode="lines", line={"width": 0}, fill="tonexty", opacity=0.16, name=f"Uncertainty · {base_name}", hoverinfo="skip", showlegend=True, legendgroup=f"uq-{base_name}"))
        try:
            trace.error_y.visible = False
        except Exception:
            pass
    for band in bands:
        fig.add_trace(band)
    return len(bands) // 2


def _hide_error_y(fig: Any) -> int:
    count = 0
    for trace in getattr(fig, "data", ()):
        if _error_arrays(trace) is not None:
            try:
                trace.error_y.visible = False
                count += 1
            except Exception:
                pass
    return count


def _apply_3d(fig: Any, settings: dict[str, Any]) -> bool:
    has_3d = False
    for trace in getattr(fig, "data", ()):
        t = str(getattr(trace, "type", ""))
        if t == "scatter3d":
            has_3d = True
            try:
                if getattr(trace, "line", None) is not None:
                    trace.line.width = int(settings.get("trajectory_line_width", 3))
                if getattr(trace, "marker", None) is not None:
                    trace.marker.size = int(settings.get("trajectory_marker_size", 4))
            except Exception:
                pass
        elif t in {"surface", "mesh3d"}:
            has_3d = True
            try:
                trace.opacity = float(settings.get("surface_opacity", 1.0))
                if hasattr(trace, "showscale"):
                    trace.showscale = bool(settings.get("show_colorbar", True))
            except Exception:
                pass
    if not has_3d:
        return False
    camera = settings.get("camera", "Respect model")
    aspect = settings.get("aspect", "Respect model")
    kwargs = {}
    if camera in CAMERAS:
        kwargs["camera"] = CAMERAS[camera]
    if aspect != "Respect model":
        kwargs["aspectmode"] = str(aspect).lower()
    if kwargs:
        fig.update_layout(scene=kwargs)
    return True


def render_engineering_visual_controls(st: Any, profile: str) -> dict[str, Any]:
    with st.expander("Visualization Studio · Engineering overlays", expanded=False):
        st.caption("Cross-run baselines, authored uncertainty and 3D controls are display-only. A baseline is the previous rendered solver state from this session; it is not experimental validation.")
        c0, c00 = st.columns([2, 1])
        preset = c0.selectbox("Visualization preset", list(PRESETS), key=f"pl_viz2_preset_{profile}")
        if c00.button("Apply preset", key=f"pl_viz2_apply_{profile}"):
            p = PRESETS[preset]
            for field, value in p.items():
                st.session_state[f"pl_viz2_{field}_{profile}"] = value
            st.rerun()

        c1, c2, c3 = st.columns(3)
        uncertainty_style = c1.selectbox("Authored uncertainty", ["As authored", "Band from authored error_y", "Hide authored uncertainty"], key=f"pl_viz2_uncertainty_style_{profile}")
        overlay = c2.toggle("Cross-run baseline overlay", value=False, key=f"pl_viz2_overlay_{profile}")
        camera = c3.selectbox("3D camera", ["Respect model", "Isometric", "Front", "Side", "Top"], key=f"pl_viz2_camera_{profile}")
        c4, c5, c6 = st.columns(3)
        aspect = c4.selectbox("3D aspect", ["Respect model", "Data", "Cube", "Auto"], key=f"pl_viz2_aspect_{profile}")
        surface_opacity = c5.slider("Surface opacity", 0.15, 1.0, 1.0, 0.05, key=f"pl_viz2_surface_opacity_{profile}")
        show_colorbar = c6.toggle("3D color scale", value=True, key=f"pl_viz2_show_colorbar_{profile}")
        c7, c8 = st.columns(2)
        trajectory_line_width = c7.slider("3D trajectory line width", 1, 9, 3, 1, key=f"pl_viz2_trajectory_line_width_{profile}")
        trajectory_marker_size = c8.slider("3D trajectory marker size", 1, 12, 4, 1, key=f"pl_viz2_trajectory_marker_size_{profile}")

        last = st.session_state.get(f"__pl_viz2_last_{profile}") or []
        baseline = st.session_state.get(f"__pl_viz2_baseline_{profile}") or []
        b1, b2 = st.columns(2)
        if b1.button(f"Capture previous render as baseline ({len(last)} charts)", disabled=not bool(last), key=f"pl_viz2_capture_{profile}"):
            st.session_state[f"__pl_viz2_baseline_{profile}"] = copy.deepcopy(last)
            st.success("Previous rendered state captured as the session baseline.")
        if b2.button("Clear baseline", disabled=not bool(baseline), key=f"pl_viz2_clear_{profile}"):
            st.session_state.pop(f"__pl_viz2_baseline_{profile}", None)
            st.success("Cross-run baseline cleared.")
        if overlay and not baseline:
            st.info("Run the model once, change a parameter, then capture the previous render as baseline before enabling comparison.")
        st.caption("Cross-run overlay is intentionally session-scoped in this version. Run Vault remains the authoritative persistent provenance record.")

    return {
        "uncertainty_style": uncertainty_style,
        "overlay": bool(overlay),
        "camera": camera,
        "aspect": aspect,
        "surface_opacity": float(surface_opacity),
        "show_colorbar": bool(show_colorbar),
        "trajectory_line_width": int(trajectory_line_width),
        "trajectory_marker_size": int(trajectory_marker_size),
    }


@contextmanager
def engineering_visualization_context(st: Any, profile: str):
    settings = render_engineering_visual_controls(st, profile)
    original = st.plotly_chart
    current_capture: list[dict[str, Any]] = []

    def wrapped(fig: Any, *args: Any, **kwargs: Any):
        try:
            import plotly.graph_objects as go
            out = go.Figure(fig)
        except Exception:
            return original(fig, *args, **kwargs)
        current_capture.append(_capture_figure(out))
        labels = []
        style = settings.get("uncertainty_style")
        if style == "Band from authored error_y":
            n = _add_uncertainty_bands(out)
            if n:
                labels.append(f"{n} authored uncertainty band(s)")
        elif style == "Hide authored uncertainty":
            n = _hide_error_y(out)
            if n:
                labels.append("authored uncertainty hidden")
        baseline = st.session_state.get(f"__pl_viz2_baseline_{profile}") or []
        if settings.get("overlay") and baseline:
            n = _apply_baseline(out, baseline)
            if n:
                labels.append(f"{n} baseline trace(s)")
        if _apply_3d(out, settings):
            if settings.get("camera") != "Respect model" or settings.get("aspect") != "Respect model":
                labels.append("3D view override")
        if labels:
            title = _title(out)
            out.update_layout(title=f"{title} · ENGINEERING VIEW: {' · '.join(labels)}")
        return original(out, *args, **kwargs)

    st.plotly_chart = wrapped
    try:
        yield settings
    finally:
        st.plotly_chart = original
        st.session_state[f"__pl_viz2_last_{profile}"] = current_capture[:20]
