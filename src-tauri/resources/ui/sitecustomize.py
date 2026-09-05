"""Physical Lab startup UI hooks.

The original shared Streamlit enhancement layer is preserved byte-for-byte in
physical_lab_sitecustomize_base. Python project browsers are patched to discover
canonical ``projects/*.physlab`` directly; compatibility aliases are therefore
no longer a prerequisite for the shared Lab UI. The Evidence Center and Project
surface remain installed for every managed Lab.
"""
from __future__ import annotations

try:
    from physical_lab_canonical_discovery_patch import install as _pl_install_canonical_discovery
    _pl_install_canonical_discovery()
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
