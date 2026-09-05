"""Evidence-state snapshots and diffs for Physical Lab projects.

Snapshots combine Credibility Passport, Claim-to-Evidence Matrix, and Cross-Check
Matrix state. Diffs explain evidence/freshness changes without interpreting them
as scientific truth or certification decisions.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import physical_lab_claims as claims
import physical_lab_credibility as credibility
import physical_lab_cross_checks as cross_checks
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import plain, utc_now

SNAPSHOT_SCHEMA = "physical-lab-evidence-snapshot-v1"
DIFF_SCHEMA = "physical-lab-evidence-diff-v1"
SNAPSHOT_VERSION = 1


def _sha(value: Any) -> str:
    raw = json.dumps(plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(plain(dict(value)), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _snapshot_dir(project_dir: Path) -> Path:
    path = project_dir / "provenance" / "evidence-snapshots"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_evidence_snapshot(project_dir: str | Path, *, label: str = "", generated_at: str | None = None) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    passport = credibility.build_credibility_passport(path, generated_at=generated_at)
    claim_matrix = claims.claim_evidence_matrix(path)
    cross_matrix = cross_checks.cross_check_matrix(path)
    graph = passport.get("evidence_graph") or {}
    graph_nodes = [
        {
            "id": row.get("id"),
            "kind": row.get("type") or row.get("kind"),
            "sha256": row.get("sha256"),
            "label": row.get("label"),
        }
        for row in graph.get("nodes") or [] if isinstance(row, Mapping)
    ]
    graph_nodes.sort(key=lambda row: (str(row.get("kind") or ""), str(row.get("id") or "")))
    factors = [
        {
            "factor_id": row.get("factor_id"),
            "status": row.get("status"),
            "gaps": list(row.get("gaps") or []),
        }
        for row in passport.get("factors") or [] if isinstance(row, Mapping)
    ]
    factors.sort(key=lambda row: str(row.get("factor_id") or ""))
    claim_rows = [
        {
            "claim_id": row.get("claim_id"),
            "status": row.get("status"),
            "evaluation_sha256": row.get("evaluation_sha256"),
            "statement": row.get("statement"),
        }
        for row in claim_matrix.get("claims") or [] if isinstance(row, Mapping)
    ]
    claim_rows.sort(key=lambda row: str(row.get("claim_id") or ""))
    cross_rows = [
        {
            "cross_check_id": row.get("cross_check_id"),
            "status": row.get("status"),
            "evaluation_sha256": row.get("evaluation_sha256"),
            "observable": row.get("observable"),
        }
        for row in cross_matrix.get("cross_checks") or [] if isinstance(row, Mapping)
    ]
    cross_rows.sort(key=lambda row: str(row.get("cross_check_id") or ""))
    stable = {
        "schema": SNAPSHOT_SCHEMA,
        "snapshot_version": SNAPSHOT_VERSION,
        "project_id": project.get("project_id"),
        "label": str(label),
        "passport_sha256": passport.get("passport_sha256"),
        "evidence_graph_sha256": passport.get("evidence_graph_sha256"),
        "claim_matrix_sha256": claim_matrix.get("matrix_sha256"),
        "cross_check_matrix_sha256": cross_matrix.get("matrix_sha256"),
        "factors": factors,
        "graph_nodes": graph_nodes,
        "claims": claim_rows,
        "cross_checks": cross_rows,
    }
    return {
        **stable,
        "generated_at": generated_at or utc_now(),
        "snapshot_sha256": _sha(stable),
        "coverage": passport.get("coverage") or {},
        "claim_status_counts": claim_matrix.get("status_counts") or {},
        "cross_check_status_counts": cross_matrix.get("status_counts") or {},
        "boundary": "Evidence snapshots preserve review state only. A fingerprint change is not itself proof that a scientific conclusion changed.",
    }


def write_evidence_snapshot(project_dir: str | Path, *, label: str = "", generated_at: str | None = None) -> tuple[Path, dict[str, Any]]:
    path = Path(project_dir).expanduser().resolve()
    snapshot = build_evidence_snapshot(path, label=label, generated_at=generated_at)
    target = _snapshot_dir(path) / f"evidence-snapshot-{str(snapshot['snapshot_sha256'])[:16]}.json"
    _atomic_json(target, snapshot)
    return target, snapshot


def load_evidence_snapshot(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).expanduser().resolve().read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != SNAPSHOT_SCHEMA:
        raise ValueError("not a Physical Lab evidence snapshot")
    return value


def _index(rows: list[Mapping[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {
        str(row.get(key)): dict(row)
        for row in rows
        if isinstance(row, Mapping) and str(row.get(key) or "")
    }


def _transition_rows(before: Mapping[str, Any], after: Mapping[str, Any], *, key: str, status_key: str = "status") -> dict[str, Any]:
    before_ids = set(before)
    after_ids = set(after)
    added = sorted(after_ids - before_ids)
    removed = sorted(before_ids - after_ids)
    changed = []
    for item_id in sorted(before_ids & after_ids):
        left = before[item_id]
        right = after[item_id]
        if left != right:
            changed.append({
                key: item_id,
                "before_status": left.get(status_key),
                "after_status": right.get(status_key),
                "before_sha256": left.get("evaluation_sha256") or left.get("sha256"),
                "after_sha256": right.get("evaluation_sha256") or right.get("sha256"),
            })
    return {"added": added, "removed": removed, "changed": changed}


def diff_evidence_snapshots(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    if before.get("schema") != SNAPSHOT_SCHEMA or after.get("schema") != SNAPSHOT_SCHEMA:
        raise ValueError("both inputs must be Physical Lab evidence snapshots")
    if str(before.get("project_id") or "") != str(after.get("project_id") or ""):
        raise ValueError("evidence snapshots belong to different projects")

    before_factors = _index(list(before.get("factors") or []), "factor_id")
    after_factors = _index(list(after.get("factors") or []), "factor_id")
    factor_transitions = []
    factor_gap_changes = []
    for factor_id in sorted(set(before_factors) | set(after_factors)):
        left = before_factors.get(factor_id)
        right = after_factors.get(factor_id)
        left_status = (left or {}).get("status")
        right_status = (right or {}).get("status")
        if left_status != right_status:
            factor_transitions.append({"factor_id": factor_id, "before": left_status, "after": right_status})
        left_gaps = set(str(x) for x in (left or {}).get("gaps") or [])
        right_gaps = set(str(x) for x in (right or {}).get("gaps") or [])
        if left_gaps != right_gaps:
            factor_gap_changes.append({
                "factor_id": factor_id,
                "added_gaps": sorted(right_gaps - left_gaps),
                "resolved_gaps": sorted(left_gaps - right_gaps),
            })

    before_nodes = _index(list(before.get("graph_nodes") or []), "id")
    after_nodes = _index(list(after.get("graph_nodes") or []), "id")
    graph_changes = _transition_rows(before_nodes, after_nodes, key="id", status_key="kind")
    before_claims = _index(list(before.get("claims") or []), "claim_id")
    after_claims = _index(list(after.get("claims") or []), "claim_id")
    claim_changes = _transition_rows(before_claims, after_claims, key="claim_id")
    before_cross = _index(list(before.get("cross_checks") or []), "cross_check_id")
    after_cross = _index(list(after.get("cross_checks") or []), "cross_check_id")
    cross_changes = _transition_rows(before_cross, after_cross, key="cross_check_id")

    stable = {
        "schema": DIFF_SCHEMA,
        "project_id": before.get("project_id"),
        "before_snapshot_sha256": before.get("snapshot_sha256"),
        "after_snapshot_sha256": after.get("snapshot_sha256"),
        "passport_changed": before.get("passport_sha256") != after.get("passport_sha256"),
        "graph_changed": before.get("evidence_graph_sha256") != after.get("evidence_graph_sha256"),
        "claim_matrix_changed": before.get("claim_matrix_sha256") != after.get("claim_matrix_sha256"),
        "cross_check_matrix_changed": before.get("cross_check_matrix_sha256") != after.get("cross_check_matrix_sha256"),
        "factor_transitions": factor_transitions,
        "factor_gap_changes": factor_gap_changes,
        "graph_changes": graph_changes,
        "claim_changes": claim_changes,
        "cross_check_changes": cross_changes,
    }
    change_count = (
        len(factor_transitions)
        + len(factor_gap_changes)
        + len(graph_changes["added"]) + len(graph_changes["removed"]) + len(graph_changes["changed"])
        + len(claim_changes["added"]) + len(claim_changes["removed"]) + len(claim_changes["changed"])
        + len(cross_changes["added"]) + len(cross_changes["removed"]) + len(cross_changes["changed"])
    )
    return {
        **stable,
        "change_count": change_count,
        "diff_sha256": _sha(stable),
        "boundary": "Evidence diffs report traceability/readiness changes. They do not determine whether a scientific claim became true or false.",
    }


def render_evidence_diff_markdown(diff: Mapping[str, Any]) -> str:
    lines = [
        "# Physical Lab Evidence Diff",
        "",
        f"- Project: `{diff.get('project_id')}`",
        f"- Before: `{diff.get('before_snapshot_sha256')}`",
        f"- After: `{diff.get('after_snapshot_sha256')}`",
        f"- Diff fingerprint: `{diff.get('diff_sha256')}`",
        f"- Detected review-state changes: **{diff.get('change_count', 0)}**",
        "",
        "## Factor transitions",
        "",
    ]
    transitions = diff.get("factor_transitions") or []
    if transitions:
        lines += [f"- `{row.get('factor_id')}`: **{row.get('before')} → {row.get('after')}**" for row in transitions]
    else:
        lines.append("- No factor status transition detected.")
    lines += ["", "## Claim changes", ""]
    cc = diff.get("claim_changes") or {}
    for row in cc.get("changed") or []:
        lines.append(f"- `{row.get('claim_id')}`: **{row.get('before_status')} → {row.get('after_status')}**")
    for cid in cc.get("added") or []:
        lines.append(f"- Added claim `{cid}`")
    for cid in cc.get("removed") or []:
        lines.append(f"- Removed claim `{cid}`")
    if not (cc.get("changed") or cc.get("added") or cc.get("removed")):
        lines.append("- No claim readiness/fingerprint change detected.")
    lines += ["", "## Cross-check changes", ""]
    xc = diff.get("cross_check_changes") or {}
    for row in xc.get("changed") or []:
        lines.append(f"- `{row.get('cross_check_id')}`: **{row.get('before_status')} → {row.get('after_status')}**")
    for cid in xc.get("added") or []:
        lines.append(f"- Added cross-check `{cid}`")
    for cid in xc.get("removed") or []:
        lines.append(f"- Removed cross-check `{cid}`")
    if not (xc.get("changed") or xc.get("added") or xc.get("removed")):
        lines.append("- No cross-check readiness/fingerprint change detected.")
    lines += ["", "## Scientific boundary", "", str(diff.get("boundary") or ""), ""]
    return "\n".join(lines)
