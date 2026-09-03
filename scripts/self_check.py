#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
required = [
    'package.json','web/index.html','web/styles.css','web/app.js',
    'src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src-tauri/src/lib.rs','src-tauri/src/research.rs',
    'src-tauri/src/main.rs','src-tauri/resources/modules.json','src-tauri/resources/dependencies.json',
    'src-tauri/resources/safe_engine_server.py','src-tauri/resources/ui/sitecustomize.py','src-tauri/resources/ui/physical_lab_advanced.py','BUILD_PHYSICAL_LAB.command','PACKAGE_RELEASE_DMG.command'
]
missing = [p for p in required if not (root / p).exists()]
if missing:
    raise SystemExit('Missing required files: ' + ', '.join(missing))

mods = json.loads((root/'src-tauri/resources/modules.json').read_text())
ids = [m['id'] for m in mods]
assert len(mods) == 10, f'Expected 10 modules, found {len(mods)}'
assert len(ids) == len(set(ids)), 'Duplicate module ids'
assert sum(m['kind']=='lab' for m in mods) == 7
assert sum(m['kind']=='runtime' for m in mods) == 3
assert all(m['repo'].startswith('lord-navy-crypto/') for m in mods)
# Old Radiation Study is explicitly out of scope and must never re-enter the app catalog.
manifest_text=(root/'src-tauri/resources/modules.json').read_text().lower()
dep_text=(root/'src-tauri/resources/dependencies.json').read_text().lower()
web_text=(root/'web/app.js').read_text().lower()
assert 'radiaition-study' not in manifest_text
assert 'radiation study' not in manifest_text
assert 'radiaition-study' not in dep_text
assert 'radiation study' not in dep_text
assert 'radiaition-study' not in web_text
assert next(m for m in mods if m['id']=='random-walk-monte-carlo')['pythonRequires']=='>=3.11'
assert 'pytest' in next(m for m in mods if m['id']=='random-walk-monte-carlo')['runtimeExcludes']
assert next(m for m in mods if m['id']=='vampire-runtime')['supportedArches']==['arm64']

labs=[m for m in mods if m['kind']=='lab']
for m in labs:
    assert 'fragileDependencies' in m
    assert m['safeBackend'] in {'standard','radia-analytic','radiation-analytic'}
    assert m['safeModeNote'] and m['fullModeNote']
    assert m['entrypoint']

radia_mag=next(m for m in mods if m['id']=='radia-magnet-studio')
radiation=next(m for m in mods if m['id']=='radiation-platform')
assert radia_mag['fragileDependencies']==['radia']
assert radiation['fragileDependencies']==['radia']
fragile={d for m in labs for d in m['fragileDependencies']}
assert not fragile & {'numpy','scipy','matplotlib','pandas','plotly','streamlit','mpmath','h5py'}
assert not any('pychrono' in m['fragileDependencies'] for m in labs)
assert not any('chrono-modal' in m['fragileDependencies'] for m in labs)
assert not any('vampire' in m['fragileDependencies'] for m in labs)

lib = (root/'src-tauri/src/lib.rs').read_text()
for needle in [
    'fn dependency_statuses(', 'struct DependencyStatus', 'fn discovered_python_envs(',
    'fn conda_python_candidates(', 'fn append_log(', 'fn open_log_directory(',
    'fn open_data_directory(', 'fn uninstall_module(', 'server-{safe_id}-{safe_mode}.log',
    'PHYSICAL_LAB_PYCHRONO_PYTHON', 'fn radia_abi_minor()', 'safe_ready', 'full_ready'
]:
    assert needle in lib, needle

web=(root/'web/app.js').read_text()
for needle in ['dependency_statuses','health-light','data-uninstall','uninstall_module','data-task-delete','open_log_directory','open_data_directory']:
    assert needle in web, needle

deps=json.loads((root/'src-tauri/resources/dependencies.json').read_text())
dep_ids={d['id'] for d in deps}
assert len(deps) >= 17
assert {'python-runtime','numpy','scipy','pandas','plotly','streamlit','matplotlib','h5py','mpmath','xcode-clt','native-toolchain','cmake','fftw','radia','pychrono','chrono-modal','vampire'} <= dep_ids

conf=json.loads((root/'src-tauri/tauri.conf.json').read_text())
assert conf['version']=='0.5.0'
assert json.loads((root/'package.json').read_text())['version']=='0.5.0'
assert 'version = "0.5.0"' in (root/'src-tauri/Cargo.toml').read_text()
assert 'resources/safe_engine_server.py' in conf['bundle']['resources']
assert 'resources/ui/sitecustomize.py' in conf['bundle']['resources']
assert 'resources/ui/physical_lab_advanced.py' in conf['bundle']['resources']
ui=(root/'src-tauri/resources/ui/sitecustomize.py').read_text()
for profile in ['numerical-methods','ising-monte-carlo','random-walk-monte-carlo','nonlinear-chaos','oscillation-integration','radia-magnet-studio','radiation-platform']:
    assert profile in ui
