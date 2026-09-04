"""Model-aware, display-only visualization controls for Physical Lab advanced suites.

This module never mutates solver inputs or stored scientific results. It wraps
Streamlit Plotly rendering only while Physical Lab advanced experiments render.
Display transforms are explicitly labeled and are suppressed when authored
uncertainty or an engineering overlay would make an independent transform
physically misleading.
"""
from __future__ import annotations

from contextlib import contextmanager
import math
from typing import Any, Iterable


PROFILE_LABELS = {
    "numerical-methods": "Numerical Reliability",
    "ising-monte-carlo": "Ising Criticality",
    "random-walk-monte-carlo": "Random Walk & Monte Carlo",
    "nonlinear-chaos": "Nonlinear Dynamics & Chaos",
    "oscillation-integration": "Oscillator Dynamics",
    "radia-magnet-studio": "RADIA Magnet Engineering",
    "radiation-platform": "Radiation & Undulator Analysis",
}

PROFILE_HINTS = {
    "numerical-methods": "Prioritize error scale, cancellation structure and threshold visibility.",
    "ising-monte-carlo": "Compare finite-size response curves without hiding raw critical behavior.",
    "random-walk-monte-carlo": "Keep theory/reference overlays optional and preserve authored scaling.",
    "nonlinear-chaos": "Keep phase portraits dense enough to show structure while bounding rendering cost.",
    "oscillation-integration": "Preserve resonance, phase and energy-balance structure; heatmap transforms are display-only.",
    "radia-magnet-studio": "Compare solved/tolerance metrics without converting normalized views into physical units.",
    "radiation-platform": "Separate ideal/reference overlays from upstream/full-model traces and keep units explicit.",
}

REFERENCE_TOKENS = ("reference", "theory", "ideal", "exact", "asymptotic", "onsager")

VIEW_PRESETS = {
    "Model default": {
        "line_transform": "As authored", "heatmap_transform": "As authored", "template": "Physical Lab",
        "x_scale": "Respect model", "y_scale": "Respect model", "height": 500, "max_points": 5000,
        "line_width": 2.0, "marker_size": 6, "font_size": 13, "hover": "closest",
        "show_legend": True, "show_grid": True, "show_reference": True, "modebar": True, "scroll_zoom": False,
    },
    "Engineering review": {
        "line_transform": "As authored", "heatmap_transform": "As authored", "template": "Physical Lab",
        "x_scale": "Respect model", "y_scale": "Respect model", "height": 580, "max_points": 5000,
        "line_width": 2.5, "marker_size": 6, "font_size": 13, "hover": "x unified",
        "show_legend": True, "show_grid": True, "show_reference": True, "modebar": True, "scroll_zoom": False,
    },
    "Publication": {
        "line_transform": "As authored", "heatmap_transform": "As authored", "template": "Light",
        "x_scale": "Respect model", "y_scale": "Respect model", "height": 580, "max_points": 10000,
        "line_width": 2.5, "marker_size": 5, "font_size": 14, "hover": "closest",
        "show_legend": True, "show_grid": True, "show_reference": True, "modebar": False, "scroll_zoom": False,
    },
    "Dense / performance": {
        "line_transform": "As authored", "heatmap_transform": "As authored", "template": "Physical Lab",
        "x_scale": "Respect model", "y_scale": "Respect model", "height": 500, "max_points": 2500,
        "line_width": 1.5, "marker_size": 4, "font_size": 12, "hover": "closest",
        "show_legend": True, "show_grid": False, "show_reference": True, "modebar": True, "scroll_zoom": False,
    },
}


def _finite_numeric(values: Any) -> list[float]:
    try:
        seq = list(values)
    except Exception:
        return []
    out: list[float] = []
    for value in seq:
        try:
            x = float(value)
        except Exception:
            continue
        if math.isfinite(x):
            out.append(x)
    return out


