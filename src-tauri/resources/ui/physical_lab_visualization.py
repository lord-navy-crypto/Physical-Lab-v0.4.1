"""Model-aware, display-only visualization controls for Physical Lab advanced suites.

This module never mutates solver inputs or stored scientific results. It wraps
Streamlit Plotly rendering only while Physical Lab advanced experiments render.
Any normalization, log-magnitude or z-score operation is therefore a view
transform and is labeled as such on the chart.
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
    "random-walk-monte-carlo": "Keep theory/reference overlays optional and preserve log-scaling when authored.",
    "nonlinear-chaos": "Keep phase portraits dense enough to show structure while bounding rendering cost.",
    "oscillation-integration": "Preserve resonance, phase and energy-balance structure; heatmap transforms are display-only.",
    "radia-magnet-studio": "Compare solved/tolerance metrics without converting normalized views into physical units.",
    "radiation-platform": "Separate ideal/reference overlays from upstream/full-model traces and keep units explicit.",
}

REFERENCE_TOKENS = ("reference", "theory", "ideal", "exact", "asymptotic", "onsager")


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


def _safe_decimate(trace: Any, max_points: int) -> bool:
    """Decimate simple scatter traces only when aligned auxiliary arrays are absent."""
    if getattr(trace, "type", "") not in {"scatter", "scattergl"}:
        return False
    x = getattr(trace, "x", None); y = getattr(trace, "y", None)
    try:
        n = min(len(x), len(y))
    except Exception:
        return False
    if n <= max_points or max_points < 100:
        return False
    if getattr(trace, "customdata", None) is not None or getattr(trace, "text", None) is not None:
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


def _axis_is_positive(fig: Any, axis: str) -> bool:
    found = False
    for trace in getattr(fig, "data", ()):
        values = getattr(trace, axis, None)
        nums = _finite_numeric(values)
        if nums:
            found = True
            if min(nums) <= 0:
                return False
    return found


def _append_view_label(fig: Any, labels: Iterable[str]) -> None:
    clean = [x for x in labels if x]
    if not clean:
        return
    title_obj = getattr(getattr(fig, "layout", None), "title", None)
    title = getattr(title_obj, "text", None) or "Physical Lab visualization"
    suffix = " · ".join(clean)
    if suffix.lower() not in str(title).lower():
        fig.update_layout(title=f"{title} · VIEW: {suffix}")


def render_visualization_studio(st: Any, profile: str) -> dict[str, Any]:
    """Render one persistent display-control panel and return its current settings."""
    label = PROFILE_LABELS.get(profile, profile)
    with st.expander(f"Visualization Studio · {label}", expanded=False):
        st.caption(
            "Display controls affect Plotly figures only. Solver inputs, stored arrays, measurements, fitted values and Run Vault scientific results are not rewritten. "
            + PROFILE_HINTS.get(profile, "")
        )
        c1, c2, c3 = st.columns(3)
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
        template = c3.selectbox(
            "Plot theme",
            ["Physical Lab", "Light", "Dark"],
            key=f"pl_viz_template_{profile}",
        )

        c4, c5, c6, c7 = st.columns(4)
        x_scale = c4.selectbox("X axis", ["Respect model", "Linear", "Log"], key=f"pl_viz_xscale_{profile}")
        y_scale = c5.selectbox("Y axis", ["Respect model", "Linear", "Log"], key=f"pl_viz_yscale_{profile}")
        height = c6.select_slider("Chart height", options=[420, 500, 580, 660, 760], value=580, key=f"pl_viz_height_{profile}")
        max_points = c7.select_slider("Max rendered points / simple trace", options=[1000, 2500, 5000, 10000, 20000], value=5000, key=f"pl_viz_points_{profile}")

        c8, c9, c10, c11 = st.columns(4)
        line_width = c8.slider("Line width", 1.0, 6.0, 2.0, 0.5, key=f"pl_viz_linewidth_{profile}")
        marker_size = c9.slider("Marker size", 2, 14, 6, 1, key=f"pl_viz_markersize_{profile}")
        font_size = c10.slider("Figure font", 10, 20, 13, 1, key=f"pl_viz_font_{profile}")
        hover = c11.selectbox("Hover", ["closest", "x unified", "x", "y"], key=f"pl_viz_hover_{profile}")

        c12, c13, c14, c15 = st.columns(4)
        show_legend = c12.toggle("Legend", value=True, key=f"pl_viz_legend_{profile}")
        show_grid = c13.toggle("Grid", value=True, key=f"pl_viz_grid_{profile}")
        show_reference = c14.toggle("Theory / reference traces", value=True, key=f"pl_viz_reference_{profile}")
        modebar = c15.toggle("Plotly tool bar", value=True, key=f"pl_viz_modebar_{profile}")

        c16, c17 = st.columns(2)
        scroll_zoom = c16.toggle("Scroll to zoom", value=False, key=f"pl_viz_scrollzoom_{profile}")
        phase_equal = c17.toggle(
            "Equal scale on phase portraits",
            value=(profile == "nonlinear-chaos"),
            key=f"pl_viz_phase_equal_{profile}",
            disabled=(profile != "nonlinear-chaos"),
        )
        if line_transform != "As authored" or heatmap_transform != "As authored":
            st.warning("A visualization transform is active. Read axis labels and the VIEW tag before interpreting magnitudes; raw solver results remain unchanged.")
        st.caption("These visualization settings use `pl_viz_*` keys, so Run Vault captures them alongside the advanced experiment state for reproducibility.")

    return {
        "line_transform": line_transform,
        "heatmap_transform": heatmap_transform,
        "template": template,
        "x_scale": x_scale,
        "y_scale": y_scale,
        "height": int(height),
        "max_points": int(max_points),
        "line_width": float(line_width),
        "marker_size": int(marker_size),
        "font_size": int(font_size),
        "hover": hover,
        "show_legend": bool(show_legend),
        "show_grid": bool(show_grid),
        "show_reference": bool(show_reference),
        "modebar": bool(modebar),
        "scroll_zoom": bool(scroll_zoom),
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
    line_transform = str(settings.get("line_transform", "As authored"))
    heatmap_transform = str(settings.get("heatmap_transform", "As authored"))
    decimated = False

    for trace in out.data:
        name = str(getattr(trace, "name", "") or "").lower()
        if not settings.get("show_reference", True) and any(token in name for token in REFERENCE_TOKENS):
            trace.visible = "legendonly"
        ttype = getattr(trace, "type", "")
        if ttype in {"scatter", "scattergl"}:
            if line_transform != "As authored" and getattr(trace, "y", None) is not None:
                trace.y = _array_transform(trace.y, line_transform)
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

    if line_transform != "As authored":
        labels.append(line_transform)
    if heatmap_transform != "As authored":
        labels.append(heatmap_transform)
    if decimated:
        labels.append(f"display decimated ≤{settings.get('max_points', 5000)} pts")

    template = settings.get("template", "Physical Lab")
    if template == "Light":
        template_name = "plotly_white"
    elif template == "Dark":
        template_name = "plotly_dark"
    else:
        template_name = "plotly"

    out.update_layout(
        template=template_name,
        height=int(settings.get("height", 580)),
        showlegend=bool(settings.get("show_legend", True)),
        hovermode=str(settings.get("hover", "closest")),
        font={"size": int(settings.get("font_size", 13))},
    )
    out.update_xaxes(showgrid=bool(settings.get("show_grid", True)))
    out.update_yaxes(showgrid=bool(settings.get("show_grid", True)))

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
