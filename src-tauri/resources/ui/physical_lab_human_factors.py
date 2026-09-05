"""Evidence-linked human-factors and operator-workflow studies for Physical Lab.

The module stores descriptive task observations linked to explicit Project evidence.
It is designed for pseudonymous/anonymous session labels and intentionally avoids
collecting personal identity data. Outputs describe observed task performance and
evidence freshness only; they are not usability certification, safety approval,
medical/fitness assessment, or a judgment about a person's ability.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
from pathlib import Path
from typing import Any, Mapping

import physical_lab_claims as claims
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import plain, utc_now

SCHEMA = "physical-lab-human-factors-study-v1"
INDEX_SCHEMA = "physical-lab-human-factors-study-index-v1"
VERSION = 1
EVIDENCE_STATES = ("CURRENT", "STALE", "EVIDENCE_MISSING")
COMPLETION_STATES = ("COMPLETED", "NOT_COMPLETED")


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


def _finite(value: Any, label: str) -> float:
    try:
        out = float(value)
    except Exception as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(out):
        raise ValueError(f"{label} must be finite")
    return out


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative integer")
    try:
        out = int(value)
    except Exception as exc:
        raise ValueError(f"{label} must be a non-negative integer") from exc
    if out < 0 or float(out) != float(value):
        raise ValueError(f"{label} must be a non-negative integer")
    return out


def _normalize_refs(references: Any) -> list[dict[str, str]]:
    if not isinstance(references, list):
        raise ValueError("references must be a list")
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in references:
        if not isinstance(item, Mapping):
            raise ValueError("each evidence reference must be an object")
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
    if not rows:
        raise ValueError("at least one explicit Project evidence reference is required")
    rows.sort(key=lambda row: (row["kind"], row["id"]))
    return rows


def _resolve_refs(project_dir: Path, project: Mapping[str, Any], owner_id: str, references: list[Mapping[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ref in references:
        resolved = claims._resolve_reference(project_dir, project, str(ref["kind"]), str(ref["id"]))
        if resolved is None:
            raise ValueError(f"evidence reference does not exist: {ref['kind']}:{ref['id']}")
        rows.append({"owner_id": owner_id, **resolved})
    return rows


def _evidence_checks(
    project_dir: Path,
    project: Mapping[str, Any],
    snapshots: list[Mapping[str, Any]],
    observations: list[Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[str], list[str]]:
    snapshot_map = {
        (str(row.get("owner_id")), str(row.get("kind")), str(row.get("id"))): row
        for row in snapshots
        if isinstance(row, Mapping)
    }
    checks: list[dict[str, Any]] = []
    missing: list[str] = []
    stale: list[str] = []
    for observation in observations:
        owner_id = str(observation.get("observation_id") or "")
        for ref in observation.get("references") or []:
            kind = str(ref.get("kind") or "")
            ref_id = str(ref.get("id") or "")
            key = f"{owner_id}:{kind}:{ref_id}"
            current = claims._resolve_reference(project_dir, project, kind, ref_id)
            snapshot = snapshot_map.get((owner_id, kind, ref_id))
            if current is None:
                missing.append(key)
                checks.append({"reference": key, "state": "EVIDENCE_MISSING", "snapshot_sha256": (snapshot or {}).get("sha256"), "current_sha256": None})
                continue
            is_stale = bool(snapshot and str(snapshot.get("sha256") or "") != str(current.get("sha256") or ""))
            if is_stale:
                stale.append(key)
            checks.append({
                "reference": key,
                "state": "STALE" if is_stale else "CURRENT",
                "snapshot_sha256": (snapshot or {}).get("sha256"),
                "current_sha256": current.get("sha256"),
            })
    state = "EVIDENCE_MISSING" if missing else ("STALE" if stale else "CURRENT")
    return state, checks, missing, stale


def _root(project_dir: Path) -> Path:
    root = project_dir / "provenance" / "human-factors"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalize_observations(observations: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(observations, list) or not observations:
        raise ValueError("observations must contain at least one row")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(observations, start=1):
        if not isinstance(item, Mapping):
            raise ValueError("each human-factors observation must be an object")
        observation_id = str(item.get("observation_id") or f"hfobs-{index:04d}").strip()
        if not observation_id or observation_id in seen:
            raise ValueError("observation_id values must be non-empty and unique")
        seen.add(observation_id)
        task_id = str(item.get("task_id") or "").strip()
        task_name = str(item.get("task_name") or task_id).strip()
        if not task_id or not task_name:
            raise ValueError(f"{observation_id}.task_id and task_name are required")
        completion_state = str(item.get("completion_state") or "").strip().upper()
        if completion_state not in COMPLETION_STATES:
            raise ValueError(f"{observation_id}.completion_state must be one of {COMPLETION_STATES}")
        completion_time = item.get("completion_time_s")
        if completion_time in (None, ""):
            completion_time_s = None
        else:
            completion_time_s = _finite(completion_time, f"{observation_id}.completion_time_s")
            if completion_time_s < 0:
                raise ValueError(f"{observation_id}.completion_time_s must be non-negative")
        ease_rating = item.get("ease_rating_1_to_7")
        if ease_rating in (None, ""):
            rating = None
        else:
            rating = _finite(ease_rating, f"{observation_id}.ease_rating_1_to_7")
            if not 1.0 <= rating <= 7.0:
                raise ValueError(f"{observation_id}.ease_rating_1_to_7 must be in [1, 7]")
        session_label = str(item.get("session_label") or "").strip()
        if any(token in session_label.lower() for token in ("@", "email:", "phone:")):
            raise ValueError("session_label must be pseudonymous and must not contain contact information")
        rows.append({
            "observation_id": observation_id,
            "session_label": session_label,
            "task_id": task_id,
            "task_name": task_name,
            "completion_state": completion_state,
            "completion_time_s": completion_time_s,
            "error_count": _nonnegative_int(item.get("error_count", 0), f"{observation_id}.error_count"),
            "assistance_count": _nonnegative_int(item.get("assistance_count", 0), f"{observation_id}.assistance_count"),
            "ease_rating_1_to_7": rating,
            "references": _normalize_refs(item.get("references")),
            "notes": str(item.get("notes") or ""),
        })
    return rows


def register_human_factors_study(
    project_dir: str | Path,
    *,
    name: str,
    system_context: str,
    observations: list[Mapping[str, Any]],
    intended_use: str = "",
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    name = str(name).strip()
    system_context = str(system_context).strip()
    if not name or not system_context:
        raise ValueError("study name and system_context are required")
    normalized = _normalize_observations(observations)
    snapshots: list[dict[str, Any]] = []
    for row in normalized:
        snapshots.extend(_resolve_refs(path, project, row["observation_id"], row["references"]))
    identity = {
        "project_id": project.get("project_id"),
        "name": name,
        "system_context": system_context,
        "observations": normalized,
        "intended_use": str(intended_use),
    }
    study_id = "hf-" + _sha(identity)[:20]
    record = {
        "schema": SCHEMA,
        "version": VERSION,
        "study_id": study_id,
        "project_id": project.get("project_id"),
        "name": name,
        "system_context": system_context,
        "observations": normalized,
        "evidence_snapshots": snapshots,
        "intended_use": str(intended_use),
        "notes": str(notes),
        "privacy_boundary": "Use anonymous or pseudonymous session labels only. Do not store names, email addresses, phone numbers, account identifiers, medical information, or other direct personal identifiers in this study layer.",
        "boundary": "Descriptive human-factors/operator-workflow evidence only. No usability certification, operator fitness judgment, health diagnosis, ergonomic safety approval, accessibility compliance, product qualification, or standards-compliance verdict is generated.",
        "created_at": utc_now(),
    }
    record["study_sha256"] = _sha({k: v for k, v in record.items() if k not in {"created_at", "study_sha256"}})
    out = _root(path) / f"{study_id}.json"
    if not out.exists():
        _atomic_json(out, record)
    _write_index(path)
    return _read_json(out) or record


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "sample_std": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "median": statistics.median(values),
        "sample_std": statistics.stdev(values) if len(values) > 1 else None,
        "min": min(values),
        "max": max(values),
    }


def evaluate_human_factors_study(project_dir: str | Path, study_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    record = _read_json(_root(path) / f"{study_id}.json")
    if not record or record.get("schema") != SCHEMA:
        raise ValueError(f"unknown human-factors study: {study_id}")
    observations = [row for row in record.get("observations") or [] if isinstance(row, Mapping)]
    state, checks, missing, stale = _evidence_checks(path, project, record.get("evidence_snapshots") or [], observations)
    completed = [row for row in observations if row.get("completion_state") == "COMPLETED"]
    timed = [float(row["completion_time_s"]) for row in completed if row.get("completion_time_s") is not None]
    ratings = [float(row["ease_rating_1_to_7"]) for row in observations if row.get("ease_rating_1_to_7") is not None]

    task_rows: list[dict[str, Any]] = []
    for task_id in sorted({str(row.get("task_id")) for row in observations}):
        group = [row for row in observations if str(row.get("task_id")) == task_id]
        group_completed = [row for row in group if row.get("completion_state") == "COMPLETED"]
        group_times = [float(row["completion_time_s"]) for row in group_completed if row.get("completion_time_s") is not None]
        group_ratings = [float(row["ease_rating_1_to_7"]) for row in group if row.get("ease_rating_1_to_7") is not None]
        task_rows.append({
            "task_id": task_id,
            "task_name": str(group[0].get("task_name") or task_id),
            "observation_count": len(group),
            "completion_fraction": len(group_completed) / len(group),
            "completion_time_s": _summary(group_times),
            "total_errors": sum(int(row.get("error_count") or 0) for row in group),
            "errors_per_observation": sum(int(row.get("error_count") or 0) for row in group) / len(group),
            "total_assistance": sum(int(row.get("assistance_count") or 0) for row in group),
            "assistance_per_observation": sum(int(row.get("assistance_count") or 0) for row in group) / len(group),
            "ease_rating_1_to_7": _summary(group_ratings),
        })

    result = {
        "schema": "physical-lab-human-factors-evaluation-v1",
        "study_id": record.get("study_id"),
        "name": record.get("name"),
        "system_context": record.get("system_context"),
        "evidence_state": state,
        "evidence_checks": checks,
        "missing_references": missing,
        "stale_references": stale,
        "observation_count": len(observations),
        "task_count": len(task_rows),
        "completed_count": len(completed),
        "completion_fraction": len(completed) / len(observations) if observations else None,
        "completion_time_s": _summary(timed),
        "total_errors": sum(int(row.get("error_count") or 0) for row in observations),
        "errors_per_observation": sum(int(row.get("error_count") or 0) for row in observations) / len(observations) if observations else None,
        "total_assistance": sum(int(row.get("assistance_count") or 0) for row in observations),
        "assistance_per_observation": sum(int(row.get("assistance_count") or 0) for row in observations) / len(observations) if observations else None,
        "ease_rating_1_to_7": _summary(ratings),
        "task_summaries": task_rows,
        "privacy_boundary": record.get("privacy_boundary"),
        "boundary": record.get("boundary"),
    }
    result["evaluation_sha256"] = _sha({k: v for k, v in result.items() if k != "evaluation_sha256"})
    return result


def _write_index(project_dir: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in sorted(_root(project_dir).glob("hf-*.json")):
        record = _read_json(path)
        if not record or record.get("schema") != SCHEMA:
            continue
        try:
            evaluation = evaluate_human_factors_study(project_dir, str(record.get("study_id")))
            evidence_state = evaluation.get("evidence_state")
        except Exception:
            evidence_state = "EVIDENCE_MISSING"
        rows.append({
            "study_id": record.get("study_id"),
            "name": record.get("name"),
            "system_context": record.get("system_context"),
            "observation_count": len(record.get("observations") or []),
            "evidence_state": evidence_state,
            "created_at": record.get("created_at"),
        })
    index = {
        "schema": INDEX_SCHEMA,
        "version": VERSION,
        "studies": rows,
    }
    index["index_sha256"] = _sha({"schema": INDEX_SCHEMA, "version": VERSION, "studies": rows})
    _atomic_json(_root(project_dir) / "index.json", index)
    return index


def human_factors_matrix(project_dir: str | Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    index = _write_index(path)
    result = {
        "schema": "physical-lab-human-factors-matrix-v1",
        "project_path": str(path),
        "studies": index.get("studies") or [],
        "privacy_boundary": "Human-factors studies use anonymous/pseudonymous session labels only; direct personal identifiers and medical information are outside this layer.",
        "boundary": "Human-factors summaries are descriptive evidence, not a usability score, operator ranking, fitness assessment, ergonomic certification, safety approval, accessibility-compliance verdict, or proof of causal human performance effects.",
    }
    result["matrix_sha256"] = _sha({k: v for k, v in result.items() if k != "matrix_sha256"})
    return result
