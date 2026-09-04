"""Physical Lab .physlab Project Kernel v1.

A .physlab directory is the project-level system of record above Experiment Kernel
manifests and Compute Engine jobs. The kernel stores small JSON metadata and
portable references; it does not duplicate large scientific result arrays.

Project flow:
    Project -> Experiment manifest -> Job reference -> Result reference -> Report

Scientific boundaries:
- Experiment identity remains owned by physical_lab_experiment_kernel.
- Compute results remain owned by the Compute Engine job store.
- Project PASS/REVIEW records are indexes and provenance, not certification.
- v1 migrations are deterministic and never silently reinterpret scientific data.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Mapping

from physical_lab_experiment_kernel import (
    build_session_manifest,
    plain,
    sha256_json,
    utc_now,
    validate_manifest,
)

PROJECT_SCHEMA = "physical-lab-project-v1"
PROJECT_VERSION = 1
LEGACY_PROJECT_SCHEMA = "physical-lab-project-v0"
ACTIVE_PROJECT_SESSION_KEY = "pl_active_project_path"


def _data_dir() -> Path | None:
    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
    if not raw:
        return None
    root = Path(raw).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def projects_root() -> Path | None:
    root = _data_dir()
    if root is None:
        return None
    path = root / "projects"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _slugify(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip()).strip("-._").lower()
    return (text or "physical-lab-project")[:72]


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(plain(dict(value)), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _project_json(project_dir: Path) -> Path:
    return project_dir / "project.json"


def _ensure_structure(project_dir: Path) -> None:
    for name in ("experiments", "jobs", "results", "measurements", "calibration", "reports", "provenance"):
        (project_dir / name).mkdir(parents=True, exist_ok=True)


def _portable_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    root = _data_dir()
    if root is not None:
        try:
            return resolved.relative_to(root).as_posix()
        except ValueError:
            pass
    return str(resolved)


def _resolve_reference(reference: str) -> Path:
    path = Path(str(reference)).expanduser()
    if path.is_absolute():
        return path
    root = _data_dir()
    return (root / path) if root is not None else path


def new_project_document(
    name: str,
    *,
    project_id: str | None = None,
    description: str = "",
    research_question: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    now = created_at or utc_now()
    return {
        "schema": PROJECT_SCHEMA,
        "project_version": PROJECT_VERSION,
        "project_id": project_id or f"plproj-{uuid.uuid4().hex}",
        "name": str(name).strip() or "Physical Lab Project",
        "slug": _slugify(name),
        "description": str(description),
        "research_question": str(research_question),
        "created_at": now,
        "updated_at": now,
        "profiles": [],
        "experiments": {},
        "jobs": {},
        "results": {},
        "reports": [],
        "migration": {"current_version": PROJECT_VERSION, "history": []},
        "boundary": (
            "Project metadata and provenance index only. Scientific validity remains governed by each experiment, "
            "solver, measurement and V&V record; project membership does not certify a result."
        ),
    }


def migrate_project_document(document: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Deterministically migrate supported legacy metadata to Project v1."""
    doc = plain(dict(document))
    if doc.get("schema") == PROJECT_SCHEMA and int(doc.get("project_version") or 0) == PROJECT_VERSION:
        return dict(doc), []
    if doc.get("schema") != LEGACY_PROJECT_SCHEMA:
        raise ValueError(f"unsupported project schema: {doc.get('schema')!r}")
    migrated = new_project_document(
        str(doc.get("name") or "Physical Lab Project"),
        project_id=str(doc.get("project_id") or f"plproj-{uuid.uuid4().hex}"),
        description=str(doc.get("description") or ""),
        research_question=str(doc.get("research_question") or ""),
        created_at=str(doc.get("created_at") or utc_now()),
    )
    migrated["experiments"] = dict(doc.get("experiments") or {})
    migrated["jobs"] = dict(doc.get("jobs") or {})
    migrated["profiles"] = sorted({
        str(item.get("profile"))
        for item in migrated["experiments"].values()
        if isinstance(item, Mapping) and item.get("profile")
    })
    migrated["updated_at"] = str(doc.get("updated_at") or migrated["created_at"])
    migrated["migration"]["history"].append({
        "from": LEGACY_PROJECT_SCHEMA,
        "to": PROJECT_SCHEMA,
        "note": "Metadata-only v0 to v1 migration; scientific payloads were not reinterpreted.",
    })
    return migrated, [f"migrated {LEGACY_PROJECT_SCHEMA} -> {PROJECT_SCHEMA}"]


