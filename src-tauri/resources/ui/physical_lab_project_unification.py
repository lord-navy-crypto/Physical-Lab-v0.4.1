"""Safe bridge from the legacy desktop workspace store to the canonical Project Kernel.

Physical Lab historically created ``workspaces/*.physlab`` directories from the
Rust desktop shell.  The newer Experiment / Evidence stack uses
``projects/*.physlab`` and a stricter project document even though both older and
newer documents once used the string ``physical-lab-project-v1``.

This module resolves that collision without deleting or reinterpreting legacy
scientific records:

* legacy workspaces remain untouched and are treated as source evidence;
* a deterministic canonical project is created under ``projects/``;
* legacy measurement datasets are copied into the canonical Measurement Registry
  with SHA-256 provenance;
* legacy runs, campaigns, pipelines, figures and exports are inventoried only --
  they are NOT promoted to canonical experiments/jobs/results;
* repeated synchronization is idempotent and preserves user edits made to the
  canonical project.

The bridge is intentionally one-way.  A later desktop-shell migration can switch
all new writes to the canonical store after this compatibility period.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import physical_lab_measurement_registry as measurements
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import plain, utc_now

LEGACY_SCHEMA_LABEL = "physical-lab-project-v1"
CANONICAL_SCHEMA = projects.PROJECT_SCHEMA
BRIDGE_SCHEMA = "physical-lab-legacy-workspace-bridge-v1"
BRIDGE_VERSION = 1


def _data_root() -> Path | None:
    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def legacy_root() -> Path | None:
    root = _data_root()
    if root is None:
        return None
    path = root / "workspaces"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(plain(dict(value)), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _sha_json(value: Any) -> str:
    raw = json.dumps(plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return _sha_bytes(raw)


def is_canonical_document(document: Mapping[str, Any]) -> bool:
    return (
        document.get("schema") == CANONICAL_SCHEMA
        and int(document.get("project_version") or 0) == projects.PROJECT_VERSION
        and str(document.get("project_id") or "").startswith("plproj-")
        and isinstance(document.get("experiments"), Mapping)
        and isinstance(document.get("jobs"), Mapping)
        and isinstance(document.get("results"), Mapping)
    )


def is_legacy_shell_document(document: Mapping[str, Any]) -> bool:
    """Detect the old Rust-shell shape rather than trusting its reused schema label."""
    return (
        document.get("schema") == LEGACY_SCHEMA_LABEL
        and bool(str(document.get("id") or "").strip())
        and "createdAt" in document
        and "updatedAt" in document
        and "project_id" not in document
        and "project_version" not in document
    )


def classify_project_document(document: Mapping[str, Any]) -> str:
    if is_canonical_document(document):
        return "canonical"
    if is_legacy_shell_document(document):
        return "legacy-shell"
    return "unknown"


def _legacy_identity(source: Path, document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "legacy_id": str(document.get("id") or source.stem),
        "name": str(document.get("name") or source.stem),
        "created_at": str(document.get("createdAt") or ""),
        "updated_at": str(document.get("updatedAt") or ""),
        "source_path": str(source.resolve()),
    }


def _deterministic_project_id(source: Path, document: Mapping[str, Any]) -> str:
    identity = _legacy_identity(source, document)
    token = _sha_json({"legacy_id": identity["legacy_id"], "source_path": identity["source_path"]})[:20]
    return f"plproj-legacy-{token}"


def _safe_slug(value: str) -> str:
    out = []
    for char in str(value).strip().lower():
        if char.isalnum() or char in ".-_":
            out.append(char)
        elif not out or out[-1] != "-":
            out.append("-")
    slug = "".join(out).strip("-._")[:72]
    return slug or "legacy-project"


def _candidate_canonical_dir(source: Path, document: Mapping[str, Any]) -> Path:
    root = projects.projects_root()
    if root is None:
        raise RuntimeError("PHYSICAL_LAB_DATA_DIR is not configured")
    base = _safe_slug(str(document.get("id") or document.get("name") or source.stem))
    candidate = root / f"{base}.physlab"
    wanted_id = _deterministic_project_id(source, document)
    if not candidate.exists():
        return candidate
    existing = _read_json(candidate / "project.json") or {}
    if str(existing.get("project_id") or "") == wanted_id:
        return candidate
    suffix = _sha_json({"source": str(source.resolve())})[:10]
    return root / f"{base}-legacy-{suffix}.physlab"


def _iter_json_records(source: Path, dirname: str) -> list[dict[str, Any]]:
    root = source / dirname
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.rglob("*.json")):
        try:
            rel = path.relative_to(source).as_posix()
            rows.append({
                "path": rel,
                "size_bytes": path.stat().st_size,
                "sha256": _sha_file(path),
            })
        except Exception:
            continue
    return rows


def _dataset_entries(source: Path) -> list[dict[str, Any]]:
    root = source / "datasets"
    output: list[dict[str, Any]] = []
    if not root.is_dir():
        return output
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        meta = _read_json(folder / "metadata.json") or {}
        assets = sorted(
            p for p in folder.iterdir()
            if p.is_file() and p.name != "metadata.json" and not p.name.startswith(".")
        )
        if not assets:
            continue
        # Legacy Data Bridge creates one stored data asset per dataset directory.
        # If extra files are present, import each independently rather than guessing.
        for asset in assets:
            output.append({
                "legacy_dataset_id": str(meta.get("id") or folder.name),
                "legacy_name": str(meta.get("name") or folder.name),
                "quantity": str(meta.get("quantity") or ""),
                "unit": str(meta.get("unit") or ""),
                "instrument": str(meta.get("sensor") or ""),
                "captured_at": str(meta.get("createdAt") or ""),
                "calibration_note": meta.get("calibration"),
                "format": str(meta.get("format") or asset.suffix.lstrip(".")),
                "asset_path": asset,
                "asset_relative_path": asset.relative_to(source).as_posix(),
                "sha256": _sha_file(asset),
                "size_bytes": asset.stat().st_size,
                "metadata_sha256": _sha_file(folder / "metadata.json") if (folder / "metadata.json").is_file() else None,
            })
    return output


def _source_fingerprint(source: Path, document: Mapping[str, Any], datasets: list[Mapping[str, Any]]) -> str:
    payload = {
        "identity": _legacy_identity(source, document),
        "project_json_sha256": _sha_file(source / "project.json"),
        "datasets": [
            {
                "legacy_dataset_id": row.get("legacy_dataset_id"),
                "asset_relative_path": row.get("asset_relative_path"),
                "sha256": row.get("sha256"),
                "metadata_sha256": row.get("metadata_sha256"),
            }
            for row in datasets
        ],
        "runs": _iter_json_records(source, "runs"),
        "campaigns": _iter_json_records(source, "campaigns"),
        "pipelines": _iter_json_records(source, "pipelines"),
        "provenance": _iter_json_records(source, "provenance"),
    }
    return _sha_json(payload)


def _bridge_path(canonical: Path) -> Path:
    return canonical / "provenance" / "legacy-workspace-bridge.json"


def _ensure_canonical_project(source: Path, legacy: Mapping[str, Any], canonical: Path) -> tuple[dict[str, Any], bool]:
    wanted_id = _deterministic_project_id(source, legacy)
    existing = _read_json(canonical / "project.json") if canonical.exists() else None
    if existing is not None:
        if not is_canonical_document(existing):
            raise ValueError(f"refusing to overwrite non-canonical project at {canonical}")
        if str(existing.get("project_id")) != wanted_id:
            raise ValueError(f"canonical project collision at {canonical}")
        projects.open_project(canonical)
        return existing, False

    canonical.mkdir(parents=True, exist_ok=False)
    created = str(legacy.get("createdAt") or utc_now())
    document = projects.new_project_document(
        str(legacy.get("name") or source.stem),
        project_id=wanted_id,
        description=str(legacy.get("description") or "Imported from legacy Physical Lab desktop workspace."),
        research_question="",
        created_at=created,
    )
    document["slug"] = canonical.stem.removesuffix(".physlab")
    document["updated_at"] = str(legacy.get("updatedAt") or created)
    document["migration"]["history"].append({
        "from": "legacy-rust-shell-workspace-v1-shape",
        "to": CANONICAL_SCHEMA,
        "bridge_schema": BRIDGE_SCHEMA,
        "source_path": str(source.resolve()),
        "note": (
            "Non-destructive compatibility import. Legacy run/campaign/pipeline records remain provenance only; "
            "they were not reinterpreted as canonical experiments, jobs or scientific results."
        ),
    })
    _atomic_json(canonical / "project.json", document)
    projects.open_project(canonical)
    return document, True


def _import_measurements(canonical: Path, datasets: list[Mapping[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    before = {row["measurement_id"] for row in measurements.list_measurements(canonical)}
    imported: list[dict[str, Any]] = []
    for row in datasets:
        asset = Path(str(row["asset_path"]))
        calibration = row.get("calibration_note")
        calibration_text = "" if calibration in (None, "") else json.dumps(plain(calibration), sort_keys=True) if not isinstance(calibration, str) else calibration
        notes = (
            f"Imported from legacy desktop dataset {row.get('legacy_dataset_id')}; "
            f"legacy path {row.get('asset_relative_path')}."
        )
        if calibration_text:
            notes += f" Legacy calibration note preserved verbatim: {calibration_text}"
        record = measurements.ingest_measurement_bytes(
            canonical,
            filename=asset.name,
            data=asset.read_bytes(),
            profile="legacy-desktop-workspace",
            instrument=str(row.get("instrument") or ""),
            quantity=str(row.get("quantity") or ""),
            unit=str(row.get("unit") or ""),
            captured_at=str(row.get("captured_at") or ""),
            notes=notes,
        )
        imported.append({
            "legacy_dataset_id": row.get("legacy_dataset_id"),
            "legacy_path": row.get("asset_relative_path"),
            "measurement_id": record.get("measurement_id"),
            "sha256": record.get("sha256"),
        })
    after = {row["measurement_id"] for row in measurements.list_measurements(canonical)}
    return len(after - before), imported


def synchronize_legacy_workspace(source_dir: str | Path) -> dict[str, Any]:
    source = Path(source_dir).expanduser().resolve()
    legacy = _read_json(source / "project.json")
    if legacy is None:
        raise FileNotFoundError(source / "project.json")
    if not is_legacy_shell_document(legacy):
        raise ValueError(f"not a recognized legacy desktop workspace: {source}")

    canonical = _candidate_canonical_dir(source, legacy)
    document, created = _ensure_canonical_project(source, legacy, canonical)
    datasets = _dataset_entries(source)
    fingerprint = _source_fingerprint(source, legacy, datasets)
    previous = _read_json(_bridge_path(canonical)) or {}
    previous_fingerprint = str(previous.get("source_fingerprint_sha256") or "")

    imported_count, measurement_links = _import_measurements(canonical, datasets)
    inventories = {
        "runs": _iter_json_records(source, "runs"),
        "campaigns": _iter_json_records(source, "campaigns"),
        "pipelines": _iter_json_records(source, "pipelines"),
        "provenance": _iter_json_records(source, "provenance"),
    }
    bridge = {
        "schema": BRIDGE_SCHEMA,
        "bridge_version": BRIDGE_VERSION,
        "canonical_project_id": document.get("project_id"),
        "canonical_project_path": str(canonical),
        "legacy": _legacy_identity(source, legacy),
        "source_schema_label": legacy.get("schema"),
        "source_shape": "legacy-rust-shell-workspace-v1-shape",
        "source_fingerprint_sha256": fingerprint,
        "measurement_links": measurement_links,
        "inventory": inventories,
        "inventory_counts": {name: len(rows) for name, rows in inventories.items()},
        "dataset_count": len(datasets),
        "synced_at": utc_now(),
        "boundary": (
            "Compatibility bridge only. Legacy datasets become file-integrity measurement evidence. Legacy runs, "
            "campaigns, pipelines, figures and exports are not promoted to canonical scientific results or validation evidence. "
            "The legacy workspace is never deleted or modified by this bridge."
        ),
    }
    _atomic_json(_bridge_path(canonical), bridge)
    return {
        "legacy_path": str(source),
        "canonical_path": str(canonical),
        "canonical_project_id": document.get("project_id"),
        "created": created,
        "changed": created or fingerprint != previous_fingerprint,
        "measurements_imported": imported_count,
        "dataset_count": len(datasets),
        "inventory_counts": bridge["inventory_counts"],
        "source_fingerprint_sha256": fingerprint,
    }


def synchronize_legacy_workspaces() -> dict[str, Any]:
    root = legacy_root()
    if root is None:
        return {"discovered": 0, "created": 0, "changed": 0, "unchanged": 0, "measurements_imported": 0, "errors": []}
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for source in sorted(root.glob("*.physlab")):
        document = _read_json(source / "project.json")
        if not document or not is_legacy_shell_document(document):
            continue
        try:
            rows.append(synchronize_legacy_workspace(source))
        except Exception as exc:
            errors.append({"legacy_path": str(source), "error": str(exc)[:500]})
    return {
        "discovered": len(rows) + len(errors),
        "created": sum(1 for row in rows if row["created"]),
        "changed": sum(1 for row in rows if row["changed"]),
        "unchanged": sum(1 for row in rows if not row["changed"]),
        "measurements_imported": sum(int(row["measurements_imported"]) for row in rows),
        "projects": rows,
        "errors": errors,
        "boundary": "One-way, non-destructive legacy compatibility sync; canonical scientific identities are never inferred from legacy run files.",
    }
