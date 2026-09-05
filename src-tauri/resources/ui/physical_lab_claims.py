"""Claim-to-Evidence Matrix for Physical Lab projects.

A scientific or engineering statement is stored as a claim with explicit evidence
references and required Credibility Passport factors. Physical Lab evaluates
whether the referenced evidence is present, unchanged, and ready for human
review. It does not decide whether the claim is scientifically true.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import physical_lab_credibility as credibility
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import plain, sha256_json, utc_now

CLAIM_SCHEMA = "physical-lab-evidence-claim-v1"
CLAIM_INDEX_SCHEMA = "physical-lab-evidence-claim-index-v1"
CLAIM_VERSION = 1
CLAIM_STATUSES = ("READY_FOR_REVIEW", "PARTIAL", "STALE", "EVIDENCE_MISSING")
REFERENCE_KINDS = ("experiment", "job", "result", "measurement", "calibration")
VALID_FACTOR_IDS = {item[0] for item in credibility.FACTOR_DEFINITIONS}


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


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    ).hexdigest()


def _claim_root(project_dir: Path) -> Path:
    path = project_dir / "provenance" / "claims"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path(project_dir: Path) -> Path:
    return _claim_root(project_dir) / "index.json"


def _load_index(project_dir: Path) -> dict[str, Any]:
    existing = _read_json(_index_path(project_dir))
    if existing and existing.get("schema") == CLAIM_INDEX_SCHEMA:
        return existing
    return {"schema": CLAIM_INDEX_SCHEMA, "claims": {}, "updated_at": None}


def _measurement_index(project_dir: Path) -> dict[str, Any]:
    return _read_json(project_dir / "measurements" / "index.json") or {}


def _calibration_index(project_dir: Path) -> dict[str, Any]:
    return _read_json(project_dir / "calibration" / "index.json") or {}


def _resolve_reference(project_dir: Path, project: Mapping[str, Any], kind: str, ref_id: str) -> dict[str, Any] | None:
    if kind == "experiment":
        row = (project.get("experiments") or {}).get(ref_id)
        if isinstance(row, Mapping):
            digest = str(row.get("experiment_sha256") or "")
            return {"kind": kind, "id": ref_id, "sha256": digest or _sha(row), "label": row.get("model")}
    elif kind == "job":
        row = (project.get("jobs") or {}).get(ref_id)
        if isinstance(row, Mapping):
            stable = {k: row.get(k) for k in ("job_id", "experiment_id", "experiment_sha256", "profile", "runner", "status", "stage", "attempt", "result_path", "log_path")}
            return {"kind": kind, "id": ref_id, "sha256": _sha(stable), "label": row.get("runner")}
    elif kind == "result":
        row = (project.get("results") or {}).get(ref_id)
        if isinstance(row, Mapping):
            digest = str(row.get("result_sha256") or "")
            return {"kind": kind, "id": ref_id, "sha256": digest or _sha(row), "label": f"result:{ref_id}"}
    elif kind == "measurement":
        row = ((_measurement_index(project_dir).get("measurements") or {}).get(ref_id))
        if isinstance(row, Mapping):
            digest = str(row.get("sha256") or "")
            return {"kind": kind, "id": ref_id, "sha256": digest or _sha(row), "label": row.get("file_name")}
    elif kind == "calibration":
        row = ((_calibration_index(project_dir).get("calibrations") or {}).get(ref_id))
        if isinstance(row, Mapping):
            return {"kind": kind, "id": ref_id, "sha256": _sha(row), "label": row.get("parameter")}
    return None


def _normalize_refs(references: list[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in references or []:
        kind = str(item.get("kind") or "").strip().lower()
        ref_id = str(item.get("id") or "").strip()
        if kind not in REFERENCE_KINDS:
            raise ValueError(f"unsupported evidence reference kind: {kind!r}")
        if not ref_id:
            raise ValueError("evidence reference id is required")
        key = (kind, ref_id)
        if key not in seen:
            rows.append({"kind": kind, "id": ref_id})
            seen.add(key)
    rows.sort(key=lambda row: (row["kind"], row["id"]))
    return rows


def _normalize_factors(factors: list[str] | None) -> list[str]:
    values = sorted({str(value).strip() for value in (factors or []) if str(value).strip()})
    unknown = [value for value in values if value not in VALID_FACTOR_IDS]
    if unknown:
        raise ValueError("unknown credibility factor IDs: " + ", ".join(unknown))
    return values


def register_claim(
    project_dir: str | Path,
    *,
    statement: str,
    claim_type: str = "scientific",
    intended_use: str = "",
    required_factors: list[str] | None = None,
    references: list[Mapping[str, Any]] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    statement = str(statement).strip()
    if not statement:
        raise ValueError("claim statement is required")
    factors = _normalize_factors(required_factors)
    refs = _normalize_refs(references)
    snapshots: list[dict[str, Any]] = []
    for ref in refs:
        resolved = _resolve_reference(path, project, ref["kind"], ref["id"])
        if resolved is None:
            raise ValueError(f"evidence reference does not exist: {ref['kind']}:{ref['id']}")
        snapshots.append(resolved)

    identity = {
        "project_id": project["project_id"],
        "statement": statement,
        "claim_type": str(claim_type).strip() or "scientific",
        "intended_use": str(intended_use).strip(),
        "required_factors": factors,
        "references": refs,
    }
    claim_id = f"claim-{_sha(identity)[:20]}"
    now = utc_now()
    existing = _read_json(_claim_root(path) / f"{claim_id}.json")
    registered_at = str((existing or {}).get("registered_at") or now)
    record = {
        "schema": CLAIM_SCHEMA,
        "claim_version": CLAIM_VERSION,
        "claim_id": claim_id,
        **identity,
        "evidence_snapshot": snapshots,
        "registered_at": registered_at,
        "updated_at": now,
        "notes": str(notes),
        "boundary": "This record links a human-authored claim to evidence. Registration does not establish scientific truth or certification.",
    }
    record["claim_sha256"] = _sha({k: record[k] for k in ("schema", "claim_version", "claim_id", "project_id", "statement", "claim_type", "intended_use", "required_factors", "references", "evidence_snapshot")})
    _atomic_json(_claim_root(path) / f"{claim_id}.json", record)
    index = _load_index(path)
    index.setdefault("claims", {})[claim_id] = {
        "claim_id": claim_id,
        "statement": statement,
        "claim_type": record["claim_type"],
        "intended_use": record["intended_use"],
        "claim_sha256": record["claim_sha256"],
        "path": f"provenance/claims/{claim_id}.json",
        "updated_at": now,
    }
    index["updated_at"] = now
    _atomic_json(_index_path(path), index)
    return record


def get_claim(project_dir: str | Path, claim_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    record = _read_json(_claim_root(path) / f"{claim_id}.json")
    if not record or record.get("schema") != CLAIM_SCHEMA:
        raise ValueError(f"unknown claim_id: {claim_id}")
    return record


def list_claims(project_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    index = _load_index(path)
    rows = [dict(v) for v in (index.get("claims") or {}).values() if isinstance(v, Mapping)]
    rows.sort(key=lambda row: (str(row.get("updated_at") or ""), str(row.get("claim_id") or "")), reverse=True)
    return rows


def evaluate_claim(project_dir: str | Path, claim_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    claim = get_claim(path, claim_id)
    snapshots = {(str(row.get("kind")), str(row.get("id"))): row for row in claim.get("evidence_snapshot") or [] if isinstance(row, Mapping)}

    refs: list[dict[str, Any]] = []
    missing: list[str] = []
    stale: list[str] = []
    for ref in claim.get("references") or []:
        kind = str(ref.get("kind") or "")
        ref_id = str(ref.get("id") or "")
        current = _resolve_reference(path, project, kind, ref_id)
        snapshot = snapshots.get((kind, ref_id))
        if current is None:
            missing.append(f"{kind}:{ref_id}")
            refs.append({"kind": kind, "id": ref_id, "state": "MISSING", "snapshot_sha256": (snapshot or {}).get("sha256"), "current_sha256": None})
            continue
        is_stale = bool(snapshot and str(snapshot.get("sha256") or "") != str(current.get("sha256") or ""))
        if is_stale:
            stale.append(f"{kind}:{ref_id}")
        refs.append({"kind": kind, "id": ref_id, "state": "STALE" if is_stale else "CURRENT", "snapshot_sha256": (snapshot or {}).get("sha256"), "current_sha256": current.get("sha256")})

    experiment_refs = [r["id"] for r in claim.get("references") or [] if r.get("kind") == "experiment"]
    job_refs = [r["id"] for r in claim.get("references") or [] if r.get("kind") == "job"]
    passport = credibility.build_credibility_passport(
        path,
        experiment_id=experiment_refs[0] if len(experiment_refs) == 1 else None,
        job_id=job_refs[0] if len(job_refs) == 1 else None,
    )
    factor_map = {str(row.get("factor_id")): row for row in passport.get("factors") or [] if isinstance(row, Mapping)}
    factor_checks = []
    for factor_id in claim.get("required_factors") or []:
        row = factor_map.get(str(factor_id)) or {}
        factor_checks.append({"factor_id": factor_id, "status": row.get("status") or "MISSING", "rationale": row.get("rationale")})
    factors_ready = all(row["status"] == "PRESENT" for row in factor_checks)

    if missing:
        status = "EVIDENCE_MISSING"
        rationale = "One or more explicitly referenced evidence artifacts no longer resolve."
    elif stale:
        status = "STALE"
        rationale = "One or more evidence fingerprints changed after the claim was registered; human review must be repeated."
    elif not claim.get("references"):
        status = "EVIDENCE_MISSING"
        rationale = "The claim has no explicit evidence references."
    elif factors_ready:
        status = "READY_FOR_REVIEW"
        rationale = "All referenced evidence is current and all required credibility factors have PRESENT project evidence."
    else:
        status = "PARTIAL"
        rationale = "Evidence references are current, but one or more required credibility factors are PARTIAL or MISSING."

    stable = {
        "schema": "physical-lab-claim-evaluation-v1",
        "claim_id": claim_id,
        "claim_sha256": claim.get("claim_sha256"),
        "status": status,
        "reference_checks": refs,
        "factor_checks": factor_checks,
        "passport_sha256": passport.get("passport_sha256"),
    }
    return {
        **stable,
        "evaluation_sha256": _sha(stable),
        "rationale": rationale,
        "missing_references": missing,
        "stale_references": stale,
        "boundary": "READY_FOR_REVIEW means evidence readiness only. Physical Lab does not determine that the claim is true, valid for every intended use, or certified.",
    }


def claim_evidence_matrix(project_dir: str | Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    rows = []
    for item in list_claims(path):
        claim_id = str(item.get("claim_id") or "")
        if not claim_id:
            continue
        claim = get_claim(path, claim_id)
        evaluation = evaluate_claim(path, claim_id)
        rows.append({
            "claim_id": claim_id,
            "statement": claim.get("statement"),
            "claim_type": claim.get("claim_type"),
            "intended_use": claim.get("intended_use"),
            "status": evaluation.get("status"),
            "required_factors": claim.get("required_factors") or [],
            "reference_count": len(claim.get("references") or []),
            "evaluation_sha256": evaluation.get("evaluation_sha256"),
        })
    stable = {"schema": "physical-lab-claim-evidence-matrix-v1", "project_id": project.get("project_id"), "claims": rows}
    return {
        **stable,
        "matrix_sha256": _sha(stable),
        "status_counts": {status: sum(1 for row in rows if row["status"] == status) for status in CLAIM_STATUSES},
        "boundary": "Matrix status summarizes evidence readiness and freshness, not scientific truth or certification.",
    }


def render_matrix_markdown(matrix: Mapping[str, Any]) -> str:
    lines = [
        "# Physical Lab Claim-to-Evidence Matrix",
        "",
        f"- Project: `{matrix.get('project_id')}`",
        f"- Matrix fingerprint: `{matrix.get('matrix_sha256')}`",
        "",
        "| Claim | Status | Evidence refs | Required factors |",
        "|---|---|---:|---|",
    ]
    for row in matrix.get("claims") or []:
        if not isinstance(row, Mapping):
            continue
        statement = str(row.get("statement") or "").replace("|", "\\|")
        factors = ", ".join(str(x) for x in row.get("required_factors") or []) or "—"
        lines.append(f"| {statement} | **{row.get('status')}** | {row.get('reference_count') or 0} | {factors} |")
    if not matrix.get("claims"):
        lines.append("| — | — | 0 | — |")
    lines += ["", "## Boundary", "", str(matrix.get("boundary") or ""), ""]
    return "\n".join(lines)
