#!/usr/bin/env python3
from __future__ import annotations

import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_PATH = ROOT / "src-tauri/src/research_legacy_impl.rs"
FACADE_PATH = ROOT / "src-tauri/src/research.rs"
SUPPORT_PATH = ROOT / "src-tauri/src/research_runtime_support.rs"
VALIDATION_PATH = ROOT / "scripts/research_runtime_support_validation.py"
SELF_CHECK_PATH = ROOT / "scripts/self_check.py"
SOURCE_INTEGRITY_PATH = ROOT / ".github/workflows/source-integrity.yml"


def function_block(text: str, name: str) -> str:
    starts = []
    for marker in (f"pub fn {name}(", f"fn {name}("):
        found = text.find(marker)
        if found >= 0:
            starts.append(found)
    if not starts:
        raise RuntimeError(f"missing function: {name}")
    start = min(starts)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise RuntimeError(f"unterminated function: {name}")


def main() -> int:
    legacy = LEGACY_PATH.read_text(encoding="utf-8")

    struct_start = legacy.index("#[derive(Clone, Debug, Deserialize)]")
    struct_end = legacy.index("fn app_root(", struct_start)
    structs = legacy[struct_start:struct_end].rstrip()

    helper_names = [
        "app_root",
        "modules_root",
        "lab_specs",
        "requirement_name",
        "command_text",
        "pep440_probe",
        "lab_compatibility_matrix",
        "repair_lab_environment",
        "smoke_script",
        "scientific_smoke_tests",
        "adapter_statuses",
    ]
    blocks = [function_block(legacy, name) for name in helper_names]

    support = (
        "//! Runtime-only research support for Physical Lab desktop commands.\n"
        "//!\n"
        "//! This module intentionally contains no Project/workspace storage implementation.\n"
        "//! It owns shared DTOs plus Lab environment compatibility, managed-venv repair,\n"
        "//! scientific smoke checks, and optional adapter presence reporting.\n"
        "//!\n"
        "//! `research_legacy_impl.rs` remains frozen in the repository as a compatibility\n"
        "//! and regression fixture; it is not compiled into the desktop runtime.\n\n"
        "use serde::{Deserialize, Serialize};\n"
        "use std::{\n"
        "    fs,\n"
        "    path::{Path, PathBuf},\n"
        "    process::Command,\n"
        "    time::Instant,\n"
        "};\n"
        "use tauri::{AppHandle, Manager};\n\n"
        + structs
        + "\n\n"
        + "\n\n".join(blocks)
        + "\n"
    )
    SUPPORT_PATH.write_text(support, encoding="utf-8")

    facade = FACADE_PATH.read_text(encoding="utf-8")
    old_doc = "\n".join(
        [
            "//! aliases. The pre-cutover research implementation is frozen in",
            "//! `research_legacy_impl.rs` for non-project helper behavior and contract comparison.",
            "//! Project reads/writes resolve canonical projects directly; no compatibility",
            "//! symlink is created or required.",
            "",
        ]
    )
    new_doc = "\n".join(
        [
            "//! aliases. Non-Project desktop support lives in `research_runtime_support.rs`.",
            "//! The pre-cutover `research_legacy_impl.rs` stays frozen only as a compatibility",
            "//! and regression fixture and is not compiled into the desktop runtime.",
            "//! Project reads/writes resolve canonical projects directly; no compatibility",
            "//! symlink is created or required.",
            "",
        ]
    )
    if old_doc not in facade:
        raise RuntimeError("facade documentation block changed")
    facade = facade.replace(old_doc, new_doc, 1)

    old_module = '#[path = "research_legacy_impl.rs"]\nmod legacy;\n'
    new_module = '#[path = "research_runtime_support.rs"]\nmod runtime_support;\n'
    if old_module not in facade:
        raise RuntimeError("legacy module declaration changed")
    facade = facade.replace(old_module, new_module, 1)
    facade = facade.replace("pub use legacy::{", "pub use runtime_support::{", 1)
    if facade.count("legacy::") != 4:
        raise RuntimeError(f"expected 4 runtime legacy delegates, found {facade.count('legacy::')}")
    facade = facade.replace("legacy::", "runtime_support::")
    old_marker = (
        "//! Self-check marker: legacy requirement evaluation still uses SpecifierSet in\n"
        "//! `research_legacy_impl.rs`; this facade does not duplicate that logic.\n"
    )
    new_marker = (
        "//! Self-check marker: runtime requirement evaluation uses SpecifierSet in\n"
        "//! `research_runtime_support.rs`; this facade does not duplicate that logic.\n"
    )
    if old_marker not in facade:
        raise RuntimeError("facade SpecifierSet marker changed")
    FACADE_PATH.write_text(facade.replace(old_marker, new_marker, 1), encoding="utf-8")

    self_check = SELF_CHECK_PATH.read_text(encoding="utf-8")
    old_req = (
        "'src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src-tauri/src/lib.rs',"
        "'src-tauri/src/research.rs',"
    )
    new_req = (
        "'src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src-tauri/src/lib.rs',"
        "'src-tauri/src/research.rs','src-tauri/src/research_runtime_support.rs',"
        "'src-tauri/src/research_legacy_impl.rs',"
    )
    if old_req not in self_check:
        raise RuntimeError("self-check required-file anchor changed")
    self_check = self_check.replace(old_req, new_req, 1)

    old_needles = "    'fn lab_compatibility_matrix(', 'SpecifierSet', 'fn scientific_smoke_tests(',\n"
    new_needles = "    'fn lab_compatibility_matrix(', 'fn scientific_smoke_tests(',\n"
    if old_needles not in self_check:
        raise RuntimeError("self-check research needle anchor changed")
    self_check = self_check.replace(old_needles, new_needles, 1)

    anchor = "research=(root/'src-tauri/src/research.rs').read_text()\n"
    addition = (
        "runtime_support=(root/'src-tauri/src/research_runtime_support.rs').read_text()\n"
        "assert 'SpecifierSet' in runtime_support\n"
        "assert '#[path = \\\"research_legacy_impl.rs\\\"]' not in research\n"
        "assert 'mod legacy;' not in research\n"
        "assert 'legacy::' not in research\n"
    )
    if self_check.count(anchor) != 1:
        raise RuntimeError("self-check research anchor changed")
    SELF_CHECK_PATH.write_text(self_check.replace(anchor, anchor + addition, 1), encoding="utf-8")

    validation = r'''#!/usr/bin/env python3
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
'''
    VALIDATION_PATH.write_text(textwrap.dedent(validation), encoding="utf-8")

    source_integrity = SOURCE_INTEGRITY_PATH.read_text(encoding="utf-8")
    py_anchor = (
        "scripts/rust_canonical_serial_capture_validation.py "
        "scripts/experiment_kernel_compute_validation.py"
    )
    py_new = (
        "scripts/rust_canonical_serial_capture_validation.py "
        "scripts/research_runtime_support_validation.py "
        "scripts/experiment_kernel_compute_validation.py"
    )
    if source_integrity.count(py_anchor) != 1:
        raise RuntimeError("Source Integrity Python anchor changed")
    source_integrity = source_integrity.replace(py_anchor, py_new, 1)

    rust_anchor = (
        "          rustfmt --edition 2021 --emit stdout src-tauri/src/research.rs >/dev/null\n"
        "          rustfmt --edition 2021 --emit stdout src-tauri/src/research_legacy_impl.rs >/dev/null\n"
    )
    rust_new = (
        "          rustfmt --edition 2021 --emit stdout src-tauri/src/research.rs >/dev/null\n"
        "          rustfmt --edition 2021 --emit stdout src-tauri/src/research_runtime_support.rs >/dev/null\n"
        "          rustfmt --edition 2021 --emit stdout src-tauri/src/research_legacy_impl.rs >/dev/null\n"
    )
    if source_integrity.count(rust_anchor) != 1:
        raise RuntimeError("Source Integrity Rust anchor changed")
    source_integrity = source_integrity.replace(rust_anchor, rust_new, 1)

    det_anchor = (
        "          python scripts/rust_canonical_serial_capture_validation.py\n"
        "          python scripts/experiment_kernel_compute_validation.py\n"
    )
    det_new = (
        "          python scripts/rust_canonical_serial_capture_validation.py\n"
        "          python scripts/research_runtime_support_validation.py\n"
        "          python scripts/experiment_kernel_compute_validation.py\n"
    )
    if source_integrity.count(det_anchor) != 1:
        raise RuntimeError("Source Integrity deterministic anchor changed")
    SOURCE_INTEGRITY_PATH.write_text(source_integrity.replace(det_anchor, det_new, 1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
