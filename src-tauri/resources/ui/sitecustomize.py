"""Physical Lab startup UI hooks.

The original shared Streamlit enhancement layer is preserved byte-for-byte in
physical_lab_sitecustomize_base. This wrapper prepares compatibility discovery
aliases for canonical projects, executes the shared UI layer, then installs the
project-level Evidence Center and shared Project surface for every managed Lab.
"""
from __future__ import annotations

try:
    from physical_lab_workspace_aliases import ensure_workspace_aliases as _pl_ensure_workspace_aliases
    _pl_ensure_workspace_aliases()
except Exception:
    pass

try:
    import physical_lab_sitecustomize_base  # noqa: F401
except Exception:
    pass

try:
    from physical_lab_evidence_center_patch import install as _pl_install_evidence_center
    _pl_install_evidence_center()
except Exception:
    pass

try:
    from physical_lab_project_surface_patch import install as _pl_install_project_surface
    _pl_install_project_surface()
except Exception:
    pass
