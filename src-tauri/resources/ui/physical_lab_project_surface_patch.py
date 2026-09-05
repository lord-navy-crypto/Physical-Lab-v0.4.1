"""Mount the shared .physlab Project surface after every managed Lab UI.

The individual upstream Labs remain unchanged. This wrapper extends Physical
Lab's shared advanced renderer so all seven managed profiles expose the same
Project Kernel; the Evidence Center patch then extends that Project Kernel.
"""
from __future__ import annotations

import os

SUPPORTED_PROFILES = {
    "numerical-methods",
    "ising-monte-carlo",
    "random-walk-monte-carlo",
    "nonlinear-chaos",
    "oscillation-integration",
    "radiation-platform",
    "radia-magnet-studio",
}


def install() -> None:
    try:
        import physical_lab_advanced as advanced
    except Exception:
        return
    if getattr(advanced, "_physical_lab_project_surface_patched", False):
        return
    original = advanced.render_advanced_experiments

    def wrapped(namespace):
        original(namespace)
        profile = os.environ.get("PHYSICAL_LAB_UI_PROFILE", "").strip()
        if profile not in SUPPORTED_PROFILES:
            return
        try:
            import streamlit as st
            from physical_lab_project_kernel import render_project_workspace
            render_project_workspace(st, profile, namespace)
        except Exception as exc:
            try:
                import streamlit as st
                st.warning(f"Physical Lab Project / Evidence surface could not load: {exc}")
            except Exception:
                pass

    advanced.render_advanced_experiments = wrapped
    advanced._physical_lab_project_surface_patched = True
