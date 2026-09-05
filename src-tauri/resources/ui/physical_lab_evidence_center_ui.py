"""Shared Evidence Center UI for every Physical Lab experiment profile.

This layer reads and writes the same project-level evidence APIs used by CLI and
CI. It does not recompute scientific truth or create a separate UI-only state.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _artifact_refs(project_path: Path, doc: Mapping[str, Any]) -> list[str]:
    rows: list[str] = []
    for kind, key in (("experiment", "experiments"), ("job", "jobs"), ("result", "results")):
        for item_id in sorted((doc.get(key) or {}).keys()):
            rows.append(f"{kind}:{item_id}")
    measurement_index = _read_json(project_path / "measurements" / "index.json")
    calibration_index = _read_json(project_path / "calibration" / "index.json")
    for item_id in sorted((measurement_index.get("measurements") or {}).keys()):
        rows.append(f"measurement:{item_id}")
    for item_id in sorted((calibration_index.get("calibrations") or {}).keys()):
        rows.append(f"calibration:{item_id}")
    return rows


def _parse_ref(value: str) -> dict[str, str]:
    kind, ref_id = str(value).split(":", 1)
    return {"kind": kind, "id": ref_id}


def _snapshot_files(project_path: Path) -> list[Path]:
    root = project_path / "provenance" / "evidence-snapshots"
    if not root.is_dir():
        return []
    return sorted(root.glob("evidence-snapshot-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)


def render_evidence_center(st: Any, project_path: str | Path, profile: str) -> None:
    import physical_lab_claims as claims
    import physical_lab_credibility as credibility
    import physical_lab_cross_checks as cross_checks
    import physical_lab_evidence_diff as evidence_diff
    import physical_lab_engineering_decision_ui as decision_ui
    import physical_lab_operations_ui as operations_ui
    import physical_lab_project_kernel as projects
    import physical_lab_quality_reliability_ui as quality_reliability_ui

    path = Path(project_path).expanduser().resolve()
    doc = projects.open_project(path)
    passport = credibility.build_credibility_passport(path)
    claim_matrix = claims.claim_evidence_matrix(path)
    cross_matrix = cross_checks.cross_check_matrix(path)
    coverage = passport.get("coverage") or {}

    with st.expander("Physical Lab · Evidence Center", expanded=False):
        st.caption(
            "Evidence-first review across the active .physlab project. Passport, claims, cross-checks, engineering decisions, operations plans, quality/reliability studies, snapshots and diffs "
            "use the same deterministic project state. No aggregate credibility score, machine truth verdict, design verdict, globally optimal schedule, process qualification, or certification verdict is produced."
        )
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Evidence PRESENT", int(coverage.get("present") or 0))
        c2.metric("PARTIAL", int(coverage.get("partial") or 0))
        c3.metric("MISSING", int(coverage.get("missing") or 0))
        c4.metric("Claims", len(claim_matrix.get("claims") or []))
        c5.metric("Cross-checks", len(cross_matrix.get("cross_checks") or []))
        c6.metric("Graph nodes", len((passport.get("evidence_graph") or {}).get("nodes") or []))
        st.caption(
            f"Passport `{str(passport.get('passport_sha256') or '')[:16]}…` · "
            f"Evidence graph `{str(passport.get('evidence_graph_sha256') or '')[:16]}…`"
        )

        passport_tab, claims_tab, cross_tab, decision_tab, operations_tab, quality_tab, diff_tab = st.tabs([
            "Credibility Passport", "Claims", "Cross-Checks", "Engineering Decisions", "Operations", "Quality & Reliability", "Snapshots & Diff"
        ])

        with passport_tab:
            factor_rows = []
            gaps = []
            for row in passport.get("factors") or []:
                if not isinstance(row, Mapping):
                    continue
                factor_rows.append({
                    "Factor": row.get("title"),
                    "Status": row.get("status"),
                    "Rationale": row.get("rationale"),
                    "Evidence records": len(row.get("evidence") or []),
                })
                for gap in row.get("gaps") or []:
                    gaps.append({"Factor": row.get("title"), "Gap": gap})
            st.dataframe(factor_rows, width="stretch", hide_index=True)
            if gaps:
                st.markdown("#### Evidence gaps")
                st.dataframe(gaps, width="stretch", hide_index=True)
            else:
                st.info("No automatically detected evidence gaps. Domain review is still required.")
            with st.expander("Evidence Graph", expanded=False):
                st.json(passport.get("evidence_graph") or {})
            st.caption(str(passport.get("boundary") or ""))

        refs = _artifact_refs(path, doc)
        with claims_tab:
            rows = claim_matrix.get("claims") or []
            if rows:
                st.dataframe([
                    {
                        "Claim": row.get("statement"),
                        "Status": row.get("status"),
                        "Evidence refs": row.get("reference_count"),
                        "Required factors": ", ".join(row.get("required_factors") or []),
                    }
                    for row in rows
                ], width="stretch", hide_index=True)
            else:
                st.info("No registered claims yet.")

            with st.expander("Register scientific / engineering claim", expanded=False):
                statement = st.text_area("Claim statement", key=f"pl_evidence_claim_statement_{profile}")
                intended_use = st.text_input("Intended use", key=f"pl_evidence_claim_use_{profile}")
                factor_options = [fid for fid, _title in credibility.FACTOR_DEFINITIONS]
                required = st.multiselect(
                    "Required evidence factors",
                    factor_options,
                    default=["verification", "results_robustness"],
                    key=f"pl_evidence_claim_factors_{profile}",
                )
                selected_refs = st.multiselect(
                    "Explicit evidence references",
                    refs,
                    key=f"pl_evidence_claim_refs_{profile}",
                    help="Claims with no explicit evidence references evaluate to EVIDENCE_MISSING.",
                )
                if st.button("Register claim", type="primary", key=f"pl_evidence_claim_register_{profile}"):
                    if not statement.strip():
                        st.error("Claim statement is required.")
                    elif not selected_refs:
                        st.error("Select at least one explicit evidence reference.")
                    else:
                        record = claims.register_claim(
                            path,
                            statement=statement,
                            intended_use=intended_use,
                            required_factors=required,
                            references=[_parse_ref(value) for value in selected_refs],
                        )
                        evaluation = claims.evaluate_claim(path, record["claim_id"])
                        st.success(f"Registered {record['claim_id']} · {evaluation['status']}")
                        st.rerun()
            st.caption("READY_FOR_REVIEW means evidence readiness/freshness only; it is not a truth or certification decision.")

        with cross_tab:
            rows = cross_matrix.get("cross_checks") or []
            if rows:
                st.dataframe([
                    {
                        "Cross-check": row.get("name"),
                        "Observable": row.get("observable"),
                        "Status": row.get("status"),
                        "Relative difference": row.get("relative_difference"),
                        "Tolerance": row.get("tolerance"),
                        "Mode": row.get("tolerance_mode"),
                    }
                    for row in rows
                ], width="stretch", hide_index=True)
            else:
                st.info("No evidence-linked cross-checks yet.")

            with st.expander("Register cross-check", expanded=False):
                a, b = st.columns(2)
                name = a.text_input("Cross-check name", key=f"pl_xcheck_name_{profile}")
                observable = b.text_input("Observable", key=f"pl_xcheck_observable_{profile}")
                a, b, c = st.columns(3)
                primary_value = a.number_input("Primary value", value=0.0, format="%.12g", key=f"pl_xcheck_primary_value_{profile}")
                comparison_value = b.number_input("Comparison value", value=0.0, format="%.12g", key=f"pl_xcheck_comparison_value_{profile}")
                unit = c.text_input("Unit", value="1", key=f"pl_xcheck_unit_{profile}")
                a, b = st.columns(2)
                primary_family = a.text_input("Primary method family", key=f"pl_xcheck_primary_family_{profile}", placeholder="numerical-rk4")
                comparison_family = b.text_input("Comparison method family", key=f"pl_xcheck_comparison_family_{profile}", placeholder="analytic-closed-form")
                a, b = st.columns(2)
                primary_source = a.text_input("Primary source identity", key=f"pl_xcheck_primary_source_{profile}")
                comparison_source = b.text_input("Comparison source identity", key=f"pl_xcheck_comparison_source_{profile}")
                a, b = st.columns(2)
                primary_ref = a.selectbox("Primary evidence", [""] + refs, key=f"pl_xcheck_primary_ref_{profile}")
                comparison_ref = b.selectbox("Comparison evidence", [""] + refs, key=f"pl_xcheck_comparison_ref_{profile}")
                a, b = st.columns(2)
                mode = a.selectbox("Tolerance mode", ["relative", "absolute"], key=f"pl_xcheck_mode_{profile}")
                tolerance = b.number_input("Tolerance", min_value=0.0, value=0.001, format="%.12g", key=f"pl_xcheck_tolerance_{profile}")
                intended = st.text_input("Intended use", key=f"pl_xcheck_use_{profile}")
                if st.button("Register cross-check", type="primary", key=f"pl_xcheck_register_{profile}"):
                    required_text = [name, observable, primary_family, comparison_family, primary_source, comparison_source, primary_ref, comparison_ref]
                    if not all(str(value).strip() for value in required_text):
                        st.error("Name, observable, both method/source identities, and both evidence references are required.")
                    else:
                        record = cross_checks.register_cross_check(
                            path,
                            name=name,
                            observable=observable,
                            primary={
                                "value": primary_value,
                                "method_family": primary_family,
                                "source_identity": primary_source,
                                "references": [_parse_ref(primary_ref)],
                            },
                            comparison={
                                "value": comparison_value,
                                "method_family": comparison_family,
                                "source_identity": comparison_source,
                                "references": [_parse_ref(comparison_ref)],
                            },
                            tolerance=tolerance,
                            tolerance_mode=mode,
                            unit=unit,
                            intended_use=intended,
                        )
                        evaluation = cross_checks.evaluate_cross_check(path, record["cross_check_id"])
                        st.success(f"Registered {record['cross_check_id']} · {evaluation['status']}")
                        st.rerun()
            st.caption("Different method/source labels are declared metadata, not proof of true algorithmic or statistical independence.")

        with decision_tab:
            decision_ui.render_engineering_decision_tab(st, path, profile, refs)

        with operations_tab:
            operations_ui.render_operations_tab(st, path, profile)

        with quality_tab:
            quality_reliability_ui.render_quality_reliability_tab(st, path, profile, refs)

        with diff_tab:
            if st.button("Capture evidence snapshot", type="primary", key=f"pl_evidence_snapshot_{profile}"):
                snap_path, snap = evidence_diff.write_evidence_snapshot(path, label=f"{profile} review")
                st.success(f"Captured {snap_path.name} · {str(snap['snapshot_sha256'])[:16]}…")
                st.rerun()
            files = _snapshot_files(path)
            if files:
                st.caption(f"Saved evidence snapshots: {len(files)}")
                if len(files) >= 2:
                    names = [item.name for item in files]
                    a, b = st.columns(2)
                    before_name = a.selectbox("Before snapshot", names, index=min(1, len(names) - 1), key=f"pl_evidence_before_{profile}")
                    after_name = b.selectbox("After snapshot", names, index=0, key=f"pl_evidence_after_{profile}")
                    if st.button("Compare evidence snapshots", key=f"pl_evidence_diff_{profile}"):
                        before = evidence_diff.load_evidence_snapshot(path / "provenance" / "evidence-snapshots" / before_name)
                        after = evidence_diff.load_evidence_snapshot(path / "provenance" / "evidence-snapshots" / after_name)
                        diff = evidence_diff.diff_evidence_snapshots(before, after)
                        st.markdown(evidence_diff.render_evidence_diff_markdown(diff))
                        with st.expander("Evidence Diff JSON", expanded=False):
                            st.json(diff)
                else:
                    st.info("Capture another snapshot after evidence changes to enable diff review.")
            else:
                st.info("No evidence snapshots saved yet.")
            st.caption("A changed fingerprint means review state changed; it does not by itself prove that a scientific conclusion changed.")
