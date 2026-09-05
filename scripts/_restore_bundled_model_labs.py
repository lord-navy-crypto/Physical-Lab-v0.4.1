#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_modules() -> None:
    path = ROOT / "src-tauri/resources/modules.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    ids = {row["id"] for row in rows}
    expected = {
        "numerical-methods", "ising-monte-carlo", "random-walk-monte-carlo",
        "nonlinear-chaos", "oscillation-integration", "radia-magnet-studio",
        "radiation-platform", "radia-runtime", "chrono-modal-runtime", "vampire-runtime",
    }
    if ids != expected:
        raise RuntimeError(f"unexpected pre-restoration module catalog: {sorted(ids)}")

    common = {
        "kind": "lab",
        "repo": "lord-navy-crypto/Physical-Lab-v0.4.1",
        "branch": "main",
        "bundled": True,
        "entrypoint": "app.py",
        "requirements": "requirements.txt",
        "launcher": None,
        "runtimeRequires": [],
        "pythonRequires": ">=3.10",
        "verifyImports": ["numpy", "scipy", "pandas", "plotly", "streamlit"],
        "supportedArches": ["arm64", "x86_64"],
        "systemRequires": [],
        "runtimeExcludes": [],
        "fragileDependencies": [],
        "safeBackend": "standard",
    }
    restored = [
        {
            **common,
            "id": "kerr-geodesics",
            "name": "Kerr Black Hole Geodesics",
            "category": "Relativity & Astrophysics",
            "description": "Strengthened Kerr geodesic workspace with massive and photon orbits, Carter-Mino integration, invariant residuals, verification campaigns and frequency-structure refinement.",
            "tags": ["Kerr", "Relativity", "Geodesics"],
            "safeModeNote": "Uses the Kerr solver and verification UI bundled with this Physical Lab build; no second solver checkout is downloaded.",
            "fullModeNote": "Same bundled Kerr implementation today. Full mode does not silently substitute a different relativity engine.",
        },
        {
            **common,
            "id": "solar-system-dynamics",
            "name": "Sun–Jupiter–Saturn Dynamics",
            "category": "Computational Astrophysics",
            "description": "Barycentric Sun-Jupiter-Saturn orbital dynamics with Newtonian baseline, bounded 1PN approximation, long-horizon diagnostics, verification workflow and 5:2 commensurability refinement.",
            "tags": ["Orbital dynamics", "Astrophysics", "N-body"],
            "safeModeNote": "Uses the solar-system solver and verification UI bundled with this Physical Lab build; no second solver checkout is downloaded.",
            "fullModeNote": "Same bundled orbital implementation today. Optional model terms remain explicitly labeled approximations or phenomenological studies.",
        },
        {
            **common,
            "id": "honeycomb-lattice",
            "name": "Multilayer Honeycomb Lattice",
            "category": "Materials & Condensed Matter",
            "description": "Reduced-unit multilayer honeycomb lattice dynamics with stacking, defects, strain, driven/Langevin studies, phonon dispersion, DOS and transport refinement.",
            "tags": ["Materials", "Phonons", "Lattice dynamics"],
            "safeModeNote": "Uses the lattice dynamics and phonon implementation bundled with this Physical Lab build; no second solver checkout is downloaded.",
            "fullModeNote": "Same bundled reduced-unit lattice model today. It is not relabeled as an ab-initio or calibrated graphene solver.",
        },
    ]
    first_runtime = next(i for i, row in enumerate(rows) if row["kind"] == "runtime")
    rows[first_runtime:first_runtime] = restored
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def patch_lib() -> None:
    path = ROOT / "src-tauri/src/lib.rs"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    branch: String,\n    #[serde(default)]\n    revision: Option<String>,',
        '    branch: String,\n    #[serde(default)]\n    bundled: bool,\n    #[serde(default)]\n    revision: Option<String>,',
        "ModuleSpec bundled field",
    )
    text = replace_once(
        text,
        'branch:String::new(),revision:None,entrypoint:None',
        'branch:String::new(),bundled:false,revision:None,entrypoint:None',
        "python probe bundled field",
    )

    marker = 'async fn download_source(app: &AppHandle, task: &str, spec: &ModuleSpec, start_pct: f64, end_pct: f64) -> Result<PathBuf, String> {'
    if text.count(marker) != 1:
        raise RuntimeError("download_source marker drift")
    helper = r'''fn prepare_bundled_lab_source(app:&AppHandle,task:&str,spec:&ModuleSpec)->Result<PathBuf,String>{
    if !spec.bundled{return Err(format!("{} is not a bundled Lab",spec.name))}
    let root=module_root(app,&spec.id)?;
    fs::create_dir_all(&root).map_err(|e|e.to_string())?;
    let source=root.join("source");
    if source.exists(){fs::remove_dir_all(&source).map_err(|e|e.to_string())?;}
    fs::create_dir_all(&source).map_err(|e|e.to_string())?;
    let ui=ui_overlay_dir(app).ok_or_else(||"Bundled Physical Lab UI resources are unavailable.".to_string())?;
    let entry=spec.entrypoint.as_deref().ok_or_else(||format!("{} has no bundled entrypoint",spec.name))?;
    let requirements=spec.requirements.as_deref().ok_or_else(||format!("{} has no bundled requirements file",spec.name))?;
    fs::copy(ui.join("physical_lab_builtin_lab_entry.py"),source.join(entry)).map_err(|e|format!("Could not prepare bundled entrypoint for {}: {e}",spec.name))?;
    fs::copy(ui.join("physical_lab_builtin_requirements.txt"),source.join(requirements)).map_err(|e|format!("Could not prepare bundled requirements for {}: {e}",spec.name))?;
    fs::write(source.join("README.md"),format!("# {}\n\nThis managed launcher wrapper uses the scientific implementation bundled with Physical Lab v{}.\n",spec.name,env!("CARGO_PKG_VERSION"))).map_err(|e|e.to_string())?;
    let provenance=serde_json::json!({
        "schema":"physical-lab-bundled-source-v1",
        "moduleId":spec.id,
        "repository":spec.repo,
        "branch":spec.branch,
        "appVersion":env!("CARGO_PKG_VERSION"),
        "preparedAt":chrono::Utc::now().to_rfc3339(),
        "policy":"bundled-app-resource"
    });
    fs::write(source.join("physical-lab-source.json"),serde_json::to_vec_pretty(&provenance).unwrap_or_default()).map_err(|e|e.to_string())?;
    emit_task(app,task,&spec.id,&spec.name,"Preparing bundled Lab","Running",Some(45.0),"Prepared the app-bundled model host; no external solver repository was downloaded.",false,None);
    Ok(source)
}

'''
    text = text.replace(marker, helper + marker, 1)

    old_install = '    if spec.kind=="runtime"{download_source(app,task,spec,4.0,42.0).await?;let app2=app.clone();let task2=task.to_string();let spec2=spec.clone();tokio::task::spawn_blocking(move||run_runtime_builder(&app2,&task2,&spec2,None)).await.map_err(|e|e.to_string())??;return Ok(())}\n    download_source(app,task,spec,5.0,50.0).await?;'
    new_install = '    if spec.kind=="runtime"{download_source(app,task,spec,4.0,42.0).await?;let app2=app.clone();let task2=task.to_string();let spec2=spec.clone();tokio::task::spawn_blocking(move||run_runtime_builder(&app2,&task2,&spec2,None)).await.map_err(|e|e.to_string())??;return Ok(())}\n    if spec.bundled{prepare_bundled_lab_source(app,task,spec)?;}else{download_source(app,task,spec,5.0,50.0).await?;}'
    text = replace_once(text, old_install, new_install, "bundled install routing")

    old_profiles = 'matches!(module_id.as_str(), "numerical-methods"|"ising-monte-carlo"|"random-walk-monte-carlo"|"nonlinear-chaos"|"oscillation-integration"|"radia-magnet-studio"|"radiation-platform")'
    new_profiles = 'matches!(module_id.as_str(), "numerical-methods"|"ising-monte-carlo"|"random-walk-monte-carlo"|"nonlinear-chaos"|"oscillation-integration"|"radia-magnet-studio"|"radiation-platform"|"kerr-geodesics"|"solar-system-dynamics"|"honeycomb-lattice")'
    text = replace_once(text, old_profiles, new_profiles, "launch PYTHONPATH profiles")
    path.write_text(text, encoding="utf-8")


