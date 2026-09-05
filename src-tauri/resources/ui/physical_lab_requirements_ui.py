"""Streamlit UI for Physical Lab Requirements & Traceability Layer v1."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _engineering_link_options(project_path: Path) -> list[str]:
    import physical_lab_claims as claims
    import physical_lab_cross_checks as cross_checks
    import physical_lab_engineering_decisions as decisions
    import physical_lab_operations_planning as operations
    import physical_lab_quality_reliability as quality
    import physical_lab_risk_economics as risk_economics

    rows: list[str] = []
    rows.extend(f"claim:{row.get('claim_id')}" for row in claims.list_claims(project_path) if row.get("claim_id"))
    rows.extend(f"cross-check:{row.get('cross_check_id')}" for row in cross_checks.list_cross_checks(project_path) if row.get("cross_check_id"))
    rows.extend(f"decision-study:{row.get('study_id')}" for row in decisions.list_decision_studies(project_path) if row.get("study_id"))
    rows.extend(f"operations-plan:{row.get('plan_id')}" for row in operations.list_operations_plans(project_path) if row.get("plan_id"))
    qrm = quality.quality_reliability_matrix(project_path)
    rows.extend(f"quality-study:{row.get('study_id')}" for row in qrm.get("quality_studies") or [] if row.get("study_id"))
    rows.extend(f"reliability-study:{row.get('study_id')}" for row in qrm.get("reliability_studies") or [] if row.get("study_id"))
    rem = risk_economics.risk_economics_matrix(project_path)
    rows.extend(f"risk-study:{row.get('study_id')}" for row in rem.get("risk_studies") or [] if row.get("study_id"))
    rows.extend(f"economics-study:{row.get('study_id')}" for row in rem.get("economics_studies") or [] if row.get("study_id"))
    return sorted(set(rows))


def _parse_link(value: str) -> dict[str, str]:
    kind, ref_id = str(value).split(":", 1)
    return {"kind": kind, "id": ref_id}


def render_requirements_tab(st: Any, project_path: str | Path, profile: str, evidence_refs: list[str]) -> None:
    import physical_lab_requirements as requirements

    path = Path(project_path).expanduser().resolve()
    matrix = requirements.traceability_matrix(path)
    rows = matrix.get("requirements") or []
    counts = matrix.get("counts") or {}

    st.caption(
        "Maintain requirement source/flowdown, verification planning, explicit Project evidence, and engineering-record traceability. "
        "READY_FOR_REVIEW is an evidence/planning state only; Physical Lab does not automatically mark requirements VERIFIED, VALIDATED, compliant, safe, accepted, or certified."
    )
    columns = st.columns(5)
    for column, state in zip(columns, requirements.REVIEW_STATES):
        column.metric(state, int(counts.get(state) or 0))

    if rows:
        st.dataframe([
            {
                "Key": row.get("requirement_key"),
                "Status": row.get("status"),
                "Level": row.get("level"),
                "Method": row.get("verification_method") or "unplanned",
                "Parents": row.get("parent_count"),
                "Children": row.get("child_count"),
                "Evidence": row.get("evidence_reference_count"),
                "Engineering links": row.get("engineering_link_count"),
                "Statement": row.get("statement"),
            }
            for row in rows
        ], width="stretch", hide_index=True)
    else:
        st.info("No requirements registered yet.")

    requirement_rows = requirements.list_requirements(path)
    requirement_labels = {
        f"{row.get('requirement_key')} · {row.get('requirement_id')}": str(row.get("requirement_id"))
        for row in requirement_rows
    }
    if requirement_labels:
        selected = st.selectbox("Review requirement", [""] + list(requirement_labels), key=f"pl_req_review_{profile}")
        if selected:
            requirement_id = requirement_labels[selected]
            record = requirements.get_requirement(path, requirement_id)
            evaluation = requirements.evaluate_requirement(path, requirement_id)
            a, b, c, d = st.columns(4)
            a.metric("Review state", evaluation.get("status"))
            b.metric("Evidence refs", len(record.get("evidence_references") or []))
            c.metric("Engineering links", len(record.get("engineering_links") or []))
            d.metric("Parents", len(record.get("parent_requirement_ids") or []))
            st.markdown(f"**{record.get('requirement_key')}** — {record.get('statement')}")
            st.markdown(f"**Source:** `{record.get('source')}` · **Level:** `{record.get('level')}`")
            st.markdown(f"**Verification method:** `{record.get('verification_method') or 'unplanned'}`")
            st.markdown(f"**Verification criteria:** {record.get('verification_criteria') or 'Not declared'}")
            st.info(str(evaluation.get("rationale") or ""))
            if evaluation.get("evidence_checks"):
                st.markdown("#### Evidence trace")
                st.dataframe(evaluation.get("evidence_checks"), width="stretch", hide_index=True)
            if evaluation.get("engineering_checks"):
                st.markdown("#### Engineering-record trace")
                st.dataframe(evaluation.get("engineering_checks"), width="stretch", hide_index=True)
            if evaluation.get("parent_checks"):
                st.markdown("#### Parent requirement trace")
                st.dataframe(evaluation.get("parent_checks"), width="stretch", hide_index=True)
            st.caption(str(evaluation.get("boundary") or ""))

    with st.expander("Register requirement", expanded=False):
        a, b, c = st.columns(3)
        requirement_key = a.text_input("Requirement key", placeholder="SYS-001", key=f"pl_req_key_{profile}")
        source = b.text_input("Requirement source", placeholder="System specification §3.2", key=f"pl_req_source_{profile}")
        level = c.text_input("Level", value="system", key=f"pl_req_level_{profile}")
        statement = st.text_area("Requirement statement", placeholder="The system shall ...", key=f"pl_req_statement_{profile}")

        parent_options = list(requirement_labels)
        selected_parents = st.multiselect("Parent requirements", parent_options, key=f"pl_req_parents_{profile}")
        a, b = st.columns(2)
        method = a.selectbox("Planned verification method", [""] + list(requirements.VERIFICATION_METHODS), key=f"pl_req_method_{profile}")
        criteria = b.text_input("Verification criteria", key=f"pl_req_criteria_{profile}")

        selected_evidence = st.multiselect(
            "Explicit Project evidence",
            evidence_refs,
            key=f"pl_req_evidence_{profile}",
            help="A requirement with no evidence can be registered for planning, but it cannot become READY_FOR_REVIEW.",
        )
        engineering_options = _engineering_link_options(path)
        selected_engineering = st.multiselect(
            "Engineering-record links",
            engineering_options,
            key=f"pl_req_engineering_links_{profile}",
            help="Links are fingerprinted at registration so later engineering-record drift can mark the requirement STALE.",
        )
        rationale = st.text_area("Requirement rationale", key=f"pl_req_rationale_{profile}")
        intended_use = st.text_input("Intended use", key=f"pl_req_use_{profile}")
        if st.button("Register requirement", type="primary", key=f"pl_req_register_{profile}"):
            try:
                if not requirement_key.strip() or not statement.strip() or not source.strip():
                    raise ValueError("Requirement key, statement, and source are required.")
                record = requirements.register_requirement(
                    path,
                    requirement_key=requirement_key,
                    statement=statement,
                    source=source,
                    level=level,
                    parent_requirement_ids=[requirement_labels[label] for label in selected_parents],
                    verification_method=method,
                    verification_criteria=criteria,
                    evidence_references=[_parse_link(value) for value in selected_evidence],
                    engineering_links=[_parse_link(value) for value in selected_engineering],
                    rationale=rationale,
                    intended_use=intended_use,
                )
                evaluation = requirements.evaluate_requirement(path, record["requirement_id"])
                st.success(f"Registered {record['requirement_key']} · {evaluation['status']}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.caption(
        "Verification method names follow common systems-engineering planning vocabulary, but their presence does not mean that the activity was performed or passed. "
        "Human/domain review remains responsible for actual verification and validation conclusions."
    )
