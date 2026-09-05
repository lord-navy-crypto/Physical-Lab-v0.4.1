"""Canonical-first discovery for Physical Lab .physlab projects.

The canonical Project Kernel lives under ``projects/*.physlab``. During the
compatibility period, genuinely legacy Rust-shell workspaces may still exist under
``workspaces/*.physlab``. This module makes Python UI consumers independent of
workspace symlinks by discovering canonical projects directly and considering
legacy projects only as a fallback.

Discovery never migrates, rewrites, aliases, or interprets scientific records.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

CANONICAL_SCHEMA = "physical-lab-project-v1"
CANONICAL_VERSION = 1


def data_root() -> Path | None:
    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    return root if root.exists() else None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def is_canonical_document(document: Mapping[str, Any]) -> bool:
    return (
        document.get("schema") == CANONICAL_SCHEMA
        and int(document.get("project_version") or 0) == CANONICAL_VERSION
        and str(document.get("project_id") or "").startswith("plproj-")
        and isinstance(document.get("experiments"), Mapping)
        and isinstance(document.get("jobs"), Mapping)
        and isinstance(document.get("results"), Mapping)
    )


def is_legacy_document(document: Mapping[str, Any]) -> bool:
    return (
        document.get("schema") == CANONICAL_SCHEMA
        and bool(str(document.get("id") or "").strip())
        and "createdAt" in document
        and "updatedAt" in document
        and "project_id" not in document
        and "project_version" not in document
    )


def _resolved_key(path: Path) -> str:
    try:
        return str(path.resolve())
    except Exception:
        return str(path.absolute())


def discover_projects(*, include_legacy: bool = True) -> list[dict[str, Any]]:
    """Return canonical projects first, then genuinely legacy fallback projects.

    Compatibility symlinks under ``workspaces/`` are ignored because their resolved
    path is already represented by a canonical project. A real legacy workspace is
    included only when it is not an alias/duplicate of a canonical directory.
    """
    root = data_root()
    if root is None:
        return []

    rows: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()

    for folder in sorted((root / "projects").glob("*.physlab")):
        if not folder.is_dir():
            continue
        document = _read_json(folder / "project.json")
        if not document or not is_canonical_document(document):
            continue
        project_id = str(document["project_id"])
        resolved = _resolved_key(folder)
        rows.append({
            "id": project_id,
            "project_id": project_id,
            "name": str(document.get("name") or folder.stem),
            "path": folder.resolve(),
            "source": "canonical",
            "schema": CANONICAL_SCHEMA,
            "project_version": CANONICAL_VERSION,
            "updated_at": str(document.get("updated_at") or ""),
        })
        seen_paths.add(resolved)
        seen_ids.add(project_id)

    if include_legacy:
        for folder in sorted((root / "workspaces").glob("*.physlab")):
            # A workspace symlink is compatibility plumbing, never a second project.
            if folder.is_symlink():
                continue
            if not folder.is_dir():
                continue
            resolved = _resolved_key(folder)
            if resolved in seen_paths:
                continue
            document = _read_json(folder / "project.json")
            if not document or not is_legacy_document(document):
                continue
            legacy_id = str(document.get("id") or folder.stem)
            identity = f"legacy:{legacy_id}:{resolved}"
            if identity in seen_ids:
                continue
            rows.append({
                "id": legacy_id,
                "project_id": None,
                "name": str(document.get("name") or folder.stem),
                "path": folder.resolve(),
                "source": "legacy",
                "schema": CANONICAL_SCHEMA,
                "project_version": None,
                "updated_at": str(document.get("updatedAt") or ""),
            })
            seen_paths.add(resolved)
            seen_ids.add(identity)

    rows.sort(key=lambda row: (0 if row["source"] == "canonical" else 1, -len(str(row.get("updated_at") or "")), str(row["name"]).lower()))
    return rows


def discovery_summary(*, include_legacy: bool = True) -> dict[str, Any]:
    rows = discover_projects(include_legacy=include_legacy)
    return {
        "total": len(rows),
        "canonical": sum(1 for row in rows if row["source"] == "canonical"),
        "legacy": sum(1 for row in rows if row["source"] == "legacy"),
        "boundary": (
            "Project discovery only. Canonical-first listing does not migrate, validate, "
            "or reinterpret datasets, runs, results, measurements, or claims."
        ),
    }
