#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {n}")
    return text.replace(old, new, 1)


runtime = ROOT / "src-tauri/src/research_runtime_support.rs"
text = runtime.read_text(encoding="utf-8")
text = once(
    text,
    'fn modules_root(app: &AppHandle) -> Result<PathBuf, String> {\n',
    '''fn ui_overlay_dir(app:&AppHandle)->Option<PathBuf>{\n    if let Ok(resource_dir)=app.path().resource_dir(){\n        let p=resource_dir.join("ui");\n        if p.join("sitecustomize.py").is_file(){return Some(p)}\n    }\n    let dev=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/ui");\n    if dev.join("sitecustomize.py").is_file(){Some(dev)}else{None}\n}\n\nfn modules_root(app: &AppHandle) -> Result<PathBuf, String> {\n''',
    "runtime UI overlay helper",
)
old_arm = '''        "radiation-platform"=>"import numpy as np; g=1000.; K=1.; lu=0.05; lam=lu*(1+K*K/2)/(2*g*g); assert np.isfinite(lam) and lam>0; print('ideal undulator resonance baseline passed')",\n        _=>"print('No smoke script')"'''
new_arm = '''        "radiation-platform"=>"import numpy as np; g=1000.; K=1.; lu=0.05; lam=lu*(1+K*K/2)/(2*g*g); assert np.isfinite(lam) and lam>0; print('ideal undulator resonance baseline passed')",\n        "kerr-geodesics"=>"import numpy as np; from physical_lab_kerr_geodesics import KerrOrbitConfig,integrate_case,result_summary; c=KerrOrbitConfig(spin=0.5,inclination_deg=30.0,particle_type='massive',periapsis=6.5,apoapsis=10.0,lam_max=1.0,samples=200); r=integrate_case(c); s=result_summary(r); assert np.isfinite(float(s['first_integral_residual_max'])); print('bundled Kerr geodesic core passed')",\n        "solar-system-dynamics"=>"import numpy as np; from physical_lab_solar_system_dynamics import SolarSystemConfig,integrate_case; c=SolarSystemConfig(duration_years=0.1,samples=100,max_step_years=0.01); r=integrate_case(c); assert np.isfinite(np.asarray(r['positions_AU'],dtype=float)).all(); print('bundled Sun-Jupiter-Saturn core passed')",\n        "honeycomb-lattice"=>"import numpy as np; from physical_lab_lattice_dynamics import LatticeConfig,build_lattice; m=build_lattice(LatticeConfig(nx=2,ny=2,layers=2,drive_mode='none')); assert len(m.positions)==16 and len(m.inplane_i)>0 and np.isfinite(m.positions).all(); print('bundled honeycomb lattice core passed')",\n        _=>"import sys; print('No scientific smoke script registered',file=sys.stderr); raise SystemExit(3)"'''
text = once(text, old_arm, new_arm, "bundled smoke scripts")
text = once(
    text,
    '        let proc=Command::new(&py).args(["-c",smoke_script(&m.id)]).output();\n',
    '''        let mut command=Command::new(&py);\n        command.args(["-c",smoke_script(&m.id)]);\n        if let Some(ui)=ui_overlay_dir(&app){command.env("PYTHONPATH",ui);}\n        let proc=command.output();\n''',
    "smoke PYTHONPATH wiring",
)
runtime.write_text(text, encoding="utf-8")

validation = ROOT / "scripts/bundled_model_labs_validation.py"
v = validation.read_text(encoding="utf-8")
needle = '    tauri = json.loads((ROOT / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))\n'
insert = '''    runtime_support = (ROOT / "src-tauri" / "src" / "research_runtime_support.rs").read_text(encoding="utf-8")\n    for marker in (\n        '"kerr-geodesics"=>',\n        '"solar-system-dynamics"=>',\n        '"honeycomb-lattice"=>',\n        'command.env("PYTHONPATH",ui)',\n        "No scientific smoke script registered",\n    ):\n        assert marker in runtime_support, marker\n\n'''
v = once(v, needle, insert + needle, "bundled smoke validation")
validation.write_text(v, encoding="utf-8")
print("bundled scientific smoke patch applied")
