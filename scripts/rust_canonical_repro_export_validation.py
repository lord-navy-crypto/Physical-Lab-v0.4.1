#!/usr/bin/env python3
"""Acceptance checks for alias-independent reproducibility package export."""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src-tauri/src/research.rs"
LEGACY = ROOT / "src-tauri/src/research_legacy_impl.rs"

def compact(value: str) -> str:
    return "".join(value.split())

def function_block(text: str, name: str) -> str:
    marker = f"fn {name}("
    start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{": depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0: return text[start:index + 1]
    raise AssertionError(name)

def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")
    command = compact(function_block(source, "export_reproducibility_package"))
    assert "resolve_project_dir" in command
    assert "export_reproducibility_package_from_dir" in command
    assert "ensure_alias_for_id" not in command
    assert "legacy::" not in command

    helper = compact(function_block(source, "export_reproducibility_package_from_dir"))
    old = compact(function_block(legacy, "export_reproducibility_package"))
    for token in (
        'join("provenance")',
        'join("environment.json")',
        '"createdAt":now_iso()',
        '"arch":command_text("uname",&["-m"])',
        '"os":command_text("sw_vers",&["-productVersion"])',
        '"build":command_text("sw_vers",&["-buildVersion"])',
        '"sourceCommit"',
        '"python"',
        '"pipFreeze"',
        '"rev-parse","HEAD"',
        '"-m","pip","freeze","--all"',
        'app_root(app)?.join("exports")',
        '"{}-reproducible-{}.zip"',
        '"/usr/bin/ditto"',
        '"--sequesterRsrc"',
        '"--keepParent"',
        '"/usr/bin/zip"',
        '"Reproducibilityarchivecreationfailed"',
    ):
        assert token in helper, token

    for token in (
        'join("provenance")',
        'join("environment.json")',
        '"createdAt":now_iso()',
        '"arch":command_text("uname",&["-m"])',
        '"os":command_text("sw_vers",&["-productVersion"])',
        '"build":command_text("sw_vers",&["-buildVersion"])',
        '"sourceCommit"',
        '"python"',
        '"pipFreeze"',
        '"rev-parse","HEAD"',
        '"-m","pip","freeze","--all"',
        'app_root(&app)?.join("exports")',
        '"{}-reproducible-{}.zip"',
        '"/usr/bin/ditto"',
        '"--sequesterRsrc"',
        '"--keepParent"',
        '"/usr/bin/zip"',
        '"Reproducibilityarchivecreationfailed"',
    ):
        assert token in old, token

    lab_pairs = compact(function_block(source, "research_lab_id_name_pairs"))
    assert 'include_str!("../resources/modules.json")' in lab_pairs
    assert 'Some("lab")' in lab_pairs
    assert 'value.get("id")' in lab_pairs
    assert 'value.get("name")' in lab_pairs

    print("Physical Lab Rust canonical reproducibility export: PASS")
    print("- canonical/legacy direct resolver, no compatibility alias")
    print("- environment provenance fields preserved")
    print("- Lab source commit / Python / pip freeze capture preserved")
    print("- ditto archive + zip fallback preserved")
    print("Boundary: a reproducibility package records environment/provenance; it is not a scientific verification or validation certificate.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
