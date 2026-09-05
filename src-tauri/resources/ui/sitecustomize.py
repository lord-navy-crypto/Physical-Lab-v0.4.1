"""Physical Lab startup UI hooks.

The original shared Streamlit enhancement layer is preserved byte-for-byte in
physical_lab_sitecustomize_base. This wrapper executes it, then installs the
project-level Evidence Center hook for every managed Lab process.
"""
from __future__ import annotations

try:
    import physical_lab_sitecustomize_base  # noqa: F401
except Exception:
    pass

try:
    from physical_lab_evidence_center_patch import install as _pl_install_evidence_center
    _pl_install_evidence_center()
except Exception:
    pass
