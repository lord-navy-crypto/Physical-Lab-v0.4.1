"""Evidence-linked requirements and verification planning for Physical Lab Projects.

The layer stores normative engineering requirements, declared verification plans,
explicit Project evidence references, evidence freshness, and human review notes.
It does not automatically declare a requirement verified, compliant, accepted,
qualified, certified, safe, or validated for stakeholder use.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

import physical_lab_claims as claims
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import plain, utc_now

REQUIREMENT_SCHEMA = "physical-lab-requirement-verification-plan-v1"
INDEX_SCHEMA = "physical-lab-requirement-verification-index-v1"
VERSION = 1
VERIFICATION_METHODS = ("test", "analysis", "inspection", "demonstration")
EVIDENCE_STATES = ("READY_FOR_REVIEW", "STALE", "EVIDENCE_MISSING")
REVIEW_OUTCOMES = (
    "EVIDENCE_SUFFICIENT_FOR_PROJECT_REVIEW",
    "MORE_EVIDENCE_NEEDED",
    "PLAN_REVISION_NEEDED",
)
BOUNDARY = (
    "Requirements & Verification Planning records declared requirements, methods, "
    "traceability identifiers, evidence freshness and human review notes only. "
    "It does not automatically establish requirement compliance, verification, "
    "validation, qualification, acceptance, safety approval, standards compliance, "
    "or certification."
)


def _sha(value: Any) -> str:
    raw = json.dumps(
        plain(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
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
    temp.write_text(
        json.dumps(plain(dict(value)), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp, path)


def _root(project_dir: Path) -> Path:
    root = project_dir / "provenance" / "requirements-verification"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _index_path(project_dir: Path) -> Path:
    return _root(project_dir) / "index.json"


def _load_index(project_dir: Path) -> dict[str, Any]:
    doc = _read_json(_index_path(project_dir))
    if not doc or doc.get("schema") != INDEX_SCHEMA:
        return {"schema": INDEX_SCHEMA, "version": VERSION, "requirements": {}}
    requirements = doc.get("requirements")
    if not isinstance(requirements, dict):
        doc["requirements"] = {}
    return doc


def _save_index(project_dir: Path, doc: Mapping[str, Any]) -> None:
    _atomic_json(_index_path(project_dir), doc)


def _normalize_refs(references: Any) -> list[dict[str, str]]:
    if references in (None, ""):
        return []
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
    rows.sort(key=lambda row: (row["kind"], row["id"]))
    return rows


def _normalize_ids(values: Any) -> list[str]:
    if values in (None, ""):
        return []
    if not isinstance(values, list):
        raise ValueError("upstream_requirement_ids must be a list")
    rows = sorted({str(value).strip() for value in values if str(value).strip()})
    return rows


def _resolve_snapshots(
    project_dir: Path,
    project: Mapping[str, Any],
    references: list[Mapping[str, str]],
) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for ref in references:
        kind = str(ref.get("kind") or "")
        ref_id = str(ref.get("id") or "")
        resolved = claims._resolve_reference(project_dir, project, kind, ref_id)
        if resolved is None:
            raise ValueError(f"evidence reference does not exist: {kind}:{ref_id}")
        snapshots.append(resolved)
    return snapshots


def _check_evidence(
    project_dir: Path,
    project: Mapping[str, Any],
    references: list[Mapping[str, str]],
    snapshots: list[Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[str], list[str]]:
    if not references:
        return "EVIDENCE_MISSING", [], ["no-explicit-evidence-reference"], []

    snapshot_map = {
        (str(row.get("kind") or ""), str(row.get("id") or "")): row
        for row in snapshots
        if isinstance(row, Mapping)
    }
    checks: list[dict[str, Any]] = []
    missing: list[str] = []
    stale: list[str] = []
    for ref in references:
        kind = str(ref.get("kind") or "")
        ref_id = str(ref.get("id") or "")
        key = f"{kind}:{ref_id}"
        current = claims._resolve_reference(project_dir, project, kind, ref_id)
        snapshot = snapshot_map.get((kind, ref_id))
        if current is None:
            missing.append(key)
            checks.append(
                {
                    "reference": key,
                    "state": "EVIDENCE_MISSING",
                    "snapshot_sha256": (snapshot or {}).get("sha256"),
                    "current_sha256": None,
                }
            )
            continue
        is_stale = bool(
            snapshot
            and str(snapshot.get("sha256") or "")
            != str(current.get("sha256") or "")
        )
        if is_stale:
            stale.append(key)
        checks.append(
            {
                "reference": key,
                "state": "STALE" if is_stale else "CURRENT",
                "snapshot_sha256": (snapshot or {}).get("sha256"),
                "current_sha256": current.get("sha256"),
            }
        )
    state = "EVIDENCE_MISSING" if missing else ("STALE" if stale else "READY_FOR_REVIEW")
    return state, checks, missing, stale


def _requirement_path(project_dir: Path, requirement_id: str) -> Path:
    return _root(project_dir) / f"{requirement_id}.json"


def _load_requirement(project_dir: Path, requirement_id: str) -> dict[str, Any]:
    doc = _read_json(_requirement_path(project_dir, requirement_id))
    if not doc or doc.get("schema") != REQUIREMENT_SCHEMA:
        raise ValueError(f"requirement plan not found: {requirement_id}")
    return doc


def _contains_shall(statement: str) -> bool:
    return bool(re.search(r"\bshall\b", statement, flags=re.IGNORECASE))


def register_requirement(
    project_dir: str | Path,
    *,
    requirement_id: str,
    statement: str,
    verification_method: str,
    verification_activity: str,
    success_criteria: str,
    references: list[Mapping[str, Any]] | None = None,
    source_document: str = "",
    source_locator: str = "",
    rationale: str = "",
    level: str = "system",
    owner: str = "",
    upstream_requirement_ids: list[str] | None = None,
    intended_use: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)

    req_id = str(requirement_id).strip()
    if not req_id:
        raise ValueError("requirement_id is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,95}", req_id):
        raise ValueError("requirement_id contains unsupported characters")

    text = str(statement).strip()
    if not text:
        raise ValueError("requirement statement is required")
    if not _contains_shall(text):
        raise ValueError("verification-matrix requirements must contain the normative keyword 'shall'")

    method = str(verification_method).strip().lower()
    if method not in VERIFICATION_METHODS:
        raise ValueError(f"verification_method must be one of {VERIFICATION_METHODS}")
    activity = str(verification_activity).strip()
    criteria = str(success_criteria).strip()
    if not activity:
        raise ValueError("verification_activity is required")
    if not criteria:
        raise ValueError("success_criteria is required")

    refs = _normalize_refs(references)
    snapshots = _resolve_snapshots(path, project, refs) if refs else []
    upstream = _normalize_ids(upstream_requirement_ids)

    identity = {
        "project_id": project.get("project_id"),
        "requirement_id": req_id,
        "statement": text,
        "verification_method": method,
        "verification_activity": activity,
        "success_criteria": criteria,
        "source_document": str(source_document).strip(),
        "source_locator": str(source_locator).strip(),
        "rationale": str(rationale).strip(),
        "level": str(level).strip() or "system",
        "owner": str(owner).strip(),
        "upstream_requirement_ids": upstream,
        "intended_use": str(intended_use).strip(),
        "references": refs,
    }
    requirement_sha = _sha(identity)
    existing_path = _requirement_path(path, req_id)
    existing = _read_json(existing_path)
    review_history = []
    registered_at = utc_now()
    if existing and existing.get("schema") == REQUIREMENT_SCHEMA:
        review_history = list(existing.get("review_history") or [])
        registered_at = str(existing.get("registered_at") or registered_at)

    record = {
        "schema": REQUIREMENT_SCHEMA,
        "version": VERSION,
        **identity,
        "normative_keyword": "shall",
        "evidence_snapshots": snapshots,
        "review_history": review_history,
        "registered_at": registered_at,
        "updated_at": utc_now(),
        "requirement_sha256": requirement_sha,
        "boundary": BOUNDARY,
    }
    _atomic_json(existing_path, record)

    index = _load_index(path)
    index["requirements"][req_id] = {
        "requirement_id": req_id,
        "statement": text,
        "verification_method": method,
        "source_document": identity["source_document"],
        "level": identity["level"],
        "requirement_sha256": requirement_sha,
        "file": existing_path.name,
        "updated_at": record["updated_at"],
    }
    index["updated_at"] = record["updated_at"]
    _save_index(path, index)
    return record


def evaluate_requirement(project_dir: str | Path, requirement_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    record = _load_requirement(path, str(requirement_id))
    references = list(record.get("references") or [])
    snapshots = list(record.get("evidence_snapshots") or [])
    state, checks, missing, stale = _check_evidence(path, project, references, snapshots)
    reviews = list(record.get("review_history") or [])
    latest_review = reviews[-1] if reviews else None
    payload = {
        "schema": "physical-lab-requirement-verification-evaluation-v1",
        "version": VERSION,
        "requirement_id": record.get("requirement_id"),
        "statement": record.get("statement"),
        "normative_keyword": record.get("normative_keyword"),
        "source_document": record.get("source_document"),
        "source_locator": record.get("source_locator"),
        "rationale": record.get("rationale"),
        "level": record.get("level"),
        "owner": record.get("owner"),
        "upstream_requirement_ids": record.get("upstream_requirement_ids") or [],
        "verification_method": record.get("verification_method"),
        "verification_activity": record.get("verification_activity"),
        "success_criteria": record.get("success_criteria"),
        "intended_use": record.get("intended_use"),
        "evidence_state": state,
        "evidence_checks": checks,
        "missing_references": missing,
        "stale_references": stale,
        "reference_count": len(references),
        "latest_human_review": latest_review,
        "requirement_sha256": record.get("requirement_sha256"),
        "boundary": BOUNDARY,
    }
    payload["evaluation_sha256"] = _sha(payload)
    return payload


def record_requirement_review(
    project_dir: str | Path,
    requirement_id: str,
    *,
    outcome: str,
    rationale: str,
    reviewer: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    record = _load_requirement(path, str(requirement_id))
    normalized_outcome = str(outcome).strip().upper()
    if normalized_outcome not in REVIEW_OUTCOMES:
        raise ValueError(f"outcome must be one of {REVIEW_OUTCOMES}")
    reason = str(rationale).strip()
    if not reason:
        raise ValueError("human review rationale is required")

    evaluation = evaluate_requirement(path, str(requirement_id))
    if (
        normalized_outcome == "EVIDENCE_SUFFICIENT_FOR_PROJECT_REVIEW"
        and evaluation.get("evidence_state") != "READY_FOR_REVIEW"
    ):
        raise ValueError("evidence cannot be marked sufficient for project review while missing or stale")

    review = {
        "review_id": f"review-{_sha({'requirement_id': requirement_id, 'outcome': normalized_outcome, 'rationale': reason, 'reviewer': reviewer, 'at': utc_now()})[:20]}",
        "outcome": normalized_outcome,
        "rationale": reason,
        "reviewer": str(reviewer).strip(),
        "evidence_state_at_review": evaluation.get("evidence_state"),
        "evaluation_sha256_at_review": evaluation.get("evaluation_sha256"),
        "reviewed_at": utc_now(),
        "boundary": (
            "This is a human project review note about evidence sufficiency or plan revision. "
            "It is not an automatic or formal declaration that the requirement is verified, "
            "compliant, accepted, qualified, certified, safe, or stakeholder-validated."
        ),
    }
    history = list(record.get("review_history") or [])
    history.append(review)
    record["review_history"] = history
    record["updated_at"] = utc_now()
    _atomic_json(_requirement_path(path, str(requirement_id)), record)

    index = _load_index(path)
    if str(requirement_id) in index.get("requirements", {}):
        index["requirements"][str(requirement_id)]["updated_at"] = record["updated_at"]
        index["requirements"][str(requirement_id)]["latest_review_outcome"] = normalized_outcome
        index["updated_at"] = record["updated_at"]
        _save_index(path, index)
    return review


def requirements_verification_matrix(project_dir: str | Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    index = _load_index(path)
    rows: list[dict[str, Any]] = []
    for req_id in sorted(index.get("requirements", {})):
        try:
            evaluation = evaluate_requirement(path, req_id)
        except Exception as exc:
            rows.append(
                {
                    "requirement_id": req_id,
                    "evidence_state": "EVIDENCE_MISSING",
                    "error": str(exc),
                }
            )
            continue
        latest = evaluation.get("latest_human_review") or {}
        rows.append(
            {
                "requirement_id": req_id,
                "statement": evaluation.get("statement"),
                "source_document": evaluation.get("source_document"),
                "source_locator": evaluation.get("source_locator"),
                "level": evaluation.get("level"),
                "verification_method": evaluation.get("verification_method"),
                "verification_activity": evaluation.get("verification_activity"),
                "success_criteria": evaluation.get("success_criteria"),
                "upstream_requirement_ids": evaluation.get("upstream_requirement_ids") or [],
                "evidence_state": evaluation.get("evidence_state"),
                "reference_count": evaluation.get("reference_count"),
                "latest_review_outcome": latest.get("outcome"),
                "requirement_sha256": evaluation.get("requirement_sha256"),
                "evaluation_sha256": evaluation.get("evaluation_sha256"),
            }
        )
    matrix = {
        "schema": "physical-lab-requirements-verification-matrix-v1",
        "version": VERSION,
        "requirements": rows,
        "requirement_count": len(rows),
        "verification_methods": list(VERIFICATION_METHODS),
        "boundary": BOUNDARY,
    }
    matrix["matrix_sha256"] = _sha(matrix)
    return matrix
