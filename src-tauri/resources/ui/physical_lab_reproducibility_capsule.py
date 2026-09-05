"""Deterministic Evidence-First Reproducibility Capsule for Physical Lab.

A capsule is a portable review package built from the canonical `.physlab`
Project Kernel.  It carries project/experiment identities, measurement and
calibration evidence, result references, current Credibility Passport, Claims,
Cross-Checks and Evidence Snapshot, plus a bounded inventory of workflow
provenance.

The capsule does not promote workflow artifacts into scientific evidence and it
does not manufacture a verification, validation, truth, compliance or
certification verdict. Large files may be omitted by policy, but every omission
is explicit and fingerprinted when readable.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

import physical_lab_claims as claims
import physical_lab_credibility as credibility
import physical_lab_cross_checks as cross_checks
import physical_lab_evidence_diff as evidence_diff
import physical_lab_measurement_registry as measurements
import physical_lab_project_kernel as projects
from physical_lab_experiment_kernel import plain

CAPSULE_SCHEMA = "physical-lab-reproducibility-capsule-v1"
CAPSULE_VERSION = 1
VERIFY_SCHEMA = "physical-lab-reproducibility-capsule-verification-v1"
DEFAULT_MAX_FILE_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 100 * 1024 * 1024
ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        plain(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _pretty_json_bytes(value: Any) -> bytes:
    return (json.dumps(plain(value), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _safe_component(value: str, fallback: str = "item") -> str:
    text = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in str(value)).strip("-.")
    return (text or fallback)[:120]


def _archive_path(value: str) -> str:
    path = PurePosixPath(str(value).replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe capsule archive path: {value!r}")
    cleaned = "/".join(part for part in path.parts if part not in ("", "."))
    if not cleaned:
        raise ValueError("empty capsule archive path")
    return cleaned


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _resolve_data_reference(reference: str) -> Path:
    value = Path(str(reference)).expanduser()
    if value.is_absolute():
        return value.resolve()
    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
    if raw:
        return (Path(raw).expanduser().resolve() / value).resolve()
    return value.resolve()


def _entry(
    *,
    archive_path: str,
    source_reference: str,
    scientific_role: str,
    data: bytes | None,
    included: bool,
    omission_reason: str | None = None,
    source_sha256: str | None = None,
    source_size_bytes: int | None = None,
) -> dict[str, Any]:
    archive = _archive_path(archive_path)
    if data is not None:
        digest = _sha_bytes(data)
        size = len(data)
    else:
        digest = source_sha256
        size = source_size_bytes
    return {
        "archive_path": archive,
        "source_reference": str(source_reference),
        "scientific_role": str(scientific_role),
        "included": bool(included),
        "size_bytes": size,
        "sha256": digest,
        "omission_reason": omission_reason,
    }


def _file_candidate(
    source: Path,
    *,
    archive_path: str,
    source_reference: str,
    scientific_role: str,
) -> dict[str, Any]:
    try:
        if not source.is_file():
            return {
                "archive_path": _archive_path(archive_path),
                "source_reference": source_reference,
                "scientific_role": scientific_role,
                "source_path": source,
                "readable": False,
                "size_bytes": None,
                "sha256": None,
                "error": "source file does not exist",
            }
        return {
            "archive_path": _archive_path(archive_path),
            "source_reference": source_reference,
            "scientific_role": scientific_role,
            "source_path": source,
            "readable": True,
            "size_bytes": source.stat().st_size,
            "sha256": _sha_file(source),
            "error": None,
        }
    except Exception as exc:
        return {
            "archive_path": _archive_path(archive_path),
            "source_reference": source_reference,
            "scientific_role": scientific_role,
            "source_path": source,
            "readable": False,
            "size_bytes": None,
            "sha256": None,
            "error": str(exc)[:300],
        }


def _generated_candidate(archive_path: str, value: Any, *, role: str, source_reference: str) -> dict[str, Any]:
    data = _pretty_json_bytes(value)
    return {
        "archive_path": _archive_path(archive_path),
        "source_reference": source_reference,
        "scientific_role": role,
        "generated_data": data,
        "readable": True,
        "size_bytes": len(data),
        "sha256": _sha_bytes(data),
        "error": None,
    }


def _add_tree_candidates(
    candidates: list[dict[str, Any]],
    project_path: Path,
    relative_root: str,
    *,
    archive_root: str,
    role: str,
    patterns: tuple[str, ...] = ("*.json",),
) -> None:
    root = project_path / relative_root
    if not root.is_dir():
        return
    seen: set[Path] = set()
    for pattern in patterns:
        for source in sorted(root.rglob(pattern)):
            if not source.is_file() or source in seen:
                continue
            seen.add(source)
            rel = source.relative_to(root).as_posix()
            candidates.append(_file_candidate(
                source,
                archive_path=f"{archive_root}/{rel}",
                source_reference=f"project:{relative_root}/{rel}",
                scientific_role=role,
            ))


def _project_candidates(project_path: Path, project: Mapping[str, Any], state_time: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    candidates.append(_file_candidate(
        project_path / "project.json",
        archive_path="project/project.json",
        source_reference="project:project.json",
        scientific_role="project-identity",
    ))

    # Canonical experiment manifests.
    for exp_id, row in sorted((project.get("experiments") or {}).items()):
        if not isinstance(row, Mapping):
            continue
        ref = str(row.get("manifest_path") or f"experiments/{exp_id}/manifest.json")
        source = project_path / ref
        candidates.append(_file_candidate(
            source,
            archive_path=f"experiments/{_safe_component(str(exp_id))}/manifest.json",
            source_reference=f"experiment:{exp_id}",
            scientific_role="experiment-manifest",
        ))

    # Project-local result reference records plus independently stored compute result payloads.
    for job_id, row in sorted((project.get("results") or {}).items()):
        if not isinstance(row, Mapping):
            continue
        local_ref = project_path / "results" / f"{job_id}.json"
        if local_ref.is_file():
            candidates.append(_file_candidate(
                local_ref,
                archive_path=f"results/{_safe_component(str(job_id))}/reference.json",
                source_reference=f"result-reference:{job_id}",
                scientific_role="result-reference",
            ))
        result_path = row.get("result_path")
        if result_path:
            source = _resolve_data_reference(str(result_path))
            candidates.append(_file_candidate(
                source,
                archive_path=f"results/{_safe_component(str(job_id))}/result.json",
                source_reference=f"result:{job_id}",
                scientific_role="compute-result",
            ))

    # Measurement records and raw evidence assets.
    for row in sorted(measurements.list_measurements(project_path), key=lambda item: str(item.get("measurement_id") or "")):
        mid = str(row.get("measurement_id") or "")
        if not mid:
            continue
        record_path = project_path / "measurements" / mid / "measurement.json"
        candidates.append(_file_candidate(
            record_path,
            archive_path=f"measurements/{_safe_component(mid)}/measurement.json",
            source_reference=f"measurement-record:{mid}",
            scientific_role="measurement-metadata",
        ))
        asset_ref = str(row.get("asset_path") or "")
        if asset_ref:
            asset = project_path / asset_ref
            candidates.append(_file_candidate(
                asset,
                archive_path=f"measurements/{_safe_component(mid)}/assets/{_safe_component(str(row.get('file_name') or asset.name), 'measurement.dat')}",
                source_reference=f"measurement:{mid}",
                scientific_role="measurement-asset",
            ))

    # Calibration evidence is metadata supplied by the user; its own boundary travels with the record.
    for row in sorted(measurements.list_calibrations(project_path), key=lambda item: str(item.get("calibration_id") or "")):
        cid = str(row.get("calibration_id") or "")
        if not cid:
            continue
        candidates.append(_file_candidate(
            project_path / "calibration" / f"{cid}.json",
            archive_path=f"calibration/{_safe_component(cid)}.json",
            source_reference=f"calibration:{cid}",
            scientific_role="calibration-metadata",
        ))

    # Raw human-authored claim/cross-check records, not only their generated matrix summaries.
    _add_tree_candidates(candidates, project_path, "provenance/claims", archive_root="evidence/claims", role="claim-record")
    _add_tree_candidates(candidates, project_path, "provenance/cross-checks", archive_root="evidence/cross-checks", role="cross-check-record")
    _add_tree_candidates(candidates, project_path, "provenance/evidence-snapshots", archive_root="evidence/saved-snapshots", role="evidence-snapshot")

    # Bounded desktop workflow artifacts are provenance only; they are never labeled scientific results here.
    for dirname in ("runs", "campaigns", "pipelines"):
        _add_tree_candidates(
            candidates,
            project_path,
            dirname,
            archive_root=f"workflow/{dirname}",
            role="workflow-provenance",
            patterns=("*.json",),
        )
    _add_tree_candidates(
        candidates,
        project_path,
        "reports",
        archive_root="reports",
        role="project-report",
        patterns=("*.json", "*.md", "*.txt"),
    )

    passport = credibility.build_credibility_passport(project_path, generated_at=state_time)
    claim_matrix = claims.claim_evidence_matrix(project_path)
    cross_matrix = cross_checks.cross_check_matrix(project_path)
    snapshot = evidence_diff.build_evidence_snapshot(project_path, label="reproducibility-capsule", generated_at=state_time)
    evidence_summary = measurements.evidence_summary(project_path)
    candidates.extend([
        _generated_candidate("evidence/credibility-passport.json", passport, role="credibility-passport", source_reference="generated:credibility-passport"),
        _generated_candidate("evidence/claim-matrix.json", claim_matrix, role="claim-evidence-matrix", source_reference="generated:claim-matrix"),
        _generated_candidate("evidence/cross-check-matrix.json", cross_matrix, role="cross-check-matrix", source_reference="generated:cross-check-matrix"),
        _generated_candidate("evidence/current-evidence-snapshot.json", snapshot, role="evidence-snapshot", source_reference="generated:current-evidence-snapshot"),
        _generated_candidate("evidence/measurement-summary.json", evidence_summary, role="measurement-summary", source_reference="generated:measurement-summary"),
    ])
    return candidates


def _apply_policy(
    candidates: list[dict[str, Any]],
    *,
    max_file_bytes: int,
    max_total_bytes: int,
) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    if max_file_bytes <= 0 or max_total_bytes <= 0:
        raise ValueError("capsule size limits must be positive")
    payloads: dict[str, bytes] = {}
    inventory: list[dict[str, Any]] = []
    total = 0
    used_paths: set[str] = set()
    for candidate in sorted(candidates, key=lambda row: str(row.get("archive_path") or "")):
        archive = _archive_path(str(candidate["archive_path"]))
        if archive == "capsule.json":
            raise ValueError("capsule payload may not use reserved path capsule.json")
        if archive in used_paths:
            raise ValueError(f"duplicate capsule archive path: {archive}")
        used_paths.add(archive)
        readable = bool(candidate.get("readable"))
        size = candidate.get("size_bytes")
        digest = candidate.get("sha256")
        role = str(candidate.get("scientific_role") or "unclassified")
        source_reference = str(candidate.get("source_reference") or "")
        if not readable:
            inventory.append(_entry(
                archive_path=archive,
                source_reference=source_reference,
                scientific_role=role,
                data=None,
                included=False,
                omission_reason=f"unavailable: {candidate.get('error') or 'source could not be read'}",
                source_sha256=digest,
                source_size_bytes=size if isinstance(size, int) else None,
            ))
            continue
        if not isinstance(size, int):
            inventory.append(_entry(
                archive_path=archive, source_reference=source_reference, scientific_role=role,
                data=None, included=False, omission_reason="source size unavailable", source_sha256=digest,
            ))
            continue
        if size > max_file_bytes:
            inventory.append(_entry(
                archive_path=archive, source_reference=source_reference, scientific_role=role,
                data=None, included=False, omission_reason=f"file exceeds max_file_bytes={max_file_bytes}",
                source_sha256=str(digest or "") or None, source_size_bytes=size,
            ))
            continue
        if total + size > max_total_bytes:
            inventory.append(_entry(
                archive_path=archive, source_reference=source_reference, scientific_role=role,
                data=None, included=False, omission_reason=f"including file would exceed max_total_bytes={max_total_bytes}",
                source_sha256=str(digest or "") or None, source_size_bytes=size,
            ))
            continue
        if "generated_data" in candidate:
            data = bytes(candidate["generated_data"])
        else:
            source = candidate.get("source_path")
            if not isinstance(source, Path):
                raise ValueError(f"missing source path for {archive}")
            data = source.read_bytes()
        if len(data) != size or _sha_bytes(data) != digest:
            raise ValueError(f"capsule source changed while packaging: {source_reference or archive}")
        payloads[archive] = data
        total += len(data)
        inventory.append(_entry(
            archive_path=archive,
            source_reference=source_reference,
            scientific_role=role,
            data=data,
            included=True,
        ))
    return inventory, payloads


def build_capsule_manifest(
    project_dir: str | Path,
    *,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    path = Path(project_dir).expanduser().resolve()
    project = projects.open_project(path)
    state_time = str(project.get("updated_at") or project.get("created_at") or "")
    candidates = _project_candidates(path, project, state_time)
    inventory, payloads = _apply_policy(
        candidates,
        max_file_bytes=int(max_file_bytes),
        max_total_bytes=int(max_total_bytes),
    )
    stable = {
        "schema": CAPSULE_SCHEMA,
        "capsule_version": CAPSULE_VERSION,
        "project_id": project.get("project_id"),
        "project_schema": project.get("schema"),
        "project_version": project.get("project_version"),
        "project_state_updated_at": state_time,
        "policy": {
            "max_file_bytes": int(max_file_bytes),
            "max_total_bytes": int(max_total_bytes),
            "exports_recursively_included": False,
            "workflow_artifacts_are_scientific_results": False,
        },
        "inventory": inventory,
        "evidence_fingerprints": {
            "passport_sha256": credibility.build_credibility_passport(path, generated_at=state_time).get("passport_sha256"),
            "claim_matrix_sha256": claims.claim_evidence_matrix(path).get("matrix_sha256"),
            "cross_check_matrix_sha256": cross_checks.cross_check_matrix(path).get("matrix_sha256"),
            "evidence_snapshot_sha256": evidence_diff.build_evidence_snapshot(path, label="reproducibility-capsule", generated_at=state_time).get("snapshot_sha256"),
        },
    }
    capsule_sha = _sha_bytes(_canonical_json_bytes(stable))
    manifest = {
        **stable,
        "capsule_sha256": capsule_sha,
        "included_file_count": sum(1 for row in inventory if row["included"]),
        "omitted_file_count": sum(1 for row in inventory if not row["included"]),
        "included_payload_bytes": sum(int(row.get("size_bytes") or 0) for row in inventory if row["included"]),
        "boundary": (
            "Portable evidence/reproducibility package only. Inclusion means an artifact and its fingerprint were captured; "
            "it does not establish scientific truth, experimental validation, standards compliance, accreditation or certification."
        ),
    }
    return manifest, payloads


def _zip_bytes(manifest: Mapping[str, Any], payloads: Mapping[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        members = {"capsule.json": _pretty_json_bytes(manifest), **dict(payloads)}
        for name in sorted(members):
            safe = _archive_path(name)
            info = zipfile.ZipInfo(safe, date_time=ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            info.flag_bits = 0
            archive.writestr(info, members[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return buffer.getvalue()


def write_reproducibility_capsule(
    project_dir: str | Path,
    *,
    output_path: str | Path | None = None,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
) -> tuple[Path, dict[str, Any], str]:
    path = Path(project_dir).expanduser().resolve()
    manifest, payloads = build_capsule_manifest(
        path,
        max_file_bytes=max_file_bytes,
        max_total_bytes=max_total_bytes,
    )
    data = _zip_bytes(manifest, payloads)
    archive_sha = _sha_bytes(data)
    if output_path is None:
        target = path / "exports" / f"reproducibility-capsule-{str(manifest['capsule_sha256'])[:16]}.zip"
    else:
        target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    temp.write_bytes(data)
    os.replace(temp, target)
    return target, manifest, archive_sha


def verify_reproducibility_capsule(capsule_path: str | Path) -> dict[str, Any]:
    path = Path(capsule_path).expanduser().resolve()
    archive_sha = _sha_file(path) if path.is_file() else None
    errors: list[str] = []
    missing: list[str] = []
    corrupt: list[str] = []
    unexpected: list[str] = []
    manifest: dict[str, Any] = {}
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            if "capsule.json" not in names:
                raise ValueError("capsule.json is missing")
            manifest_value = json.loads(archive.read("capsule.json").decode("utf-8"))
            if not isinstance(manifest_value, dict):
                raise ValueError("capsule.json is not an object")
            manifest = manifest_value
            if manifest.get("schema") != CAPSULE_SCHEMA or int(manifest.get("capsule_version") or 0) != CAPSULE_VERSION:
                errors.append("unsupported capsule schema/version")
            stable = {
                key: manifest.get(key)
                for key in (
                    "schema", "capsule_version", "project_id", "project_schema", "project_version",
                    "project_state_updated_at", "policy", "inventory", "evidence_fingerprints",
                )
            }
            expected_capsule_sha = _sha_bytes(_canonical_json_bytes(stable))
            if str(manifest.get("capsule_sha256") or "") != expected_capsule_sha:
                errors.append("capsule manifest fingerprint mismatch")
            expected_members = {"capsule.json"}
            for row in manifest.get("inventory") or []:
                if not isinstance(row, Mapping) or not row.get("included"):
                    continue
                name = _archive_path(str(row.get("archive_path") or ""))
                expected_members.add(name)
                if name not in names:
                    missing.append(name)
                    continue
                data = archive.read(name)
                if len(data) != int(row.get("size_bytes") or -1) or _sha_bytes(data) != str(row.get("sha256") or ""):
                    corrupt.append(name)
            unexpected = sorted(set(names) - expected_members)
            duplicates = sorted({name for name in names if names.count(name) > 1})
            if duplicates:
                errors.append("duplicate ZIP members: " + ", ".join(duplicates))
            bad_crc = archive.testzip()
            if bad_crc:
                errors.append(f"ZIP CRC failure: {bad_crc}")
    except Exception as exc:
        errors.append(str(exc))

    valid = not errors and not missing and not corrupt and not unexpected
    stable_report = {
        "schema": VERIFY_SCHEMA,
        "valid": valid,
        "capsule_sha256": manifest.get("capsule_sha256") if manifest else None,
        "archive_sha256": archive_sha,
        "errors": errors,
        "missing_members": sorted(missing),
        "corrupt_members": sorted(corrupt),
        "unexpected_members": sorted(unexpected),
    }
    return {
        **stable_report,
        "verification_sha256": _sha_bytes(_canonical_json_bytes(stable_report)),
        "project_id": manifest.get("project_id") if manifest else None,
        "included_file_count": manifest.get("included_file_count") if manifest else None,
        "omitted_file_count": manifest.get("omitted_file_count") if manifest else None,
        "boundary": "Integrity verification only. A valid capsule proves archive/member consistency, not scientific validity or certification.",
    }
