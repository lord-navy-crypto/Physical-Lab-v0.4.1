//! Runtime-only research support for Physical Lab desktop commands.
//!
//! This module intentionally contains no Project/workspace storage implementation.
//! It owns shared DTOs plus Lab environment compatibility, managed-venv repair,
//! scientific smoke checks, and optional adapter presence reporting.
//!
//! `research_legacy_impl.rs` remains frozen in the repository as a compatibility
//! and regression fixture; it is not compiled into the desktop runtime.

use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    time::Instant,
};
use tauri::{AppHandle, Manager};

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct LabSpec {
    id: String,
    name: String,
    kind: String,
    requirements: Option<String>,
    #[serde(default)]
    verify_imports: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WorkspaceSummary {
    pub id: String,
    pub name: String,
    pub created_at: String,
    pub updated_at: String,
    pub path: String,
    pub datasets: usize,
    pub runs: usize,
    pub campaigns: usize,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CompatibilityRow {
    pub module_id: String,
    pub module_name: String,
    pub installed: bool,
    pub interpreter: Option<String>,
    pub package: String,
    pub requirement: String,
    pub found_version: Option<String>,
    pub compatible: Option<bool>,
    pub detail: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SmokeResult {
    pub module_id: String,
    pub module_name: String,
    pub installed: bool,
    pub passed: bool,
    pub scientific_ready: bool,
    pub detail: String,
    pub duration_ms: u128,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct DatasetSummary {
    pub id: String,
    pub name: String,
    pub quantity: String,
    pub unit: String,
    pub sensor: String,
    pub format: String,
    pub source_file: String,
    pub stored_file: String,
    pub sha256: Option<String>,
    pub created_at: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ColumnStats {
    pub column: String,
    pub n: usize,
    pub mean: f64,
    pub std_dev: f64,
    pub ci95_low: f64,
    pub ci95_high: f64,
    pub min: f64,
    pub max: f64,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ValidationResult {
    pub n: usize,
    pub mae: f64,
    pub rmse: f64,
    pub max_abs_error: f64,
    pub relative_rmse: Option<f64>,
    pub r2: Option<f64>,
    pub agreement: String,
    pub notes: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AdapterStatus {
    pub id: String,
    pub name: String,
    pub runtime_found: bool,
    pub consumed_by_current_lab: bool,
    pub adapter_state: String,
    pub interchange: Vec<String>,
    pub note: String,
}

fn app_root(app: &AppHandle) -> Result<PathBuf, String> {
    let p = app.path().app_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&p).map_err(|e| e.to_string())?;
    Ok(p)
}

fn modules_root(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app_root(app)?.join("modules"))
}

fn lab_specs() -> Result<Vec<LabSpec>, String> {
    let all: Vec<LabSpec> = serde_json::from_str(include_str!("../resources/modules.json")).map_err(|e| e.to_string())?;
    Ok(all.into_iter().filter(|m| m.kind == "lab").collect())
}

fn requirement_name(line:&str)->String{
    let trimmed=line.trim(); let mut name=String::new();
    for c in trimmed.chars(){if c.is_ascii_alphanumeric()||c=='-'||c=='_'||c=='.'{name.push(c)}else{break}}
    name
}

fn command_text(program:&str,args:&[&str])->Option<String>{
    let out=Command::new(program).args(args).output().ok()?; if !out.status.success(){return None} Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn pep440_probe(py:&Path, package:&str, requirement:&str)->(Option<String>,Option<bool>,String){
    let code=r#"import sys,importlib.metadata as m
name=sys.argv[1]; req=sys.argv[2]
try: v=m.version(name)
except Exception: print('MISSING|||'); raise SystemExit(0)
try:
 try:
  from packaging.specifiers import SpecifierSet
  from packaging.version import Version
 except Exception:
  from pip._vendor.packaging.specifiers import SpecifierSet
  from pip._vendor.packaging.version import Version
 spec=req[len(name):].split(';',1)[0].strip()
 ok=Version(v) in SpecifierSet(spec) if spec else True
 print(v+'|||'+('1' if ok else '0'))
except Exception as e: print(v+'|||?|||'+str(e))
"#;
    let out=Command::new(py).args(["-c",code,package,requirement]).output();
    let Ok(out)=out else{return(None,None,"Version probe failed".into())};
    let text=String::from_utf8_lossy(&out.stdout).trim().to_string();
    if text.starts_with("MISSING|||"){return(None,Some(false),"Package missing from this Lab environment".into())}
    let parts:Vec<&str>=text.split("|||").collect(); let v=parts.first().filter(|s|!s.is_empty()).map(|s|s.to_string());
    let ok=match parts.get(1).copied(){Some("1")=>Some(true),Some("0")=>Some(false),_=>None};
    (v,ok,parts.get(2).unwrap_or(&"").to_string())
}

pub fn lab_compatibility_matrix(app:AppHandle)->Result<Vec<CompatibilityRow>,String>{
    let mut rows=vec![]; let root=modules_root(&app)?;
    for m in lab_specs()?{
        let moddir=root.join(&m.id); let src=moddir.join("source"); let py=moddir.join(".venv/bin/python"); let installed=src.exists()&&py.exists();
        if !installed{
            rows.push(CompatibilityRow{module_id:m.id,module_name:m.name,installed:false,interpreter:None,package:"Environment".into(),requirement:"installed Lab venv".into(),found_version:None,compatible:None,detail:"Install the Lab before per-environment compatibility can be evaluated.".into()}); continue
        }
        let interp=command_text(py.to_string_lossy().as_ref(), &["-c","import sys; print(sys.executable+' | '+sys.version.split()[0])"]);
        let req_path=m.requirements.as_ref().map(|r|src.join(r));
        if let Some(req)=req_path.filter(|p|p.exists()){
            let text=fs::read_to_string(req).map_err(|e|e.to_string())?;
            for line in text.lines(){
                let line=line.split('#').next().unwrap_or("").trim(); if line.is_empty()||line.starts_with('-'){continue}
                let pkg=requirement_name(line); if pkg.is_empty(){continue}
                let (ver,ok,detail)=pep440_probe(&py,&pkg,line);
                rows.push(CompatibilityRow{module_id:m.id.clone(),module_name:m.name.clone(),installed:true,interpreter:interp.clone(),package:pkg,requirement:line.into(),found_version:ver,compatible:ok,detail});
            }
        }else{
            for pkg in &m.verify_imports{
                let req=pkg.clone(); let (ver,ok,detail)=pep440_probe(&py,pkg,&req);
                rows.push(CompatibilityRow{module_id:m.id.clone(),module_name:m.name.clone(),installed:true,interpreter:interp.clone(),package:pkg.clone(),requirement:req,found_version:ver,compatible:ok,detail});
            }
        }
    }
    Ok(rows)
}

pub fn repair_lab_environment(app:AppHandle,module_id:String)->Result<String,String>{
    let m=lab_specs()?.into_iter().find(|m|m.id==module_id).ok_or("Unknown Lab")?; let moddir=modules_root(&app)?.join(&m.id); let py=moddir.join(".venv/bin/python"); let src=moddir.join("source");
    if !py.exists(){return Err("Managed Lab venv not found. Install the Lab first.".into())}
    let req=m.requirements.map(|r|src.join(r)).ok_or("Lab has no requirements file")?; if !req.exists(){return Err("Lab requirements file not found".into())}
    let status=Command::new(&py).args(["-m","pip","install","-r",req.to_string_lossy().as_ref()]).status().map_err(|e|e.to_string())?;
    if !status.success(){return Err("Managed venv repair failed; system Python and Conda environments were not modified.".into())}
    Ok(format!("Repaired only {}'s managed .venv.",m.name))
}

fn smoke_script(id:&str)->&'static str{
    match id{
        "numerical-methods"=>"import math,numpy as np; x=0.1; approx=sum(((-1)**k)*x**(2*k+1)/math.factorial(2*k+1) for k in range(8)); assert np.isfinite(approx) and abs(approx-math.sin(x))<1e-12; print('Taylor sine finite and accurate')",
        "ising-monte-carlo"=>"import numpy as np; a=np.ones((8,8)); e=-float((a*np.roll(a,1,0)).sum()+(a*np.roll(a,1,1)).sum()); assert np.isfinite(e) and e<0; print('8x8 ferromagnetic energy finite')",
        "random-walk-monte-carlo"=>"import numpy as np; rng=np.random.default_rng(7); s=rng.choice([-1,1],size=(2000,100)); x=s.sum(1); msd=float(np.mean(x*x)); assert np.isfinite(msd) and 70<msd<130; print('random-walk MSD finite and near N')",
        "nonlinear-chaos"=>"import numpy as np; from scipy.integrate import solve_ivp; f=lambda t,y:[y[1],-np.sin(y[0])]; sol=solve_ivp(f,[0,1],[0.3,0.0],rtol=1e-7,atol=1e-9); assert sol.success and np.isfinite(sol.y).all(); print('nonlinear pendulum short integration passed')",
        "oscillation-integration"=>"import numpy as np; from scipy.integrate import solve_ivp; f=lambda t,y:[y[1],-y[0]]; sol=solve_ivp(f,[0,6.28],[1,0],rtol=1e-8,atol=1e-10); err=abs(sol.y[0,-1]-1); assert sol.success and err<1e-3; print('harmonic oscillator returns near initial state')",
        "radia-magnet-studio"=>"import numpy as np; assert np.isfinite(0.934*1.0*5.0); print('RADIA Lab scientific Python baseline passed')",
        "radiation-platform"=>"import numpy as np; g=1000.; K=1.; lu=0.05; lam=lu*(1+K*K/2)/(2*g*g); assert np.isfinite(lam) and lam>0; print('ideal undulator resonance baseline passed')",
        _=>"print('No smoke script')"
    }
}

pub fn scientific_smoke_tests(app:AppHandle)->Result<Vec<SmokeResult>,String>{
    let mut out=vec![]; let root=modules_root(&app)?;
    for m in lab_specs()?{
        let py=root.join(&m.id).join(".venv/bin/python"); let installed=py.exists(); let start=Instant::now();
        if !installed{out.push(SmokeResult{module_id:m.id,module_name:m.name,installed:false,passed:false,scientific_ready:false,detail:"Lab not installed; smoke test skipped.".into(),duration_ms:start.elapsed().as_millis()});continue}
        let proc=Command::new(&py).args(["-c",smoke_script(&m.id)]).output();
        match proc{
            Ok(p)=>{let passed=p.status.success();let detail=if passed{String::from_utf8_lossy(&p.stdout).trim().to_string()}else{String::from_utf8_lossy(&p.stderr).trim().to_string()};out.push(SmokeResult{module_id:m.id,module_name:m.name,installed:true,passed,scientific_ready:passed,detail,duration_ms:start.elapsed().as_millis()})},
            Err(e)=>out.push(SmokeResult{module_id:m.id,module_name:m.name,installed:true,passed:false,scientific_ready:false,detail:e.to_string(),duration_ms:start.elapsed().as_millis()})
        }
    }
    Ok(out)
}

pub fn adapter_statuses(app:AppHandle)->Result<Vec<AdapterStatus>,String>{
    let home=std::env::var("HOME").unwrap_or_default(); let chrono_found=[format!("{home}/Desktop/ChronoModal-Universal2"),format!("{home}/.local/chrono-modal")].iter().any(|p|Path::new(p).exists()); let vamp=Path::new(&format!("{home}/.local/vampire-apple-silicon/bin/vampire")).exists();
    Ok(vec![
        AdapterStatus{id:"chrono-modal".into(),name:"Chrono::Modal".into(),runtime_found:chrono_found,consumed_by_current_lab:false,adapter_state:"Interchange contract ready; solver adapter intentionally not claimed".into(),interchange:vec!["mass matrix".into(),"stiffness matrix".into(),"damping matrix".into(),"units".into(),"coordinate order".into(),"solver tolerances".into(),"provenance".into()],note:"Use CMake find_package(Chrono COMPONENTS Modal CONFIG) and provider verification before enabling a real comparison adapter.".into()},
        AdapterStatus{id:"vampire".into(),name:"VAMPIRE".into(),runtime_found:vamp,consumed_by_current_lab:false,adapter_state:"Input/result contract ready; no fake atomistic solver".into(),interchange:vec!["material".into(),"lattice".into(),"temperature".into(),"field".into(),"magnetization results".into(),"provenance".into()],note:"The current Apple-Silicon runtime remains optional until a validated Lab adapter consumes it.".into()}
    ])
}