def validate_project_document(document: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if document.get("schema") != PROJECT_SCHEMA:
        errors.append(f"schema must be {PROJECT_SCHEMA}")
    if int(document.get("project_version") or 0) != PROJECT_VERSION:
        errors.append(f"project_version must be {PROJECT_VERSION}")
    if not str(document.get("project_id") or "").startswith("plproj-"):
        errors.append("project_id must start with plproj-")
    if not str(document.get("name") or "").strip():
        errors.append("project name is required")
    for key in ("experiments", "jobs", "results"):
        if not isinstance(document.get(key), Mapping):
            errors.append(f"{key} must be an object")
    if not isinstance(document.get("reports"), list):
        errors.append("reports must be a list")
    if not document.get("research_question"):
        warnings.append("research question is not set")
    return {"valid": not errors, "errors": errors, "warnings": warnings}


def create_project(
    name: str,
    *,
    description: str = "",
    research_question: str = "",
    slug: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    root = projects_root()
    if root is None:
        raise RuntimeError("PHYSICAL_LAB_DATA_DIR is not configured")
    base = _slugify(slug or name)
    project_dir = root / f"{base}.physlab"
    if project_dir.exists():
        raise FileExistsError(project_dir)
    _ensure_structure(project_dir)
    doc = new_project_document(name, description=description, research_question=research_question)
    doc["slug"] = base
    _atomic_json(_project_json(project_dir), doc)
    return project_dir, doc


def open_project(project_dir: str | Path, *, migrate: bool = True) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    document = _read_json(_project_json(path))
    if document is None:
        raise FileNotFoundError(_project_json(path))
    if document.get("schema") != PROJECT_SCHEMA or int(document.get("project_version") or 0) != PROJECT_VERSION:
        if not migrate:
            raise ValueError("project requires migration")
        document, _ = migrate_project_document(document)
        _ensure_structure(path)
        _atomic_json(_project_json(path), document)
    check = validate_project_document(document)
    if not check["valid"]:
        raise ValueError("invalid project: " + "; ".join(check["errors"]))
    _ensure_structure(path)
    return document


def save_project(project_dir: str | Path, document: Mapping[str, Any], *, touch: bool = True) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    doc = plain(dict(document))
    if touch:
        doc["updated_at"] = utc_now()
    check = validate_project_document(doc)
    if not check["valid"]:
        raise ValueError("invalid project: " + "; ".join(check["errors"]))
    _ensure_structure(path)
    _atomic_json(_project_json(path), doc)
    return doc


def list_projects() -> list[dict[str, Any]]:
    root = projects_root()
    if root is None:
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.physlab")):
        doc = _read_json(_project_json(path))
        if not doc:
            continue
        try:
            if doc.get("schema") != PROJECT_SCHEMA:
                doc, _ = migrate_project_document(doc)
        except Exception:
            continue
        rows.append({
            "path": str(path.resolve()),
            "project_id": doc.get("project_id"),
            "name": doc.get("name"),
            "updated_at": doc.get("updated_at"),
            "experiments": len(doc.get("experiments") or {}),
            "jobs": len(doc.get("jobs") or {}),
        })
    rows.sort(key=lambda row: str(row.get("updated_at") or ""), reverse=True)
    return rows


def update_project_metadata(
    project_dir: str | Path,
    *,
    description: str | None = None,
    research_question: str | None = None,
) -> dict[str, Any]:
    doc = open_project(project_dir)
    if description is not None:
        doc["description"] = str(description)
    if research_question is not None:
        doc["research_question"] = str(research_question)
    return save_project(project_dir, doc)


def experiment_id(manifest: Mapping[str, Any]) -> str:
    check = validate_manifest(manifest)
    if not check["valid"]:
        raise ValueError("invalid experiment manifest: " + "; ".join(check["errors"]))
    sha = str(manifest.get("experiment_sha256") or check.get("calculated_sha256") or "")
    return f"exp-{sha[:16]}"


def register_experiment(project_dir: str | Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    project_path = Path(project_dir).expanduser().resolve()
    doc = open_project(project_path)
    exp_id = experiment_id(manifest)
    sha = str(manifest.get("experiment_sha256") or "")
    relative = Path("experiments") / exp_id / "manifest.json"
    target = project_path / relative
    existing = _read_json(target)
    if existing is not None and str(existing.get("experiment_sha256") or "") != sha:
        raise ValueError(f"experiment path collision: {exp_id}")
    _atomic_json(target, dict(manifest))
    previous = dict((doc.get("experiments") or {}).get(exp_id) or {})
    entry = {
        "experiment_id": exp_id,
        "experiment_sha256": sha,
        "profile": manifest.get("profile"),
        "model": (manifest.get("model") or {}).get("title") if isinstance(manifest.get("model"), Mapping) else None,
        "manifest_path": relative.as_posix(),
        "created_at": manifest.get("created_at"),
        "first_registered_at": previous.get("first_registered_at") or utc_now(),
    }
    doc.setdefault("experiments", {})[exp_id] = entry
    profiles = set(str(x) for x in (doc.get("profiles") or []) if x)
    if manifest.get("profile"):
        profiles.add(str(manifest["profile"]))
    doc["profiles"] = sorted(profiles)
    save_project(project_path, doc)
    return entry


def project_reference(project_dir: str | Path) -> dict[str, Any]:
    path = Path(project_dir).expanduser().resolve()
    doc = open_project(path)
    return {
        "project_id": doc["project_id"],
        "project_path": _portable_path(path),
        "schema": PROJECT_SCHEMA,
    }


def _result_summary(result: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, Mapping):
        return {}
    summary: dict[str, Any] = {}
    for key, value in list(result.items())[:120]:
        if value is None or isinstance(value, (str, bool, int, float)):
            summary[str(key)] = plain(value)
        elif isinstance(value, Mapping):
            scalars = {
                str(k): plain(v)
                for k, v in list(value.items())[:40]
                if v is None or isinstance(v, (str, bool, int, float))
            }
            if scalars:
                summary[str(key)] = scalars
        if len(summary) >= 30:
            break
    return summary


def register_job_reference(
    project_dir: str | Path,
    record: Mapping[str, Any],
    *,
    result: Mapping[str, Any] | None = None,
) -> bool:
    project_path = Path(project_dir).expanduser().resolve()
    doc = open_project(project_path)
    sha = str(record.get("experiment_sha256") or "")
    matching = [
        exp_id for exp_id, item in (doc.get("experiments") or {}).items()
        if isinstance(item, Mapping) and str(item.get("experiment_sha256") or "") == sha
    ]
    if not matching:
        return False
    job_id = str(record.get("id") or "")
    if not job_id:
        return False
    job_entry = {
        "job_id": job_id,
        "experiment_id": matching[0],
        "experiment_sha256": sha,
        "profile": record.get("profile"),
        "runner": record.get("runner"),
        "status": record.get("status"),
        "stage": record.get("stage"),
        "attempt": record.get("attempt"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
        "result_path": _portable_path(Path(str(record["result_path"]))) if record.get("result_path") else None,
        "log_path": _portable_path(Path(str(record["log_path"]))) if record.get("log_path") else None,
    }
    previous = (doc.get("jobs") or {}).get(job_id)
    changed = previous != job_entry
    doc.setdefault("jobs", {})[job_id] = job_entry
    if result is not None:
        result_path = record.get("result_path")
        if not result_path:
            root = _data_dir()
            candidate = (root / "compute-jobs" / job_id / "result.json") if root is not None else Path("result.json")
            result_path = str(candidate)
        result_entry = {
            "job_id": job_id,
            "experiment_id": matching[0],
            "result_path": _portable_path(Path(str(result_path))),
            "result_sha256": sha256_json(result),
            "summary": _result_summary(result),
            "updated_at": record.get("updated_at") or utc_now(),
        }
        if (doc.get("results") or {}).get(job_id) != result_entry:
            changed = True
        doc.setdefault("results", {})[job_id] = result_entry
        ref_path = project_path / "results" / f"{job_id}.json"
        _atomic_json(ref_path, result_entry)
    if changed:
        save_project(project_path, doc)
    return True


def sync_compute_jobs(project_dir: str | Path) -> dict[str, int]:
    """Index matching Compute Engine jobs/results by experiment fingerprint."""
    try:
        import physical_lab_compute_engine as compute
    except Exception:
        return {"matched": 0, "results": 0}
    matched = 0
    results = 0
    for record in compute.list_jobs(limit=500):
        result = compute.read_result(str(record.get("id"))) if record.get("status") == "succeeded" else None
        if register_job_reference(project_dir, record, result=result):
            matched += 1
            if result is not None:
                results += 1
    return {"matched": matched, "results": results}


def project_summary(project_dir: str | Path) -> dict[str, Any]:
    doc = open_project(project_dir)
    jobs = list((doc.get("jobs") or {}).values())
    statuses: dict[str, int] = {}
    for row in jobs:
        if isinstance(row, Mapping):
            state = str(row.get("status") or "unknown")
            statuses[state] = statuses.get(state, 0) + 1
    return {
        "project_id": doc.get("project_id"),
        "name": doc.get("name"),
        "research_question": doc.get("research_question"),
        "profiles": list(doc.get("profiles") or []),
        "experiment_count": len(doc.get("experiments") or {}),
        "job_count": len(doc.get("jobs") or {}),
        "result_count": len(doc.get("results") or {}),
        "job_statuses": statuses,
        "updated_at": doc.get("updated_at"),
    }


def render_project_report_markdown(project_dir: str | Path, *, generated_at: str | None = None) -> str:
    project_path = Path(project_dir).expanduser().resolve()
    doc = open_project(project_path)
    generated = generated_at or utc_now()
    lines = [
        f"# Physical Lab Project Report · {doc['name']}",
        "",
        f"- Project ID: `{doc['project_id']}`",
        f"- Schema: `{doc['schema']}`",
        f"- Generated: {generated}",
        f"- Profiles: {', '.join(doc.get('profiles') or []) or '—'}",
        "",
        "## Research question",
        "",
        str(doc.get("research_question") or "Not specified."),
        "",
        "## Project description",
        "",
        str(doc.get("description") or "Not specified."),
        "",
        "## Experiments",
        "",
        "| Experiment | Profile | Model | Scientific fingerprint |",
        "|---|---|---|---|",
    ]
    for exp_id, item in sorted((doc.get("experiments") or {}).items()):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"| `{exp_id}` | {item.get('profile') or '—'} | {item.get('model') or '—'} | `{item.get('experiment_sha256') or ''}` |"
        )
    if not doc.get("experiments"):
        lines.append("| — | — | — | — |")
    lines += [
        "",
        "## Compute jobs",
        "",
        "| Job | Experiment | Runner | Status | Attempt |",
        "|---|---|---|---|---:|",
    ]
    for job_id, item in sorted((doc.get("jobs") or {}).items()):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            f"| `{job_id}` | `{item.get('experiment_id') or ''}` | {item.get('runner') or '—'} | {item.get('status') or '—'} | {item.get('attempt') or 0} |"
        )
    if not doc.get("jobs"):
        lines.append("| — | — | — | — | 0 |")
    lines += [
        "",
        "## Result references",
        "",
    ]
    if doc.get("results"):
        for job_id, item in sorted((doc.get("results") or {}).items()):
            if isinstance(item, Mapping):
                lines.append(
                    f"- `{job_id}` → `{item.get('result_path')}` · sha256 `{item.get('result_sha256')}`"
                )
    else:
        lines.append("No completed result references are indexed yet.")
    lines += [
        "",
        "## Reproducibility and V&V boundary",
        "",
        "Experiment fingerprints identify stable scientific content. Job/result records preserve execution provenance, but this report does not convert simulation into experimental validation or product certification. Measurement calibration, model-form uncertainty and applicable engineering requirements remain separate evidence.",
        "",
        "## Project boundary",
        "",
        str(doc.get("boundary") or ""),
        "",
    ]
    return "\n".join(lines)


def write_project_report(project_dir: str | Path, *, generated_at: str | None = None) -> tuple[Path, str]:
    project_path = Path(project_dir).expanduser().resolve()
    generated = generated_at or utc_now()
    text = render_project_report_markdown(project_path, generated_at=generated)
    safe_stamp = re.sub(r"[^0-9]", "", generated)[:14] or "report"
    report_path = project_path / "reports" / f"project-report-{safe_stamp}.md"
    report_path.write_text(text, encoding="utf-8")
    doc = open_project(project_path)
    entry = {
        "path": report_path.relative_to(project_path).as_posix(),
        "generated_at": generated,
        "sha256": sha256_json({"text": text}),
    }
    reports = [item for item in (doc.get("reports") or []) if isinstance(item, Mapping) and item.get("path") != entry["path"]]
    reports.append(entry)
    doc["reports"] = reports[-100:]
    save_project(project_path, doc)
    return report_path, text


def render_project_workspace(st: Any, profile: str, namespace: Mapping[str, Any] | None = None) -> None:
    root = projects_root()
    st.markdown("---")
    with st.expander("Physical Lab · .physlab Project", expanded=False):
        st.caption(
            "Project-level source of truth for experiment manifests, compute-job/result references, provenance and reports. "
            "Large solver outputs stay in their native stores and are referenced rather than duplicated."
        )
        if root is None:
            st.info("Project Kernel needs PHYSICAL_LAB_DATA_DIR from the desktop shell.")
            return

        rows = list_projects()
        options = ["Create new project"] + [str(row["path"]) for row in rows]
        active = str(st.session_state.get(ACTIVE_PROJECT_SESSION_KEY) or "")
        default_index = options.index(active) if active in options else (1 if len(options) > 1 else 0)
        selected = st.selectbox(
            "Project", options, index=default_index,
            format_func=lambda value: "Create new project" if value == "Create new project" else Path(value).stem,
            key=f"pl_project_select_{profile}",
        )
        if selected == "Create new project":
            c1, c2 = st.columns(2)
            name = c1.text_input("Project name", value="My Physical Lab Project", key=f"pl_project_name_{profile}")
            question = c2.text_input("Research question", value="", key=f"pl_project_question_new_{profile}")
            description = st.text_input("Description", value="", key=f"pl_project_description_new_{profile}")
            if st.button("Create .physlab project", type="primary", key=f"pl_project_create_{profile}"):
                project_path, _ = create_project(name, description=description, research_question=question)
                st.session_state[ACTIVE_PROJECT_SESSION_KEY] = str(project_path)
                st.success(f"Created {project_path.name}")
                st.rerun()
            return

        project_path = Path(selected)
        st.session_state[ACTIVE_PROJECT_SESSION_KEY] = str(project_path)
        doc = open_project(project_path)
        sync = sync_compute_jobs(project_path)
        summary = project_summary(project_path)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Experiments", summary["experiment_count"])
        m2.metric("Jobs", summary["job_count"])
        m3.metric("Results", summary["result_count"])
        m4.metric("Profiles", len(summary["profiles"]))
        st.caption(f"Project ID: {summary['project_id']} · synced jobs: {sync['matched']} · completed results: {sync['results']}")

        q = st.text_input("Project research question", value=str(doc.get("research_question") or ""), key=f"pl_project_question_{profile}")
        desc = st.text_input("Project description", value=str(doc.get("description") or ""), key=f"pl_project_description_{profile}")
        c1, c2, c3 = st.columns(3)
        if c1.button("Save project metadata", key=f"pl_project_save_{profile}", width="stretch"):
            update_project_metadata(project_path, description=desc, research_question=q)
            st.success("Project metadata saved.")

        source_commit = os.environ.get("PHYSICAL_LAB_SOURCE_COMMIT") or None
        manifest = build_session_manifest(profile, namespace or {}, st.session_state, source_commit=source_commit)
        exp_id = experiment_id(manifest)
        if c2.button("Register current experiment", type="primary", key=f"pl_project_register_{profile}", width="stretch"):
            entry = register_experiment(project_path, manifest)
            sync_compute_jobs(project_path)
            st.success(f"Registered {entry['experiment_id']} ({entry['profile']}).")
            st.rerun()
        c2.caption(f"Current scientific identity: `{exp_id}`")

        if c3.button("Generate project report", key=f"pl_project_report_{profile}", width="stretch"):
            report_path, text = write_project_report(project_path)
            st.session_state[f"pl_project_report_text_{profile}"] = text
            st.session_state[f"pl_project_report_path_{profile}"] = str(report_path)
        report_text = st.session_state.get(f"pl_project_report_text_{profile}")
        report_path = st.session_state.get(f"pl_project_report_path_{profile}")
        if report_text:
            st.download_button(
                "Download Markdown project report",
                data=report_text,
                file_name=Path(str(report_path or "physical-lab-project-report.md")).name,
                mime="text/markdown",
                key=f"pl_project_report_download_{profile}",
            )

        with st.expander("Project index", expanded=False):
            st.json({
                "project": summary,
                "experiments": doc.get("experiments") or {},
                "jobs": doc.get("jobs") or {},
                "results": doc.get("results") or {},
            })
