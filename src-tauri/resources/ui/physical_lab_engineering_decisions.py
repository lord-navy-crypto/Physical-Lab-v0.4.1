"""Evidence-linked engineering decision studies for Physical Lab projects.

This layer turns project evidence into explicit alternatives, metrics, constraints,
and Pareto trade studies. It intentionally does not produce a synthetic overall
score, a machine recommendation, or a scientific truth/certification verdict.
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

STUDY_SCHEMA = "physical-lab-engineering-decision-study-v1"
INDEX_SCHEMA = "physical-lab-engineering-decision-index-v1"
EVALUATION_SCHEMA = "physical-lab-engineering-decision-evaluation-v1"
DECISION_RECORD_SCHEMA = "physical-lab-human-engineering-decision-v1"
STUDY_VERSION = 1
METRIC_DIRECTIONS = ("minimize", "maximize")
CONSTRAINT_OPERATORS = ("<=", ">=")
REVIEW_STATES = ("FEASIBLE", "INFEASIBLE", "STALE", "EVIDENCE_MISSING")


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
    path = project_dir / "provenance" / "engineering-decisions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path(project_dir: Path) -> Path:
    return _root(project_dir) / "index.json"


def _load_index(project_dir: Path) -> dict[str, Any]:
    existing = _read_json(_index_path(project_dir))
    if existing and existing.get("schema") == INDEX_SCHEMA:
        return existing
    return {"schema": INDEX_SCHEMA, "studies": {}, "updated_at": None}


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


def _normalize_metrics(metrics: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in metrics:
        metric_id = str(item.get("metric_id") or item.get("id") or "").strip()
        label = str(item.get("label") or metric_id).strip()
        direction = str(item.get("direction") or "").strip().lower()
        unit = str(item.get("unit") or "").strip()
        if not metric_id or metric_id in seen:
            raise ValueError("metric ids must be non-empty and unique")
        if direction not in METRIC_DIRECTIONS:
            raise ValueError(f"metric direction must be one of {METRIC_DIRECTIONS}")
        rows.append({"metric_id": metric_id, "label": label, "direction": direction, "unit": unit})
        seen.add(metric_id)
    if not rows:
        raise ValueError("at least one decision metric is required")
    rows.sort(key=lambda row: row["metric_id"])
    return rows


def _normalize_constraints(constraints: list[Mapping[str, Any]] | None, metric_ids: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in constraints or []:
        metric_id = str(item.get("metric_id") or "").strip()
        operator = str(item.get("operator") or "").strip()
        if metric_id not in metric_ids:
            raise ValueError(f"constraint references unknown metric: {metric_id!r}")
        if operator not in CONSTRAINT_OPERATORS:
            raise ValueError(f"constraint operator must be one of {CONSTRAINT_OPERATORS}")
        rows.append({"metric_id": metric_id, "operator": operator, "threshold": _finite(item.get("threshold"), "constraint threshold")})
    rows.sort(key=lambda row: (row["metric_id"], row["operator"], row["threshold"]))
    return rows


def _normalize_alternatives(alternatives: list[Mapping[str, Any]], metric_ids: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in alternatives:
        alt_id = str(item.get("alternative_id") or item.get("id") or "").strip()
        label = str(item.get("label") or alt_id).strip()
        if not alt_id or alt_id in seen:
            raise ValueError("alternative ids must be non-empty and unique")
        raw_values = item.get("values") or {}
        if not isinstance(raw_values, Mapping):
            raise ValueError(f"{alt_id}.values must be an object")
        values = {metric_id: _finite(raw_values.get(metric_id), f"{alt_id}.{metric_id}") for metric_id in metric_ids}
        refs = _normalize_refs(item.get("references") if isinstance(item.get("references"), list) else None)
        if not refs:
            raise ValueError(f"{alt_id}.references must contain at least one project evidence reference")
        rows.append({"alternative_id": alt_id, "label": label, "values": values, "references": refs})
        seen.add(alt_id)
    if len(rows) < 2:
        raise ValueError("at least two alternatives are required")
    rows.sort(key=lambda row: row["alternative_id"])
    return rows


def _resolve_snapshot(project_dir: Path, project: Mapping[str, Any], alternative: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for ref in alternative.get("references") or []:
        resolved = claims._resolve_reference(project_dir, project, str(ref.get("kind")), str(ref.get("id")))
        if resolved is None:
            raise ValueError(f"evidence reference does not exist: {ref.get('kind')}:{ref.get('id')}")
        rows.append({"alternative_id": alternative.get("alternative_id"), **resolved})
    return rows


def register_decision_study(
    project_dir: str | Path,
    *,
    name: str,
    decision_question: str,
    metrics: list[Mapping[str, Any]],
    alternatives: list[Mapping[str, Any]],
    constraints: list[Mapping[str, Any]] | None = None,
    intended_use: str = "",
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    name = str(name).strip()
    decision_question = str(decision_question).strip()
    if not name or not decision_question:
        raise ValueError("decision study name and decision question are required")
    metric_rows = _normalize_metrics(metrics)
    metric_ids = {row["metric_id"] for row in metric_rows}
    constraint_rows = _normalize_constraints(constraints, metric_ids)
    alternative_rows = _normalize_alternatives(alternatives, metric_ids)
    evidence_snapshot = []
    for alternative in alternative_rows:
        evidence_snapshot.extend(_resolve_snapshot(path, project, alternative))
    identity = {
        "project_id": project.get("project_id"),
        "name": name,
        "decision_question": decision_question,
        "metrics": metric_rows,
        "constraints": constraint_rows,
        "alternatives": alternative_rows,
        "intended_use": str(intended_use).strip(),
    }
    study_id = f"trade-{_sha(identity)[:20]}"
    now = utc_now()
    existing = _read_json(_root(path) / f"{study_id}.json")
    record = {
        "schema": STUDY_SCHEMA,
        "study_version": STUDY_VERSION,
        "study_id": study_id,
        **identity,
        "evidence_snapshot": evidence_snapshot,
        "registered_at": str((existing or {}).get("registered_at") or now),
        "updated_at": now,
        "notes": str(notes),
        "boundary": (
            "Constraint feasibility and Pareto dominance are computed only from user-declared metrics and evidence-linked values. "
            "Physical Lab does not infer unstated objectives, assign an overall score, or select a best alternative."
        ),
    }
    stable = {key: record[key] for key in (
        "schema", "study_version", "study_id", "project_id", "name", "decision_question",
        "metrics", "constraints", "alternatives", "intended_use", "evidence_snapshot",
    )}
    record["study_sha256"] = _sha(stable)
    _atomic_json(_root(path) / f"{study_id}.json", record)
    index = _load_index(path)
    index.setdefault("studies", {})[study_id] = {
        "study_id": study_id,
        "name": name,
        "decision_question": decision_question,
        "study_sha256": record["study_sha256"],
        "path": f"provenance/engineering-decisions/{study_id}.json",
        "updated_at": now,
    }
    index["updated_at"] = now
    _atomic_json(_index_path(path), index)
    return record


def get_decision_study(project_dir: str | Path, study_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    value = _read_json(_root(path) / f"{study_id}.json")
    if not value or value.get("schema") != STUDY_SCHEMA:
        raise ValueError(f"unknown study_id: {study_id}")
    return value


def list_decision_studies(project_dir: str | Path) -> list[dict[str, Any]]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    index = _load_index(path)
    rows = [dict(value) for value in (index.get("studies") or {}).values() if isinstance(value, Mapping)]
    rows.sort(key=lambda row: (str(row.get("updated_at") or ""), str(row.get("study_id") or "")), reverse=True)
    return rows


def _constraint_checks(values: Mapping[str, Any], constraints: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    checks = []
    for constraint in constraints:
        metric_id = str(constraint.get("metric_id"))
        operator = str(constraint.get("operator"))
        threshold = float(constraint.get("threshold"))
        value = float(values[metric_id])
        passed = value <= threshold if operator == "<=" else value >= threshold
        checks.append({"metric_id": metric_id, "operator": operator, "threshold": threshold, "value": value, "passed": passed})
    return checks


def _dominates(a: Mapping[str, float], b: Mapping[str, float], metrics: list[Mapping[str, Any]]) -> bool:
    no_worse = True
    strictly_better = False
    for metric in metrics:
        metric_id = str(metric.get("metric_id"))
        direction = str(metric.get("direction"))
        av = float(a[metric_id])
        bv = float(b[metric_id])
        if direction == "maximize":
            if av < bv:
                no_worse = False
                break
            if av > bv:
                strictly_better = True
        else:
            if av > bv:
                no_worse = False
                break
            if av < bv:
                strictly_better = True
    return no_worse and strictly_better


def evaluate_decision_study(project_dir: str | Path, study_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    study = get_decision_study(path, study_id)
    snapshots = {
        (str(row.get("alternative_id")), str(row.get("kind")), str(row.get("id"))): row
        for row in study.get("evidence_snapshot") or [] if isinstance(row, Mapping)
    }
    metrics = [dict(row) for row in study.get("metrics") or [] if isinstance(row, Mapping)]
    constraints = [dict(row) for row in study.get("constraints") or [] if isinstance(row, Mapping)]
    evaluations: list[dict[str, Any]] = []
    for alternative in study.get("alternatives") or []:
        alt_id = str(alternative.get("alternative_id"))
        missing: list[str] = []
        stale: list[str] = []
        ref_checks = []
        for ref in alternative.get("references") or []:
            kind = str(ref.get("kind") or "")
            ref_id = str(ref.get("id") or "")
            current = claims._resolve_reference(path, project, kind, ref_id)
            snapshot = snapshots.get((alt_id, kind, ref_id))
            key = f"{kind}:{ref_id}"
            if current is None:
                missing.append(key)
                ref_checks.append({"reference": key, "state": "MISSING", "snapshot_sha256": (snapshot or {}).get("sha256"), "current_sha256": None})
                continue
            is_stale = bool(snapshot and str(snapshot.get("sha256") or "") != str(current.get("sha256") or ""))
            if is_stale:
                stale.append(key)
            ref_checks.append({
                "reference": key,
                "state": "STALE" if is_stale else "CURRENT",
                "snapshot_sha256": (snapshot or {}).get("sha256"),
                "current_sha256": current.get("sha256"),
            })
        checks = _constraint_checks(alternative.get("values") or {}, constraints)
        feasible = all(row["passed"] for row in checks)
        if missing:
            review_state = "EVIDENCE_MISSING"
        elif stale:
            review_state = "STALE"
        elif not feasible:
            review_state = "INFEASIBLE"
        else:
            review_state = "FEASIBLE"
        evaluations.append({
            "alternative_id": alt_id,
            "label": alternative.get("label"),
            "values": plain(alternative.get("values") or {}),
            "constraint_checks": checks,
            "feasible": feasible,
            "review_state": review_state,
            "reference_checks": ref_checks,
            "missing_references": missing,
            "stale_references": stale,
        })

    eligible = [row for row in evaluations if row["review_state"] == "FEASIBLE"]
    dominated_by: dict[str, list[str]] = {str(row["alternative_id"]): [] for row in eligible}
    for row in eligible:
        for other in eligible:
            if row is other:
                continue
            if _dominates(other["values"], row["values"], metrics):
                dominated_by[str(row["alternative_id"])].append(str(other["alternative_id"]))
    pareto = sorted([alt_id for alt_id, dominators in dominated_by.items() if not dominators])
    for row in evaluations:
        row["pareto_eligible"] = row["review_state"] == "FEASIBLE"
        row["pareto_nondominated"] = str(row["alternative_id"]) in pareto
        row["dominated_by"] = sorted(dominated_by.get(str(row["alternative_id"]), []))

    stable = {
        "schema": EVALUATION_SCHEMA,
        "study_id": study_id,
        "study_sha256": study.get("study_sha256"),
        "alternatives": evaluations,
        "pareto_frontier": pareto,
    }
    return {
        **stable,
        "evaluation_sha256": _sha(stable),
        "counts": {
            state: sum(row["review_state"] == state for row in evaluations)
            for state in REVIEW_STATES
        },
        "boundary": (
            "Pareto membership means only that no other CURRENT, constraint-feasible alternative is better in every declared metric. "
            "It is not a machine recommendation, proof of optimality for unstated objectives, safety approval, or scientific validation."
        ),
    }


def decision_matrix(project_dir: str | Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    rows = []
    for item in list_decision_studies(path):
        evaluation = evaluate_decision_study(path, str(item["study_id"]))
        rows.append({
            "study_id": item.get("study_id"),
            "name": item.get("name"),
            "decision_question": item.get("decision_question"),
            "pareto_frontier": evaluation.get("pareto_frontier") or [],
            "counts": evaluation.get("counts") or {},
            "evaluation_sha256": evaluation.get("evaluation_sha256"),
        })
    stable = {"schema": "physical-lab-engineering-decision-matrix-v1", "studies": rows}
    return {**stable, "matrix_sha256": _sha(stable)}


def record_human_decision(
    project_dir: str | Path,
    study_id: str,
    *,
    selected_alternative_id: str,
    rationale: str,
    reviewer: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    study = get_decision_study(path, study_id)
    evaluation = evaluate_decision_study(path, study_id)
    selected = str(selected_alternative_id).strip()
    valid_ids = {str(row.get("alternative_id")) for row in study.get("alternatives") or []}
    if selected not in valid_ids:
        raise ValueError("selected alternative is not part of this study")
    rationale = str(rationale).strip()
    if not rationale:
        raise ValueError("human decision rationale is required")
    stable = {
        "schema": DECISION_RECORD_SCHEMA,
        "study_id": study_id,
        "study_sha256": study.get("study_sha256"),
        "evaluation_sha256": evaluation.get("evaluation_sha256"),
        "selected_alternative_id": selected,
        "rationale": rationale,
        "reviewer": str(reviewer).strip(),
    }
    record = {
        **stable,
        "recorded_at": utc_now(),
        "decision_sha256": _sha(stable),
        "boundary": "This is a human-authored decision record. Physical Lab stores the rationale and evidence state but does not endorse the selection.",
    }
    target = _root(path) / study_id / "human-decisions" / f"decision-{record['decision_sha256'][:16]}.json"
    _atomic_json(target, record)
    return record


def render_decision_markdown(evaluation: Mapping[str, Any]) -> str:
    lines = [
        "# Physical Lab Engineering Decision Study",
        "",
        f"- Study: `{evaluation.get('study_id')}`",
        f"- Evaluation fingerprint: `{evaluation.get('evaluation_sha256')}`",
        f"- Pareto frontier: {', '.join(f'`{x}`' for x in evaluation.get('pareto_frontier') or []) or 'None'}",
        "",
        "## Alternatives",
        "",
    ]
    for row in evaluation.get("alternatives") or []:
        lines.append(
            f"- `{row.get('alternative_id')}` · **{row.get('review_state')}** · "
            f"Pareto nondominated: **{bool(row.get('pareto_nondominated'))}**"
        )
    lines += ["", "## Engineering boundary", "", str(evaluation.get("boundary") or ""), ""]
    return "\n".join(lines)
