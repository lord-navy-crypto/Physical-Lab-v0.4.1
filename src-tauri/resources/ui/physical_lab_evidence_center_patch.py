"""Install shared Evidence and Engineering Decision Centers without modifying Lab sources."""
from __future__ import annotations

from pathlib import Path


def install() -> None:
    try:
        import physical_lab_project_kernel as project_kernel
    except Exception:
        return
    if getattr(project_kernel, "_physical_lab_evidence_center_patched", False):
        return
    original = project_kernel.render_project_workspace

    def wrapped(st, profile, namespace=None):
        original(st, profile, namespace)
        try:
            # The Project Kernel intentionally returns early while the create-new
            # form is selected. An older active path can still exist in session
            # state, so do not leak that project's review surfaces underneath the
            # creation form.
            selector_key = f"pl_project_select_{profile}"
            if str(st.session_state.get(selector_key) or "") == "Create new project":
                return
            active = str(st.session_state.get(project_kernel.ACTIVE_PROJECT_SESSION_KEY) or "").strip()
            if not active:
                return

            from physical_lab_evidence_center_ui import _artifact_refs, render_evidence_center
            render_evidence_center(st, active, profile)

            # Engineering decisions consume the same active canonical project and
            # explicit evidence-reference vocabulary. A stale/non-canonical path
            # left in session state is simply ineligible for the decision surface;
            # it is not treated as an Engineering Decision Center runtime error.
            project_path = Path(active).expanduser().resolve()
            if not project_path.join("project.json").is_file():
                return
            try:
                project_doc = project_kernel.open_project(project_path)
            except Exception:
                return

            try:
                from physical_lab_engineering_decision_ui import render_engineering_decision_tab
                refs = _artifact_refs(project_path, project_doc)
                with st.expander("Physical Lab · Engineering Decision Center", expanded=False):
                    st.caption(
                        "Turn current project evidence into explicit alternatives, constraints and Pareto trade studies. "
                        "Physical Lab does not assign an overall design score or make the final engineering selection."
                    )
                    render_engineering_decision_tab(st, project_path, profile, refs)
            except Exception as exc:
                try:
                    st.warning(f"Physical Lab Engineering Decision Center could not load: {exc}")
                except Exception:
                    pass
        except Exception as exc:
            try:
                st.warning(f"Physical Lab Evidence Center could not load: {exc}")
            except Exception:
                pass

    project_kernel.render_project_workspace = wrapped
    project_kernel._physical_lab_evidence_center_patched = True
