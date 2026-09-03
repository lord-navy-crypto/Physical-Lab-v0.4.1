#!/usr/bin/env python3
"""One-time deterministic source patch for Physical Lab v0.6 phase 1 integration.

This script is intentionally deleted by its applying workflow after the patch is
validated and committed. It avoids replacing large Rust/Python source files via a
remote editor while keeping every source transformation explicit and fail-fast.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one patch anchor in {path.relative_to(ROOT)}; found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


advanced = ROOT / "src-tauri/resources/ui/physical_lab_advanced.py"
replace_once(
    advanced,
    "    _render_content_validation(st, profile, namespace)\n    _render_run_vault(st, profile)\n",
    "    _render_content_validation(st, profile, namespace)\n"
    "    try:\n"
    "        from physical_lab_digital_twin_ui import render_digital_twin_workspace\n"
    "        render_digital_twin_workspace(st, profile)\n"
    "    except Exception as _pl_digital_twin_error:\n"
    "        st.warning(f\"Physical Lab Measurement Digital Twin could not load: {_pl_digital_twin_error}\")\n"
    "    _render_run_vault(st, profile)\n",
)

lib = ROOT / "src-tauri/src/lib.rs"
replace_once(
    lib,
    'if matches!(module_id.as_str(), "numerical-methods"|"ising-monte-carlo"|"random-walk-monte-carlo"|"nonlinear-chaos"|"oscillation-integration"|"radiation-platform") {',
    'if matches!(module_id.as_str(), "numerical-methods"|"ising-monte-carlo"|"random-walk-monte-carlo"|"nonlinear-chaos"|"oscillation-integration"|"radia-magnet-studio"|"radiation-platform") {',
)

self_check = ROOT / "scripts/self_check.py"
replace_once(
    self_check,
    "print('Deterministic reference validation: configured')\n",
    "print('Deterministic reference validation: configured')\n"
    "digital_core=(root/'src-tauri/resources/ui/physical_lab_digital_twin.py').read_text()\n"
    "digital_ui=(root/'src-tauri/resources/ui/physical_lab_digital_twin_ui.py').read_text()\n"
    "advanced_text=(root/'src-tauri/resources/ui/physical_lab_advanced.py').read_text()\n"
    "lib_text=(root/'src-tauri/src/lib.rs').read_text()\n"
    "tauri_text=(root/'src-tauri/tauri.conf.json').read_text()\n"
    "for needle in ['fit_linear_calibration','compare_field_series','fit_model_affine','analyze_beam_phase_space','suggest_residual_measurement_points']:\n"
    "    assert needle in digital_core, needle\n"
    "for needle in ['Measurement Digital Twin','linear-sensor-calibration','measured-model-field-comparison','beam-phase-space','residual-guided-remeasurement']:\n"
    "    assert needle in digital_ui, needle\n"
    "assert 'render_digital_twin_workspace(st, profile)' in advanced_text\n"
    "assert '\\"radia-magnet-studio\\"|\\"radiation-platform\\"' in lib_text\n"
    "assert 'physical_lab_digital_twin.py' in tauri_text and 'physical_lab_digital_twin_ui.py' in tauri_text\n"
    "assert (root/'scripts/digital_twin_reference_validation.py').is_file()\n"
    "assert (root/'scripts/physical_lab_digital_twin_cli.py').is_file()\n"
    "assert (root/'.github/workflows/full-mode-acceptance.yml').is_file()\n"
    "print('Measurement Digital Twin core + project UI: configured')\n"
    "print('RADIA Full-mode acceptance workflow: configured')\n",
)

readme = ROOT / "README.md"
section = """## Measurement Digital Twin\n\nPhysical Lab now has a shared **measurement → calibration → model → comparison → update** scientific core instead of treating sensor data as a generic file attachment. `physical_lab_digital_twin.py` provides deterministic definitions for linear sensor calibration, measured/model field residuals and field integrals, affine model-discrepancy fitting, transverse beam phase-space/RMS-emittance statistics, and transparent residual-guided remeasurement priorities.\n\nThe project-level **Measurement Digital Twin** view is injected into the accelerator/dynamics research layer and reads CSV/TSV datasets directly from `.physlab` workspaces. Calibration results can create lineage-tracked derived datasets; comparison, inverse-fit, phase-space and remeasurement outputs are written back to project provenance. Units and coordinate conventions are never silently inferred.\n\nThe same core is exposed through `scripts/physical_lab_digital_twin_cli.py`, so GUI and scripted workflows share the same mathematical definitions. See [`docs/DIGITAL_TWIN_CORE.md`](docs/DIGITAL_TWIN_CORE.md).\n\n### Native Full-mode acceptance\n\nSource CI still keeps RADIA outside the deterministic source-only reference snapshot. Separately, `.github/workflows/full-mode-acceptance.yml` runs on a clean macOS runner, builds a **pinned RADIA Universal2** revision, verifies `arm64 + x86_64`, evaluates a real native magnetic field with `radia.Fld`, checks symmetry/sanity conditions, reruns the digital-twin reference core, and uploads a JSON evidence artifact. This proves a small native RADIA Full-mode path works in the acceptance environment; it does **not** claim validation of a specific undulator, manufactured magnet or radiation experiment.\n\n"""
replace_once(readme, "## Reproducible reference validation\n", section + "## Reproducible reference validation\n")

print("v0.6 phase 1 integration patch: APPLIED")