def patch_refinement_ui() -> None:
    path = ROOT / "src-tauri/resources/ui/physical_lab_new_model_refinement_ui.py"
    text = path.read_text(encoding="utf-8")
    marker = 'def render_new_model_refinement_workspace(st: Any, profile: str) -> None:\n'
    if text.count(marker) != 1:
        raise RuntimeError("refinement workspace marker drift")
    helper = '''def render_new_model_refinement_for_variant(st: Any, variant: str) -> None:\n    """Render only one strengthened model's refinement/evidence workspace."""\n    st.markdown("---")\n    st.markdown("## Physical Lab · Model Refinement Evidence")\n    if variant == KERR_VARIANT:\n        _render_kerr(st)\n    elif variant == SOLAR_VARIANT:\n        _render_solar(st)\n    elif variant == LATTICE_VARIANT:\n        _render_lattice(st)\n    else:\n        raise ValueError(f"unsupported refinement model variant: {variant}")\n\n\n'''
    text = text.replace(marker, helper + marker, 1)
    path.write_text(text, encoding="utf-8")


def patch_ui_profiles() -> None:
    path = ROOT / "src-tauri/resources/ui/physical_lab_sitecustomize_base.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    "oscillation-integration",\n    "radiation-platform",',
        '    "oscillation-integration",\n    "kerr-geodesics",\n    "solar-system-dynamics",\n    "honeycomb-lattice",\n    "radiation-platform",',
        "enabled bundled profiles",
    )
    text = replace_once(
        text,
        '            "oscillation-integration": "Oscillation",\n            "radiation-platform": "Radiation workflow",',
        '            "oscillation-integration": "Oscillation",\n            "kerr-geodesics": "Kerr black hole geodesics",\n            "solar-system-dynamics": "Sun–Jupiter–Saturn dynamics",\n            "honeycomb-lattice": "Multilayer honeycomb lattice",\n            "radiation-platform": "Radiation workflow",',
        "bundled profile labels",
    )
    path.write_text(text, encoding="utf-8")

    path = ROOT / "src-tauri/resources/ui/physical_lab_project_surface_patch.py"
    text = path.read_text(encoding="utf-8")
    text = text.replace("all seven managed profiles", "all ten managed Lab profiles")
    text = replace_once(
        text,
        '    "oscillation-integration",\n    "radiation-platform",',
        '    "oscillation-integration",\n    "kerr-geodesics",\n    "solar-system-dynamics",\n    "honeycomb-lattice",\n    "radiation-platform",',
        "project surface bundled profiles",
    )
    path.write_text(text, encoding="utf-8")


