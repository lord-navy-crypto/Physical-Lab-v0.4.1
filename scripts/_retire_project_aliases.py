#!/usr/bin/env python3
from __future__ import annotations

import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src-tauri/src/research.rs"
RUST_VALIDATION = ROOT / "scripts/rust_canonical_read_paths_validation.py"
DESKTOP_VALIDATION = ROOT / "scripts/desktop_canonical_project_store_validation.py"
CONF = ROOT / "src-tauri/tauri.conf.json"
ALIAS_MODULE = ROOT / "src-tauri/resources/ui/physical_lab_workspace_aliases.py"


def remove_plain_fn(text: str, name: str) -> str:
    marker = f"fn {name}("
    start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                while end < len(text) and text[end] == "\n":
                    end += 1
                return text[:start] + text[end:]
    raise RuntimeError(name)


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")

    old_doc = "\n".join([
        "//! aliases. The pre-cutover research implementation is frozen in",
        "//! `research_legacy_impl.rs`; write/computation paths that still delegate to that",
        "//! implementation create an on-demand `workspaces/*.physlab` symlink only during",
        "//! the compatibility period.",
        "//!",
        "//! Existing real legacy workspaces are never replaced or rewritten. They remain",
        "//! readable as a fallback until explicit migration/retirement is complete.",
        "",
    ])
    new_doc = "\n".join([
        "//! aliases. The pre-cutover research implementation is frozen in",
        "//! `research_legacy_impl.rs` for non-project helper behavior and contract comparison.",
        "//! Project reads/writes resolve canonical projects directly; no compatibility",
        "//! symlink is created or required.",
        "//!",
        "//! Existing real legacy workspaces are never replaced or rewritten. They remain",
        "//! directly readable as a fallback and eligible for the explicit non-destructive",
        "//! Project Kernel bridge.",
        "",
    ])
    if old_doc not in text:
        raise RuntimeError("research facade compatibility doc block not found")
    text = text.replace(old_doc, new_doc, 1)

    start = text.index("fn legacy_root(app: &AppHandle)")
    end = text.index("fn safe_slug(", start)
    text = text[:start] + text[end:]

    start = text.index("#[cfg(unix)]\nfn create_alias(")
    end = text.index("fn ensure_alias_for_id(", start)
    text = text[:start] + text[end:]
    text = remove_plain_fn(text, "ensure_alias_for_id")

    if text.count("touch_canonical_after_write(") != 1:
        raise RuntimeError("touch_canonical_after_write gained a caller; review before retirement")
    text = remove_plain_fn(text, "touch_canonical_after_write")

    if "let legacy = legacy_root(&app)?;" not in text:
        raise RuntimeError("create_workspace legacy-root line not found")
    text = text.replace("let legacy = legacy_root(&app)?;", "let legacy = legacy_root_path(&app)?;", 1)
    alias_lines = "    let alias = legacy.join(format!(\"{id}.physlab\"));\n    create_alias(&alias, &dir)?;\n"
    if alias_lines not in text:
        raise RuntimeError("create_workspace alias creation lines not found")
    text = text.replace(alias_lines, "", 1)

    for forbidden in (
        "fn ensure_alias_for_id(",
        "fn create_alias(",
        "fn legacy_root(",
        "touch_canonical_after_write(",
    ):
        if forbidden in text:
            raise RuntimeError(f"compatibility helper still present: {forbidden}")
    SOURCE.write_text(text, encoding="utf-8")

    conf = CONF.read_text(encoding="utf-8")
    resource_line = '      "resources/ui/physical_lab_workspace_aliases.py": "ui/physical_lab_workspace_aliases.py",\n'
    if resource_line not in conf:
        raise RuntimeError("workspace alias resource entry not found")
    CONF.write_text(conf.replace(resource_line, "", 1), encoding="utf-8")
    if not ALIAS_MODULE.is_file():
        raise RuntimeError("workspace alias module missing before retirement")
    ALIAS_MODULE.unlink()

    RUST_VALIDATION.write_text(textwrap.dedent(r'''\
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
    assert "symlink" not in create_block
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
'''), encoding="utf-8")

    DESKTOP_VALIDATION.write_text(textwrap.dedent(r'''\
#!/usr/bin/env python3
"""Acceptance checks for the alias-free desktop canonical Project store."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri/resources/ui"
sys.path.insert(0, str(UI))

import physical_lab_project_discovery as discovery
import physical_lab_project_kernel as projects


def compact(text: str) -> str:
    return "".join(text.split())


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
    facade = (ROOT / "src-tauri/src/research.rs").read_text(encoding="utf-8")
    legacy = (ROOT / "src-tauri/src/research_legacy_impl.rs").read_text(encoding="utf-8")
    assert '#[path = "research_legacy_impl.rs"]' in facade
    assert len(legacy) > 25_000

    create_block = compact(function_block(facade, "create_workspace"))
    for needle in (
        '"project_version":PROJECT_VERSION',
        '"project_id":project_id',
        '"created_at":now',
        '"updated_at":now',
        '"experiments":{}',
        '"jobs":{}',
        '"results":{}',
        '"reports":[]',
        '"migration":{"current_version":PROJECT_VERSION,"history":[]}',
        'legacy_root_path(&app)',
    ):
        assert needle in create_block, needle
    for retired in (
        'create_alias',
        'ensure_alias_for_id',
        'legacy_root(&app)',
        '"id":&id',
        '"createdAt":&now',
        '"updatedAt":&now',
    ):
        assert retired not in create_block, retired
    assert "fn create_alias(" not in facade
    assert "fn ensure_alias_for_id(" not in facade
    assert "fn legacy_root(" not in facade

    conf = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    assert "resources/ui/physical_lab_workspace_aliases.py" not in resources
    assert not (UI / "physical_lab_workspace_aliases.py").exists()
    assert "resources/ui/physical_lab_project_discovery.py" in resources
    assert "resources/ui/physical_lab_canonical_discovery_patch.py" in resources
    assert "resources/ui/physical_lab_project_unification.py" in resources

    startup = (UI / "sitecustomize.py").read_text(encoding="utf-8")
    assert "ensure_workspace_aliases" not in startup
    assert "physical_lab_workspace_aliases" not in startup
    assert "physical_lab_canonical_discovery_patch" in startup

    old_data = os.environ.get("PHYSICAL_LAB_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="physical-lab-alias-free-store-") as td:
            root = Path(td)
            os.environ["PHYSICAL_LAB_DATA_DIR"] = str(root)

            canonical_path, canonical_doc = projects.create_project(
                "Alias-free canonical fixture",
                slug="alias-free-fixture",
                research_question="Can canonical project discovery operate without workspace aliases?",
            )
            assert canonical_path.parent == root / "projects"
            assert not (root / "workspaces").exists()
            rows = discovery.discover_projects()
            assert len(rows) == 1
            assert rows[0]["source"] == "canonical"
            assert rows[0]["project_id"] == canonical_doc["project_id"]
            assert rows[0]["path"].resolve() == canonical_path.resolve()
            assert not (root / "workspaces").exists()

            real_legacy = root / "workspaces/legacy-owned.physlab"
            real_legacy.mkdir(parents=True)
            legacy_doc = {
                "schema": "physical-lab-project-v1",
                "id": "legacy-owned",
                "name": "Real legacy project",
                "createdAt": "2026-01-01T00:00:00+00:00",
                "updatedAt": "2026-01-02T00:00:00+00:00",
            }
            legacy_bytes = json.dumps(legacy_doc, sort_keys=True).encode("utf-8")
            (real_legacy / "project.json").write_bytes(legacy_bytes)
            rows = discovery.discover_projects()
            assert [row["source"] for row in rows] == ["canonical", "legacy"]
            assert rows[1]["id"] == "legacy-owned"
            assert (real_legacy / "project.json").read_bytes() == legacy_bytes

            historical_alias = root / "workspaces" / canonical_path.name
            historical_alias.symlink_to(canonical_path, target_is_directory=True)
            rows = discovery.discover_projects()
            assert len(rows) == 2
            assert sum(row["source"] == "canonical" for row in rows) == 1
            assert sum(row["source"] == "legacy" for row in rows) == 1
            assert (real_legacy / "project.json").read_bytes() == legacy_bytes

            malformed = root / "projects/not-canonical.physlab"
            malformed.mkdir(parents=True)
            (malformed / "project.json").write_text(
                '{"schema":"physical-lab-project-v1","id":"wrong-shape"}',
                encoding="utf-8",
            )
            canonical_only = discovery.discover_projects(include_legacy=False)
            assert len(canonical_only) == 1
            assert canonical_only[0]["project_id"] == canonical_doc["project_id"]
    finally:
        if old_data is None:
            os.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
        else:
            os.environ["PHYSICAL_LAB_DATA_DIR"] = old_data

    print("Physical Lab desktop canonical Project store: PASS")
    print("- new projects live only under projects/*.physlab")
    print("- compatibility alias module/resource retired")
    print("- canonical discovery needs no workspaces directory")
    print("- genuine legacy workspace fallback preserved byte-for-byte")
    print("- historical alias deduplication preserved for upgraded installs")
    print("- explicit Project Kernel bridge remains packaged")
    print("Boundary: alias retirement changes storage plumbing only; it does not reinterpret runs, datasets, results, measurements, or claims.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
