"""Compatibility aliases for legacy readers during Project Kernel cutover.

New desktop projects live under ``projects/*.physlab``. A few older read-only UI
surfaces (notably the Measurement Digital Twin dataset browser) still discover
projects under ``workspaces/*.physlab``. On macOS/Linux this module creates a
symlink only when that legacy path is absent. Existing legacy workspaces are
never replaced, moved or modified.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _root() -> Path | None:
    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _is_canonical_project(path: Path) -> bool:
    try:
        doc = json.loads((path / "project.json").read_text(encoding="utf-8"))
    except Exception:
        return False
    return (
        isinstance(doc, dict)
        and doc.get("schema") == "physical-lab-project-v1"
        and int(doc.get("project_version") or 0) == 1
        and str(doc.get("project_id") or "").startswith("plproj-")
    )


def ensure_workspace_aliases() -> dict[str, Any]:
    root = _root()
    if root is None:
        return {"canonical": 0, "created": 0, "preserved_legacy": 0, "errors": []}
    projects = root / "projects"
    legacy = root / "workspaces"
    projects.mkdir(parents=True, exist_ok=True)
    legacy.mkdir(parents=True, exist_ok=True)
    created = 0
    preserved = 0
    canonical = 0
    errors: list[dict[str, str]] = []
    for project in sorted(projects.glob("*.physlab")):
        if not project.is_dir() or not _is_canonical_project(project):
            continue
        canonical += 1
        alias = legacy / project.name
        if alias.exists() or alias.is_symlink():
            # Never replace a real legacy workspace. Existing aliases are also left
            # alone so the operation stays idempotent and non-destructive.
            preserved += 1
            continue
        try:
            alias.symlink_to(project, target_is_directory=True)
            created += 1
        except Exception as exc:
            errors.append({"project": str(project), "alias": str(alias), "error": str(exc)[:300]})
    return {
        "canonical": canonical,
        "created": created,
        "preserved_legacy": preserved,
        "errors": errors,
        "boundary": "Compatibility discovery aliases only; canonical project data remains stored under projects/ and existing workspaces are never replaced.",
    }