def patch_tauri() -> None:
    path = ROOT / "src-tauri/tauri.conf.json"
    text = path.read_text(encoding="utf-8")
    old = '      "resources/ui/sitecustomize.py": "ui/sitecustomize.py",\n'
    new = old + '      "resources/ui/physical_lab_builtin_lab_entry.py": "ui/physical_lab_builtin_lab_entry.py",\n      "resources/ui/physical_lab_builtin_requirements.txt": "ui/physical_lab_builtin_requirements.txt",\n'
    text = replace_once(text, old, new, "Tauri bundled Lab resources")
    json.loads(text)
    path.write_text(text, encoding="utf-8")


def patch_self_check() -> None:
    path = ROOT / "scripts/self_check.py"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "    'src-tauri/resources/safe_engine_server.py','src-tauri/resources/ui/sitecustomize.py',",
        "    'src-tauri/resources/safe_engine_server.py','src-tauri/resources/ui/sitecustomize.py',\n    'src-tauri/resources/ui/physical_lab_builtin_lab_entry.py','src-tauri/resources/ui/physical_lab_builtin_requirements.txt',",
        "self-check bundled resource files",
    )
    text = replace_once(text, "assert len(mods) == 10, f'Expected 10 modules, found {len(mods)}'", "assert len(mods) == 13, f'Expected 13 modules, found {len(mods)}'", "module count")
    text = replace_once(text, "assert sum(m['kind']=='lab' for m in mods) == 7", "assert sum(m['kind']=='lab' for m in mods) == 10", "lab count")
    count_marker = "assert sum(m['kind']=='runtime' for m in mods) == 3\n"
    addition = count_marker + "bundled_ids={'kerr-geodesics','solar-system-dynamics','honeycomb-lattice'}\nassert {m['id'] for m in mods if m.get('bundled',False)} == bundled_ids\nassert all(not m.get('fragileDependencies') for m in mods if m.get('bundled',False))\n"
    text = replace_once(text, count_marker, addition, "bundled catalog assertions")

    resource_marker = "    'resources/ui/sitecustomize.py',\n"
    text = replace_once(
        text,
        resource_marker,
        resource_marker + "    'resources/ui/physical_lab_builtin_lab_entry.py',\n    'resources/ui/physical_lab_builtin_requirements.txt',\n",
        "self-check Tauri bundled resources",
    )

    profile_assertion = "for profile in ['numerical-methods','ising-monte-carlo','random-walk-monte-carlo','nonlinear-chaos','oscillation-integration','radia-magnet-studio','radiation-platform']:\n    assert profile in ui_base\n"
    text = replace_once(
        text,
        profile_assertion,
        profile_assertion + "for profile in ['kerr-geodesics','solar-system-dynamics','honeycomb-lattice']:\n    assert profile in ui_base, profile\n",
        "bundled UI base profiles",
    )

    lib_profile_assertion = "for profile in ['numerical-methods','ising-monte-carlo','random-walk-monte-carlo','nonlinear-chaos','oscillation-integration','radia-magnet-studio','radiation-platform']:\n    assert profile in lib, profile\n"
    text = replace_once(
        text,
        lib_profile_assertion,
        lib_profile_assertion + "for profile in ['kerr-geodesics','solar-system-dynamics','honeycomb-lattice']:\n    assert profile in lib, profile\nassert 'fn prepare_bundled_lab_source' in lib\nassert 'bundled: bool' in lib\n",
        "bundled Rust profiles",
    )

    text = replace_once(text, "print('Modules: 10 (7 labs + 3 runtime/builders)')", "print('Modules: 13 (10 labs + 3 runtime/builders)')\nprint('Top-level Labs: 10')", "module print")
    text = replace_once(text, "print('Enhanced simulation profiles: 7')", "print('Enhanced external simulation profiles: 7')\nprint('Top-level Labs: 10')", "profile print")

    old_pin = "for m in mods:\n    rev=m.get('revision','')\n    assert isinstance(rev,str) and len(rev)==40 and all(c in '0123456789abcdef' for c in rev.lower()), f\"{m.get('id')} missing pinned 40-char revision\"\nprint('Source pinning: 10/10 module revisions pinned')"
    new_pin = "for m in mods:\n    if m.get('bundled',False):\n        assert not m.get('revision'), f\"{m.get('id')} bundled app source must not masquerade as a network revision\"\n        continue\n    rev=m.get('revision','')\n    assert isinstance(rev,str) and len(rev)==40 and all(c in '0123456789abcdef' for c in rev.lower()), f\"{m.get('id')} missing pinned 40-char revision\"\nprint('Network-downloaded source pinning: 10/10 non-bundled module revisions pinned')"
    text = replace_once(text, old_pin, new_pin, "bundled source pinning semantics")
    path.write_text(text, encoding="utf-8")


