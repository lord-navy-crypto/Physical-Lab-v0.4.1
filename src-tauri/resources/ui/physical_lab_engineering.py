"""Compatibility facade for Physical Lab engineering tools.

The original Engineering V&V/UQ implementation is retained verbatim in
``physical_lab_engineering_legacy``. This facade inserts the project-level
``.physlab`` workspace, project-bound measurement/calibration evidence, the
dual-mode physics application layer, engineering decision lens, model-specific
workspaces and unified Run & Diagnostics Log before delegating to the established
engineering workflow. Existing public helpers and scientific behavior remain
backward compatible.

Sibling modules are loadable both through the normal packaged UI import path and
through path-based deterministic validation, which imports this file directly.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

try:
    import physical_lab_engineering_legacy as _legacy
except ModuleNotFoundError:
    _legacy_path = Path(__file__).with_name("physical_lab_engineering_legacy.py")
    _spec = importlib.util.spec_from_file_location("physical_lab_engineering_legacy", _legacy_path)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Unable to load Physical Lab engineering implementation: {_legacy_path}")
    _legacy = importlib.util.module_from_spec(_spec)
    sys.modules.setdefault("physical_lab_engineering_legacy", _legacy)
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
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        if sys.modules.get(module_name) is module:
            sys.modules.pop(module_name, None)
        raise
    return module


def _load_project_kernel_module():
    try:
        import physical_lab_project_kernel as project_kernel
        return project_kernel
    except ModuleNotFoundError:
        return _load_module_by_path(
            "physical_lab_project_kernel", "physical_lab_project_kernel.py"
        )


def _load_measurement_registry_module():
    try:
        import physical_lab_measurement_registry as measurement_registry
        return measurement_registry
    except ModuleNotFoundError:
        return _load_module_by_path(
            "physical_lab_measurement_registry", "physical_lab_measurement_registry.py"
        )


def _load_diagnostics_module():
    try:
        import physical_lab_diagnostics as diagnostics
        return diagnostics
    except ModuleNotFoundError:
        return _load_module_by_path(
            "physical_lab_diagnostics", "physical_lab_diagnostics.py"
        )


def _load_compute_engine_module():
    try:
        import physical_lab_compute_engine as compute_engine
        return compute_engine
    except ModuleNotFoundError:
        return _load_module_by_path(
            "physical_lab_compute_engine", "physical_lab_compute_engine.py"
        )


def _load_kerr_ui_module():
    try:
        import physical_lab_kerr_ui as kerr_ui
        return kerr_ui
    except ModuleNotFoundError:
        try:
            import physical_lab_kerr_geodesics  # noqa: F401
        except ModuleNotFoundError:
            _load_module_by_path(
                "physical_lab_kerr_geodesics", "physical_lab_kerr_geodesics.py"
            )
        return _load_module_by_path(
            "physical_lab_kerr_ui", "physical_lab_kerr_ui.py"
        )


def _load_kerr_platform_ui_module():
    try:
        import physical_lab_kerr_platform_ui as kerr_platform_ui
        return kerr_platform_ui
    except ModuleNotFoundError:
        try:
            import physical_lab_kerr_geodesics  # noqa: F401
        except ModuleNotFoundError:
            _load_module_by_path(
                "physical_lab_kerr_geodesics", "physical_lab_kerr_geodesics.py"
            )
        try:
            import physical_lab_experiment_kernel  # noqa: F401
        except ModuleNotFoundError:
            _load_module_by_path(
                "physical_lab_experiment_kernel", "physical_lab_experiment_kernel.py"
            )
        try:
            import physical_lab_kerr_workflow  # noqa: F401
        except ModuleNotFoundError:
            _load_module_by_path(
                "physical_lab_kerr_workflow", "physical_lab_kerr_workflow.py"
            )
        return _load_module_by_path(
            "physical_lab_kerr_platform_ui", "physical_lab_kerr_platform_ui.py"
        )


def _record_module_exception(source: str, exc: Exception, profile: str) -> None:
    try:
        diagnostics = _load_diagnostics_module()
        diagnostics.record_exception(
            source,
            exc,
            profile=profile,
            code="PLATFORM_MODULE_ERROR",
        )
    except Exception:
        # Logging must never create a second failure path.
        pass


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
    if profile == "nonlinear-chaos":
        try:
            kerr_ui = _load_kerr_ui_module()
            kerr_ui.render_kerr_geodesic_workspace(st, profile)
        except Exception as exc:
            _record_module_exception("kerr-geodesic-model", exc, profile)
            st.warning(f"Physical Lab Kerr Geodesic Dynamics could not load: {exc}")

        try:
            kerr_platform_ui = _load_kerr_platform_ui_module()
            kerr_platform_ui.render_kerr_platform_workspace(st, profile)
        except Exception as exc:
            _record_module_exception("kerr-platform-workflow", exc, profile)
            st.warning(f"Physical Lab Kerr Experiment/Compute workflow could not load: {exc}")

    try:
        project_kernel = _load_project_kernel_module()
        project_kernel.render_project_workspace(st, profile, namespace)
    except Exception as exc:
        _record_module_exception("project-kernel", exc, profile)
        st.warning(f"Physical Lab Project Kernel could not load: {exc}")

    try:
        measurement_registry = _load_measurement_registry_module()
        measurement_registry.render_measurement_workspace(st, profile)
    except Exception as exc:
        _record_module_exception("measurement-calibration", exc, profile)
        st.warning(f"Physical Lab Measurement/Calibration Evidence could not load: {exc}")

    try:
        application_modes, padded_range = _load_application_modules()
        application_modes.padded_range = padded_range
        application_modes.render_application_mode(st, profile, namespace)
    except Exception as exc:
        _record_module_exception("application-mode", exc, profile)
        st.warning(f"Physical Lab Application Mode could not load: {exc}")

    try:
        engineering_scenarios = _load_engineering_scenario_module()
        engineering_scenarios.render_engineering_scenario_review(st, profile)
    except Exception as exc:
        _record_module_exception("engineering-scenario", exc, profile)
        st.warning(f"Physical Lab Engineering Scenario Review could not load: {exc}")

    try:
        diagnostics = _load_diagnostics_module()
        compute_engine = _load_compute_engine_module()
        diagnostics.render_diagnostics_workspace(st, profile, compute_engine)
    except Exception as exc:
        _record_module_exception("diagnostics-workspace", exc, profile)
        st.warning(f"Physical Lab Run & Diagnostics Log could not load: {exc}")

    _render_engineering_vvuq_legacy(st, profile, namespace)
