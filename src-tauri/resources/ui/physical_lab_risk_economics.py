"""Evidence-linked risk and engineering-economics studies for Physical Lab Projects.

All probability, consequence, cash-flow, and discount-rate inputs are explicitly
user/project declared. The module performs transparent arithmetic and evidence
freshness checks only; it does not accept risk, approve safety, recommend an
investment, or establish economic/scientific truth.
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

RISK_SCHEMA = "physical-lab-risk-study-v1"
RISK_INDEX_SCHEMA = "physical-lab-risk-study-index-v1"
ECONOMICS_SCHEMA = "physical-lab-engineering-economics-study-v1"
ECONOMICS_INDEX_SCHEMA = "physical-lab-engineering-economics-study-index-v1"
RISK_VERSION = 1
ECONOMICS_VERSION = 1
EVIDENCE_STATES = ("CURRENT", "STALE", "EVIDENCE_MISSING")
CONSEQUENCE_DIMENSIONS = ("cost", "schedule", "performance")


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


def _optional_finite(value: Any, label: str) -> float | None:
    if value in (None, ""):
        return None
    return _finite(value, label)


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
    snapshots: list[dict[str, Any]] = []
    for ref in references:
        resolved = claims._resolve_reference(project_dir, project, str(ref["kind"]), str(ref["id"]))
        if resolved is None:
            raise ValueError(f"evidence reference does not exist: {ref['kind']}:{ref['id']}")
        snapshots.append({"owner_id": owner_id, **resolved})
    return snapshots


def _evidence_checks(
    project_dir: Path,
    project: Mapping[str, Any],
    snapshots: list[Mapping[str, Any]],
    owners: list[Mapping[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[str], list[str]]:
    snapshot_map = {
        (str(row.get("owner_id")), str(row.get("kind")), str(row.get("id"))): row
        for row in snapshots
        if isinstance(row, Mapping)
    }
    missing: list[str] = []
    stale: list[str] = []
    checks: list[dict[str, Any]] = []
    for owner in owners:
        owner_id = str(owner.get("owner_id") or "")
        for ref in owner.get("references") or []:
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


def _risk_root(project_dir: Path) -> Path:
    root = project_dir / "provenance" / "risk-studies"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _economics_root(project_dir: Path) -> Path:
    root = project_dir / "provenance" / "engineering-economics"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalize_consequences(value: Any, scenario_id: str) -> dict[str, float | None]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{scenario_id}.consequences must be an object")
    rows: dict[str, float | None] = {}
    for dimension in CONSEQUENCE_DIMENSIONS:
        item = _optional_finite(value.get(dimension), f"{scenario_id}.consequences.{dimension}")
        if item is not None and item < 0:
            raise ValueError(f"{scenario_id}.consequences.{dimension} must be non-negative magnitude")
        rows[dimension] = item
    if all(item is None for item in rows.values()):
        raise ValueError(f"{scenario_id} must declare at least one consequence magnitude")
    return rows


def _normalize_scenarios(scenarios: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("scenarios must contain at least one row")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(scenarios, start=1):
        if not isinstance(item, Mapping):
            raise ValueError("each risk scenario must be an object")
        scenario_id = str(item.get("scenario_id") or f"risk-{index:04d}").strip()
        if not scenario_id or scenario_id in seen:
            raise ValueError("scenario_id values must be non-empty and unique")
        seen.add(scenario_id)
        name = str(item.get("name") or scenario_id).strip()
        probability = _optional_finite(item.get("probability"), f"{scenario_id}.probability")
        if probability is not None and not 0.0 <= probability <= 1.0:
            raise ValueError(f"{scenario_id}.probability must be in [0, 1]")
        rows.append({
            "scenario_id": scenario_id,
            "name": name,
            "probability": probability,
            "consequences": _normalize_consequences(item.get("consequences"), scenario_id),
            "references": _normalize_refs(item.get("references")),
            "notes": str(item.get("notes") or ""),
        })
    return rows


def register_risk_study(
    project_dir: str | Path,
    *,
    name: str,
    scenarios: list[Mapping[str, Any]],
    cost_unit: str = "currency",
    schedule_unit: str = "time",
    performance_unit: str = "1",
    intended_use: str = "",
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    name = str(name).strip()
    if not name:
        raise ValueError("risk-study name is required")
    normalized = _normalize_scenarios(scenarios)
    snapshots: list[dict[str, Any]] = []
    for row in normalized:
        snapshots.extend(_resolve_refs(path, project, row["scenario_id"], row["references"]))
    units = {"cost": str(cost_unit), "schedule": str(schedule_unit), "performance": str(performance_unit)}
    identity = {
        "project_id": project.get("project_id"),
        "name": name,
        "scenarios": normalized,
        "consequence_units": units,
        "intended_use": str(intended_use).strip(),
    }
    study_id = f"risk-{_sha(identity)[:20]}"
    now = utc_now()
    record = {
        "schema": RISK_SCHEMA,
        "risk_version": RISK_VERSION,
        "study_id": study_id,
        **identity,
        "evidence_snapshot": snapshots,
        "registered_at": now,
        "updated_at": now,
        "notes": str(notes),
        "boundary": (
            "Probabilities and consequences are user/project-declared assumptions. Expected-consequence arithmetic is not a safety decision, "
            "risk-acceptance decision, calibrated risk forecast, standards determination, or certification."
        ),
    }
    record["study_sha256"] = _sha({key: record[key] for key in ("schema", "risk_version", "study_id", "project_id", "name", "scenarios", "consequence_units", "intended_use", "evidence_snapshot")})
    root = _risk_root(path)
    _atomic_json(root / f"{study_id}.json", record)
    index_path = root / "index.json"
    index = _read_json(index_path) or {"schema": RISK_INDEX_SCHEMA, "studies": {}, "updated_at": None}
    index.setdefault("studies", {})[study_id] = {"study_id": study_id, "name": name, "study_sha256": record["study_sha256"], "path": f"provenance/risk-studies/{study_id}.json", "updated_at": now}
    index["updated_at"] = now
    _atomic_json(index_path, index)
    return record


def get_risk_study(project_dir: str | Path, study_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    record = _read_json(_risk_root(path) / f"{study_id}.json")
    if not record or record.get("schema") != RISK_SCHEMA:
        raise ValueError(f"unknown risk study: {study_id}")
    return record


def evaluate_risk_study(project_dir: str | Path, study_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    record = get_risk_study(path, study_id)
    scenarios = [row for row in record.get("scenarios") or [] if isinstance(row, Mapping)]
    owners = [{"owner_id": row["scenario_id"], "references": row.get("references") or []} for row in scenarios]
    evidence_state, reference_checks, missing, stale = _evidence_checks(path, project, record.get("evidence_snapshot") or [], owners)

    rows: list[dict[str, Any]] = []
    totals: dict[str, float] = {dimension: 0.0 for dimension in CONSEQUENCE_DIMENSIONS}
    contributors: dict[str, int] = {dimension: 0 for dimension in CONSEQUENCE_DIMENSIONS}
    probability_count = 0
    for scenario in scenarios:
        probability = scenario.get("probability")
        if probability is not None:
            probability_count += 1
        expected: dict[str, float | None] = {}
        for dimension in CONSEQUENCE_DIMENSIONS:
            consequence = (scenario.get("consequences") or {}).get(dimension)
            contribution = None if probability is None or consequence is None else float(probability) * float(consequence)
            expected[dimension] = contribution
            if contribution is not None:
                totals[dimension] += contribution
                contributors[dimension] += 1
        rows.append({
            "scenario_id": scenario.get("scenario_id"),
            "name": scenario.get("name"),
            "probability": probability,
            "consequences": scenario.get("consequences"),
            "expected_consequence": expected,
        })

    expected_totals = {
        dimension: (totals[dimension] if contributors[dimension] else None)
        for dimension in CONSEQUENCE_DIMENSIONS
    }
    stable = {
        "schema": "physical-lab-risk-study-evaluation-v1",
        "study_id": study_id,
        "study_sha256": record.get("study_sha256"),
        "evidence_state": evidence_state,
        "scenario_count": len(rows),
        "probability_declared_count": probability_count,
        "scenarios": rows,
        "expected_consequence_totals": expected_totals,
        "expected_consequence_contributor_counts": contributors,
        "consequence_units": record.get("consequence_units"),
        "reference_checks": reference_checks,
    }
    return {
        **stable,
        "evaluation_sha256": _sha(stable),
        "missing_references": missing,
        "stale_references": stale,
        "boundary": record.get("boundary"),
    }


def _normalize_cash_flows(cash_flows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(cash_flows, list) or not cash_flows:
        raise ValueError("cash_flows must contain at least one row")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(cash_flows, start=1):
        if not isinstance(item, Mapping):
            raise ValueError("each cash-flow row must be an object")
        flow_id = str(item.get("flow_id") or f"flow-{index:04d}").strip()
        if not flow_id or flow_id in seen:
            raise ValueError("flow_id values must be non-empty and unique")
        seen.add(flow_id)
        period = _finite(item.get("period"), f"{flow_id}.period")
        if period < 0:
            raise ValueError(f"{flow_id}.period must be non-negative")
        amount = _finite(item.get("amount"), f"{flow_id}.amount")
        rows.append({
            "flow_id": flow_id,
            "period": period,
            "amount": amount,
            "label": str(item.get("label") or flow_id).strip(),
            "references": _normalize_refs(item.get("references")),
            "notes": str(item.get("notes") or ""),
        })
    rows.sort(key=lambda row: (float(row["period"]), str(row["flow_id"])))
    return rows


def register_economics_study(
    project_dir: str | Path,
    *,
    name: str,
    cash_flows: list[Mapping[str, Any]],
    discount_rate: float,
    currency_unit: str = "currency",
    period_unit: str = "period",
    intended_use: str = "",
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    name = str(name).strip()
    if not name:
        raise ValueError("engineering-economics study name is required")
    rate = _finite(discount_rate, "discount_rate")
    if rate <= -1.0:
        raise ValueError("discount_rate must be greater than -1")
    flows = _normalize_cash_flows(cash_flows)
    snapshots: list[dict[str, Any]] = []
    for row in flows:
        snapshots.extend(_resolve_refs(path, project, row["flow_id"], row["references"]))
    identity = {
        "project_id": project.get("project_id"),
        "name": name,
        "cash_flows": flows,
        "discount_rate": rate,
        "currency_unit": str(currency_unit),
        "period_unit": str(period_unit),
        "sign_convention": "positive=inflow_or_benefit; negative=outflow_or_cost",
        "intended_use": str(intended_use).strip(),
    }
    study_id = f"economics-{_sha(identity)[:20]}"
    now = utc_now()
    record = {
        "schema": ECONOMICS_SCHEMA,
        "economics_version": ECONOMICS_VERSION,
        "study_id": study_id,
        **identity,
        "evidence_snapshot": snapshots,
        "registered_at": now,
        "updated_at": now,
        "notes": str(notes),
        "boundary": (
            "Present-worth arithmetic uses the explicitly declared cash flows and discount rate only. It is not financial advice, "
            "a market forecast, an investment recommendation, proof of economic superiority, or a certification decision."
        ),
    }
    record["study_sha256"] = _sha({key: record[key] for key in ("schema", "economics_version", "study_id", "project_id", "name", "cash_flows", "discount_rate", "currency_unit", "period_unit", "sign_convention", "intended_use", "evidence_snapshot")})
    root = _economics_root(path)
    _atomic_json(root / f"{study_id}.json", record)
    index_path = root / "index.json"
    index = _read_json(index_path) or {"schema": ECONOMICS_INDEX_SCHEMA, "studies": {}, "updated_at": None}
    index.setdefault("studies", {})[study_id] = {"study_id": study_id, "name": name, "study_sha256": record["study_sha256"], "path": f"provenance/engineering-economics/{study_id}.json", "updated_at": now}
    index["updated_at"] = now
    _atomic_json(index_path, index)
    return record


def get_economics_study(project_dir: str | Path, study_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    record = _read_json(_economics_root(path) / f"{study_id}.json")
    if not record or record.get("schema") != ECONOMICS_SCHEMA:
        raise ValueError(f"unknown engineering-economics study: {study_id}")
    return record


def evaluate_economics_study(project_dir: str | Path, study_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    record = get_economics_study(path, study_id)
    flows = [row for row in record.get("cash_flows") or [] if isinstance(row, Mapping)]
    owners = [{"owner_id": row["flow_id"], "references": row.get("references") or []} for row in flows]
    evidence_state, reference_checks, missing, stale = _evidence_checks(path, project, record.get("evidence_snapshot") or [], owners)
    rate = float(record.get("discount_rate"))
    evaluated: list[dict[str, Any]] = []
    undiscounted = 0.0
    present_worth = 0.0
    for row in flows:
        period = float(row["period"])
        amount = float(row["amount"])
        factor = 1.0 / ((1.0 + rate) ** period)
        pv = amount * factor
        undiscounted += amount
        present_worth += pv
        evaluated.append({
            "flow_id": row.get("flow_id"),
            "label": row.get("label"),
            "period": period,
            "amount": amount,
            "discount_factor": factor,
            "present_value": pv,
        })
    stable = {
        "schema": "physical-lab-engineering-economics-evaluation-v1",
        "study_id": study_id,
        "study_sha256": record.get("study_sha256"),
        "evidence_state": evidence_state,
        "discount_rate": rate,
        "currency_unit": record.get("currency_unit"),
        "period_unit": record.get("period_unit"),
        "sign_convention": record.get("sign_convention"),
        "cash_flows": evaluated,
        "undiscounted_net_total": undiscounted,
        "present_worth": present_worth,
        "reference_checks": reference_checks,
    }
    return {
        **stable,
        "evaluation_sha256": _sha(stable),
        "missing_references": missing,
        "stale_references": stale,
        "boundary": record.get("boundary"),
    }


def risk_economics_matrix(project_dir: str | Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    risk_index = _read_json(_risk_root(path) / "index.json") or {"studies": {}}
    economics_index = _read_json(_economics_root(path) / "index.json") or {"studies": {}}
    risk_rows = [dict(value) for value in (risk_index.get("studies") or {}).values() if isinstance(value, Mapping)]
    economics_rows = [dict(value) for value in (economics_index.get("studies") or {}).values() if isinstance(value, Mapping)]
    risk_rows.sort(key=lambda row: str(row.get("study_id") or ""))
    economics_rows.sort(key=lambda row: str(row.get("study_id") or ""))
    stable = {
        "schema": "physical-lab-risk-economics-matrix-v1",
        "project_id": project.get("project_id"),
        "risk_studies": risk_rows,
        "economics_studies": economics_rows,
    }
    return {**stable, "matrix_sha256": _sha(stable), "boundary": "Inventory only; no aggregate risk/economic score or recommendation is produced."}
