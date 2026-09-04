#!/usr/bin/env python3
"""Deterministic checks for engineering visualization behavior."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "src-tauri" / "resources" / "ui" / "physical_lab_visualization_engineering.py"
spec = importlib.util.spec_from_file_location("physical_lab_visualization_engineering", MOD)
viz = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(viz)

# Authored error bars may become a band, but source data must not be mutated.
source = go.Figure()
source.add_scatter(
    x=[0, 1, 2], y=[10.0, 11.0, 12.0], mode="lines+markers", name="measured",
    error_y={"type": "data", "array": [0.5, 0.6, 0.7], "visible": True},
)
copy_fig = go.Figure(source)
count = viz._add_uncertainty_bands(copy_fig)
assert count == 1
assert len(copy_fig.data) == 3
assert list(source.data[0].y) == [10.0, 12.0 - 1.0, 12.0]
assert len(source.data) == 1
assert bool(source.data[0].error_y.visible) is True
assert bool(copy_fig.data[0].error_y.visible) is False
assert copy_fig.data[1].meta["physical_lab_role"] == "uncertainty_band"
assert copy_fig.data[2].meta["physical_lab_role"] == "uncertainty_band"
assert str(copy_fig.data[2].legendgroup).startswith("uq-")

# No error_y -> no invented uncertainty band.
plain = go.Failsafe if False else go.Figure(go.Scatter(x=[0, 1], y=[1, 2], name="plain"))
assert viz._add_uncertainty_bands(plain) == 0
assert len(plain.data) == 1

# Cross-run baseline must match by authored chart title and only add display traces.
cur = go.Figure(go.Scatter(x=[0, 1], y=[2, 3], name="current"))
cur.update_layout(title="Response")
baseline = [{"title": "Response", "traces": [{"type": "scatter", "name": "old", "x": [0, 1], "y": [1, 2]}]}]
assert viz._apply_baseline(cur, baseline) == 1
assert len(cur.data) == 2
assert str(cur.data[1].name).startswith("Baseline")
assert cur.data[1].meta["physical_lab_role"] == "baseline"

# Mismatched titles must not silently overlay unrelated runs.
other = go.Figure(go.Scatter(x=[0, 1], y=[2, 3]))
other.update_layout(title="Different chart")
assert viz._apply_baseline(other, baseline) == 0
assert len(other.data) == 1

# 3D controls only change figure presentation.
traj = go.Figure(go.Scatter3d(x=[0, 1], y=[0, 1], z=[0, 1], mode="lines+markers", name="trajectory"))
settings = {
    "trajectory_line_width": 6, "trajectory_marker_size": 7,
    "camera": "Isometric", "aspect": "Data",
    "surface_opacity": 0.7, "show_colorbar": True,
}
assert viz._apply_3d(traj, settings) is True
assert traj.data[0].line.width == 6
assert traj.data[0].marker.size == 7
assert traj.layout.scene.aspectmode == "data"
assert traj.layout.scene.camera.eye.x == viz.CAMERAS["Isometric"]["eye"]["x"]

# Capture is bounded, materializes an iterator once, and retains the final point.
large = go.Figure(go.Scatter(x=list(range(10000)), y=list(range(10000)), name="large"))
large.update_layout(title="Large trace")
cap = viz._capture_figure(large)
assert cap["title"] == "Large trace"
assert len(cap["traces"]) == 1
assert len(cap["traces"][0]["x"]) <= 4001
assert cap["traces"][0]["x"][-1] == 9999
seq = viz._bounded_seq(iter(range(10000)), limit=4000)
assert seq is not None and len(seq) <= 4001 and seq[-1] == 9999

# The UI must expose grouped review / 3D / baseline sections rather than a second control wall.
text = MOD.read_text(encoding="utf-8")
assert "Engineering overlays & comparison" in text
assert 'st.tabs(["Review", "3D", "Baseline"])' in text
assert "comparison-compatible" in text

print("PASS engineering visualization overlays, role metadata, bounded capture, authored uncertainty, baseline matching, grouped UI, and 3D controls")