assert 'pl-result-grid' in ui
assert 'Quick preset' in ui
assert 'PHYSICAL_LAB_UI_PROFILE' in lib
assert 'ensure_advanced_experiment_hook' in lib
for profile in ['numerical-methods','ising-monte-carlo','random-walk-monte-carlo','nonlinear-chaos','oscillation-integration','radia-magnet-studio','radiation-platform']:
    assert profile in lib, profile
advanced=(root/'src-tauri/resources/ui/physical_lab_advanced.py').read_text()
for feature in ['2D sensitivity atlas','Binder cumulant','Twin-trajectory divergence','Run adaptive critical scan','Run stability atlas','Reliability frontier','Diffusion scaling law','Damping × drive atlas','Manufacturing seed ensemble','Driven bifurcation intelligence','Magnetization-distribution microscope']:
    assert feature in advanced, feature
for profile in ['numerical-methods','ising-monte-carlo','random-walk-monte-carlo','nonlinear-chaos','oscillation-integration','radia-magnet-studio','radiation-platform']:
    assert profile in advanced, profile

print('Physical Lab v0.5.0 Research Workspace self-check: PASS')
print('Modules: 10 (7 labs + 3 runtime/builders)')
print('Dependency health catalog:', len(deps), 'items')
print('Persistent backend logs + data-folder access: configured')
print('Per-model uninstall + per-task delete: configured')
print('Old radiaition-study / Radiation Study: hard-excluded')

research=(root/'src-tauri/src/research.rs').read_text()
for needle2 in [
    'fn create_workspace(', 'fn import_measurement_dataset(', 'fn capture_serial_measurement(',
    'fn lab_compatibility_matrix(', 'SpecifierSet', 'fn scientific_smoke_tests(',
    'fn pipeline_templates(', 'fn create_campaign(', 'fn export_reproducibility_package(',
    'fn validate_dataset_columns(', 'fn adapter_statuses(', 'fn compare_run_snapshots('
]:
    assert needle2 in research, needle2
for needle2 in ['fn cancel_task(', 'task_cancelled(app,task)', 'cancelled: Mutex<HashSet<String>>']:
    assert needle2 in lib, needle2
web_html=(root/'web/index.html').read_text()
for needle2 in ['workspacesView','dataView','integrityView','pipelinesView','campaignsView','resultsView','captureSerial','compareRuns']:
    assert needle2 in web_html, needle2
web_js=(root/'web/app.js').read_text()
for needle2 in ['list_workspaces','import_measurement_dataset','lab_compatibility_matrix','scientific_smoke_tests','create_campaign','export_reproducibility_package','compare_run_snapshots','cancel_task']:
    assert needle2 in web_js, needle2
print('Research workspace + measurement bridge + integrity matrix: configured')
print('Pipeline contracts + campaign queues + run comparison: configured')
print('Reproducibility export + task cancellation: configured')
print('Enhanced simulation profiles: 7')
print('Responsive KPI/result-card system: configured')

# v0.5.0 public/reproducibility hardening
required_public = [
    'docs/ORIGINAL_CONTRIBUTIONS.md', 'docs/VALIDATION.md', 'docs/RESEARCH_NOTE_RADIATION.md',
    'docs/source-integrity.example.yml', '.github/workflows/source-integrity.yml', 'scripts/reference_validation.py', 'docs/REFERENCE_VALIDATION.md', 'docs/reference-validation.json'
]
for rel in required_public:
    assert (root/rel).is_file(), f'missing public/research file: {rel}'
for m in mods:
    rev=m.get('revision','')
    assert isinstance(rev,str) and len(rev)==40 and all(c in '0123456789abcdef' for c in rev.lower()), f"{m.get('id')} missing pinned 40-char revision"
print('Source pinning: 10/10 module revisions pinned')
print('Admissions/research README: configured')
print('Original-contribution boundary: configured')
print('Validation/research note: configured')
print('Source Integrity CI: configured')
print('Deterministic reference validation: configured')
digital_core=(root/'src-tauri/resources/ui/physical_lab_digital_twin.py').read_text()
digital_ui=(root/'src-tauri/resources/ui/physical_lab_digital_twin_ui.py').read_text()
advanced_text=(root/'src-tauri/resources/ui/physical_lab_advanced.py').read_text()
lib_text=(root/'src-tauri/src/lib.rs').read_text()
tauri_text=(root/'src-tauri/tauri.conf.json').read_text()
for needle in ['fit_linear_calibration','compare_field_series','fit_model_affine','analyze_beam_phase_space','suggest_residual_measurement_points']:
    assert needle in digital_core, needle
for needle in ['Measurement Digital Twin','linear-sensor-calibration','measured-model-field-comparison','beam-phase-space','residual-guided-remeasurement']:
    assert needle in digital_ui, needle
assert 'render_digital_twin_workspace(st, profile)' in advanced_text
assert 'radia-magnet-studio' in lib_text and 'radiation-platform' in lib_text
assert 'physical_lab_digital_twin.py' in tauri_text and 'physical_lab_digital_twin_ui.py' in tauri_text
assert (root/'scripts/digital_twin_reference_validation.py').is_file()
assert (root/'scripts/physical_lab_digital_twin_cli.py').is_file()
assert (root/'.github/workflows/full-mode-acceptance.yml').is_file()
print('Measurement Digital Twin core + project UI: configured')
print('RADIA Full-mode acceptance workflow: configured')
