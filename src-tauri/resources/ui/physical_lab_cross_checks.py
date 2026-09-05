"""Evidence-linked cross-checks for Physical Lab projects.

A cross-check compares one scalar observable produced by two user-declared
distinct method paths and binds that comparison to explicit project evidence.
The result can show agreement/disagreement within a declared tolerance, but it
never establishes scientific truth, standards compliance, or solver independence.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

import physical_lab_claims as claims
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import plain, utc_now

CROSS_CHECK_SCHEMA = "physical-lab-cross-check-v1"
CROSS_CHECK_INDEX_SCHEMA = "physical-lab-cross-check-index-v1"
CROSS_CHECK_VERSION = 1
CROSS_CHECK_STATUSES = (
    "AGREES_WITHIN_TOLERANCE",
    "DISAGREES",
    "NOT_DISTINCT",
    "STALE",
    "EVIDENCE_MISSING",
)
TOLERANCE_MODES = ("absolute", "relative")


def _sha(value: Any) -> str:
    raw = json.dumps(plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


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


def _root(project_dir: Path) -> Path:
    path = project_dir / "provenance" / "cross-checks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path(project_dir: Path) -> Path:
    return _root(project_dir) / "index.json"


def _load_index(project_dir: Path) -> dict[str, Any]:
    existing = _read_json(_index_path(project_dir))
    if existing and existing.get("schema") == CROSS_CHECK_INDEX_SCHEMA:
        return existing
    return {"schema": CROSS_CHECK_INDEX_SCHEMA, "cross_checks": {}, "updated_at": None}


def _finite(value: Any, label: str) -> float:
    try:
        out = float(value)
    except Exception as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(out):
        raise ValueError(f"{label} must be finite")
    return out


def _normalize_refs(references: list[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in references or []:
        kind = str(item.get("kind") or "").strip().lower()
        ref_id = str(item.get("id") or "").strip()
        if kind not in claims.REFERENCE_KINDS:
            raise ValueError(f"unsupported evidence reference kind: {kind!r}")
        if not ref_id:
            raise ValueError("evidence reference id is required")
        key = (kind, ref_id)
        if key not in seen:
            rows.append({"kind": kind, "id": ref_id})
            seen.add(key)
    rows.sort(key=lambda row: (row["kind"], row["id"]))
    return rows


def _normalize_path(role: str, value: Mapping[str, Any]) -> dict[str, Any]:
    label = str(value.get("label") or role).strip() or role
    method_family = str(value.get("method_family") or "").strip()
    source_identity = str(value.get("source_identity") or "").strip()
    if not method_family:
        raise ValueError(f"{role}.method_family is required")
    if not source_identity:
        raise ValueError(f"{role}.source_identity is required")
    refs = _normalize_refs(value.get("references") if isinstance(value.get("references"), list) else None)
    if not refs:
        raise ValueError(f"{role}.references must contain at least one project evidence reference")
    return {
        "role": role,
        "label": label,
        "value": _finite(value.get("value"), f"{role}.value"),
        "method_family": method_family,
        "source_identity": source_identity,
        "references": refs,
    }


def _resolve_refs(project_dir: Path, project: Mapping[str, Any], path_record: Mapping[str, Any]) -> list[dict[str, Any]]:
    snapshots = []
    for ref in path_record.get("references") or []:
        resolved = claims._resolve_reference(project_dir, project, str(ref.get("kind")), str(ref.get("id")))
        if resolved is None:
            raise ValueError(f"evidence reference does not exist: {ref.get('kind')}:{ref.get('id')}")
        snapshots.append({"role": path_record.get("role"), **resolved})
    return snapshots


def _declared_distinct(primary: Mapping[str, Any], comparison: Mapping[str, Any]) -> bool:
    family_a = str(primary.get("method_family") or "").strip().casefold()
    family_b = str(comparison.get("method_family") or "").strip().casefold()
    source_a = str(primary.get("source_identity") or "").strip().casefold()
    source_b = str(comparison.get("source_identity") or "").strip().casefold()
    return bool(family_a and family_b and source_a and source_b and family_a != family_b and source_a != source_b)


def register_cross_check(
    project_dir: str | Path,
    *,
    name: str,
    observable: str,
    primary: Mapping[str, Any],
    comparison: Mapping[str, Any],
    tolerance: float,
    tolerance_mode: str = "relative",
    unit: str = "",
    intended_use: str = "",
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    name = str(name).strip()
    observable = str(observable).strip()
    if not name or not observable:
        raise ValueError("cross-check name and observable are required")
    mode = str(tolerance_mode).strip().lower()
    if mode not in TOLERANCE_MODES:
        raise ValueError(f"tolerance_mode must be one of {TOLERANCE_MODES}")
    tol = _finite(tolerance, "tolerance")
    if tol < 0:
        raise ValueError("tolerance must be non-negative")
    p = _normalize_path("primary", primary)
    c = _normalize_path("comparison", comparison)
    snapshots = _resolve_refs(path, project, p) + _resolve_refs(path, project, c)
    identity = {
        "project_id": project.get("project_id"),
        "name": name,
        "observable": observable,
        "primary": p,
        "comparison": c,
        "tolerance": tol,
        "tolerance_mode": mode,
        "unit": str(unit),
        "intended_use": str(intended_use).strip(),
    }
    cross_check_id = f"xcheck-{_sha(identity)[:20]}"
    now = utc_now()
    existing = _read_json(_root(path) / f"{cross_check_id}.json")
    registered_at = str((existing or {}).get("registered_at") or now)
    record = {
        "schema": CROSS_CHECK_SCHEMA,
        "cross_check_version": CROSS_CHECK_VERSION,
        "cross_check_id": cross_check_id,
        **identity,
        "evidence_snapshot": snapshots,
        "declared_distinct": _declared_distinct(p, c),
        "registered_at": registered_at,
        "updated_at": now,
        "notes": str(notes),
        "boundary": (
            "Distinct method_family/source_identity values are user-declared metadata, not proof of statistical or algorithmic independence. "
            "Agreement within tolerance is corroborating evidence only."
        ),
    }
    record["cross_check_sha256"] = _sha({
        key: record[key]
        for key in (
            "schema", "cross_check_version", "cross_check_id", "project_id", "name", "observable",
            "primary", "comparison", "tolerance", "tolerance_mode", "unit", "intended_use",
            "evidence_snapshot", "declared_distinct",
        )
    })
    _atomic_json(_root(path) / f"{cross_check_id}.json", record)
    index = _load_index(path)
    index.setdefault("cross_checks", {})[cross_check_id] = {
        "cross_check_id": cross_check_id,
        "name": name,
        "observable": observable,
        "cross_check_sha256": record["cross_check_sha256"],
        "path": f"provenance/cross-checks/{cross_check_id}.json",
        "updated_at": now,
    }
    index["updated_at"] = now
    _atomic_json(_index_path(path), index)
    return record


def get_cross_check(project_dir: str | Path, cross_check_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    row = _read_json(_root(path) / f"{cross_check_id}.json")
    if not row or row.get("schema") != CROSS_CHECK_SCHEMA:
        raise ValueError(f"unknown cross_check_id: {cross_check_id}")
    return row


def list_cross_checks(project_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    index = _load_index(path)
    rows = [dict(v) for v in (index.get("cross_checks") or {}).values() if isinstance(v, Mapping)]
    rows.sort(key=lambda row: (str(row.get("updated_at") or ""), str(row.get("cross_check_id") or "")), reverse=True)
    return rows


def evaluate_cross_check(project_dir: str | Path, cross_check_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    record = get_cross_check(path, cross_check_id)
    snapshots = {
        (str(row.get("role")), str(row.get("kind")), str(row.get("id"))): row
        for row in record.get("evidence_snapshot") or [] if isinstance(row, Mapping)
    }
    missing: list[str] = []
    stale: list[str] = []
    reference_checks: list[dict[str, Any]] = []
    for side in (record.get("primary") or {}, record.get("comparison") or {}):
        role = str(side.get("role") or "")
        for ref in side.get("references") or []:
            kind = str(ref.get("kind") or "")
            ref_id = str(ref.get("id") or "")
            current = claims._resolve_reference(path, project, kind, ref_id)
            snapshot = snapshots.get((role, kind, ref_id))
            key = f"{role}:{kind}:{ref_id}"
            if current is None:
                missing.append(key)
                reference_checks.append({"reference": key, "state": "MISSING", "snapshot_sha256": (snapshot or {}).get("sha256"), "current_sha256": None})
                continue
            is_stale = bool(snapshot and str(snapshot.get("sha256") or "") != str(current.get("sha256") or ""))
            if is_stale:
                stale.append(key)
            reference_checks.append({
                "reference": key,
                "state": "STALE" if is_stale else "CURRENT",
                "snapshot_sha256": (snapshot or {}).get("sha256"),
                "current_sha256": current.get("sha256"),
            })

    primary_value = float((record.get("primary") or {}).get("value"))
    comparison_value = float((record.get("comparison") or {}).get("value"))
    absolute_difference = abs(primary_value - comparison_value)
    scale = max(abs(primary_value), abs(comparison_value), 1e-30)
    relative_difference = absolute_difference / scale
    tolerance = float(record.get("tolerance") or 0.0)
    tolerance_mode = str(record.get("tolerance_mode") or "relative")
    comparison_metric = absolute_difference if tolerance_mode == "absolute" else relative_difference
    within = comparison_metric <= tolerance
    declared_distinct = bool(record.get("declared_distinct"))

    if missing:
        status = "EVIDENCE_MISSING"
        rationale = "One or more evidence references no longer resolve."
    elif stale:
        status = "STALE"
        rationale = "One or more supporting evidence fingerprints changed after registration."
    elif not declared_distinct:
        status = "NOT_DISTINCT"
        rationale = "The two paths do not declare different method families and source identities."
    elif within:
        status = "AGREES_WITHIN_TOLERANCE"
        rationale = "The two declared-distinct paths agree within the registered tolerance."
    else:
        status = "DISAGREES"
        rationale = "The two declared-distinct paths differ by more than the registered tolerance."

    stable = {
        "schema": "physical-lab-cross-check-evaluation-v1",
        "cross_check_id": cross_check_id,
        "cross_check_sha256": record.get("cross_check_sha256"),
        "status": status,
        "observable": record.get("observable"),
        "primary_value": primary_value,
        "comparison_value": comparison_value,
        "unit": record.get("unit"),
        "absolute_difference": absolute_difference,
        "relative_difference": relative_difference,
        "tolerance": tolerance,
        "tolerance_mode": tolerance_mode,
        "declared_distinct": declared_distinct,
        "reference_checks": reference_checks,
    }
    return {
        **stable,
        "evaluation_sha256": _sha(stable),
        "rationale": rationale,
        "missing_references": missing,
        "stale_references": stale,
        "boundary": (
            "AGREES_WITHIN_TOLERANCE is corroborating evidence only. It does not establish scientific truth, "
            "validation, certification, or actual independence of the two methods."
        ),
    }


def cross_check_matrix(project_dir: str | Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    rows = []
    for item in list_cross_checks(path):
        cid = str(item.get("cross_check_id") or "")
        if not cid:
            continue
        record = get_cross_check(path, cid)
        evaluation = evaluate_cross_check(path, cid)
        rows.append({
            "cross_check_id": cid,
            "name": record.get("name"),
            "observable": record.get("observable"),
            "status": evaluation.get("status"),
            "absolute_difference": evaluation.get("absolute_difference"),
            "relative_difference": evaluation.get("relative_difference"),
            "tolerance": record.get("tolerance"),
            "tolerance_mode": record.get("tolerance_mode"),
            "evaluation_sha256": evaluation.get("evaluation_sha256"),
        })
    stable = {"schema": "physical-lab-cross-check-matrix-v1", "project_id": project.get("project_id"), "cross_checks": rows}
    return {
        **stable,
        "matrix_sha256": _sha(stable),
        "status_counts": {status: sum(1 for row in rows if row.get("status") == status) for status in CROSS_CHECK_STATUSES},
        "boundary": "Cross-check status summarizes evidence-linked numerical agreement, not scientific truth or certification.",
    }
