"""Compatibility facade for Physical Lab engineering tools.

The original Engineering V&V/UQ implementation is retained verbatim in
``physical_lab_engineering_legacy``. This facade inserts the dual-mode physics
application layer before delegating to the established engineering workflow, so
existing public helpers and scientific behavior remain backward compatible.

The legacy module is loadable both through the normal packaged UI import path and
through path-based deterministic validation, which imports this file directly.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

try:
    import physical_lab_engineering_legacy as _legacy
except ModuleNotFoundError:
    _legacy_path = Path(__file__).with_name("physical_lab_engineering_legacy.py")
    _spec = importlib.util.spec_from_file_location("physical_lab_engineering_legacy", _legacy_path)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Unable to load Physical Lab engineering implementation: {_legacy_path}")
    _legacy = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_legacy)

for _name, _value in vars(_legacy).items():
    if not _name.startswith("_") and _name != "render_engineering_vvuq":
        globals()[_name] = _value

_render_engineering_vvuq_legacy = _legacy.render_engineering_vvuq


def _load_application_modules():
    try:
        import physical_lab_application_modes as application_modes
        from physical_lab_display_ranges import padded_range
        return application_modes, padded_range
    except ModuleNotFoundError:
        ui_dir = Path(__file__).resolve().parent

        app_spec = importlib.util.spec_from_file_location(
            "physical_lab_application_modes", ui_dir / "physical_lab_application_modes.py"
        )
        range_spec = importlib.util.spec_from_file_location(
            "physical_lab_display_ranges", ui_dir / "physical_lab_display_ranges.py"
        )
        if app_spec is None or app_spec.loader is None or range_spec is None or range_spec.loader is None:
            raise ImportError("Unable to load Physical Lab application-mode modules")
        application_modes = importlib.util.module_from_spec(app_spec)
        app_spec.loader.exec_module(application_modes)
        range_module = importlib.util.module_from_spec(range_spec)
        range_spec.loader.exec_module(range_module)
        return application_modes, range_module.padded_range


def render_engineering_vvuq(st, profile: str, namespace: dict | None = None) -> None:
    try:
        application_modes, padded_range = _load_application_modules()
        application_modes.padded_range = padded_range
        application_modes.render_application_mode(st, profile, namespace)
    except Exception as exc:
        st.warning(f"Physical Lab Application Mode could not load: {exc}")
    _render_engineering_vvuq_legacy(st, profile, namespace)
