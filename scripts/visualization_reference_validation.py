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
    apply_visualization_settings,
)


def close(a: float, b: float, tol: float = 1e-10) -> bool:
    return abs(float(a) - float(b)) <= tol


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
    settings = {
        "line_transform": "Normalize max |y|",
        "heatmap_transform": "As authored",
        "template": "Physical Lab",
        "x_scale": "Respect model",
        "y_scale": "Respect model",
        "height": 580,
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
    rendered, labels = apply_visualization_settings(original, settings, "random-walk-monte-carlo")
    assert list(original.data[0].y) == [2, 4, 8], "view transform mutated the original figure"
    assert np.allclose(np.asarray(rendered.data[0].y, dtype=float), [0.25, 0.5, 1.0])
    assert rendered.data[1].visible == "legendonly"
    assert close(float(rendered.data[0].line.width), 3.0)
    assert "Normalize max |y|" in labels

    negative = go.Figure(go.Scatter(x=[-1.0, 1.0], y=[1.0, 2.0], mode="lines"))
    bad_settings = dict(settings); bad_settings.update({"line_transform": "As authored", "show_reference": True, "x_scale": "Log"})
    safe, safe_labels = apply_visualization_settings(negative, bad_settings, "numerical-methods")
    assert safe.layout.xaxis.type != "log"
    assert any("X log skipped" in item for item in safe_labels)

    phase = go.Figure(go.Scatter(x=[0.0, 1.0], y=[0.0, 2.0], mode="lines"))
    phase.update_layout(title="theta phase portrait")
    phase_settings = dict(bad_settings); phase_settings.update({"x_scale": "Respect model", "phase_equal": True})
    equal, equal_labels = apply_visualization_settings(phase, phase_settings, "nonlinear-chaos")
    assert equal.layout.yaxis.scaleanchor == "x"
    assert any("equal phase scale" in item for item in equal_labels)

    many = go.Figure(go.Scatter(x=list(range(6000)), y=[math.sin(i / 100) for i in range(6000)], mode="lines"))
    dec_settings = dict(phase_settings); dec_settings.update({"phase_equal": False, "max_points": 1000})
    dec, dec_labels = apply_visualization_settings(many, dec_settings, "oscillation-integration")
    assert len(dec.data[0].x) <= 1001
    assert any("display decimated" in item for item in dec_labels)

    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    app = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    advanced = (UI / "physical_lab_advanced.py").read_text(encoding="utf-8")
    assert 'data-view="settings"' in index and 'id="settingsView"' in index
    assert "physicalLab.uiSettings" in app and "applyUiSettings" in app
    assert "visualization_context" in advanced

    print("PASS visualization studio: display transforms, provenance boundaries, log safety, phase scaling, decimation, shell settings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
