"""Evidence-linked quality and reliability summaries for Physical Lab Projects.

This module deliberately separates descriptive engineering evidence from
certification or production-qualification claims. It can summarize declared
replicates, specification context, two-level factor contrasts, and observed
reliability events while tracking the freshness of the Project evidence that
supports those records.
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

QUALITY_SCHEMA = "physical-lab-quality-study-v1"
QUALITY_INDEX_SCHEMA = "physical-lab-quality-study-index-v1"
RELIABILITY_SCHEMA = "physical-lab-reliability-event-study-v1"
RELIABILITY_INDEX_SCHEMA = "physical-lab-reliability-event-study-index-v1"
QUALITY_VERSION = 1
RELIABILITY_VERSION = 1
EVIDENCE_STATES = ("CURRENT", "STALE", "EVIDENCE_MISSING")


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


def _sample_variance(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return sum((value - mean) ** 2 for value in values) / (len(values) - 1)


def _sample_std(values: list[float]) -> float | None:
    variance = _sample_variance(values)
    return math.sqrt(variance) if variance is not None else None


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


def _evidence_checks(project_dir: Path, project: Mapping[str, Any], snapshots: list[Mapping[str, Any]], owners: list[Mapping[str, Any]]) -> tuple[str, list[dict[str, Any]], list[str], list[str]]:
    snapshot_map = {
        (str(row.get("owner_id")), str(row.get("kind")), str(row.get("id"))): row
        for row in snapshots
        if isinstance(row, Mapping)
    }
    missing: list[str] = []
    stale: list[str] = []
    checks: list[dict[str, Any]] = []
    for owner in owners:
        owner_id = str(owner.get("owner_id") or owner.get("observation_id") or owner.get("trial_id") or "")
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


def _quality_root(project_dir: Path) -> Path:
    root = project_dir / "provenance" / "quality-studies"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _reliability_root(project_dir: Path) -> Path:
    root = project_dir / "provenance" / "reliability-studies"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _normalize_specification(value: Mapping[str, Any] | None) -> dict[str, float | None]:
    if not value:
        return {"lower": None, "upper": None}
    lower = None if value.get("lower") in (None, "") else _finite(value.get("lower"), "specification.lower")
    upper = None if value.get("upper") in (None, "") else _finite(value.get("upper"), "specification.upper")
    if lower is not None and upper is not None and lower > upper:
        raise ValueError("specification.lower cannot exceed specification.upper")
    return {"lower": lower, "upper": upper}


def _normalize_observations(observations: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(observations, list) or not observations:
        raise ValueError("observations must contain at least one row")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(observations, start=1):
        if not isinstance(item, Mapping):
            raise ValueError("each observation must be an object")
        observation_id = str(item.get("observation_id") or f"obs-{index:04d}").strip()
        if not observation_id or observation_id in seen:
            raise ValueError("observation_id values must be non-empty and unique")
        seen.add(observation_id)
        factors_raw = item.get("factors") or {}
        if not isinstance(factors_raw, Mapping):
            raise ValueError(f"{observation_id}.factors must be an object")
        factors = {str(key): str(value) for key, value in sorted(factors_raw.items(), key=lambda pair: str(pair[0]))}
        rows.append({
            "observation_id": observation_id,
            "value": _finite(item.get("value"), f"{observation_id}.value"),
            "replicate_group": str(item.get("replicate_group") or "").strip(),
            "factors": factors,
            "references": _normalize_refs(item.get("references")),
        })
    return rows


def register_quality_study(
    project_dir: str | Path,
    *,
    name: str,
    measurement: str,
    unit: str,
    observations: list[Mapping[str, Any]],
    specification: Mapping[str, Any] | None = None,
    intended_use: str = "",
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    name = str(name).strip()
    measurement = str(measurement).strip()
    if not name or not measurement:
        raise ValueError("quality-study name and measurement are required")
    obs = _normalize_observations(observations)
    spec = _normalize_specification(specification)
    snapshots: list[dict[str, Any]] = []
    for row in obs:
        snapshots.extend(_resolve_refs(path, project, row["observation_id"], row["references"]))
    identity = {
        "project_id": project.get("project_id"),
        "name": name,
        "measurement": measurement,
        "unit": str(unit),
        "observations": obs,
        "specification": spec,
        "intended_use": str(intended_use).strip(),
    }
    study_id = f"quality-{_sha(identity)[:20]}"
    now = utc_now()
    record = {
        "schema": QUALITY_SCHEMA,
        "quality_version": QUALITY_VERSION,
        "study_id": study_id,
        **identity,
        "evidence_snapshot": snapshots,
        "registered_at": now,
        "updated_at": now,
        "notes": str(notes),
        "boundary": (
            "Specification comparisons and repeatability/factor summaries are descriptive evidence only. "
            "They do not establish process stability, capability, causality, production qualification, safety approval, or certification."
        ),
    }
    record["study_sha256"] = _sha({key: record[key] for key in ("schema", "quality_version", "study_id", "project_id", "name", "measurement", "unit", "observations", "specification", "intended_use", "evidence_snapshot")})
    root = _quality_root(path)
    _atomic_json(root / f"{study_id}.json", record)
    index_path = root / "index.json"
    index = _read_json(index_path) or {"schema": QUALITY_INDEX_SCHEMA, "studies": {}, "updated_at": None}
    index.setdefault("studies", {})[study_id] = {"study_id": study_id, "name": name, "measurement": measurement, "study_sha256": record["study_sha256"], "path": f"provenance/quality-studies/{study_id}.json", "updated_at": now}
    index["updated_at"] = now
    _atomic_json(index_path, index)
    return record


def get_quality_study(project_dir: str | Path, study_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    record = _read_json(_quality_root(path) / f"{study_id}.json")
    if not record or record.get("schema") != QUALITY_SCHEMA:
        raise ValueError(f"unknown quality study: {study_id}")
    return record


def evaluate_quality_study(project_dir: str | Path, study_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    record = get_quality_study(path, study_id)
    owners = [{"owner_id": row["observation_id"], "references": row.get("references") or []} for row in record.get("observations") or []]
    evidence_state, reference_checks, missing, stale = _evidence_checks(path, project, record.get("evidence_snapshot") or [], owners)
    observations = [row for row in record.get("observations") or [] if isinstance(row, Mapping)]
    values = [float(row["value"]) for row in observations]
    mean = sum(values) / len(values)
    std = _sample_std(values)
    summary = {"count": len(values), "mean": mean, "sample_std": std, "min": min(values), "max": max(values)}

    spec = record.get("specification") or {}
    lower = spec.get("lower")
    upper = spec.get("upper")
    if lower is None and upper is None:
        specification_summary = {"declared": False, "within_count": None, "outside_count": None, "observed_within_fraction": None}
    else:
        within = [value for value in values if (lower is None or value >= float(lower)) and (upper is None or value <= float(upper))]
        specification_summary = {
            "declared": True,
            "lower": lower,
            "upper": upper,
            "within_count": len(within),
            "outside_count": len(values) - len(within),
            "observed_within_fraction": len(within) / len(values),
        }

    groups: dict[str, list[float]] = {}
    for row in observations:
        group = str(row.get("replicate_group") or "").strip()
        if group:
            groups.setdefault(group, []).append(float(row["value"]))
    replicate_rows: list[dict[str, Any]] = []
    pooled_numerator = 0.0
    pooled_df = 0
    for group in sorted(groups):
        group_values = groups[group]
        variance = _sample_variance(group_values)
        row = {"replicate_group": group, "count": len(group_values), "mean": sum(group_values) / len(group_values), "sample_std": math.sqrt(variance) if variance is not None else None}
        replicate_rows.append(row)
        if variance is not None:
            df = len(group_values) - 1
            pooled_numerator += df * variance
            pooled_df += df
    pooled_repeatability_std = math.sqrt(pooled_numerator / pooled_df) if pooled_df else None

    factor_names = sorted({str(key) for row in observations for key in (row.get("factors") or {}).keys()})
    factor_summaries: list[dict[str, Any]] = []
    for factor in factor_names:
        level_values: dict[str, list[float]] = {}
        for row in observations:
            factors = row.get("factors") or {}
            if factor in factors:
                level_values.setdefault(str(factors[factor]), []).append(float(row["value"]))
        levels = sorted(level_values)
        level_means = {level: sum(level_values[level]) / len(level_values[level]) for level in levels}
        entry: dict[str, Any] = {"factor": factor, "levels": levels, "level_means": level_means, "descriptive_two_level_contrast": None}
        if len(levels) == 2:
            entry["descriptive_two_level_contrast"] = {
                "from_level": levels[0],
                "to_level": levels[1],
                "difference_of_means": level_means[levels[1]] - level_means[levels[0]],
            }
        factor_summaries.append(entry)

    stable = {
        "schema": "physical-lab-quality-study-evaluation-v1",
        "study_id": study_id,
        "study_sha256": record.get("study_sha256"),
        "evidence_state": evidence_state,
        "summary": summary,
        "specification_summary": specification_summary,
        "replicate_groups": replicate_rows,
        "pooled_repeatability_std": pooled_repeatability_std,
        "repeatability_degrees_freedom": pooled_df,
        "factor_summaries": factor_summaries,
        "reference_checks": reference_checks,
    }
    return {
        **stable,
        "evaluation_sha256": _sha(stable),
        "missing_references": missing,
        "stale_references": stale,
        "boundary": record.get("boundary"),
    }


def _normalize_trials(trials: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(trials, list) or not trials:
        raise ValueError("trials must contain at least one row")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(trials, start=1):
        if not isinstance(item, Mapping):
            raise ValueError("each reliability trial must be an object")
        trial_id = str(item.get("trial_id") or f"trial-{index:04d}").strip()
        if not trial_id or trial_id in seen:
            raise ValueError("trial_id values must be non-empty and unique")
        seen.add(trial_id)
        exposure = _finite(item.get("exposure", 0.0), f"{trial_id}.exposure")
        if exposure < 0:
            raise ValueError(f"{trial_id}.exposure must be non-negative")
        rows.append({
            "trial_id": trial_id,
            "exposure": exposure,
            "event_observed": bool(item.get("event_observed")),
            "event_category": str(item.get("event_category") or "").strip(),
            "references": _normalize_refs(item.get("references")),
        })
    return rows


def register_reliability_study(
    project_dir: str | Path,
    *,
    name: str,
    item: str,
    trials: list[Mapping[str, Any]],
    exposure_unit: str = "",
    intended_use: str = "",
    notes: str = "",
) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    name = str(name).strip()
    item = str(item).strip()
    if not name or not item:
        raise ValueError("reliability-study name and item are required")
    normalized = _normalize_trials(trials)
    snapshots: list[dict[str, Any]] = []
    for row in normalized:
        snapshots.extend(_resolve_refs(path, project, row["trial_id"], row["references"]))
    identity = {
        "project_id": project.get("project_id"),
        "name": name,
        "item": item,
        "trials": normalized,
        "exposure_unit": str(exposure_unit),
        "intended_use": str(intended_use).strip(),
    }
    study_id = f"reliability-{_sha(identity)[:20]}"
    now = utc_now()
    record = {
        "schema": RELIABILITY_SCHEMA,
        "reliability_version": RELIABILITY_VERSION,
        "study_id": study_id,
        **identity,
        "evidence_snapshot": snapshots,
        "registered_at": now,
        "updated_at": now,
        "notes": str(notes),
        "boundary": (
            "Observed event fractions and exposure-normalized event rates are descriptive summaries of the declared trials only. "
            "No lifetime distribution, reliability function, MTBF, certification, safety approval, or field-performance claim is inferred."
        ),
    }
    record["study_sha256"] = _sha({key: record[key] for key in ("schema", "reliability_version", "study_id", "project_id", "name", "item", "trials", "exposure_unit", "intended_use", "evidence_snapshot")})
    root = _reliability_root(path)
    _atomic_json(root / f"{study_id}.json", record)
    index_path = root / "index.json"
    index = _read_json(index_path) or {"schema": RELIABILITY_INDEX_SCHEMA, "studies": {}, "updated_at": None}
    index.setdefault("studies", {})[study_id] = {"study_id": study_id, "name": name, "item": item, "study_sha256": record["study_sha256"], "path": f"provenance/reliability-studies/{study_id}.json", "updated_at": now}
    index["updated_at"] = now
    _atomic_json(index_path, index)
    return record


def get_reliability_study(project_dir: str | Path, study_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    projects.open_project(path)
    record = _read_json(_reliability_root(path) / f"{study_id}.json")
    if not record or record.get("schema") != RELIABILITY_SCHEMA:
        raise ValueError(f"unknown reliability study: {study_id}")
    return record


def evaluate_reliability_study(project_dir: str | Path, study_id: str) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    record = get_reliability_study(path, study_id)
    trials = [row for row in record.get("trials") or [] if isinstance(row, Mapping)]
    owners = [{"owner_id": row["trial_id"], "references": row.get("references") or []} for row in trials]
    evidence_state, reference_checks, missing, stale = _evidence_checks(path, project, record.get("evidence_snapshot") or [], owners)
    event_count = sum(1 for row in trials if bool(row.get("event_observed")))
    total_exposure = sum(float(row.get("exposure") or 0.0) for row in trials)
    categories: dict[str, int] = {}
    for row in trials:
        if bool(row.get("event_observed")):
            category = str(row.get("event_category") or "unspecified") or "unspecified"
            categories[category] = categories.get(category, 0) + 1
    stable = {
        "schema": "physical-lab-reliability-event-study-evaluation-v1",
        "study_id": study_id,
        "study_sha256": record.get("study_sha256"),
        "evidence_state": evidence_state,
        "trial_count": len(trials),
        "event_count": event_count,
        "observed_event_fraction": event_count / len(trials),
        "total_exposure": total_exposure,
        "exposure_unit": record.get("exposure_unit"),
        "observed_event_rate_per_exposure": (event_count / total_exposure) if total_exposure > 0 else None,
        "event_categories": dict(sorted(categories.items())),
        "reference_checks": reference_checks,
    }
    return {
        **stable,
        "evaluation_sha256": _sha(stable),
        "missing_references": missing,
        "stale_references": stale,
        "boundary": record.get("boundary"),
    }


def quality_reliability_matrix(project_dir: str | Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    quality_index = _read_json(_quality_root(path) / "index.json") or {"studies": {}}
    reliability_index = _read_json(_reliability_root(path) / "index.json") or {"studies": {}}
    quality_rows = [dict(value) for value in (quality_index.get("studies") or {}).values() if isinstance(value, Mapping)]
    reliability_rows = [dict(value) for value in (reliability_index.get("studies") or {}).values() if isinstance(value, Mapping)]
    quality_rows.sort(key=lambda row: str(row.get("study_id") or ""))
    reliability_rows.sort(key=lambda row: str(row.get("study_id") or ""))
    stable = {
        "schema": "physical-lab-quality-reliability-matrix-v1",
        "project_id": project.get("project_id"),
        "quality_studies": quality_rows,
        "reliability_studies": reliability_rows,
    }
    return {**stable, "matrix_sha256": _sha(stable), "boundary": "Inventory only; no aggregate quality or reliability score is produced."}
