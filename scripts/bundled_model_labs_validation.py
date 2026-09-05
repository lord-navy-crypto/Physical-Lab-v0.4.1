#!/usr/bin/env python3
"""Contract for restoring Kerr, Solar System, and Honeycomb as first-class Labs."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "src-tauri" / "resources" / "ui"

BUNDLED = {
    "kerr-geodesics": {
        "name": "Kerr Black Hole Geodesics",
        "category": "Relativity & Astrophysics",
        "solver": "physical_lab_kerr_geodesics.py",
        "ui": "physical_lab_kerr_ui.py",
        "validation": "kerr_geodesic_validation.py",
    },
    "solar-system-dynamics": {
        "name": "Sun–Jupiter–Saturn Dynamics",
        "category": "Computational Astrophysics",
        "solver": "physical_lab_solar_system_dynamics.py",
        "ui": "physical_lab_solar_system_ui.py",
        "validation": "solar_system_dynamics_validation.py",
    },
    "honeycomb-lattice": {
        "name": "Multilayer Honeycomb Lattice",
        "category": "Materials & Condensed Matter",
        "solver": "physical_lab_lattice_dynamics.py",
        "ui": "physical_lab_lattice_ui.py",
        "validation": "honeycomb_lattice_validation.py",
    },
}

ORIGINAL_EXTERNAL_LABS = {
    "numerical-methods",
    "ising-monte-carlo",
    "random-walk-monte-carlo",
    "nonlinear-chaos",
    "oscillation-integration",
    "radia-magnet-studio",
    "radiation-platform",
}


def main() -> int:
    modules = json.loads((ROOT / "src-tauri" / "resources" / "modules.json").read_text(encoding="utf-8"))
    labs = [m for m in modules if m.get("kind") == "lab"]
    runtimes = [m for m in modules if m.get("kind") == "runtime"]
    assert len(modules) == 13, len(modules)
    assert len(labs) == 10, len(labs)
    assert len(runtimes) == 3, len(runtimes)
    assert {m["id"] for m in labs if not m.get("bundled", False)} == ORIGINAL_EXTERNAL_LABS
    assert {m["id"] for m in labs if m.get("bundled", False)} == set(BUNDLED)

    for module_id, expected in BUNDLED.items():
        row = next(m for m in labs if m["id"] == module_id)
        assert row["name"] == expected["name"]
        assert row["category"] == expected["category"]
        assert row["repo"] == "lord-navy-crypto/Physical-Lab-v0.4.1"
        assert row["branch"] == "main"
        assert row.get("revision") in {None, ""}, "bundled app source must not masquerade as a downloaded pinned repo revision"
        assert row["entrypoint"] == "app.py"
        assert row["requirements"] == "requirements.txt"
        assert row["safeBackend"] == "standard"
        assert row["fragileDependencies"] == []
        assert row["runtimeRequires"] == []
        assert set(row["supportedArches"]) == {"arm64", "x86_64"}
        assert expected["solver"] in {p.name for p in UI.iterdir()}
        assert expected["ui"] in {p.name for p in UI.iterdir()}
        assert (ROOT / "scripts" / expected["validation"]).is_file()

    host = (UI / "physical_lab_builtin_lab_entry.py").read_text(encoding="utf-8")
    for module_id in BUNDLED:
        assert module_id in host
    for marker in (
        "render_kerr_geodesic_workspace",
        "render_kerr_platform_workspace",
        "render_solar_system_workspace",
        "render_lattice_workspace",
        "render_new_model_refinement_for_variant",
        "render_project_workspace",
    ):
        assert marker in host, marker
    for forbidden in ("usability_score", "experimental validation", "certification verdict"):
        # Host may mention the concepts only as explicit negations/boundaries; it must not implement verdict fields.
        if forbidden == "usability_score":
            assert forbidden not in host

    refinement_ui = (UI / "physical_lab_new_model_refinement_ui.py").read_text(encoding="utf-8")
    assert "def render_new_model_refinement_for_variant" in refinement_ui
    for marker in ("KERR_VARIANT", "SOLAR_VARIANT", "LATTICE_VARIANT"):
        assert marker in refinement_ui

    lib = (ROOT / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
    for marker in (
        "bundled: bool",
        "fn prepare_bundled_lab_source",
        "if spec.bundled",
        "physical_lab_builtin_lab_entry.py",
        "physical_lab_builtin_requirements.txt",
        '"kerr-geodesics"',
        '"solar-system-dynamics"',
        '"honeycomb-lattice"',
    ):
        assert marker in lib, marker
    # A bundled model must be prepared from packaged resources, not codeload.
    prep = lib.split("fn prepare_bundled_lab_source", 1)[1].split("async fn", 1)[0]
    assert "codeload.github.com" not in prep
    assert "fs::copy" in prep
    assert "physical-lab-bundled-source-v1" in prep

    runtime_support = (ROOT / "src-tauri" / "src" / "research_runtime_support.rs").read_text(encoding="utf-8")
    for marker in (
        '"kerr-geodesics"=>',
        '"solar-system-dynamics"=>',
        '"honeycomb-lattice"=>',
        'command.env("PYTHONPATH",ui)',
        "No scientific smoke script registered",
    ):
        assert marker in runtime_support, marker

    tauri = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    resources = (tauri.get("bundle") or {}).get("resources") or {}
    for resource in (
        "resources/ui/physical_lab_builtin_lab_entry.py",
        "resources/ui/physical_lab_builtin_requirements.txt",
    ):
        assert resource in resources, resource

    self_check = (ROOT / "scripts" / "self_check.py").read_text(encoding="utf-8")
    assert "Modules: 13 (10 labs + 3 runtime/builders)" in self_check
    assert "Top-level Labs: 10" in self_check

    print("Bundled first-class model Labs: PASS")
    print("- catalog: 10 Labs + 3 runtimes")
    print("- Kerr / Solar / Honeycomb use packaged strengthened solver/UI modules")
    print("- installation path creates an isolated environment without external solver download")
    print("- shared Project / Evidence surface remains available")
    print("Boundary: restoration changes launcher/product identity only; it does not change the scientific equations or imply experimental validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