def _array_transform(values: Any, mode: str) -> Any:
    if mode == "As authored":
        return values
    try:
        import numpy as np
        arr = np.asarray(values, dtype=float)
    except Exception:
        return values
    finite = np.isfinite(arr)
    if not finite.any():
        return values
    out = arr.copy()
    data = arr[finite]
    if mode == "Normalize max |y|":
        scale = float(np.max(np.abs(data)))
        if scale <= np.finfo(float).tiny:
            return values
        out[finite] = data / scale
    elif mode == "Z-score":
        mean = float(np.mean(data)); sd = float(np.std(data))
        if sd <= np.finfo(float).tiny:
            return values
        out[finite] = (data - mean) / sd
    elif mode == "Percent change from first":
        first = next((float(x) for x in data if abs(float(x)) > np.finfo(float).tiny), None)
        if first is None:
            return values
        out[finite] = 100.0 * (data / first - 1.0)
    else:
        return values
    return out


def _heatmap_transform(values: Any, mode: str) -> Any:
    if mode == "As authored":
        return values
    try:
        import numpy as np
        arr = np.asarray(values, dtype=float)
    except Exception:
        return values
    finite = np.isfinite(arr)
    if not finite.any():
        return values
    out = arr.copy(); data = arr[finite]
    if mode == "log10 |z|":
        positive = np.abs(data)
        positive = positive[positive > np.finfo(float).tiny]
        if not positive.size:
            return values
        floor = float(np.min(positive))
        out[finite] = np.log10(np.maximum(np.abs(data), floor))
    elif mode == "Normalize 0–1":
        lo = float(np.min(data)); hi = float(np.max(data))
        if hi - lo <= np.finfo(float).tiny:
            return values
        out[finite] = (data - lo) / (hi - lo)
    elif mode == "Z-score":
        mean = float(np.mean(data)); sd = float(np.std(data))
        if sd <= np.finfo(float).tiny:
            return values
        out[finite] = (data - mean) / sd
    else:
        return values
    return out


def _sequence_matches(value: Any, n: int) -> bool:
    if value is None or isinstance(value, (str, bytes)):
        return False
    try:
        return len(value) == n
    except Exception:
        return False


def _trace_has_error_arrays(trace: Any) -> bool:
    for axis_name in ("error_x", "error_y"):
        err = getattr(trace, axis_name, None)
        if err is not None and (getattr(err, "array", None) is not None or getattr(err, "arrayminus", None) is not None):
            return True
    return False


def _has_aligned_auxiliary_arrays(trace: Any, n: int) -> bool:
    """Return True when stride-decimation could desynchronize authored metadata."""
    for attr in ("customdata", "text", "hovertext", "ids"):
        if _sequence_matches(getattr(trace, attr, None), n):
            return True
    for axis_name in ("error_x", "error_y"):
        err = getattr(trace, axis_name, None)
        if err is not None and (
            _sequence_matches(getattr(err, "array", None), n)
            or _sequence_matches(getattr(err, "arrayminus", None), n)
        ):
            return True
    marker = getattr(trace, "marker", None)
    if marker is not None:
        for attr in ("color", "size", "symbol", "opacity"):
            if _sequence_matches(getattr(marker, attr, None), n):
                return True
    return False


def _safe_decimate(trace: Any, max_points: int) -> bool:
    """Decimate only simple scatter traces whose aligned metadata stays valid."""
    if getattr(trace, "type", "") not in {"scatter", "scattergl"}:
        return False
    x = getattr(trace, "x", None); y = getattr(trace, "y", None)
    try:
        n = min(len(x), len(y))
    except Exception:
        return False
    if n <= max_points or max_points < 100:
        return False
    if _has_aligned_auxiliary_arrays(trace, n):
        return False
    stride = max(1, int(math.ceil(n / max_points)))
    idx = list(range(0, n, stride))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    try:
        trace.x = [x[i] for i in idx]
        trace.y = [y[i] for i in idx]
        return True
    except Exception:
        return False


