"""Project-local requirements traceability for Physical Lab.

Requirements link source/flowdown metadata, planned verification methods,
explicit evidence, and engineering records by deterministic fingerprints.
The resulting states describe planning/readiness/freshness for human review;
they never constitute a machine verification, validation, compliance, safety,
or certification verdict.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import physical_lab_claims as claims
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import plain, utc_now

REQUIREMENT_SCHEMA = "physical-lab-requirement-v1"
REQUIREMENT_INDEX_SCHEMA = "physical-lab-requirement-index-v1"
REQUIREMENT_VERSION = 1
VERIFICATION_METHODS = ("analysis", "inspection", "demonstration", "test", "other")
REVIEW_STATES = ("UNPLANNED", "EVIDENCE_MISSING", "LINK_MISSING", "STALE", "READY_FOR_REVIEW")
ENGINEERING_LINK_KINDS = (
    "claim",
    "cross-check",
    "decision-study",
    "operations-plan",
    "quality-study",
    "reliability-study",
    "risk-study",
    "economics-study",
)


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
    root = project_dir / "provenance" / "requirements"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _index_path(project_dir: Path) -> Path:
    return _root(project_dir) / "index.json"


def _load_index(project_dir: Path) -> dict[str, Any]:
    existing = _read_json(_index_path(project_dir))
    if existing and existing.get("schema") == REQUIREMENT_INDEX_SCHEMA:
        return existing
    return {"schema": REQUIREMENT_INDEX_SCHEMA, "requirements": {}, "updated_at": None}


def _normalize_evidence_refs(references: list[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in references or []:
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


def _normalize_engineering_links(links: list[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in links or []:
        if not isinstance(item, Mapping):
            raise ValueError("each engineering link must be an object")
        kind = str(item.get("kind") or "").strip().lower()
        ref_id = str(item.get("id") or "").strip()
        if kind not in ENGINEERING_LINK_KINDS:
            raise ValueError(f"unsupported engineering link kind: {kind!r}")
        if not ref_id:
            raise ValueError("engineering link id is required")
        key = (kind, ref_id)
        if key not in seen:
            rows.append({"kind": kind, "id": ref_id})
            seen.add(key)
    rows.sort(key=lambda row: (row["kind"], row["id"]))
    return rows


def _resolve_engineering_link(project_dir: Path, kind: str, ref_id: str) -> dict[str, Any] | None:
    try:
        if kind == "claim":
            import physical_lab_claims as module
            value = module.get_claim(project_dir, ref_id)
            digest = value.get("claim_sha256")
            label = value.get("statement")
        elif kind == "cross-check":
            import physical_lab_cross_checks as module
            value = module.get_cross_check(project_dir, ref_id)
            digest = value.get("cross_check_sha256")
            label = value.get("name")
        elif kind == "decision-study":
            import physical_lab_engineering_decisions as module
            value = module.get_decision_study(project_dir, ref_id)
            digest = value.get("study_sha256")
            label = value.get("name")
        elif kind == "operations-plan":
            import physical_lab_operations_planning as module
            value = module.get_operations_plan(project_dir, ref_id)
            digest = value.get("plan_sha256")
            label = value.get("name")
        elif kind == "quality-study":
            import physical_lab_quality_reliability as module
            value = module.get_quality_study(project_dir, ref_id)
            digest = value.get("study_sha256")
            label = value.get("name")
        elif kind == "reliability-study":
            import physical_lab_quality_reliability as module
            value = module.get_reliability_study(project_dir, ref_id)
            digest = value.get("study_sha256")
            label = value.get("name")
        elif kind == "risk-study":
            import physical_lab_risk_economics as module
            value = module.get_risk_study(project_dir, ref_id)
            digest = value.get("study_sha256")
            label = value.get("name")
        elif kind == "economics-study":
            import physical_lab_risk_economics as module
            value = module.get_economics_study(project_dir, ref_id)
            digest = value.get("study_sha256")
            label = value.get("name")
        else:
            return None
    except Exception:
        return None
    return {"kind": kind, "id": ref_id, "sha256": str(digest or _sha(value)), "label": label}


def get_requirement(project_dir: str | Path, requirement_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    value = _read_json(_root(path) / f"{requirement_id}.json")
    if not value or value.get("schema") != REQUIREMENT_SCHEMA:
        raise ValueError(f"unknown requirement_id: {requirement_id}")
    return value


def list_requirements(project_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    rows = [dict(value) for value in (_load_index(path).get("requirements") or {}).values() if isinstance(value, Mapping)]
    rows.sort(key=lambda row: (str(row.get("requirement_key") or ""), str(row.get("requirement_id") or "")))
    return rows


def _requirement_key_map(project_dir: Path) -> dict[str, str]:
    return {
        str(row.get("requirement_key")): str(row.get("requirement_id"))
        for row in list_requirements(project_dir)
        if str(row.get("requirement_key") or "") and str(row.get("requirement_id") or "")
    }


def _parent_snapshots(project_dir: Path, parent_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for parent_id in parent_ids:
        parent = get_requirement(project_dir, parent_id)
        rows.append({
            "requirement_id": parent_id,
            "requirement_key": parent.get("requirement_key"),
            "sha256": parent.get("requirement_sha256") or _sha(parent),
        })
    return rows


def register_requirement(
    project_dir: str | Path,
    *,
    requirement_key: str,
    statement: str,
    source: str,
    level: str = "system",
    parent_requirement_ids: list[str] | None = None,
    verification_method: str = "",
    verification_criteria: str = "",
    evidence_references: list[Mapping[str, Any]] | None = None,
    engineering_links: list[Mapping[str, Any]] | None = None,
    rationale: str = "",
    intended_use: str = "",
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    key = str(requirement_key).strip()
    statement = str(statement).strip()
    source = str(source).strip()
    level = str(level).strip() or "system"
    if not key or not statement or not source:
        raise ValueError("requirement_key, statement, and source are required")
    existing_keys = _requirement_key_map(path)
    if key in existing_keys:
        raise ValueError(f"requirement_key already exists: {key}")

    method = str(verification_method).strip().lower()
    if method and method not in VERIFICATION_METHODS:
        raise ValueError(f"verification_method must be blank or one of {VERIFICATION_METHODS}")
    criteria = str(verification_criteria).strip()
    parents = sorted({str(value).strip() for value in (parent_requirement_ids or []) if str(value).strip()})
    for parent_id in parents:
        get_requirement(path, parent_id)
    evidence_refs = _normalize_evidence_refs(evidence_references)
    links = _normalize_engineering_links(engineering_links)

    evidence_snapshot: list[dict[str, Any]] = []
    for ref in evidence_refs:
        resolved = claims._resolve_reference(path, project, ref["kind"], ref["id"])
        if resolved is None:
            raise ValueError(f"evidence reference does not exist: {ref['kind']}:{ref['id']}")
        evidence_snapshot.append(resolved)

    engineering_snapshot: list[dict[str, Any]] = []
    for link in links:
        resolved = _resolve_engineering_link(path, link["kind"], link["id"])
        if resolved is None:
            raise ValueError(f"engineering link does not exist: {link['kind']}:{link['id']}")
        engineering_snapshot.append(resolved)

    parent_snapshot = _parent_snapshots(path, parents)
    identity = {
        "project_id": project.get("project_id"),
        "requirement_key": key,
        "statement": statement,
        "source": source,
        "level": level,
        "parent_requirement_ids": parents,
        "verification_method": method,
        "verification_criteria": criteria,
        "evidence_references": evidence_refs,
        "engineering_links": links,
        "rationale": str(rationale).strip(),
        "intended_use": str(intended_use).strip(),
    }
    requirement_id = f"req-{_sha(identity)[:20]}"
    now = utc_now()
    record = {
        "schema": REQUIREMENT_SCHEMA,
        "requirement_version": REQUIREMENT_VERSION,
        "requirement_id": requirement_id,
        **identity,
        "evidence_snapshot": evidence_snapshot,
        "engineering_snapshot": engineering_snapshot,
        "parent_snapshot": parent_snapshot,
        "registered_at": now,
        "updated_at": now,
        "notes": str(notes),
        "boundary": (
            "This record supports requirements planning and traceability. READY_FOR_REVIEW means the declared verification plan and linked evidence are present/current; "
            "it does not mean the requirement is verified, validated, compliant, safe, accepted, or certified."
        ),
    }
    stable_keys = (
        "schema", "requirement_version", "requirement_id", "project_id", "requirement_key", "statement", "source", "level",
        "parent_requirement_ids", "verification_method", "verification_criteria", "evidence_references", "engineering_links",
        "rationale", "intended_use", "evidence_snapshot", "engineering_snapshot", "parent_snapshot",
    )
    record["requirement_sha256"] = _sha({key_name: record[key_name] for key_name in stable_keys})
    _atomic_json(_root(path) / f"{requirement_id}.json", record)
    index = _load_index(path)
    index.setdefault("requirements", {})[requirement_id] = {
        "requirement_id": requirement_id,
        "requirement_key": key,
        "statement": statement,
        "source": source,
        "level": level,
        "requirement_sha256": record["requirement_sha256"],
        "path": f"provenance/requirements/{requirement_id}.json",
        "updated_at": now,
    }
    index["updated_at"] = now
    _atomic_json(_index_path(path), index)
    return record


def evaluate_requirement(project_dir: str | Path, requirement_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    record = get_requirement(path, requirement_id)

    evidence_snapshots = {
        (str(row.get("kind")), str(row.get("id"))): row
        for row in record.get("evidence_snapshot") or []
        if isinstance(row, Mapping)
    }
    evidence_checks: list[dict[str, Any]] = []
    evidence_missing: list[str] = []
    evidence_stale: list[str] = []
    for ref in record.get("evidence_references") or []:
        kind = str(ref.get("kind") or "")
        ref_id = str(ref.get("id") or "")
        current = claims._resolve_reference(path, project, kind, ref_id)
        snapshot = evidence_snapshots.get((kind, ref_id))
        key = f"{kind}:{ref_id}"
        if current is None:
            evidence_missing.append(key)
            evidence_checks.append({"reference": key, "state": "MISSING", "snapshot_sha256": (snapshot or {}).get("sha256"), "current_sha256": None})
            continue
        is_stale = bool(snapshot and str(snapshot.get("sha256") or "") != str(current.get("sha256") or ""))
        if is_stale:
            evidence_stale.append(key)
        evidence_checks.append({
            "reference": key,
            "state": "STALE" if is_stale else "CURRENT",
            "snapshot_sha256": (snapshot or {}).get("sha256"),
            "current_sha256": current.get("sha256"),
        })

    engineering_snapshots = {
        (str(row.get("kind")), str(row.get("id"))): row
        for row in record.get("engineering_snapshot") or []
        if isinstance(row, Mapping)
    }
    engineering_checks: list[dict[str, Any]] = []
    link_missing: list[str] = []
    link_stale: list[str] = []
    for link in record.get("engineering_links") or []:
        kind = str(link.get("kind") or "")
        ref_id = str(link.get("id") or "")
        key = f"{kind}:{ref_id}"
        current = _resolve_engineering_link(path, kind, ref_id)
        snapshot = engineering_snapshots.get((kind, ref_id))
        if current is None:
            link_missing.append(key)
            engineering_checks.append({"reference": key, "state": "MISSING", "snapshot_sha256": (snapshot or {}).get("sha256"), "current_sha256": None})
            continue
        is_stale = bool(snapshot and str(snapshot.get("sha256") or "") != str(current.get("sha256") or ""))
        if is_stale:
            link_stale.append(key)
        engineering_checks.append({
            "reference": key,
            "state": "STALE" if is_stale else "CURRENT",
            "snapshot_sha256": (snapshot or {}).get("sha256"),
            "current_sha256": current.get("sha256"),
        })

    parent_snapshots = {
        str(row.get("requirement_id")): row
        for row in record.get("parent_snapshot") or []
        if isinstance(row, Mapping)
    }
    parent_checks: list[dict[str, Any]] = []
    for parent_id in record.get("parent_requirement_ids") or []:
        snapshot = parent_snapshots.get(str(parent_id))
        try:
            current_parent = get_requirement(path, str(parent_id))
        except Exception:
            link_missing.append(f"requirement:{parent_id}")
            parent_checks.append({"requirement_id": parent_id, "state": "MISSING", "snapshot_sha256": (snapshot or {}).get("sha256"), "current_sha256": None})
            continue
        current_sha = str(current_parent.get("requirement_sha256") or _sha(current_parent))
        is_stale = bool(snapshot and str(snapshot.get("sha256") or "") != current_sha)
        if is_stale:
            link_stale.append(f"requirement:{parent_id}")
        parent_checks.append({
            "requirement_id": parent_id,
            "requirement_key": current_parent.get("requirement_key"),
            "state": "STALE" if is_stale else "CURRENT",
            "snapshot_sha256": (snapshot or {}).get("sha256"),
            "current_sha256": current_sha,
        })

    method = str(record.get("verification_method") or "")
    criteria = str(record.get("verification_criteria") or "").strip()
    no_evidence = not (record.get("evidence_references") or [])
    if not method or not criteria:
        status = "UNPLANNED"
        rationale = "Verification method and criteria are not fully planned."
    elif no_evidence or evidence_missing:
        status = "EVIDENCE_MISSING"
        rationale = "The requirement has no explicit evidence references or one or more evidence references no longer resolve."
    elif link_missing:
        status = "LINK_MISSING"
        rationale = "One or more parent/engineering traceability links no longer resolve."
    elif evidence_stale or link_stale:
        status = "STALE"
        rationale = "One or more evidence, parent, or engineering-record fingerprints changed after registration."
    else:
        status = "READY_FOR_REVIEW"
        rationale = "Verification planning is declared and all registered evidence/traceability links are present and current."

    stable = {
        "schema": "physical-lab-requirement-evaluation-v1",
        "requirement_id": requirement_id,
        "requirement_key": record.get("requirement_key"),
        "requirement_sha256": record.get("requirement_sha256"),
        "status": status,
        "verification_method": method,
        "verification_criteria": criteria,
        "evidence_checks": evidence_checks,
        "engineering_checks": engineering_checks,
        "parent_checks": parent_checks,
    }
    return {
        **stable,
        "evaluation_sha256": _sha(stable),
        "rationale": rationale,
        "missing_evidence": evidence_missing,
        "stale_evidence": evidence_stale,
        "missing_links": link_missing,
        "stale_links": link_stale,
        "boundary": record.get("boundary"),
    }


def traceability_matrix(project_dir: str | Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    rows = list_requirements(path)
    children: dict[str, list[str]] = {str(row.get("requirement_id")): [] for row in rows}
    requirement_records: dict[str, dict[str, Any]] = {}
    for row in rows:
        requirement_id = str(row.get("requirement_id") or "")
        requirement_records[requirement_id] = get_requirement(path, requirement_id)
    for requirement_id, record in requirement_records.items():
        for parent_id in record.get("parent_requirement_ids") or []:
            if str(parent_id) in children:
                children[str(parent_id)].append(requirement_id)

    matrix_rows: list[dict[str, Any]] = []
    counts = {state: 0 for state in REVIEW_STATES}
    for row in rows:
        requirement_id = str(row.get("requirement_id") or "")
        record = requirement_records[requirement_id]
        evaluation = evaluate_requirement(path, requirement_id)
        counts[evaluation["status"]] += 1
        matrix_rows.append({
            "requirement_id": requirement_id,
            "requirement_key": record.get("requirement_key"),
            "statement": record.get("statement"),
            "source": record.get("source"),
            "level": record.get("level"),
            "status": evaluation.get("status"),
            "verification_method": record.get("verification_method"),
            "parent_count": len(record.get("parent_requirement_ids") or []),
            "child_count": len(children.get(requirement_id) or []),
            "evidence_reference_count": len(record.get("evidence_references") or []),
            "engineering_link_count": len(record.get("engineering_links") or []),
            "requirement_sha256": record.get("requirement_sha256"),
            "evaluation_sha256": evaluation.get("evaluation_sha256"),
        })
    matrix_rows.sort(key=lambda row: (str(row.get("requirement_key") or ""), str(row.get("requirement_id") or "")))
    stable = {
        "schema": "physical-lab-requirements-traceability-matrix-v1",
        "project_id": project.get("project_id"),
        "requirements": matrix_rows,
        "counts": counts,
    }
    return {
        **stable,
        "matrix_sha256": _sha(stable),
        "boundary": "Traceability/readiness matrix only; status does not establish requirement verification, validation, compliance, acceptance, safety, or certification.",
    }
