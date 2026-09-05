#!/usr/bin/env python3
"""Deterministic wiring checks for the shared Physical Lab Evidence Center UI."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"
sys.path.insert(0, str(UI))

import physical_lab_evidence_center_patch as patch
import physical_lab_evidence_center_ui as evidence_ui
import physical_lab_project_kernel as project_kernel


class FakeStreamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, str] = {}
        self.warnings: list[str] = []

    def warning(self, message: object) -> None:
        self.warnings.append(str(message))


def main() -> int:
    wrapper_text = (UI / "sitecustomize.py").read_text(encoding="utf-8")
    base_text = (UI / "physical_lab_sitecustomize_base.py").read_text(encoding="utf-8")
    assert "physical_lab_sitecustomize_base" in wrapper_text
    assert "physical_lab_evidence_center_patch" in wrapper_text
    assert "Physical Lab simulation UI v2" in base_text
    assert len(base_text) > 10_000, "shared legacy enhancement layer should remain intact"

    conf = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    resources = (conf.get("bundle") or {}).get("resources") or {}
    for source in (
        "resources/ui/sitecustomize.py",
        "resources/ui/physical_lab_sitecustomize_base.py",
        "resources/ui/physical_lab_evidence_center_patch.py",
        "resources/ui/physical_lab_evidence_center_ui.py",
        "resources/ui/physical_lab_credibility.py",
        "resources/ui/physical_lab_claims.py",
        "resources/ui/physical_lab_cross_checks.py",
        "resources/ui/physical_lab_evidence_diff.py",
    ):
        assert source in resources, f"missing Tauri Evidence Center resource: {source}"

    calls: list[tuple] = []
    original_workspace = project_kernel.render_project_workspace
    original_renderer = evidence_ui.render_evidence_center
    had_flag = hasattr(project_kernel, "_physical_lab_evidence_center_patched")
    old_flag = getattr(project_kernel, "_physical_lab_evidence_center_patched", None)

    def base_workspace(st, profile, namespace=None):
        calls.append(("base", profile, namespace))

    def fake_evidence_center(st, project_path, profile):
        calls.append(("evidence", str(project_path), profile))

    try:
        project_kernel.render_project_workspace = base_workspace
        project_kernel._physical_lab_evidence_center_patched = False
        evidence_ui.render_evidence_center = fake_evidence_center
        patch.install()
        wrapped = project_kernel.render_project_workspace
        assert wrapped is not base_workspace, "install() must wrap the project workspace"

        st = FakeStreamlit()
        wrapped(st, "numerical-methods", {"fixture": True})
        assert calls == [("base", "numerical-methods", {"fixture": True})]
        assert not st.warnings

        st.session_state[project_kernel.ACTIVE_PROJECT_SESSION_KEY] = "/tmp/fixture.physlab"
        wrapped(st, "numerical-methods", {"fixture": 2})
        assert calls[-2] == ("base", "numerical-methods", {"fixture": 2})
        assert calls[-1] == ("evidence", "/tmp/fixture.physlab", "numerical-methods")
        assert not st.warnings

        before = project_kernel.render_project_workspace
        patch.install()
        assert project_kernel.render_project_workspace is before, "Evidence Center patch must be idempotent"
    finally:
        project_kernel.render_project_workspace = original_workspace
        evidence_ui.render_evidence_center = original_renderer
        if had_flag:
            project_kernel._physical_lab_evidence_center_patched = old_flag
        elif hasattr(project_kernel, "_physical_lab_evidence_center_patched"):
            delattr(project_kernel, "_physical_lab_evidence_center_patched")

    print("Physical Lab Evidence Center UI wiring: PASS")
    print("- shared sitecustomize base preserved: PASS")
    print("- desktop bundle resources: PASS")
    print("- no-active-project guard: PASS")
    print("- active project -> Evidence Center render: PASS")
    print("- idempotent patch installation: PASS")
    print("Boundary: UI consumes the same project evidence APIs; it does not introduce a separate credibility/truth state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