def _trace_role(trace: Any) -> str:
    meta = getattr(trace, "meta", None)
    if isinstance(meta, dict):
        role = str(meta.get("physical_lab_role", "") or "")
        if role:
            return role
    name = str(getattr(trace, "name", "") or "")
    legendgroup = str(getattr(trace, "legendgroup", "") or "")
    if name.startswith("Baseline ·"):
        return "baseline"
    if name.startswith("Uncertainty ·") or legendgroup.startswith("uq-"):
        return "uncertainty_band"
    return ""


def _has_engineering_overlay(fig: Any) -> bool:
    return any(_trace_role(trace) in {"baseline", "uncertainty_band"} for trace in getattr(fig, "data", ()))


def _has_authored_uncertainty(fig: Any) -> bool:
    return any(_trace_has_error_arrays(trace) for trace in getattr(fig, "data", ()))


def _axis_is_positive(fig: Any, axis: str) -> bool:
    found = False
    for trace in getattr(fig, "data", ()):
        if getattr(trace, "visible", None) in {False, "legendonly"}:
            continue
        values = getattr(trace, axis, None)
        nums = _finite_numeric(values)
        if nums:
            found = True
            if min(nums) <= 0:
                return False
    return found


def _append_view_label(fig: Any, labels: Iterable[str]) -> None:
    clean = [str(x) for x in labels if x]
    if not clean:
        return
    title_obj = getattr(getattr(fig, "layout", None), "title", None)
    title = str(getattr(title_obj, "text", None) or "Physical Lab visualization")
    suffix = " · ".join(clean)
    if suffix.lower() in title.lower():
        return
    fig.update_layout(title=f"{title}<br><sup>View: {suffix}</sup>")


def _apply_preset(st: Any, profile: str, preset_name: str) -> None:
    for field, value in VIEW_PRESETS[preset_name].items():
        st.session_state[f"pl_viz_{field}_{profile}"] = value