def patch_readme() -> None:
    path = ROOT / "README.md"
    text = path.read_text(encoding="utf-8")
    text = replace_once(text, "turns seven computational-physics projects into one reproducible workflow", "turns ten computational-physics and engineering model families into one reproducible workflow", "README product count")
    text = replace_once(
        text,
        "Numerical error, Ising/Monte Carlo, random walk/QMC, chaos/Lyapunov analysis, oscillators/integration, RADIA magnetics, undulator radiation",
        "Numerical error, Ising/Monte Carlo, random walk/QMC, chaos/Lyapunov analysis, oscillators/integration, Kerr relativity, solar-system dynamics, multilayer lattice/phonons, RADIA magnetics, undulator radiation",
        "README physics coverage",
    )
    text = replace_once(text, "## Seven validated Lab interfaces", "## Ten validated Lab interfaces", "README Lab heading")
    old_list_tail = "5. **Oscillation & Numerical Integration** — linear/damped/driven/nonlinear oscillators, Euler/Symplectic/RK2/RK4/DOP853 comparisons and energy-work checks.\n6. **RADIA Magnet Studio** — 3-D magnet geometry, native RADIA field solving, harmonics, field integrals, trajectory/phase metrics and manufacturing-error ensembles.\n7. **Radiation Platform** — magnet-to-trajectory-to-radiation workflow, scan-centric analysis and ideal/reference comparisons."
    new_list_tail = "5. **Oscillation & Numerical Integration** — linear/damped/driven/nonlinear oscillators, Euler/Symplectic/RK2/RK4/DOP853 comparisons and energy-work checks.\n6. **Kerr Black Hole Geodesics** — strengthened massive/photon Kerr geodesics, Carter-Mino integration, invariant residuals, verification campaigns and frequency-structure refinement.\n7. **Sun–Jupiter–Saturn Dynamics** — barycentric orbital dynamics, controlled Newtonian/1PN studies, long-horizon diagnostics, V&V workflow and 5:2 commensurability refinement.\n8. **Multilayer Honeycomb Lattice** — reduced-unit multilayer lattice dynamics, stacking/defects/strain, phonon dispersion/DOS and transport refinement.\n9. **RADIA Magnet Studio** — 3-D magnet geometry, native RADIA field solving, harmonics, field integrals, trajectory/phase metrics and manufacturing-error ensembles.\n10. **Radiation Platform** — magnet-to-trajectory-to-radiation workflow, scan-centric analysis and ideal/reference comparisons."
    text = replace_once(text, old_list_tail, new_list_tail, "README restored Lab list")
    old_source = "All managed module downloads are pinned to explicit Git commit revisions in `src-tauri/resources/modules.json`; `physical-lab-source.json` records the revision actually requested for each managed checkout."
    new_source = "The seven external Labs and three runtime/builders remain pinned to explicit Git commit revisions in `src-tauri/resources/modules.json`. Kerr, Solar System and Honeycomb are first-class **bundled Labs**: their strengthened solver/UI implementations ship inside the Physical Lab build, while installation creates only an isolated per-Lab environment and a small managed launcher wrapper. They are not duplicated into a second solver checkout."
    text = replace_once(text, old_source, new_source, "README source policy")
    path.write_text(text, encoding="utf-8")


