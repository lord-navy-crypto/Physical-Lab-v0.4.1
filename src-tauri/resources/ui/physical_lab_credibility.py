"""Evidence-first Credibility Passports for Physical Lab projects.

The passport assembles project-local evidence into factor-by-factor readiness
records using public modeling-and-simulation credibility vocabulary. It never
converts evidence into a synthetic overall credibility score and it never treats
simulation-only evidence as experimental validation.

The factor names mirror the eight-factor vocabulary published with NASA's
modeling-and-simulation credibility guidance, but Physical Lab does not claim a
NASA assessment, NASA-STD-7009 compliance, ASME compliance, accreditation, or
certification. Intended-use sufficiency remains a human/project decision.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import plain, utc_now

PASSPORT_SCHEMA = "physical-lab-credibility-passport-v1"
GRAPH_SCHEMA = "physical-lab-evidence-graph-v1"
PASSPORT_VERSION = 1
STATUSES = ("PRESENT", "PARTIAL", "MISSING")

FACTOR_DEFINITIONS = (
    ("data_pedigree", "Data pedigree"),
    ("verification", "Verification"),
    ("validation", "Validation"),
    ("input_pedigree", "Input pedigree"),
    ("uncertainty_characterization", "Uncertainty characterization"),
    ("results_robustness", "Results robustness"),
    ("ms_history", "M&S history"),
    ("process_management", "M&S process / product management"),
)

REFERENCE_TOKENS = ("reference", "analytic", "exact", "benchmark", "verification", "convergence")
VALIDATION_TOKENS = ("measurement", "measured", "referent", "validation", "residual", "rmse", "mae", "comparison")
ROBUSTNESS_TOKENS = ("robust", "sensitivity", "spread", "rhat", "effective_samples", "replicate", "timestep", "relative_change", "tolerance", "convergence", "pareto")
SOURCE_TOKENS = ("source", "reference", "measurement_id", "calibration_id", "sha256", "doi", "citation", "asset")
UNCERTAINTY_TOKENS = ("uncertainty", "sigma", "standard_deviation", "std", "distribution", "tolerance", "confidence", "interval")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _sha(value: Any) -> str:
    raw = json.dumps(plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _keys(value: Any, prefix: str = "", limit: int = 1200) -> set[str]:
    out: set[str] = set()

    def visit(item: Any, path: str) -> None:
        if len(out) >= limit:
            return
        if isinstance(item, Mapping):
            for key, child in list(item.items())[:250]:
                name = str(key).lower()
                joined = f"{path}.{name}" if path else name
                out.add(joined)
                visit(child, joined)
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(list(item)[:100]):
                visit(child, f"{path}[{index}]")

    visit(value, prefix)
    return out


def _has(keys: Iterable[str], tokens: Iterable[str]) -> bool:
    values = tuple(str(k).lower() for k in keys)
    return any(any(str(token).lower() in key for key in values) for token in tokens)


def _factor(fid: str, title: str, status: str, evidence: list[dict[str, Any]], gaps: list[str], rationale: str) -> dict[str, Any]:
    if status not in STATUSES:
        raise ValueError(f"invalid factor status: {status}")
    return {
        "factor_id": fid,
        "title": title,
        "status": status,
        "evidence": plain(evidence),
        "gaps": [str(x) for x in gaps],
        "rationale": str(rationale),
    }


def _manifests(path: Path, project: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for exp_id, item in (project.get("experiments") or {}).items():
        if not isinstance(item, Mapping) or not item.get("manifest_path"):
            continue
        manifest = _read_json(path / str(item["manifest_path"]))
        if manifest:
            out[str(exp_id)] = manifest
    return out


def _evidence_records(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mi = _read_json(path / "measurements" / "index.json") or {}
    ci = _read_json(path / "calibration" / "index.json") or {}
    measurements = [dict(v) for v in (mi.get("measurements") or {}).values() if isinstance(v, Mapping)]
    calibrations = [dict(v) for v in (ci.get("calibrations") or {}).values() if isinstance(v, Mapping)]
    return measurements, calibrations


def _result_summaries(project: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(v) for v in (project.get("results") or {}).values() if isinstance(v, Mapping)]


def _data_pedigree(measurements: list[dict[str, Any]], calibrations: list[dict[str, Any]]) -> dict[str, Any]:
    if not measurements:
        return _factor("data_pedigree", "Data pedigree", "MISSING", [], ["No measurement/referent asset is registered."], "No project-local referent data are available.")
    complete = [m for m in measurements if len(str(m.get("sha256") or "")) == 64 and str(m.get("instrument") or "").strip() and str(m.get("captured_at") or "").strip()]
    evidence = [{"kind": "measurement", "id": m.get("measurement_id"), "sha256": m.get("sha256"), "instrument": m.get("instrument"), "captured_at": m.get("captured_at")} for m in measurements[:30]]
    evidence += [{"kind": "calibration", "id": c.get("calibration_id"), "instrument": c.get("instrument"), "reference": c.get("reference")} for c in calibrations[:30]]
    if len(complete) == len(measurements) and calibrations:
        return _factor("data_pedigree", "Data pedigree", "PRESENT", evidence, [], "Measurement assets are fingerprinted with source context and calibration evidence is registered.")
    gaps = []
    if len(complete) != len(measurements):
        gaps.append("Some measurement assets lack a SHA-256 fingerprint, instrument, or capture/run context.")
    if not calibrations:
        gaps.append("No calibration evidence is registered.")
    return _factor("data_pedigree", "Data pedigree", "PARTIAL", evidence, gaps, "Measurement evidence exists, but its pedigree is incomplete.")


def _verification(project: Mapping[str, Any], manifests: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    results = _result_summaries(project)
    result_keys = _keys([r.get("summary") or {} for r in results])
    succeeded = [j for j in (project.get("jobs") or {}).values() if isinstance(j, Mapping) and j.get("status") == "succeeded"]
    hashes_ok = all(len(str((project.get("experiments") or {}).get(eid, {}).get("experiment_sha256") or "")) == 64 for eid in manifests) if manifests else False
    reference_check = _has(result_keys, REFERENCE_TOKENS)
    evidence = []
    if manifests:
        evidence.append({"kind": "experiment-fingerprints", "count": len(manifests), "all_sha256": hashes_ok})
    if succeeded:
        evidence.append({"kind": "successful-compute-jobs", "count": len(succeeded)})
    if reference_check:
        evidence.append({"kind": "verification-result-signals", "tokens_detected": True})
    if hashes_ok and succeeded and reference_check:
        return _factor("verification", "Verification", "PRESENT", evidence, [], "Scientific identities, successful executions, and reference/convergence-style verification evidence are all discoverable.")
    if manifests or succeeded or reference_check:
        gaps = []
        if not reference_check:
            gaps.append("No analytic/exact/reference/benchmark/convergence verification signal is indexed in result summaries.")
        if not succeeded:
            gaps.append("No successful compute job is indexed.")
        return _factor("verification", "Verification", "PARTIAL", evidence, gaps, "Some computational verification evidence exists, but the chain is incomplete.")
    return _factor("verification", "Verification", "MISSING", [], ["No registered experiment execution or verification evidence."], "No computational verification chain is discoverable.")


def _validation(project: Mapping[str, Any], measurements: list[dict[str, Any]], calibrations: list[dict[str, Any]]) -> dict[str, Any]:
    result_keys = _keys([r.get("summary") or {} for r in _result_summaries(project)])
    comparison = _has(result_keys, VALIDATION_TOKENS)
    evidence = []
    if measurements:
        evidence.append({"kind": "referent-data", "count": len(measurements)})
    if comparison:
        evidence.append({"kind": "model-to-referent-comparison", "detected": True})
    if calibrations:
        evidence.append({"kind": "calibration", "count": len(calibrations)})
    if measurements and comparison and calibrations:
        return _factor("validation", "Validation", "PRESENT", evidence, [], "Project evidence contains referent data, calibration context, and model-to-referent comparison metrics.")
    if measurements or comparison:
        gaps = []
        if not measurements:
            gaps.append("A comparison-like result exists without registered referent/measurement evidence.")
        if not comparison:
            gaps.append("Measurement evidence exists but no model-to-referent comparison metric is indexed.")
        if not calibrations:
            gaps.append("Referent calibration evidence is not registered.")
        return _factor("validation", "Validation", "PARTIAL", evidence, gaps, "The validation evidence chain is incomplete.")
    return _factor("validation", "Validation", "MISSING", [], ["No referent measurement and comparison evidence is linked."], "Simulation results alone are not treated as experimental validation.")


def _input_pedigree(manifests: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if not manifests:
        return _factor("input_pedigree", "Input pedigree", "MISSING", [], ["No experiment manifests are registered."], "No traceable input records are available.")
    with_inputs = 0
    traceable = 0
    evidence = []
    for exp_id, manifest in manifests.items():
        inputs = manifest.get("inputs") or {}
        if inputs:
            with_inputs += 1
        if inputs and _has(_keys(inputs), SOURCE_TOKENS):
            traceable += 1
        evidence.append({"kind": "experiment-inputs", "experiment_id": exp_id, "input_count": len(inputs) if isinstance(inputs, Mapping) else 0, "source_metadata": bool(inputs and _has(_keys(inputs), SOURCE_TOKENS))})
    if with_inputs == len(manifests) and traceable == len(manifests):
        return _factor("input_pedigree", "Input pedigree", "PRESENT", evidence, [], "All scoped manifests contain inputs with source/reference/measurement provenance fields.")
    if with_inputs:
        return _factor("input_pedigree", "Input pedigree", "PARTIAL", evidence, ["Some experiment inputs lack explicit source/reference/measurement provenance."], "Inputs are recorded, but pedigree metadata is incomplete.")
    return _factor("input_pedigree", "Input pedigree", "MISSING", evidence, ["Registered manifests contain no explicit input records."], "Model parameters exist, but no external/input pedigree is recorded.")


def _uncertainty(manifests: Mapping[str, Mapping[str, Any]], project: Mapping[str, Any], calibrations: list[dict[str, Any]]) -> dict[str, Any]:
    manifest_uq = [eid for eid, m in manifests.items() if isinstance(m.get("uncertainty"), Mapping) and m.get("uncertainty")]
    result_uq = _has(_keys([r.get("summary") or {} for r in _result_summaries(project)]), UNCERTAINTY_TOKENS)
    evidence = []
    if manifest_uq:
        evidence.append({"kind": "manifest-uncertainty", "experiments": manifest_uq})
    if calibrations:
        evidence.append({"kind": "calibration-uncertainty", "count": len(calibrations)})
    if result_uq:
        evidence.append({"kind": "result-uncertainty", "detected": True})
    if manifest_uq and result_uq and calibrations:
        return _factor("uncertainty_characterization", "Uncertainty characterization", "PRESENT", evidence, [], "Input/measurement uncertainty and result-side uncertainty evidence are both represented.")
    if manifest_uq or result_uq or calibrations:
        return _factor("uncertainty_characterization", "Uncertainty characterization", "PARTIAL", evidence, ["Uncertainty sources and propagated/result uncertainty are not both fully represented."], "Some uncertainty evidence exists, but the characterization chain is incomplete.")
    return _factor("uncertainty_characterization", "Uncertainty characterization", "MISSING", [], ["No explicit uncertainty record or uncertainty-bearing result metric is indexed."], "Uncertainty is not explicitly characterized in project evidence.")


def _robustness(project: Mapping[str, Any]) -> dict[str, Any]:
    keys = _keys([r.get("summary") or {} for r in _result_summaries(project)])
    present = _has(keys, ROBUSTNESS_TOKENS)
    if present:
        return _factor("results_robustness", "Results robustness", "PRESENT", [{"kind": "sensitivity-or-stability-metrics", "detected": True}], [], "Sensitivity, replicate, tolerance, convergence, or stability evidence is indexed in result summaries.")
    if project.get("results"):
        return _factor("results_robustness", "Results robustness", "PARTIAL", [{"kind": "results", "count": len(project.get("results") or {})}], ["Results exist but no explicit sensitivity/stability/robustness metric is indexed."], "Completed results exist without an explicit robustness study.")
    return _factor("results_robustness", "Results robustness", "MISSING", [], ["No completed result evidence is indexed."], "No result robustness evidence is discoverable.")


def _history(project: Mapping[str, Any]) -> dict[str, Any]:
    experiments = len(project.get("experiments") or {})
    jobs = len(project.get("jobs") or {})
    results = len(project.get("results") or {})
    evidence = [{"kind": "project-history", "experiments": experiments, "jobs": jobs, "results": results}]
    if results >= 2 or experiments >= 2:
        return _factor("ms_history", "M&S history", "PRESENT", evidence, [], "Multiple experiment/result records provide reusable execution history.")
    if experiments or jobs or results:
        return _factor("ms_history", "M&S history", "PARTIAL", evidence, ["Only a single/limited execution history is available."], "A project record exists, but comparative/regression history is still limited.")
    return _factor("ms_history", "M&S history", "MISSING", evidence, ["No registered experiment/job/result history."], "No reusable modeling-and-simulation history is indexed.")


def _process(project: Mapping[str, Any], manifests: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    question = bool(str(project.get("research_question") or "").strip())
    source_commits = [str((m.get("provenance") or {}).get("source_commit") or "") for m in manifests.values()]
    source_pinned = bool(source_commits) and all(len(value) >= 7 for value in source_commits)
    exp_hashes = bool(manifests) and all(len(str(m.get("experiment_sha256") or "")) == 64 for m in manifests.values())
    jobs = [j for j in (project.get("jobs") or {}).values() if isinstance(j, Mapping)]
    logs = bool(jobs) and all(bool(j.get("log_path")) for j in jobs)
    results = [r for r in (project.get("results") or {}).values() if isinstance(r, Mapping)]
    result_hashes = bool(results) and all(len(str(r.get("result_sha256") or "")) == 64 for r in results)
    checks = {"research_question": question, "source_revision": source_pinned, "experiment_fingerprint": exp_hashes, "job_records": bool(jobs), "log_references": logs, "result_fingerprints": result_hashes}
    evidence = [{"kind": "process-controls", **checks}]
    count = sum(1 for value in checks.values() if value)
    if count == len(checks):
        return _factor("process_management", "M&S process / product management", "PRESENT", evidence, [], "Purpose, source revision, experiment identity, executions, logs, and result fingerprints are all managed.")
    gaps = [name.replace("_", " ") for name, value in checks.items() if not value]
    return _factor("process_management", "M&S process / product management", "PARTIAL" if count else "MISSING", evidence, [f"Missing managed evidence: {', '.join(gaps)}."], "Process/product management evidence is incomplete." if count else "No managed M&S process evidence is available.")


def build_evidence_graph(project_dir: str | Path, *, experiment_id: str | None = None, job_id: str | None = None) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    measurements, calibrations = _evidence_records(path)
    project_id = str(project.get("project_id") or "project")
    nodes: list[dict[str, Any]] = [{"id": project_id, "type": "project", "label": str(project.get("name") or project_id)}]
    edges: list[dict[str, str]] = []
    for exp_id, item in sorted((project.get("experiments") or {}).items()):
        if not isinstance(item, Mapping):
            continue
        nodes.append({"id": str(exp_id), "type": "experiment", "label": str(item.get("model") or exp_id), "sha256": item.get("experiment_sha256")})
        edges.append({"source": project_id, "target": str(exp_id), "relation": "contains"})
    for jid, item in sorted((project.get("jobs") or {}).items()):
        if not isinstance(item, Mapping):
            continue
        nodes.append({"id": str(jid), "type": "job", "label": str(item.get("runner") or jid), "status": item.get("status")})
        if item.get("experiment_id"):
            edges.append({"source": str(item["experiment_id"]), "target": str(jid), "relation": "executed-as"})
    for jid, item in sorted((project.get("results") or {}).items()):
        if not isinstance(item, Mapping):
            continue
        rid = f"result:{jid}"
        nodes.append({"id": rid, "type": "result", "label": str(jid), "sha256": item.get("result_sha256")})
        edges.append({"source": str(jid), "target": rid, "relation": "produced"})
    for row in measurements:
        mid = str(row.get("measurement_id") or "")
        if not mid:
            continue
        nodes.append({"id": mid, "type": "measurement", "label": str(row.get("file_name") or mid), "sha256": row.get("sha256")})
        edges.append({"source": project_id, "target": mid, "relation": "has-evidence"})
    for row in calibrations:
        cid = str(row.get("calibration_id") or "")
        if not cid:
            continue
        nodes.append({"id": cid, "type": "calibration", "label": str(row.get("parameter") or cid)})
        edges.append({"source": project_id, "target": cid, "relation": "has-calibration"})
        for mid in row.get("related_measurements") or []:
            edges.append({"source": cid, "target": str(mid), "relation": "calibrates-evidence"})
    scope = {"experiment_id": experiment_id, "job_id": job_id}
    stable = {"schema": GRAPH_SCHEMA, "project_id": project_id, "scope": scope, "nodes": nodes, "edges": edges}
    return {**stable, "graph_sha256": _sha(stable), "boundary": "Traceability relationships only; graph edges do not establish scientific validity or causality."}


def build_credibility_passport(project_dir: str | Path, *, experiment_id: str | None = None, job_id: str | None = None, generated_at: str | None = None) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    manifests = _manifests(path, project)
    if experiment_id:
        if experiment_id not in manifests:
            raise ValueError(f"unknown experiment_id: {experiment_id}")
        manifests = {experiment_id: manifests[experiment_id]}
    if job_id:
        job = (project.get("jobs") or {}).get(job_id)
        if not isinstance(job, Mapping):
            raise ValueError(f"unknown job_id: {job_id}")
        linked = str(job.get("experiment_id") or "")
        if linked and linked in manifests:
            manifests = {linked: manifests[linked]}
        experiment_id = linked or experiment_id
    measurements, calibrations = _evidence_records(path)
    factors = [
        _data_pedigree(measurements, calibrations),
        _verification(project, manifests),
        _validation(project, measurements, calibrations),
        _input_pedigree(manifests),
        _uncertainty(manifests, project, calibrations),
        _robustness(project),
        _history(project),
        _process(project, manifests),
    ]
    coverage = {status.lower(): sum(1 for row in factors if row["status"] == status) for status in STATUSES}
    graph = build_evidence_graph(path, experiment_id=experiment_id, job_id=job_id)
    stable = {
        "schema": PASSPORT_SCHEMA,
        "passport_version": PASSPORT_VERSION,
        "project_id": project.get("project_id"),
        "project_name": project.get("name"),
        "research_question": project.get("research_question"),
        "scope": {"experiment_id": experiment_id, "job_id": job_id},
        "factors": factors,
        "coverage": coverage,
        "evidence_graph_sha256": graph["graph_sha256"],
    }
    return {
        **stable,
        "generated_at": generated_at or utc_now(),
        "passport_sha256": _sha(stable),
        "evidence_graph": graph,
        "decision_note": "No aggregate credibility score is produced. Factor sufficiency depends on intended use, risk, domain guidance, and project-defined thresholds.",
        "boundary": "Physical Lab Credibility Passport is an evidence-readiness and traceability aid. It is not a NASA-STD-7009 assessment, ASME VVUQ compliance determination, experimental validation certificate, or product certification.",
    }


def render_passport_markdown(passport: Mapping[str, Any]) -> str:
    coverage = passport.get("coverage") or {}
    lines = [
        f"# Physical Lab Credibility Passport · {passport.get('project_name') or passport.get('project_id')}",
        "",
        f"- Passport fingerprint: `{passport.get('passport_sha256')}`",
        f"- Evidence graph fingerprint: `{passport.get('evidence_graph_sha256')}`",
        f"- Generated: {passport.get('generated_at')}",
        "",
        "## Evidence coverage",
        "",
        f"PRESENT: {coverage.get('present', 0)} · PARTIAL: {coverage.get('partial', 0)} · MISSING: {coverage.get('missing', 0)}",
        "",
        "**No aggregate credibility score is defined or reported.**",
        "",
        "| Factor | Status | Rationale |",
        "|---|---|---|",
    ]
    for factor in passport.get("factors") or []:
        if isinstance(factor, Mapping):
            lines.append(f"| {factor.get('title')} | **{factor.get('status')}** | {str(factor.get('rationale') or '').replace('|', '\\|')} |")
    lines += ["", "## Evidence gaps", ""]
    gaps = []
    for factor in passport.get("factors") or []:
        if isinstance(factor, Mapping):
            gaps += [f"- **{factor.get('title')}** — {gap}" for gap in factor.get("gaps") or []]
    lines += gaps or ["- No automatically detected gaps. Domain review is still required."]
    lines += ["", "## Decision boundary", "", str(passport.get("decision_note") or ""), "", "## Standards/scientific boundary", "", str(passport.get("boundary") or ""), ""]
    return "\n".join(lines)


def write_credibility_passport(project_dir: str | Path, *, experiment_id: str | None = None, job_id: str | None = None, generated_at: str | None = None) -> tuple[Path, Path, dict[str, Any]]:
    path = Path(project_dir).expanduser().resolve()
    passport = build_credibility_passport(path, experiment_id=experiment_id, job_id=job_id, generated_at=generated_at)
    prefix = str(passport["passport_sha256"])[:16]
    json_dir = path / "provenance" / "credibility-passports"
    json_dir.mkdir(parents=True, exist_ok=True)
    md_dir = path / "reports"
    md_dir.mkdir(parents=True, exist_ok=True)
    json_path = json_dir / f"credibility-passport-{prefix}.json"
    md_path = md_dir / f"credibility-passport-{prefix}.md"
    tmp = json_path.with_suffix(json_path.suffix + ".tmp")
    tmp.write_text(json.dumps(plain(passport), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, json_path)
    tmp_md = md_path.with_suffix(md_path.suffix + ".tmp")
    tmp_md.write_text(render_passport_markdown(passport), encoding="utf-8")
    os.replace(tmp_md, md_path)
    return json_path, md_path, passport


def passport_summary(passport: Mapping[str, Any]) -> dict[str, Any]:
    coverage = passport.get("coverage") or {}
    return {
        "project_id": passport.get("project_id"),
        "passport_sha256": passport.get("passport_sha256"),
        "graph_sha256": passport.get("evidence_graph_sha256"),
        "factor_count": len(passport.get("factors") or []),
        "present": int(coverage.get("present") or 0),
        "partial": int(coverage.get("partial") or 0),
        "missing": int(coverage.get("missing") or 0),
        "aggregate_credibility_score": None,
        "boundary": "Evidence coverage summary only; no aggregate credibility score is defined.",
    }