def render_visualization_studio(st: Any, profile: str) -> dict[str, Any]:
    """Render a grouped visualization workspace and return its current settings."""
    label = PROFILE_LABELS.get(profile, profile)
    with st.expander(f"Visualization workspace · {label}", expanded=False):
        st.caption(
            "Display-only controls: solver inputs, measurements, fitted values and Run Vault scientific results remain unchanged. "
            + PROFILE_HINTS.get(profile, "")
        )
        p1, p2 = st.columns([3, 1])
        preset_name = p1.selectbox("View preset", list(VIEW_PRESETS), key=f"pl_viz_preset_{profile}")
        if p2.button("Apply", key=f"pl_viz_apply_preset_{profile}", width="stretch"):
            _apply_preset(st, profile, preset_name)
            st.rerun()

        tab_view, tab_axes, tab_render = st.tabs(["View", "Axes & scale", "Rendering"])

        with tab_view:
            c1, c2 = st.columns(2)
            line_transform = c1.selectbox(
                "1D trace view",
                ["As authored", "Normalize max |y|", "Z-score", "Percent change from first"],
                key=f"pl_viz_line_transform_{profile}",
            )
            heatmap_transform = c2.selectbox(
                "Heatmap view",
                ["As authored", "log10 |z|", "Normalize 0–1", "Z-score"],
                key=f"pl_viz_heatmap_transform_{profile}",
            )
            c3, c4 = st.columns(2)
            template = c3.selectbox("Plot theme", ["Physical Lab", "Light", "Dark"], key=f"pl_viz_template_{profile}")
            hover = c4.selectbox("Hover behavior", ["closest", "x unified", "x", "y"], key=f"pl_viz_hover_{profile}")
            c5, c6, c7 = st.columns(3)
            show_legend = c5.toggle("Legend", value=True, key=f"pl_viz_show_legend_{profile}")
            show_reference = c6.toggle("Theory / reference", value=True, key=f"pl_viz_show_reference_{profile}")
            show_grid = c7.toggle("Grid", value=True, key=f"pl_viz_show_grid_{profile}")

        with tab_axes:
            c8, c9 = st.columns(2)
            x_scale = c8.selectbox("X axis", ["Respect model", "Linear", "Log"], key=f"pl_viz_x_scale_{profile}")
            y_scale = c9.selectbox("Y axis", ["Respect model", "Linear", "Log"], key=f"pl_viz_y_scale_{profile}")
            phase_equal = st.toggle(
                "Equal scale on phase portraits",
                value=(profile == "nonlinear-chaos"),
                key=f"pl_viz_phase_equal_{profile}",
                disabled=(profile != "nonlinear-chaos"),
            )
            st.caption("Log scale is applied only when visible authored values are positive; otherwise it is safely skipped and labeled on the figure.")

        with tab_render:
            c10, c11 = st.columns(2)
            height = c10.select_slider(
                "Chart height", options=[420, 500, 580, 660, 760], value=500,
                key=f"pl_viz_height_{profile}",
            )
            max_points = c11.select_slider(
                "Max rendered points / simple trace", options=[1000, 2500, 5000, 10000, 20000], value=5000,
                key=f"pl_viz_max_points_{profile}",
            )
            c12, c13, c14 = st.columns(3)
            line_width = c12.slider("Line width", 1.0, 6.0, 2.0, 0.5, key=f"pl_viz_line_width_{profile}")
            marker_size = c13.slider("Marker size", 2, 14, 6, 1, key=f"pl_viz_marker_size_{profile}")
            font_size = c14.slider("Figure font", 10, 20, 13, 1, key=f"pl_viz_font_size_{profile}")
            c15, c16 = st.columns(2)
            modebar = c15.toggle("Plotly tool bar", value=True, key=f"pl_viz_modebar_{profile}")
            scroll_zoom = c16.toggle("Scroll to zoom", value=False, key=f"pl_viz_scroll_zoom_{profile}")

        active = []
        if line_transform != "As authored": active.append(f"1D: {line_transform}")
        if heatmap_transform != "As authored": active.append(f"heatmap: {heatmap_transform}")
        if x_scale != "Respect model" or y_scale != "Respect model": active.append(f"axes: {x_scale} / {y_scale}")
        if not show_reference: active.append("reference hidden")
        if active:
            st.warning("Display override active · " + " · ".join(active))
        else:
            st.caption("View status: authored model scales and traces are preserved.")
        st.caption("Visualization settings use `pl_viz_*` keys so Run Vault can preserve the view configuration with the experiment state.")

    return {
        "line_transform": line_transform, "heatmap_transform": heatmap_transform, "template": template,
        "x_scale": x_scale, "y_scale": y_scale, "height": int(height), "max_points": int(max_points),
        "line_width": float(line_width), "marker_size": int(marker_size), "font_size": int(font_size),
        "hover": hover, "show_legend": bool(show_legend), "show_grid": bool(show_grid),
        "show_reference": bool(show_reference), "modebar": bool(modebar), "scroll_zoom": bool(scroll_zoom),
        "phase_equal": bool(phase_equal),
    }


