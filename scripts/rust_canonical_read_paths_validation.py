\
#!/usr/bin/env python3
"""Static acceptance checks for alias-free canonical Rust project paths."""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src-tauri/src/research.rs"


def compact(value: str) -> str:
    return "".join(value.split())


def function_block(text: str, name: str) -> str:
    marker = f"fn {name}("
    start = text.index(marker)
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
        "fn touch_project_after_direct_write(",
    ):
        assert helper in text, helper

    for retired in (
        "fn ensure_alias_for_id(",
        "fn create_alias(",
        "fn legacy_root(",
        "touch_canonical_after_write(",
        "ensure_all_aliases",
        "alias_targets_canonical",
    ):
        assert retired not in text, retired

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
        assert required in block, name
        assert "legacy::" not in block, name

    list_block = compact(function_block(text, "list_workspaces"))
    assert "canonical_root(&app)" in list_block
    assert "legacy_root_path(&app)" in list_block
    assert "is_compatibility_alias" in list_block
    assert "create_alias" not in list_block
    assert "legacy::" not in list_block

    create_block = compact(function_block(text, "create_workspace"))
    assert "canonical_root(&app)" in create_block
    assert "legacy_root_path(&app)" in create_block
    assert "legacy_root(&app)" not in create_block
    assert "create_alias" not in create_block
    assert "summary_from_dir(&dir)" in create_block

    serial_block = compact(function_block(text, "capture_serial_measurement"))
    assert "resolve_project_dir" in serial_block
    assert "capture_serial_measurement_to_dir" in serial_block
    assert "legacy::" not in serial_block

    touch_block = compact(function_block(text, "touch_project_after_direct_write"))
    assert 'project["updated_at"]' in touch_block
    assert 'project["updatedAt"]' in touch_block

    registration = compact(function_block(text, "register_desktop_measurement"))
    assert "canonical_project_dir" in registration
    assert "workspaces" not in registration
    assert '"physical-lab-measurement-v1"' in registration

    print("Physical Lab Rust canonical project paths: PASS")
    print("- canonical project reads/writes: direct")
    print("- project commands require no compatibility alias")
    print("- create_workspace does not create workspaces/ or symlinks")
    print("- genuine legacy workspaces remain direct fallback")
    print("- historical symlinks remain safely ignored")
    print("Boundary: path unification changes storage/discovery only; it does not promote workflow artifacts into scientific validation evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
