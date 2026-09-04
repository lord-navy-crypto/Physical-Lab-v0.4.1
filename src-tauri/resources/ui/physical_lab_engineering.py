"""Compatibility facade for Physical Lab engineering tools.

The original Engineering V&V/UQ implementation is retained verbatim in
``physical_lab_engineering_legacy``. This facade inserts the dual-mode physics
application layer, then an engineering decision lens for Physics Scenario mode,
before delegating to the established engineering workflow. Existing public
helpers and scientific behavior remain backward compatible.

The sibling modules are loadable both through the normal packaged UI import path
and through path-based deterministic validation, which imports this file directly.
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


def _load_module_by_path(module_name: str, filename: str):
    ui_dir = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location(module_name, ui_dir / filename)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load Physical Lab module: {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_application_modules():
    try:
        import physical_lab_application_modes as application_modes
        from physical_lab_display_ranges import padded_range
        return application_modes, padded_range
    except ModuleNotFoundError:
        application_modes = _load_module_by_path(
            "physical_lab_application_modes", "physical_lab_application_modes.py"
        )
        range_module = _load_module_by_path(
            "physical_lab_display_ranges", "physical_lab_display_ranges.py"
        )
        return application_modes, range_module.padded_range


def _load_engineering_scenario_module():
    try:
        import physical_lab_engineering_scenarios as engineering_scenarios
        return engineering_scenarios
    except ModuleNotFoundError:
        return _load_module_by_path(
            "physical_lab_engineering_scenarios", "physical_lab_engineering_scenarios.py"
        )


def render_engineering_vvuq(st, profile: str, namespace: dict | None = None) -> None:
    try:
        application_modes, padded_range = _load_application_modules()
        application_modes.padded_range = padded_range
        application_modes.render_application_mode(st, profile, namespace)
    except Exception as exc:
        st.warning(f"Physical Lab Application Mode could not load: {exc}")

    try:
        engineering_scenarios = _load_engineering_scenario_module()
        engineering_scenarios.render_engineering_scenario_review(st, profile)
    except Exception as exc:
        st.warning(f"Physical Lab Engineering Scenario Review could not load: {exc}")

    _render_engineering_vvuq_legacy(st, profile, namespace)
