#!/usr/bin/env python3
"""Deterministic checks for Physical Lab display-only visualization controls."""
from __future__ import annotations

from pathlib import Path
import math
import sys

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

from physical_lab_visualization import (  # noqa: E402
    _array_transform,
    _heatmap_transform,
    _safe_decimate,
    _has_engineering_overlay,
    apply_visualization_settings,
)


def close(a: float, b: float, tol: float = 1e-10) -> bool:
    return abs(float(a) - float(b)) <= tol


def base_settings() -> dict:
    return {
        "line_transform": "Normalize max |y|",
        "heatmap_transform": "As authored",
        "template": "Physical Lab",
        "x_scale": "Respect model",
        "y_scale": "Respect model",
        "height": 500,
        "max_points": 5000,
        "line_width": 3.0,
        "marker_size": 7,
        "font_size": 13,
        "hover": "x unified",
        "show_legend": True,
        "show_grid": True,
        "show_reference": False,
        "phase_equal": False,
    }


def main() -> int:
    import numpy as np
    import plotly.graph_objects as go

    norm = np.asarray(_array_transform([1.0, 2.0, 3.0], "Normalize max |y|"), dtype=float)
    assert np.allclose(norm, [1 / 3, 2 / 3, 1.0])

    z = np.asarray(_array_transform([1.0, 2.0, 3.0], "Z-score"), dtype=float)
    assert close(float(np.mean(z)), 0.0)
    assert close(float(np.std(z)), 1.0)

    pct = np.asarray(_array_transform([2.0, 4.0, 1.0], "Percent change from first"), dtype=float)
    assert np.allclose(pct, [0.0, 100.0, -50.0])

    hm = np.asarray(_heatmap_transform([[1.0, 3.0], [5.0, 7.0]], "Normalize 0–1"), dtype=float)
    assert close(float(np.min(hm)), 0.0)
    assert close(float(np.max(hm)), 1.0)

    original = go.Figure()
    original.add_scatter(x=[1, 2, 3], y=[2, 4, 8], mode="lines+markers", name="Simulation")
    original.add_scatter(x=[1, 2, 3], y=[2, 3, 4], mode="lines", name="Exact theory")
    original.update_layout(title="Scaling result")
    settings = base_settings()
    rendered, labels = apply_visualization_settings(original, settings, "random-walk-monte-carlo")
    assert list(original.data[0].y) == [2, 4, 8], "view transform mutated the original figure"
    assert np.allclose(np.asarray(rendered.data[0].y, dtype=float), [0.25, 0.5, 1.0])
    assert rendered.data[1].visible is False, "reference-off must actually hide the reference trace"
    assert close(float(rendered.data[0].line.width), 3.0)
    assert "Normalize max |y|" in labels

    # Hidden reference data must not incorrectly block a requested log axis.
    log_fig = go.Figure()
    log_fig.add_scatter(x=[1.0, 2.0, 3.0], y=[1.0, 2.0, 3.0], name="Simulation")
    log_fig.add_scatter(x=[-2.0, -1.0, 0.0], y=[1.0, 1.0, 1.0], name="Exact reference")
    log_settings = dict(settings)
    log_settings.update({"line_transform": "As authored", "x_scale": "Log"})
    log_view, _ = apply_visualization_settings(log_fig, log_settings, "numerical-methods")
    assert log_view.data[1].visible is False
    assert log_view.layout.xaxis.type == "log"

    negative = go.Figure(go.Scatter(x=[-1.0, 1.0], y=[1.0, 2.0], mode="lines"))
    bad_settings = dict(settings)
    bad_settings.update({"line_transform": "As authored", "show_reference": True, "x_scale": "Log"})
    safe, safe_labels = apply_visualization_settings(negative, bad_settings, "numerical-methods")
    assert safe.layout.xaxis.type != "log"
    assert any("X log skipped" in item for item in safe_labels)

    phase = go.Figure(go.Scatter(x=[0.0, 1.0], y=[0.0, 2.0], mode="lines"))
    phase.update_layout(title="theta phase portrait")
    phase_settings = dict(bad_settings)
    phase_settings.update({"x_scale": "Respect model", "phase_equal": True})
    equal, equal_labels = apply_visualization_settings(phase, phase_settings, "nonlinear-chaos")
    assert equal.layout.yaxis.scaleanchor == "x"
    assert any("equal phase scale" in item for item in equal_labels)

    # Plain large traces may be decimated for display performance.
    many = go.Figure(go.Scatter(x=list(range(6000)), y=[math.sin(i / 100) for i in range(6000)], mode="lines"))
    dec_settings = dict(phase_settings)
    dec_settings.update({"phase_equal": False, "max_points": 1000})
    dec, dec_labels = apply_visualization_settings(many, dec_settings, "oscillation-integration")
    assert len(dec.data[0].x) <= 1001
    assert any("display decimated" in item for item in dec_labels)

    # Error arrays are aligned scientific metadata and must never be stride-decimated independently.
    with_error = go.Scatter(
        x=list(range(6000)), y=[1.0] * 6000, mode="lines",
        error_y={"type": "data", "array": [0.1] * 6000},
    )
    assert _safe_decimate(with_error, 1000) is False
    assert len(with_error.x) == 6000 and len(with_error.error_y.array) == 6000

    # A nonlinear 1D view transform must be suppressed when authored uncertainty is present.
    authored_uq = go.Figure()
    authored_uq.add_scatter(
        x=[1, 2, 3], y=[10.0, 20.0, 30.0], name="Measured",
        error_y={"type": "data", "array": [1.0, 2.0, 3.0]},
    )
    uq_view, uq_labels = apply_visualization_settings(authored_uq, settings, "oscillation-integration")
    assert list(uq_view.data[0].y) == [10.0, 20.0, 30.0]
    assert any("authored uncertainty" in item.lower() for item in uq_labels)

    # Generated engineering overlays must keep current/baseline/band traces on one authored physical scale.
    overlay = go.Figure()
    overlay.add_scatter(x=[1, 2, 3], y=[10.0, 20.0, 30.0], name="Current")
    overlay.add_scatter(
        x=[1, 2, 3], y=[9.0, 18.0, 27.0], name="Baseline · Current",
        meta={"physical_lab_role": "baseline"},
    )
    assert _has_engineering_overlay(overlay)
    overlay_view, overlay_labels = apply_visualization_settings(overlay, settings, "random-walk-monte-carlo")
    assert list(overlay_view.data[0].y) == [10.0, 20.0, 30.0]
    assert list(overlay_view.data[1].y) == [9.0, 18.0, 27.0]
    assert any("engineering overlay" in item.lower() for item in overlay_labels)

    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    advanced = (UI / "physical_lab_advanced.py").read_text(encoding="utf-8")
    viz_text = (UI / "physical_lab_visualization.py").read_text(encoding="utf-8")
    assert 'data-view="settings"' in index and 'id="settingsView"' in index
    assert "physicalLab.uiSettings" in app and "applyUiSettings" in app
    assert "visualization_context" in advanced
    assert "Visualization workspace" in viz_text and "Axes & scale" in viz_text and "Rendering" in viz_text

    print("PASS visualization workspace: transforms, overlay safety, aligned-metadata decimation, reference hiding, log safety, phase scaling, shell settings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
