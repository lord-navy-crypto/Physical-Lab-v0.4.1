"""Compatibility facade for Physical Lab engineering tools.

The original Engineering V&V/UQ implementation is retained verbatim in
``physical_lab_engineering_legacy``.  This facade inserts the dual-mode physics
application layer before delegating to the established engineering workflow, so
existing public helpers and scientific behavior remain backward compatible.
"""
from __future__ import annotations

from physical_lab_engineering_legacy import *  # noqa: F401,F403
from physical_lab_engineering_legacy import render_engineering_vvuq as _render_engineering_vvuq_legacy


def render_engineering_vvuq(st, profile: str, namespace: dict | None = None) -> None:
    try:
        import physical_lab_application_modes as application_modes
        from physical_lab_display_ranges import padded_range
        application_modes.padded_range = padded_range
        application_modes.render_application_mode(st, profile, namespace)
    except Exception as exc:
        st.warning(f"Physical Lab Application Mode could not load: {exc}")
    _render_engineering_vvuq_legacy(st, profile, namespace)
