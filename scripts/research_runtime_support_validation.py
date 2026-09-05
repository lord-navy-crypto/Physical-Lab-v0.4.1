#!/usr/bin/env python3
"""Acceptance checks for runtime/support separation from frozen legacy research code."""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FACADE = ROOT / "src-tauri/src/research.rs"
SUPPORT = ROOT / "src-tauri/src/research_runtime_support.rs"
LEGACY = ROOT / "src-tauri/src/research_legacy_impl.rs"


def compact(value: str) -> str:
    return "".join(value.split())


def function_block(text: str, name: str) -> str:
    starts = []
    for marker in (f"pub fn {name}(", f"fn {name}("):
        found = text.find(marker)
        if found >= 0:
            starts.append(found)
    if not starts:
        raise AssertionError(name)
    start = min(starts)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError(name)


def main() -> int:
    facade = FACADE.read_text(encoding="utf-8")
    support = SUPPORT.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")

    assert '#[path = "research_runtime_support.rs"]' in facade
    assert "mod runtime_support;" in facade
    assert '#[path = "research_legacy_impl.rs"]' not in facade
    assert "mod legacy;" not in facade
    assert "legacy::" not in facade
    assert "pubuseruntime_support::{" in compact(facade)

    for name in (
        "lab_compatibility_matrix",
        "repair_lab_environment",
        "scientific_smoke_tests",
        "adapter_statuses",
    ):
        wrapper = compact(function_block(facade, name))
        assert f"runtime_support::{name}" in wrapper, name
        assert f"legacy::{name}" not in wrapper, name

    for struct_name in (
        "WorkspaceSummary",
        "CompatibilityRow",
        "SmokeResult",
        "DatasetSummary",
        "ColumnStats",
        "ValidationResult",
        "AdapterStatus",
    ):
        assert f"pub struct {struct_name}" in support, struct_name
        assert f"pub struct {struct_name}" in legacy, struct_name

    for forbidden in (
        'join("workspaces")',
        "fn workspace_dir(",
        "pub fn create_workspace(",
        "pub fn import_measurement_dataset(",
        "pub fn record_run_snapshot(",
        "pub fn create_campaign(",
        "pub fn export_reproducibility_package(",
    ):
        assert forbidden not in support, forbidden

    semantic_tokens = {
        "lab_compatibility_matrix": (
            '"installedLabvenv"',
            "pep440_probe",
            "requirements",
            "verify_imports",
        ),
        "repair_lab_environment": (
            '"ManagedLabvenvnotfound.InstalltheLabfirst."',
            '"-m","pip","install","-r"',
            '"Managedvenvrepairfailed;systemPythonandCondaenvironmentswerenotmodified."',
        ),
        "scientific_smoke_tests": (
            "smoke_script",
            "scientific_ready:passed",
            "duration_ms:start.elapsed().as_millis()",
        ),
        "adapter_statuses": (
            "Chrono::Modal",
            "VAMPIRE",
            "consumed_by_current_lab:false",
        ),
    }
    for name, tokens in semantic_tokens.items():
        current = compact(function_block(support, name))
        frozen = compact(function_block(legacy, name))
        for token in tokens:
            assert token in current, (name, token)
            assert token in frozen, (name, token)

    support_probe = compact(function_block(support, "pep440_probe"))
    legacy_probe = compact(function_block(legacy, "pep440_probe"))
    for token in ("SpecifierSet", "Version(v)inSpecifierSet(spec)", "pip._vendor.packaging"):
        assert token in support_probe, token
        assert token in legacy_probe, token

    assert "research_legacy_impl.rs" in facade
    assert "not compiled into the desktop runtime" in facade

    print("Physical Lab research runtime support separation: PASS")
    print("- frozen legacy workspace implementation is not a Rust runtime module")
    print("- shared desktop DTOs owned by runtime support")
    print("- compatibility matrix + managed-venv repair preserved")
    print("- scientific smoke checks preserved")
    print("- optional adapter presence reporting preserved")
    print("- Project/workspace storage code excluded from runtime support")
    print("Boundary: runtime separation changes code ownership only; it does not upgrade smoke checks or compatibility probes into scientific verification/validation evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
