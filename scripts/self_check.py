#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
required = [
    'package.json','web/index.html','web/styles.css','web/app.js',
    'src-tauri/Cargo.toml','src-tauri/tauri.conf.json','src-tauri/src/lib.rs',
    'src-tauri/src/main.rs','src-tauri/resources/modules.json','src-tauri/resources/dependencies.json',
    'src-tauri/resources/safe_engine_server.py','src-tauri/resources/ui/sitecustomize.py','src-tauri/resources/ui/physical_lab_advanced.py','BUILD_PHYSICAL_LAB.command'
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
assert conf['version']=='0.4.1'
assert json.loads((root/'package.json').read_text())['version']=='0.4.1'
assert 'version = "0.4.1"' in (root/'src-tauri/Cargo.toml').read_text()
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

print('Physical Lab v0.4.1 all-lab advanced-experiment self-check: PASS')
print('Modules: 10 (7 labs + 3 runtime/builders)')
print('Dependency health catalog:', len(deps), 'items')
print('Persistent backend logs + data-folder access: configured')
print('Per-model uninstall + per-task delete: configured')
print('Old radiaition-study / Radiation Study: hard-excluded')

print('Enhanced simulation profiles: 7')
print('Responsive KPI/result-card system: configured')
