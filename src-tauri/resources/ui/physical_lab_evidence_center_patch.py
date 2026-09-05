"""Install the shared Evidence Center without modifying individual Lab sources."""
from __future__ import annotations


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
            # state, so do not leak that project's Evidence Center underneath the
            # creation form.
            selector_key = f"pl_project_select_{profile}"
            if str(st.session_state.get(selector_key) or "") == "Create new project":
                return
            active = str(st.session_state.get(project_kernel.ACTIVE_PROJECT_SESSION_KEY) or "").strip()
            if not active:
                return
            from physical_lab_evidence_center_ui import render_evidence_center
            render_evidence_center(st, active, profile)
        except Exception as exc:
            try:
                st.warning(f"Physical Lab Evidence Center could not load: {exc}")
            except Exception:
                pass

    project_kernel.render_project_workspace = wrapped
    project_kernel._physical_lab_evidence_center_patched = True
