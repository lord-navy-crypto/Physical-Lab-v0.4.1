#!/usr/bin/env python3
"""Static acceptance checks for alias-independent Rust desktop read paths."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src-tauri" / "src" / "research.rs"


def compact(value: str) -> str:
    """Remove formatting whitespace so rustfmt layout cannot change the contract."""
    return "".join(value.split())


def function_block(text: str, name: str) -> str:
    marker = f"pub fn {name}("
    start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(f"unterminated Rust function: {name}")


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    packed = compact(text)

    for helper in (
        "fn canonical_project_dir(",
        "fn legacy_project_dir(",
        "fn resolve_project_dir(",
        "fn is_compatibility_alias(",
        "fn list_datasets_from_dir(",
        "fn list_run_snapshots_from_dir(",
        "fn compare_run_snapshots_from_dir(",
        "fn list_campaigns_from_dir(",
    ):
        assert helper in text, f"missing canonical read helper: {helper}"

    assert "alias_targets_canonical" not in text
    assert "ensure_all_aliases" not in text
    assert 'join("projects")' in packed
    assert 'join("workspaces")' in packed
    assert "file_type().is_symlink()" in packed
    assert "canonical_identity_matches" in text
    assert 'document.get("project_id")' in packed

    canonical_reads = {
        "open_workspace": "resolve_project_dir",
        "list_datasets": "list_datasets_from_dir",
        "list_run_snapshots": "list_run_snapshots_from_dir",
        "compare_run_snapshots": "compare_run_snapshots_from_dir",
        "list_campaigns": "list_campaigns_from_dir",
    }
    for name, required in canonical_reads.items():
        block = compact(function_block(text, name))
        assert required in block, f"{name} must use canonical read path"
        assert "ensure_alias_for_id" not in block, f"{name} must not create compatibility aliases"
        assert "legacy::" not in block, f"{name} must not delegate read access to legacy implementation"

    list_block = compact(function_block(text, "list_workspaces"))
    assert "canonical_root(&app)" in list_block
    assert "legacy_root_path(&app)" in list_block
    assert "is_compatibility_alias" in list_block
    assert "ensure_alias_for_id" not in list_block
    assert "create_alias" not in list_block
    assert "legacy::" not in list_block

    create_block = compact(function_block(text, "create_workspace"))
    assert "canonical_root(&app)" in create_block
    assert "create_alias(&alias,&dir)?" in create_block
    assert "summary_from_dir(&dir)" in create_block

    for name in (
        "capture_serial_measurement",
        "export_reproducibility_package",
    ):
        block = compact(function_block(text, name))
        assert "ensure_alias_for_id" in block, (
            f"{name} still delegates through legacy storage and must create alias on demand"
        )

    touch_block = compact(
        text[
            text.index("fn touch_canonical_after_write(") :
            text.index("fn register_desktop_measurement(")
        ]
    )
    assert "canonical_project_dir" in touch_block
    assert "workspaces" not in touch_block

    measurement_start = text.index("fn register_desktop_measurement(")
    measurement_end = text.index("fn list_datasets_from_dir(", measurement_start)
    measurement_block = compact(text[measurement_start:measurement_end])
    assert "canonical_project_dir" in measurement_block
    assert "workspaces" not in measurement_block
    assert '"physical-lab-measurement-v1"' in measurement_block

    print("Physical Lab Rust canonical read paths: PASS")
    print("- Projects list/open: canonical-first, alias-independent")
    print("- Dataset list: canonical/legacy direct read")
    print("- Run list/compare: canonical/legacy direct read")
    print("- Campaign list: canonical/legacy direct read")
    print("- compatibility symlink ignored by read discovery")
    print("- legacy write/computation delegates remain on-demand only")
    print("- canonical updated_at + Measurement Evidence write-back no longer depend on alias identity")
    print("Boundary: this changes project path resolution only; run/dataset/campaign semantics are not promoted into canonical scientific evidence by reading them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
