"""Streamlit UI for Physical Lab Requirements & Verification Planning v1."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _csv_tokens(value: str) -> list[str]:
    return [item.strip() for item in str(value).split(",") if item.strip()]


def render_requirements_verification_tab(st: Any, project_path: str | Path, profile: str, refs: list[str]) -> None:
    import physical_lab_requirements_verification as rv

    path = Path(project_path).expanduser().resolve()
    matrix = rv.requirements_verification_matrix(path)
    rows = matrix.get("requirements") or []

    st.caption(
        "Plan requirement verification using explicit shall-statements, source/trace identifiers, one declared verification method, success criteria, Project evidence freshness, and human review rationale. "
        "READY_FOR_REVIEW means evidence is present and current; it does not mean VERIFIED, PASS, compliant, accepted, qualified, certified, safe, or stakeholder-validated."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Requirements", len(rows))
    c2.metric("Ready for review", sum(1 for row in rows if row.get("evidence_state") == "READY_FOR_REVIEW"))
    c3.metric("Stale", sum(1 for row in rows if row.get("evidence_state") == "STALE"))
    c4.metric("Evidence missing", sum(1 for row in rows if row.get("evidence_state") == "EVIDENCE_MISSING"))

    if rows:
        st.dataframe(
            [
                {
                    "ID": row.get("requirement_id"),
                    "Requirement": row.get("statement"),
                    "Level": row.get("level"),
                    "Method": row.get("verification_method"),
                    "Evidence": row.get("evidence_state"),
                    "Refs": row.get("reference_count"),
                    "Latest review": row.get("latest_review_outcome"),
                }
                for row in rows
            ],
            width="stretch",
            hide_index=True,
        )
        labels = {
            f"{row.get('requirement_id')} · {row.get('verification_method')} · {row.get('evidence_state')}": str(row.get("requirement_id"))
            for row in rows
        }
        selected = st.selectbox(
            "Review requirement / verification plan",
            [""] + list(labels),
            key=f"pl_req_review_{profile}",
        )
        if selected:
            evaluation = rv.evaluate_requirement(path, labels[selected])
            a, b, c, d = st.columns(4)
            a.metric("Evidence", evaluation.get("evidence_state"))
            b.metric("Method", evaluation.get("verification_method"))
            c.metric("Evidence refs", evaluation.get("reference_count"))
            d.metric("Level", evaluation.get("level"))

            st.markdown(f"**Requirement:** {evaluation.get('statement')}")
            if evaluation.get("source_document") or evaluation.get("source_locator"):
                st.markdown(
                    f"**Source:** `{evaluation.get('source_document') or '—'}` · locator `{evaluation.get('source_locator') or '—'}`"
                )
            upstream = evaluation.get("upstream_requirement_ids") or []
            if upstream:
                st.markdown("**Declared upstream trace IDs:** " + ", ".join(f"`{value}`" for value in upstream))
            st.markdown(f"**Verification activity:** {evaluation.get('verification_activity')}")
            st.markdown(f"**Success criteria:** {evaluation.get('success_criteria')}")
            if evaluation.get("evidence_checks"):
                st.dataframe(evaluation.get("evidence_checks"), width="stretch", hide_index=True)
            if evaluation.get("stale_references") or evaluation.get("missing_references"):
                st.warning("Supporting Project evidence is stale or missing; the requirement cannot be marked evidence-sufficient for project review.")

            latest = evaluation.get("latest_human_review")
            if latest:
                st.markdown("#### Latest human review")
                st.json(latest)

            with st.expander("Record human requirement review", expanded=False):
                outcome = st.selectbox(
                    "Review outcome",
                    list(rv.REVIEW_OUTCOMES),
                    key=f"pl_req_outcome_{profile}_{labels[selected]}",
                )
                reviewer = st.text_input(
                    "Reviewer / role (optional)",
                    key=f"pl_req_reviewer_{profile}_{labels[selected]}",
                )
                rationale = st.text_area(
                    "Review rationale",
                    key=f"pl_req_rationale_{profile}_{labels[selected]}",
                )
                if st.button(
                    "Record human review",
                    key=f"pl_req_record_review_{profile}_{labels[selected]}",
                ):
                    try:
                        rv.record_requirement_review(
                            path,
                            labels[selected],
                            outcome=outcome,
                            rationale=rationale,
                            reviewer=reviewer,
                        )
                        st.success("Human review recorded.")
                        st.rerun()
                    except Exception as exc:
                        st.error(str(exc))
            st.caption(str(evaluation.get("boundary") or ""))
    else:
        st.info("No requirements / verification plans registered yet.")

    with st.expander("Register requirement / verification plan", expanded=False):
        a, b = st.columns(2)
        requirement_id = a.text_input("Requirement ID", value="REQ-001", key=f"pl_req_id_{profile}")
        level = b.text_input("Requirement level", value="system", key=f"pl_req_level_{profile}")
        statement = st.text_area(
            "Normative requirement statement (must contain 'shall')",
            value="The system shall produce the declared response within the project-defined tolerance.",
            key=f"pl_req_statement_{profile}",
        )
        a, b = st.columns(2)
        method = a.selectbox(
            "Verification method",
            list(rv.VERIFICATION_METHODS),
            key=f"pl_req_method_{profile}",
        )
        owner = b.text_input("Owner / responsible role (optional)", key=f"pl_req_owner_{profile}")
        activity = st.text_area(
            "Verification activity",
            value="Execute the declared analysis or test configuration and preserve the resulting Project evidence.",
            key=f"pl_req_activity_{profile}",
        )
        criteria = st.text_area(
            "Success criteria",
            value="Compare the declared response against the requirement-specific acceptance criterion during human project review.",
            key=f"pl_req_criteria_{profile}",
        )
        a, b = st.columns(2)
        source_document = a.text_input("Source document / authority", key=f"pl_req_source_doc_{profile}")
        source_locator = b.text_input("Source locator / section", key=f"pl_req_source_loc_{profile}")
        upstream_text = st.text_input(
            "Declared upstream requirement IDs (optional, comma-separated)",
            key=f"pl_req_upstream_{profile}",
        )
        rationale = st.text_area("Requirement rationale (optional)", key=f"pl_req_register_rationale_{profile}")
        intended_use = st.text_input("Intended use", key=f"pl_req_use_{profile}")
        selected_refs = st.multiselect(
            "Explicit Project evidence references (optional during planning)",
            refs,
            key=f"pl_req_refs_{profile}",
        )
        if st.button("Register requirement plan", type="primary", key=f"pl_req_register_{profile}"):
            try:
                references = []
                for value in selected_refs:
                    kind, ref_id = value.split(":", 1)
                    references.append({"kind": kind, "id": ref_id})
                record = rv.register_requirement(
                    path,
                    requirement_id=requirement_id,
                    statement=statement,
                    verification_method=method,
                    verification_activity=activity,
                    success_criteria=criteria,
                    references=references,
                    source_document=source_document,
                    source_locator=source_locator,
                    rationale=rationale,
                    level=level,
                    owner=owner,
                    upstream_requirement_ids=_csv_tokens(upstream_text),
                    intended_use=intended_use,
                )
                st.success(f"Registered {record['requirement_id']}")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.caption(
        "Verification methods follow the common test / analysis / inspection / demonstration planning vocabulary. Physical Lab records project evidence readiness and review rationale only; it does not issue a formal verification, validation, compliance, qualification, safety, or certification verdict."
    )
