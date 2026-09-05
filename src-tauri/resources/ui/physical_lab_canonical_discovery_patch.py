"""Route legacy Python project browsers to canonical-first discovery.

This removes the Measurement Digital Twin's dependency on ``workspaces/``
compatibility symlinks without modifying its scientific calculation code.
"""
from __future__ import annotations


def install() -> None:
    try:
        import physical_lab_digital_twin_ui as digital_twin_ui
        from physical_lab_project_discovery import discover_projects
    except Exception:
        return
    if getattr(digital_twin_ui, "_physical_lab_canonical_discovery_patched", False):
        return

    def canonical_workspaces():
        return discover_projects(include_legacy=True)

    digital_twin_ui._workspaces = canonical_workspaces
    digital_twin_ui._physical_lab_canonical_discovery_patched = True