def patch_changelog() -> None:
    path = ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    old = "## [Unreleased]\n\nNo unreleased changes."
    new = """## [Unreleased]\n\n### Restored — first-class bundled scientific Labs\n- Restored **Kerr Black Hole Geodesics**, **Sun–Jupiter–Saturn Dynamics**, and **Multilayer Honeycomb Lattice** as top-level launcher Labs instead of hiding them under nonlinear-chaos / oscillation profiles.\n- The three Labs reuse the already strengthened solver, workflow, UI, verification and Model Refinement implementations shipped inside Physical Lab; no scientific equations were rewritten for this restoration.\n- Added a bundled-Lab installation path that creates an isolated per-Lab Python environment and launcher wrapper without downloading or maintaining a second solver repository.\n- Added a regression contract requiring **10 Labs + 3 runtime/builders** so these model families cannot silently disappear from the catalog again.\n\n### Boundary\nThis restoration changes product identity, navigation and environment preparation. Existing numerical/model validity boundaries remain unchanged; first-class visibility does not imply experimental validation, calibrated material properties, astrophysical truth, safety approval or certification."""
    text = replace_once(text, old, new, "CHANGELOG Unreleased restoration")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_modules()
    patch_lib()
    patch_refinement_ui()
    patch_ui_profiles()
    patch_tauri()
    patch_self_check()
    patch_readme()
    patch_changelog()
    print("bundled model Lab restoration patch applied")


if __name__ == "__main__":
    main()