def apply_visualization_settings(fig: Any, settings: dict[str, Any], profile: str) -> tuple[Any, list[str]]:
    """Return a copied Plotly figure with display-only transformations applied."""
    try:
        import plotly.graph_objects as go
        out = go.Figure(fig)
    except Exception:
        return fig, []

    labels: list[str] = []
    requested_line_transform = str(settings.get("line_transform", "As authored"))
    heatmap_transform = str(settings.get("heatmap_transform", "As authored"))
    line_transform = requested_line_transform
    if requested_line_transform != "As authored":
        if _has_engineering_overlay(out):
            line_transform = "As authored"
            labels.append("1D transform skipped: engineering overlay")
        elif _has_authored_uncertainty(out):
            line_transform = "As authored"
            labels.append("1D transform skipped: authored uncertainty")
    decimated = False

    for trace in out.data:
        name = str(getattr(trace, "name", "") or "").lower()
        role = _trace_role(trace)
        if not settings.get("show_reference", True) and any(token in name for token in REFERENCE_TOKENS):
            trace.visible = False
        ttype = getattr(trace, "type", "")
        if ttype in {"scatter", "scattergl"}:
            if line_transform != "As authored" and getattr(trace, "y", None) is not None:
                trace.y = _array_transform(trace.y, line_transform)
            if role not in {"baseline", "uncertainty_band"}:
                try:
                    if getattr(trace, "line", None) is not None:
                        trace.line.width = float(settings.get("line_width", 2.0))
                    if getattr(trace, "marker", None) is not None:
                        trace.marker.size = int(settings.get("marker_size", 6))
                except Exception:
                    pass
                decimated = _safe_decimate(trace, int(settings.get("max_points", 5000))) or decimated
        elif ttype in {"heatmap", "contour", "surface"} and heatmap_transform != "As authored":
            z = getattr(trace, "z", None)
            if z is not None:
                trace.z = _heatmap_transform(z, heatmap_transform)

    if line_transform != "As authored": labels.append(line_transform)
    if heatmap_transform != "As authored": labels.append(heatmap_transform)
    if decimated: labels.append(f"display decimated ≤{settings.get('max_points', 5000)} pts")

    template = settings.get("template", "Physical Lab")
    template_name = "plotly_white" if template == "Light" else ("plotly_dark" if template == "Dark" else "plotly")
    out.update_layout(
        template=template_name,
        autosize=True,
        height=int(settings.get("height", 500)),
        showlegend=bool(settings.get("show_legend", True)),
        hovermode=str(settings.get("hover", "closest")),
        hoverlabel={"namelength": -1},
        font={"size": int(settings.get("font_size", 13))},
        margin={"l": 56, "r": 28, "t": 82, "b": 54},
    )
    out.update_xaxes(showgrid=bool(settings.get("show_grid", True)), automargin=True)
    out.update_yaxes(showgrid=bool(settings.get("show_grid", True)), automargin=True)

    x_scale = settings.get("x_scale", "Respect model")
    y_scale = settings.get("y_scale", "Respect model")
    if x_scale == "Linear":
        out.update_xaxes(type="linear")
    elif x_scale == "Log":
        if _axis_is_positive(out, "x"):
            out.update_xaxes(type="log")
        else:
            labels.append("X log skipped: nonpositive data")
    if y_scale == "Linear":
        out.update_yaxes(type="linear")
    elif y_scale == "Log":
        if _axis_is_positive(out, "y"):
            out.update_yaxes(type="log")
        else:
            labels.append("Y log skipped: nonpositive data")

    title = str(getattr(getattr(out.layout, "title", None), "text", "") or "").lower()
    if profile == "nonlinear-chaos" and settings.get("phase_equal") and ("phase portrait" in title or "phase space" in title):
        out.update_yaxes(scaleanchor="x", scaleratio=1)
        labels.append("equal phase scale")

    _append_view_label(out, labels)
    return out, labels


@contextmanager
def visualization_context(st: Any, profile: str):
    """Temporarily wrap st.plotly_chart for the current advanced suite only."""
    settings = render_visualization_studio(st, profile)
    original = st.plotly_chart

    def wrapped(fig: Any, *args: Any, **kwargs: Any):
        rendered, _ = apply_visualization_settings(fig, settings, profile)
        config = dict(kwargs.pop("config", {}) or {})
        config.update({
            "displaylogo": False,
            "displayModeBar": bool(settings.get("modebar", True)),
            "scrollZoom": bool(settings.get("scroll_zoom", False)),
            "responsive": True,
            "toImageButtonOptions": {"format": "png", "scale": 2},
        })
        return original(rendered, *args, config=config, **kwargs)

    st.plotly_chart = wrapped
    try:
        yield settings
    finally:
        st.plotly_chart = original
