mod research;
mod model_builder;
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use std::{
    collections::{HashMap, HashSet},
    fs::{self, OpenOptions},
    io::{BufRead, BufReader, Write},
    net::{TcpListener, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, Manager, State};
use tokio::io::AsyncWriteExt;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ModuleSpec {
    id: String,
    name: String,
    category: String,
    kind: String,
    repo: String,
    branch: String,
    #[serde(default)]
    bundled: bool,
    #[serde(default)]
    revision: Option<String>,
    entrypoint: Option<String>,
    requirements: Option<String>,
    launcher: Option<String>,
    runtime_requires: Vec<String>,
    description: String,
    tags: Vec<String>,
    #[serde(default)]
    python_requires: Option<String>,
    #[serde(default)]
    verify_imports: Vec<String>,
    #[serde(default)]
    supported_arches: Vec<String>,
    #[serde(default)]
    system_requires: Vec<String>,
    #[serde(default)]
    runtime_excludes: Vec<String>,
    #[serde(default)]
    fragile_dependencies: Vec<String>,
    #[serde(default = "default_safe_backend")]
    safe_backend: String,
    #[serde(default)]
    safe_mode_note: String,
    #[serde(default)]
    full_mode_note: String,
}

fn default_safe_backend() -> String { "standard".into() }


#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct DependencySpec {
    id: String,
    name: String,
    category: String,
    delivery: String,
    required: bool,
    source_name: String,
    source_url: String,
    description: String,
    used_by: Vec<String>,
    notes: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct DependencyStatus {
    id: String,
    level: String,
    label: String,
    detail: String,
    locations: Vec<String>,
    version: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ModuleStatus {
    id: String,
    installed: bool,
    ready: bool,
    safe_ready: bool,
    full_ready: bool,
    busy: bool,
    state: String,
    path: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeStatus {
    os: String,
    arch: String,
    python_ready: bool,
    python_version: String,
    python_path: Option<String>,
    radia_ready: bool,
    radia_detail: String,
    pychrono_ready: bool,
    pychrono_detail: String,
    pychrono_python: Option<String>,
    chrono_ready: bool,
    chrono_detail: String,
    vampire_ready: bool,
    vampire_detail: String,
    cmake_ready: bool,
    cmake_detail: String,
    xcode_clt_ready: bool,
    xcode_clt_detail: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct TaskEvent {
    task_id: String,
    module_id: String,
    title: String,
    stage: String,
    status: String,
    percent: Option<f64>,
    message: String,
    done: bool,
    error: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct LaunchInfo {
    module_id: String,
    url: String,
    port: u16,
    mode: String,
}

struct RunningServer {
    child: Child,
    port: u16,
    mode: String,
}

#[derive(Default)]
struct PhysicalLabState {
    servers: Mutex<HashMap<String, RunningServer>>,
    busy: Mutex<HashSet<String>>,
    cancelled: Mutex<HashSet<String>>,
}

fn module_specs() -> Result<Vec<ModuleSpec>, String> {
    serde_json::from_str(include_str!("../resources/modules.json")).map_err(|e| e.to_string())
}

fn dependency_specs() -> Result<Vec<DependencySpec>, String> {
    serde_json::from_str(include_str!("../resources/dependencies.json")).map_err(|e| e.to_string())
}

fn module_spec(id: &str) -> Result<ModuleSpec, String> {
    module_specs()?
        .into_iter()
        .find(|m| m.id == id)
        .ok_or_else(|| format!("Unknown Physical Lab module: {id}"))
}

fn data_root(app: &AppHandle) -> Result<PathBuf, String> {
    let root = app.path().app_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    Ok(root)
}

fn logs_dir(app: &AppHandle) -> Result<PathBuf, String> {
    let dir = data_root(app)?.join("logs");
    fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    Ok(dir)
}

fn main_log_path(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(logs_dir(app)?.join("physical-lab.log"))
}

fn append_log(app: &AppHandle, line: &str) {
    if let Ok(path) = main_log_path(app) {
        if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
            let stamp = chrono::Local::now().format("%Y-%m-%d %H:%M:%S");
            let _ = writeln!(file, "[{stamp}] {line}");
        }
    }
}

fn module_log_path(app: &AppHandle, id: &str, mode: &str) -> Result<PathBuf, String> {
    let safe_id: String = id.chars().map(|c| if c.is_ascii_alphanumeric() || c=='-' || c=='_' {c} else {'_'}).collect();
    let safe_mode: String = mode.chars().map(|c| if c.is_ascii_alphanumeric() || c=='-' || c=='_' {c} else {'_'}).collect();
    Ok(logs_dir(app)?.join(format!("server-{safe_id}-{safe_mode}.log")))
}

fn module_root(app: &AppHandle, id: &str) -> Result<PathBuf, String> {
    Ok(data_root(app)?.join("modules").join(id))
}

fn source_dir(app: &AppHandle, id: &str) -> Result<PathBuf, String> {
    Ok(module_root(app, id)?.join("source"))
}

fn venv_python(app: &AppHandle, id: &str) -> Result<PathBuf, String> {
    Ok(module_root(app, id)?.join(".venv/bin/python"))
}

fn home_dir() -> PathBuf {
    std::env::var_os("HOME").map(PathBuf::from).unwrap_or_else(|| PathBuf::from("/tmp"))
}

fn output(program: &str, args: &[&str]) -> Option<String> {
    let out = Command::new(program).args(args).output().ok()?;
    if !out.status.success() {
        return None;
    }
    let stdout = String::from_utf8_lossy(&out.stdout).trim().to_string();
    let stderr = String::from_utf8_lossy(&out.stderr).trim().to_string();
    if !stdout.is_empty() { Some(stdout) } else if !stderr.is_empty() { Some(stderr) } else { Some(String::new()) }
}

fn python_candidates_for_minor(minor: u32) -> Vec<String> {
    let v = format!("3.{minor}");
    vec![
        format!("/Library/Frameworks/Python.framework/Versions/{v}/bin/python{v}"),
        format!("/opt/homebrew/bin/python{v}"),
        format!("/usr/local/bin/python{v}"),
        format!("python{v}"),
    ]
}

fn python_candidates() -> Vec<String> {
    let mut candidates = Vec::new();
    if let Ok(p) = std::env::var("PYTHON_BIN") {
        if !p.trim().is_empty() { candidates.push(p); }
    }
    // Prefer well-supported desktop runtimes, but include python.org Framework
    // locations because Finder-launched apps do not inherit an interactive shell PATH.
    for minor in [12u32, 13, 14, 11, 10] {
        candidates.extend(python_candidates_for_minor(minor));
    }
    candidates.extend([
        "/opt/homebrew/bin/python3".to_string(),
        "/usr/local/bin/python3".to_string(),
        "/Library/Frameworks/Python.framework/Versions/Current/bin/python3".to_string(),
        "python3".to_string(),
    ]);
    candidates
}

fn python_tuple(program: &str) -> Option<(u32,u32,u32)> {
    let text = output(program, &["-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"])?;
    let mut it=text.trim().split('.');
    Some((it.next()?.parse().ok()?,it.next()?.parse().ok()?,it.next()?.parse().ok()?))
}

fn minimum_python(requirement: &Option<String>) -> Option<(u32,u32)> {
    let r=requirement.as_ref()?.trim();
    let v=r.strip_prefix(">=")?.split(',').next()?.trim();
    let mut it=v.split('.'); Some((it.next()?.parse().ok()?,it.next()?.parse().ok()?))
}

fn python_meets(program: &str, requirement: &Option<String>) -> bool {
    let Some((major,minor,_))=python_tuple(program) else{return false};
    minimum_python(requirement).map(|(a,b)|(major,minor)>=(a,b)).unwrap_or(major==3)
}

fn radia_abi_minor() -> Option<u32> {
    let name = radia_extension()?.file_name()?.to_string_lossy().to_string();
    let marker = "cpython-3";
    let start = name.find(marker)? + marker.len();
    let digits: String = name[start..].chars().take_while(|c| c.is_ascii_digit()).collect();
    if digits.is_empty() { return None; }
    digits.parse::<u32>().ok()
}

fn radia_compatible_python() -> Option<PathBuf> {
    let minor=radia_abi_minor()?;
    let requirement=Some(format!(">=3.{minor}"));
    for candidate in python_candidates_for_minor(minor){
        if let Some(path)=resolve_python_candidate(&candidate,&requirement){let p=PathBuf::from(path);if radia_import_ok(&p){return Some(p)}}
    }
    None
}

fn resolve_python_candidate(candidate: &str, requirement: &Option<String>) -> Option<String> {
    if !python_meets(candidate, requirement) { return None; }
    if candidate.contains('/') {
        if Path::new(candidate).is_file() { Some(candidate.to_string()) } else { None }
    } else {
        output("which", &[candidate]).filter(|s|!s.is_empty())
    }
}

fn python_for_spec(spec: &ModuleSpec) -> Option<String> {
    // If a Lab consumes RADIA, first choose the CPython minor that matches the
    // already-installed RADIA extension. This avoids needless ABI rebuilds.
    if spec.runtime_requires.iter().any(|r| r == "radia") {
        if let Some(minor) = radia_abi_minor() {
            for candidate in python_candidates_for_minor(minor) {
                if let Some(path) = resolve_python_candidate(&candidate, &spec.python_requires) {
                    return Some(path);
                }
            }
        }
    }
    for candidate in python_candidates() {
        if let Some(path) = resolve_python_candidate(&candidate, &spec.python_requires) {
            return Some(path);
        }
    }
    None
}

fn python_info() -> (bool, String, Option<String>) {
    let generic=ModuleSpec{id:"python-probe".into(),name:"Python".into(),category:"Runtime".into(),kind:"runtime".into(),repo:String::new(),branch:String::new(),bundled:false,revision:None,entrypoint:None,requirements:None,launcher:None,runtime_requires:vec![],description:String::new(),tags:vec![],python_requires:Some(">=3.10".into()),verify_imports:vec![],supported_arches:vec![],system_requires:vec![],runtime_excludes:vec![],fragile_dependencies:vec![],safe_backend:"standard".into(),safe_mode_note:String::new(),full_mode_note:String::new()};
    if let Some(path)=python_for_spec(&generic) { let version=output(&path,&["--version"]).unwrap_or_else(||"Python 3".into()); return (true,version,Some(path)); }
    (false, "Compatible Python 3 not found".into(), None)
}

fn machine_arch() -> String { output("uname", &["-m"]).unwrap_or_else(||std::env::consts::ARCH.into()) }

fn arch_supported(spec:&ModuleSpec)->bool { spec.supported_arches.is_empty() || spec.supported_arches.iter().any(|a|a==&machine_arch()) }

fn tool_available(tool:&str)->bool {
    if tool=="xcode-clt" { return Command::new("xcode-select").arg("-p").output().map(|o|o.status.success()).unwrap_or(false); }
    if tool=="cmake" {
        let mut c=vec!["cmake".to_string(),"/opt/homebrew/bin/cmake".into(),"/usr/local/bin/cmake".into()];
        let h=home_dir(); for p in ["miniforge3/envs/chrono/bin/cmake","miniconda3/envs/chrono/bin/cmake","anaconda3/envs/chrono/bin/cmake"] {c.push(h.join(p).to_string_lossy().into());}
        return c.into_iter().any(|p|Command::new(&p).arg("--version").output().map(|o|o.status.success()).unwrap_or(false));
    }
    Command::new("/usr/bin/env").args(["which",tool]).output().map(|o|o.status.success()).unwrap_or(false)
}

fn preflight_system(spec:&ModuleSpec)->Result<(),String>{
    if !arch_supported(spec){return Err(format!("{} supports {}, but this Mac is {}.",spec.name,spec.supported_arches.join(" / "),machine_arch()))}
    if spec.python_requires.is_some() && python_for_spec(spec).is_none(){return Err(format!("{} requires Python {}, but no compatible interpreter was found.",spec.name,spec.python_requires.clone().unwrap_or_default()))}
    let missing:Vec<String>=spec.system_requires.iter().filter(|t|!tool_available(t)).cloned().collect();
    if !missing.is_empty(){return Err(format!("Missing required system tools for {}: {}. Xcode Command Line Tools must be installed through Apple; Chrono::Modal also requires CMake.",spec.name,missing.join(", ")))}
    Ok(())
}

fn radia_dir() -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(p) = std::env::var("RADIA_PYTHONPATH") { if !p.trim().is_empty() { candidates.push(PathBuf::from(p)); } }
    if let Ok(p) = std::env::var("RADIA_DEST") { if !p.trim().is_empty() { candidates.push(PathBuf::from(p).join("cpp/gcc")); } }
    let home = home_dir();
    candidates.push(home.join("Desktop/Radia-master/cpp/gcc"));
    candidates.push(home.join("Radia-master/cpp/gcc"));
    candidates.push(home.join(".local/radia/cpp/gcc"));
    candidates.into_iter().find(|p| p.is_dir())
}

fn radia_extension() -> Option<PathBuf> {
    let dir = radia_dir()?;
    let entries = fs::read_dir(&dir).ok()?;
    for entry in entries.flatten() {
        let path = entry.path();
        let name = path.file_name()?.to_string_lossy().to_ascii_lowercase();
        if path.is_file() && name.starts_with("radia") && name.ends_with(".so") { return Some(path); }
    }
    None
}


fn pychrono_candidates() -> Vec<PathBuf> {
    let home = home_dir();
    let mut out = Vec::new();
    if let Ok(p) = std::env::var("PHYSICAL_LAB_PYCHRONO_PYTHON") {
        if !p.trim().is_empty() { out.push(PathBuf::from(p)); }
    }
    if let Ok(p) = std::env::var("PYCHRONO_PYTHON") {
        if !p.trim().is_empty() { out.push(PathBuf::from(p)); }
    }
    out.extend([
        home.join("miniforge3/envs/chrono/bin/python"),
        home.join("miniconda3/envs/chrono/bin/python"),
        home.join("anaconda3/envs/chrono/bin/python"),
        home.join("mambaforge/envs/chrono/bin/python"),
    ]);
    out
}

fn pychrono_probe(program: &Path) -> Option<String> {
    if !program.is_file() { return None; }
    let code = r#"
import importlib, sys
import pychrono as chrono
mods = ['fea','vehicle','robot','postprocess','irrlicht','vsg3d','sensor','fsi','pardisomkl','cascade','ros']
ok=[]; missing=[]
for m in mods:
    try:
        importlib.import_module('pychrono.'+m); ok.append(m)
    except Exception:
        missing.append(m)
print('Python '+sys.version.split()[0])
print('core=ok')
print('available='+','.join(ok))
print('missing='+','.join(missing))
"#;
    let out = Command::new(program).args(["-c", code]).output().ok()?;
    if !out.status.success() { return None; }
    let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if text.contains("core=ok") { Some(text) } else { None }
}

fn pychrono_runtime() -> Option<(PathBuf, String)> {
    for p in pychrono_candidates() {
        if let Some(detail) = pychrono_probe(&p) { return Some((p, detail)); }
    }
    None
}

fn chrono_zip_in(path: &Path) -> Option<PathBuf> {
    if path.is_file() {
        let n = path.file_name()?.to_string_lossy().to_ascii_lowercase();
        if n.ends_with(".zip") && n.contains("chrono") { return Some(path.to_path_buf()); }
        return None;
    }
    for e in fs::read_dir(path).ok()?.flatten() {
        let p = e.path();
        if p.is_file() {
            let n = p.file_name()?.to_string_lossy().to_ascii_lowercase();
            if n.ends_with(".zip") && n.contains("chrono") { return Some(p); }
        }
    }
    None
}

fn chrono_output(app: &AppHandle) -> Option<PathBuf> {
    let home = home_dir();
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Ok(p) = std::env::var("PHYSICAL_LAB_CHRONO_SDK") { if !p.trim().is_empty() { candidates.push(PathBuf::from(p)); } }
    if let Ok(p) = std::env::var("CHRONO_MODAL_SDK") { if !p.trim().is_empty() { candidates.push(PathBuf::from(p)); } }
    if let Ok(p) = source_dir(app, "chrono-modal-runtime") { candidates.push(p.join("release")); }
    candidates.extend([
        home.join("Desktop/chrono-modal-macos-universal2-builder/release"),
        home.join("Downloads/chrono-modal-macos-universal2-builder/release"),
        home.join("Documents/GitHub/chrono-modal-macos-universal2-builder/release"),
        home.join("Developer/chrono-modal-macos-universal2-builder/release"),
        home.join(".local/physical-lab/chrono-modal"),
    ]);
    candidates.into_iter().find_map(|p| chrono_zip_in(&p))
}

fn vampire_binary() -> Option<PathBuf> {
    let base = home_dir().join(".local/vampire-apple-silicon");
    for p in [base.join("bin/vampire"), base.join("vampire")] {
        if p.is_file() { return Some(p); }
    }
    None
}

fn emit_task(app: &AppHandle, task_id: &str, module_id: &str, title: &str, stage: &str, status: &str, percent: Option<f64>, message: impl Into<String>, done: bool, error: Option<String>) {
    let message=message.into();
    append_log(app,&format!("TASK {task_id} | {module_id} | {stage} | {status} | {message}"));
    if let Some(ref e)=error{append_log(app,&format!("ERROR {task_id} | {e}"));}
    let _ = app.emit("physical-lab://task-progress", TaskEvent {
        task_id: task_id.into(), module_id: module_id.into(), title: title.into(), stage: stage.into(), status: status.into(), percent,
        message, done, error,
    });
}

fn task_id(module_id: &str) -> String {
    format!("{}-{}", module_id, chrono::Utc::now().timestamp_millis())
}

fn task_cancelled(app:&AppHandle, task:&str)->bool {
    app.state::<PhysicalLabState>().cancelled.lock().map(|s|s.contains(task)).unwrap_or(false)
}

#[tauri::command]
fn cancel_task(app:AppHandle, task_id:String)->Result<String,String>{
    app.state::<PhysicalLabState>().cancelled.lock().map_err(|_|"Cancellation-state lock failed".to_string())?.insert(task_id.clone());
    append_log(&app,&format!("CANCEL REQUEST | {task_id}"));
    Ok(format!("Cancellation requested for {task_id}"))
}

fn run_streaming(app: &AppHandle, task: &str, spec: &ModuleSpec, stage: &str, percent: Option<f64>, mut command: Command) -> Result<(), String> {
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    let mut child = command.spawn().map_err(|e| format!("Could not start {stage}: {e}"))?;
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();

    let mut readers = Vec::new();
    if let Some(out) = stdout {
        let app2 = app.clone(); let t = task.to_string(); let id = spec.id.clone(); let title = spec.name.clone(); let stage2 = stage.to_string();
        readers.push(thread::spawn(move || {
            for line in BufReader::new(out).lines().map_while(Result::ok) {
                if !line.trim().is_empty() { emit_task(&app2, &t, &id, &title, &stage2, "Running", percent, line, false, None); }
            }
        }));
    }
    if let Some(err) = stderr {
        let app2 = app.clone(); let t = task.to_string(); let id = spec.id.clone(); let title = spec.name.clone(); let stage2 = stage.to_string();
        readers.push(thread::spawn(move || {
            for line in BufReader::new(err).lines().map_while(Result::ok) {
                if !line.trim().is_empty() { emit_task(&app2, &t, &id, &title, &stage2, "Running", percent, line, false, None); }
            }
        }));
    }
    let status = loop {
        if task_cancelled(app,task){ let _=child.kill(); let _=child.wait(); for reader in readers { let _=reader.join(); } return Err("Task cancelled by user".into()); }
        match child.try_wait().map_err(|e|e.to_string())? { Some(status)=>break status, None=>thread::sleep(Duration::from_millis(180)) }
    };
    for reader in readers { let _ = reader.join(); }
    if status.success() { Ok(()) } else { Err(format!("{stage} exited with status {status}")) }
}

fn prepare_bundled_lab_source(app:&AppHandle,task:&str,spec:&ModuleSpec)->Result<PathBuf,String>{
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

async fn download_source(app: &AppHandle, task: &str, spec: &ModuleSpec, start_pct: f64, end_pct: f64) -> Result<PathBuf, String> {
    let root = module_root(app, &spec.id)?;
    fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    let source = root.join("source");
    let archive = root.join("source.tar.gz");
    if source.exists() { fs::remove_dir_all(&source).map_err(|e| e.to_string())?; }
    fs::create_dir_all(&source).map_err(|e| e.to_string())?;

    let requested_revision = spec.revision.as_deref().filter(|s| !s.trim().is_empty());
    let url = if let Some(rev)=requested_revision {
        format!("https://codeload.github.com/{}/tar.gz/{}", spec.repo, rev)
    } else {
        format!("https://codeload.github.com/{}/tar.gz/refs/heads/{}", spec.repo, spec.branch)
    };
    let source_label = requested_revision.map(|r| format!("{} @ {}", spec.repo, &r[..r.len().min(12)])).unwrap_or_else(|| format!("{} @ {}", spec.repo, spec.branch));
    emit_task(app, task, &spec.id, &spec.name, "Downloading module", "Running", Some(start_pct), format!("Fetching {source_label}"), false, None);
    let response = reqwest::Client::builder().user_agent("Physical-Lab/0.5.0").build().map_err(|e| e.to_string())?
        .get(url).send().await.map_err(|e| format!("GitHub download failed: {e}"))?;
    if !response.status().is_success() { return Err(format!("GitHub returned {} for {}", response.status(), spec.repo)); }
    let total = response.content_length();
    let mut file = tokio::fs::File::create(&archive).await.map_err(|e| e.to_string())?;
    let mut stream = response.bytes_stream();
    let mut received = 0u64;
    while let Some(chunk) = stream.next().await {
        if task_cancelled(app,task){ let _=tokio::fs::remove_file(&archive).await; return Err("Task cancelled by user".into()); }
        let bytes = chunk.map_err(|e| e.to_string())?;
        received += bytes.len() as u64;
        file.write_all(&bytes).await.map_err(|e| e.to_string())?;
        if let Some(total) = total {
            if total > 0 {
                let r = received as f64 / total as f64;
                emit_task(app, task, &spec.id, &spec.name, "Downloading module", "Running", Some(start_pct + (end_pct-start_pct)*r), format!("{:.1} MB / {:.1} MB", received as f64/1_048_576.0, total as f64/1_048_576.0), false, None);
            }
        }
    }
    file.flush().await.map_err(|e| e.to_string())?;

    let source2 = source.clone(); let archive2 = archive.clone();
    tokio::task::spawn_blocking(move || {
        let status = Command::new("/usr/bin/tar").args(["-xzf"]).arg(&archive2).arg("-C").arg(&source2).args(["--strip-components", "1"]).status().map_err(|e| e.to_string())?;
        if status.success() { Ok::<(),String>(()) } else { Err(format!("Archive extraction failed with {status}")) }
    }).await.map_err(|e| e.to_string())??;
    let _ = fs::remove_file(&archive);
    let provenance = serde_json::json!({
        "schema":"physical-lab-source-v1",
        "repository":spec.repo,
        "branch":spec.branch,
        "revision":spec.revision,
        "downloadedAt":chrono::Utc::now().to_rfc3339(),
        "policy": if spec.revision.is_some() { "pinned-commit" } else { "branch-fallback" }
    });
    let _ = fs::write(source.join("physical-lab-source.json"), serde_json::to_vec_pretty(&provenance).unwrap_or_default());
    Ok(source)
}

fn requirement_package(line:&str)->String{
    line.trim().split(|c:char|matches!(c,'='|'<'|'>'|'!'|'~'|'['|' ')).next().unwrap_or("").trim().to_ascii_lowercase().replace('_',"-")
}

fn prepared_requirements(app:&AppHandle,spec:&ModuleSpec)->Result<Option<PathBuf>,String>{
    let Some(req)=&spec.requirements else{return Ok(None)};
    let src=source_dir(app,&spec.id)?.join(req); if !src.is_file(){return Ok(None)}
    if spec.runtime_excludes.is_empty(){return Ok(Some(src))}
    let excluded:HashSet<String>=spec.runtime_excludes.iter().map(|x|x.to_ascii_lowercase().replace('_',"-")).collect();
    let text=fs::read_to_string(&src).map_err(|e|e.to_string())?;
    let filtered=text.lines().filter(|line|{let p=requirement_package(line);p.is_empty()||line.trim_start().starts_with('#')||!excluded.contains(&p)}).collect::<Vec<_>>().join("\n")+"\n";
    let out=module_root(app,&spec.id)?.join("physical-lab-runtime-requirements.txt");fs::write(&out,filtered).map_err(|e|e.to_string())?;Ok(Some(out))
}

fn verify_imports(app:&AppHandle,task:&str,spec:&ModuleSpec,vpy:&Path)->Result<(),String>{
    emit_task(app,task,&spec.id,&spec.name,"Verifying Python environment","Running",Some(90.0),"Running pip check and import smoke tests",false,None);
    let mut check=Command::new(vpy);check.args(["-m","pip","check"]).current_dir(source_dir(app,&spec.id)?);run_streaming(app,task,spec,"Dependency consistency check",Some(92.0),check)?;
    if !spec.verify_imports.is_empty(){
        let code=format!("mods={:?}; import importlib; [importlib.import_module(m) for m in mods]; print('import smoke test OK:', ', '.join(mods))",spec.verify_imports);
        let mut smoke=Command::new(vpy);smoke.args(["-c",&code]).current_dir(source_dir(app,&spec.id)?);run_streaming(app,task,spec,"Import smoke test",Some(95.0),smoke)?;
    }
    let lock=module_root(app,&spec.id)?.join("physical-lab-lock.txt");
    let out=Command::new(vpy).args(["-m","pip","freeze","--all"]).output().map_err(|e|e.to_string())?;
    if out.status.success(){fs::write(lock,out.stdout).map_err(|e|e.to_string())?;}
    Ok(())
}

fn venv_base_python(vpy:&Path)->Option<String>{output(vpy.to_string_lossy().as_ref(),&["-c","import sys; print(sys._base_executable)"]).filter(|s|!s.is_empty())}

fn radia_import_ok(vpy:&Path)->bool{
    let Some(radia_dir)=radia_dir() else{return false};
    Command::new(vpy).args(["-c","import radia; o=radia.ObjRecMag([0,0,0],[1,1,1],[0,0,1]); print(radia.__file__); print(o)"])
        .env("PYTHONPATH",radia_dir).output().map(|o|o.status.success()).unwrap_or(false)
}

fn ensure_venv_and_requirements(app: &AppHandle, task: &str, spec: &ModuleSpec) -> Result<(), String> {
    preflight_system(spec)?;
    let python=python_for_spec(spec).ok_or_else(||format!("{} requires Python {}. Physical Lab could not find a compatible interpreter.",spec.name,spec.python_requires.clone().unwrap_or_else(||"3.x".into())))?;
    let root=module_root(app,&spec.id)?; let venv=root.join(".venv"); let vpy=venv.join("bin/python");
    if vpy.exists() && !python_meets(vpy.to_string_lossy().as_ref(),&spec.python_requires){fs::remove_dir_all(&venv).map_err(|e|e.to_string())?;}
    if !vpy.exists(){
        emit_task(app,task,&spec.id,&spec.name,"Preparing isolated Python","Running",Some(58.0),format!("Creating .venv with {}",python),false,None);
        let mut cmd=Command::new(&python);cmd.arg("-m").arg("venv").arg(&venv).current_dir(&root);run_streaming(app,task,spec,"Preparing isolated Python",Some(60.0),cmd)?;
    }
    emit_task(app,task,&spec.id,&spec.name,"Preparing dependencies","Running",Some(66.0),"Updating pip tooling",false,None);
    let mut up=Command::new(&vpy);up.args(["-m","pip","install","--upgrade","pip","setuptools","wheel"]).current_dir(&root);run_streaming(app,task,spec,"Preparing dependencies",Some(70.0),up)?;
    if let Some(req)=prepared_requirements(app,spec)?{
        let mut pip=Command::new(&vpy);pip.args(["-m","pip","install","-r"]).arg(req).current_dir(source_dir(app,&spec.id)?);run_streaming(app,task,spec,"Installing model dependencies",Some(84.0),pip)?;
    }
    verify_imports(app,task,spec,&vpy)?; Ok(())
}

fn run_runtime_builder(app: &AppHandle, task: &str, spec: &ModuleSpec, python_override: Option<&str>) -> Result<(), String> {
    preflight_system(spec)?;
    let launcher = spec.launcher.clone().ok_or_else(|| "Runtime module has no launcher".to_string())?;
    let source = source_dir(app, &spec.id)?;
    let launcher_path = source.join(&launcher);
    if !launcher_path.is_file() { return Err(format!("Missing runtime launcher: {launcher}")); }
    emit_task(app, task, &spec.id, &spec.name, "Running integrated builder", "Running", Some(55.0), format!("Running {launcher} inside Physical Lab"), false, None);
    let mut cmd = Command::new("/bin/zsh");
    cmd.arg(&launcher_path).current_dir(&source).env("CI","1").env("PHYSICAL_LAB","1");
    let common_path = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin";
    let inherited = std::env::var("PATH").unwrap_or_default();
    cmd.env("PATH", if inherited.is_empty() { common_path.to_string() } else { format!("{common_path}:{inherited}") });
    let py_path = python_override.map(str::to_owned).or_else(||python_for_spec(spec)).or_else(||python_info().2);
    if let Some(py) = py_path { cmd.env("PYTHON_BIN", py); }
    run_streaming(app, task, spec, "Running integrated builder", Some(72.0), cmd)
}

async fn ensure_radia_for_lab(app:&AppHandle,task:&str,parent:&ModuleSpec)->Result<(),String>{
    let vpy=venv_python(app,&parent.id)?; if radia_import_ok(&vpy){return Ok(())}
    emit_task(app,task,&parent.id,&parent.name,"Resolving runtime dependency","Running",Some(3.0),"RADIA is missing or ABI-incompatible with this Lab Python. Physical Lab will rebuild the verified Universal2 runtime.",false,None);
    let runtime=module_spec("radia-runtime")?;download_source(app,task,&runtime,5.0,28.0).await?;
    let base=venv_base_python(&vpy).ok_or_else(||"Could not resolve the base Python used by this Lab venv.".to_string())?;
    let app2=app.clone();let task2=task.to_string();let runtime2=runtime.clone();let base2=base.clone();
    tokio::task::spawn_blocking(move||run_runtime_builder(&app2,&task2,&runtime2,Some(&base2))).await.map_err(|e|e.to_string())??;
    if !radia_import_ok(&vpy){return Err(format!("RADIA was built, but import still fails inside {}. This indicates a Python ABI or native-library mismatch.",parent.name))} Ok(())
}

async fn install_inner(app:&AppHandle,task:&str,spec:&ModuleSpec)->Result<(),String>{
    preflight_system(spec)?;
    if spec.kind=="runtime"{download_source(app,task,spec,4.0,42.0).await?;let app2=app.clone();let task2=task.to_string();let spec2=spec.clone();tokio::task::spawn_blocking(move||run_runtime_builder(&app2,&task2,&spec2,None)).await.map_err(|e|e.to_string())??;return Ok(())}
    if spec.bundled{prepare_bundled_lab_source(app,task,spec)?;}else{download_source(app,task,spec,5.0,50.0).await?;}
    let app2=app.clone();let task2=task.to_string();let spec2=spec.clone();tokio::task::spawn_blocking(move||ensure_venv_and_requirements(&app2,&task2,&spec2)).await.map_err(|e|e.to_string())??;
    if spec.fragile_dependencies.iter().any(|r|r=="radia") {
        if let Err(e)=ensure_radia_for_lab(app,task,spec).await {
            emit_task(app,task,&spec.id,&spec.name,"Fragile engine unavailable","Warning",Some(98.0),format!("RADIA full mode could not be prepared: {e}. Safe mode remains available."),false,None);
        }
    }
    Ok(())
}

#[tauri::command]
fn list_modules() -> Result<Vec<ModuleSpec>, String> { module_specs() }
#[tauri::command]
fn list_dependencies() -> Result<Vec<DependencySpec>, String> { dependency_specs() }

fn conda_python_candidates() -> Vec<PathBuf> {
    let home = home_dir();
    let conda_bins = [
        home.join("miniforge3/condabin/conda"), home.join("miniforge3/bin/conda"),
        home.join("miniconda3/condabin/conda"), home.join("miniconda3/bin/conda"),
        home.join("anaconda3/condabin/conda"), home.join("anaconda3/bin/conda"),
        PathBuf::from("/opt/homebrew/bin/conda"), PathBuf::from("/usr/local/bin/conda"),
    ];
    let mut out = Vec::new();
    for conda in conda_bins {
        if !conda.is_file() { continue; }
        let Ok(result) = Command::new(&conda).args(["env","list","--json"]).output() else { continue; };
        if !result.status.success() { continue; }
        let Ok(value) = serde_json::from_slice::<serde_json::Value>(&result.stdout) else { continue; };
        if let Some(envs)=value.get("envs").and_then(|v|v.as_array()) {
            for env in envs.iter().filter_map(|v|v.as_str()) {
                let py=PathBuf::from(env).join("bin/python"); if py.is_file(){out.push(py);}
            }
        }
        break;
    }
    out
}

fn discovered_python_envs(app:&AppHandle)->Vec<PathBuf>{
    let mut out=Vec::new(); let mut seen=HashSet::new();
    for c in python_candidates(){
        let p=if c.contains('/') {PathBuf::from(c)} else {output("which", &[c.as_str()]).map(PathBuf::from).unwrap_or_default()};
        if p.is_file() && seen.insert(p.to_string_lossy().to_string()){out.push(p);}
    }
    for p in conda_python_candidates().into_iter().chain(pychrono_candidates()){
        if p.is_file() && seen.insert(p.to_string_lossy().to_string()){out.push(p);}
    }
    if let Ok(specs)=module_specs(){for spec in specs.into_iter().filter(|m|m.kind=="lab"){
        if let Ok(p)=venv_python(app,&spec.id){if p.is_file() && seen.insert(p.to_string_lossy().to_string()){out.push(p);}}
    }}
    out
}

fn python_package_probe(program:&Path,module:&str)->Option<(String,String)>{
    if !program.is_file(){return None}
    let code=format!(r#"import importlib
m=importlib.import_module({module:?})
print(getattr(m,'__version__','unknown'))
print(getattr(m,'__file__','built-in'))"#);
    let out=Command::new(program).args(["-c",&code]).output().ok()?;
    if !out.status.success(){return None}
    let text=String::from_utf8_lossy(&out.stdout); let mut lines=text.lines();
    Some((lines.next().unwrap_or("unknown").trim().to_string(),lines.next().unwrap_or("").trim().to_string()))
}

fn python_package_inventory(app:&AppHandle)->HashMap<String,Vec<(String,String,String)>>{
    let modules=["numpy","scipy","pandas","plotly","streamlit","matplotlib","h5py","mpmath"];
    let module_list=modules.iter().map(|m|format!("{m:?}")).collect::<Vec<_>>().join(",");
    let code=format!(r#"import importlib
mods=[{module_list}]
for name in mods:
    try:
        m=importlib.import_module(name)
        print(name+'\t'+str(getattr(m,'__version__','unknown'))+'\t'+str(getattr(m,'__file__','built-in')))
    except Exception:
        pass"#);
    let mut inv:HashMap<String,Vec<(String,String,String)>>=HashMap::new();
    for py in discovered_python_envs(app){
        let Ok(out)=Command::new(&py).args(["-c",&code]).output() else{continue};
        if !out.status.success(){continue}
        for line in String::from_utf8_lossy(&out.stdout).lines(){
            let mut parts=line.splitn(3,'\t');let Some(name)=parts.next() else{continue};let Some(ver)=parts.next() else{continue};let Some(path)=parts.next() else{continue};
            inv.entry(name.to_string()).or_default().push((py.to_string_lossy().to_string(),ver.to_string(),path.to_string()));
        }
    }
    inv
}

fn package_required_by_installed_lab(app:&AppHandle,module:&str)->Vec<String>{
    let mut missing=Vec::new();
    if let Ok(specs)=module_specs(){for spec in specs.into_iter().filter(|m|m.kind=="lab" && m.verify_imports.iter().any(|x|x==module)){
        let installed=source_dir(app,&spec.id).map(|p|p.is_dir()).unwrap_or(false);
        if !installed{continue}
        let ok=venv_python(app,&spec.id).ok().and_then(|p|python_package_probe(&p,module)).is_some();
        if !ok{missing.push(spec.name);}
    }}
    missing
}

fn fftw_library()->Option<PathBuf>{
    let home=home_dir();
    let mut candidates=Vec::new();
    if let Ok(dest)=std::env::var("RADIA_DEST"){if !dest.trim().is_empty(){candidates.push(PathBuf::from(dest).join("ext_lib/libfftw.a"));}}
    candidates.extend([home.join("Desktop/Radia-master/ext_lib/libfftw.a"),home.join("Radia-master/ext_lib/libfftw.a"),home.join(".local/radia/ext_lib/libfftw.a")]);
    candidates.into_iter().find(|p|p.is_file())
}

fn dependency_status(app:&AppHandle,dep:&DependencySpec,inventory:&HashMap<String,Vec<(String,String,String)>>)->DependencyStatus{
    let green=|label:String,detail:String,locations:Vec<String>,version:Option<String>|DependencyStatus{id:dep.id.clone(),level:"green".into(),label,detail,locations,version};
    let yellow=|label:String,detail:String,locations:Vec<String>,version:Option<String>|DependencyStatus{id:dep.id.clone(),level:"yellow".into(),label,detail,locations,version};
    let red=|label:String,detail:String,locations:Vec<String>,version:Option<String>|DependencyStatus{id:dep.id.clone(),level:"red".into(),label,detail,locations,version};
    match dep.id.as_str(){
        "python-runtime"=>{let (ok,ver,path)=python_info();if ok{green("Ready".into(),format!("{ver}; compatible interpreter discovered."),path.into_iter().collect(),Some(ver))}else{red("Missing".into(),ver,vec![],None)}},
        "conda-runtime"=>{if let Some(p)=conda_binary(){let v=output(p.to_string_lossy().as_ref(),&["--version"]);green("Found".into(),"Conda/Miniforge is available for specialized environments such as PyChrono; ordinary Lab venvs remain independent.".into(),vec![p.to_string_lossy().to_string()],v)}else{yellow("Optional / not found".into(),"Conda is not required by the current ordinary Lab venvs. Install it only for Conda-distributed runtimes such as PyChrono.".into(),vec![],None)}},
        "node-build"=>{let node=build_tool_binary("node");let npm=build_tool_binary("npm");if let (Some(n),Some(m))=(node,npm){let v=output(n.to_string_lossy().as_ref(),&["--version"]);green("Build ready".into(),"Node.js and npm are available for rebuilding the Physical Lab desktop shell from source.".into(),vec![n.to_string_lossy().to_string(),m.to_string_lossy().to_string()],v)}else{yellow("Build-time only / missing".into(),"Node.js + npm are needed only when rebuilding Physical Lab from source; a packaged app does not need them.".into(),vec![],None)}},
        "rust-build"=>{let cargo=build_tool_binary("cargo");let rustc=build_tool_binary("rustc");let rustup=build_tool_binary("rustup");if let (Some(c),Some(r),Some(u))=(cargo,rustc,rustup){let targets=output(u.to_string_lossy().as_ref(),&["target","list","--installed"]).unwrap_or_default();let a=targets.contains("aarch64-apple-darwin");let x=targets.contains("x86_64-apple-darwin");let detail=if a&&x{"Rust toolchain plus both Universal2 Apple targets are installed.".into()}else{format!("Rust toolchain is installed. Missing Apple target(s): {}{}; the build script can add them automatically.",if !a{"aarch64-apple-darwin "}else{""},if !x{"x86_64-apple-darwin"}else{""})};let v=output(r.to_string_lossy().as_ref(),&["--version"]);if a&&x{green("Universal2 build ready".into(),detail,vec![c.to_string_lossy().to_string(),r.to_string_lossy().to_string(),u.to_string_lossy().to_string()],v)}else{yellow("Rust ready / targets repairable".into(),detail,vec![c.to_string_lossy().to_string(),r.to_string_lossy().to_string(),u.to_string_lossy().to_string()],v)}}else{yellow("Build-time only / missing".into(),"cargo, rustc and rustup are required only to rebuild Physical Lab from source. The build script can bootstrap rustup.".into(),vec![],None)}},
        "numpy"|"scipy"|"pandas"|"plotly"|"streamlit"|"matplotlib"|"h5py"|"mpmath"=>{
            let missing=package_required_by_installed_lab(app,&dep.id);
            let entries=inventory.get(&dep.id).cloned().unwrap_or_default();
            let version=entries.first().map(|x|x.1.clone());
            let found:Vec<String>=entries.into_iter().map(|(py,v,path)|format!("{} → {} ({})",py,path,v)).collect();
            if !missing.is_empty(){red("Missing in installed Lab".into(),format!("Missing from: {}. Repair those Labs to reinstall it.",missing.join(", ")),found,version)}
            else if !found.is_empty(){green("Found".into(),format!("Detected in {} Python environment(s). Physical Lab still isolates versions per Lab.",found.len()),found,version)}
            else{yellow("Not currently installed".into(),"No discovered environment currently imports this package. It will be installed automatically when a Lab that needs it is installed.".into(),vec![],None)}
        },
        "xcode-clt"=>{let required=["clang","clang++","make","lipo","otool","install_name_tool","xcrun"];let missing:Vec<_>=required.iter().filter(|t|!tool_available(t)).map(|s|s.to_string()).collect();if let Some(path)=xcode_clt_path(){if missing.is_empty(){green("Ready".into(),"Apple native build toolchain is configured.".into(),vec![path],None)}else{red("Incomplete".into(),format!("xcode-select is configured, but these tools are missing: {}",missing.join(", ")),vec![path],None)}}else{red("Missing".into(),"Xcode Command Line Tools are not configured.".into(),vec![],None)}},
        "native-toolchain"=>{let tools=["git","curl","make","clang","clang++","ar","ranlib","lipo","shasum","tar","xcrun","file","ditto","zip","otool","install_name_tool"];let mut locations=Vec::new();let mut missing=Vec::new();for tool in tools{if let Some(path)=output("which",&[tool]).filter(|x|!x.is_empty()){locations.push(format!("{tool} → {path}"))}else{missing.push(tool.to_string())}}if missing.is_empty(){green("Ready".into(),"All native builder command-line tools were found.".into(),locations,None)}else{red("Incomplete".into(),format!("Missing native builder tools: {}",missing.join(", ")),locations,None)}},
        "cmake"=>{if let Some(p)=cmake_binary(){let v=output(p.to_string_lossy().as_ref(),&["--version"]).and_then(|x|x.lines().next().map(str::to_string));green("Ready".into(),"CMake was found in PATH, Homebrew, or a Conda environment.".into(),vec![p.to_string_lossy().to_string()],v)}else{yellow("Optional / missing".into(),"Only required when building Chrono::Modal from source.".into(),vec![],None)}},
        "fftw"=>{if let Some(p)=fftw_library(){green("Ready".into(),"Verified RADIA workflow FFTW archive was found.".into(),vec![p.to_string_lossy().to_string()],None)}else{yellow("Not found".into(),"FFTW is managed by the RADIA Universal2 builder and is only needed for RADIA Full mode.".into(),vec![],None)}},
        "radia"=>{if let Some(ext)=radia_extension(){let mut locations=vec![ext.to_string_lossy().to_string()];if let Some(py)=radia_compatible_python(){locations.push(format!("Compatible Python → {}",py.to_string_lossy()));green("Verified".into(),"RADIA extension and matching CPython import smoke test passed.".into(),locations,radia_abi_minor().map(|m|format!("CPython 3.{m}")))}else{yellow("ABI check needed".into(),"RADIA extension exists, but no discovered matching CPython interpreter passed the import smoke test. Safe mode remains available.".into(),locations,radia_abi_minor().map(|m|format!("CPython 3.{m}")))}}else{yellow("Safe mode only".into(),"RADIA was not found. Accelerator Labs remain available in Safe analytical mode.".into(),vec![],None)}},
        "pychrono"=>{if let Some((p,d))=pychrono_runtime(){green("Ready".into(),d,vec![p.to_string_lossy().to_string()],None)}else{yellow("Not found".into(),"No working PyChrono environment was discovered. Conda environments are scanned automatically.".into(),vec![],None)}},
        "chrono-modal"=>{if let Some(p)=chrono_output(app){green("Ready".into(),"Existing Chrono::Modal packaged SDK was found.".into(),vec![p.to_string_lossy().to_string()],None)}else{yellow("Not built".into(),"No packaged Chrono::Modal SDK was found; the integrated builder can create one when needed.".into(),vec![],None)}},
        "vampire"=>{if let Some(p)=vampire_binary(){green("Ready".into(),"Existing VAMPIRE executable was found.".into(),vec![p.to_string_lossy().to_string()],None)}else if machine_arch()!="arm64"{red("Unsupported".into(),format!("Current VAMPIRE builder targets Apple Silicon; this Mac reports {}.",machine_arch()),vec![],None)}else{yellow("Not installed".into(),"No VAMPIRE executable was found in the managed/common install locations.".into(),vec![],None)}},
        _=>yellow("Unknown".into(),dep.notes.clone(),vec![],None)
    }
}

#[tauri::command]
fn dependency_statuses(app:AppHandle)->Result<Vec<DependencyStatus>,String>{let inv=python_package_inventory(&app);Ok(dependency_specs()?.iter().map(|d|dependency_status(&app,d,&inv)).collect())}

fn build_tool_binary(name:&str)->Option<PathBuf>{
    let home=home_dir();
    let mut candidates=Vec::new();
    match name {
        "node"=>candidates.extend([PathBuf::from("/opt/homebrew/bin/node"),PathBuf::from("/usr/local/bin/node")]),
        "npm"=>candidates.extend([PathBuf::from("/opt/homebrew/bin/npm"),PathBuf::from("/usr/local/bin/npm")]),
        "cargo"=>candidates.extend([home.join(".cargo/bin/cargo"),PathBuf::from("/opt/homebrew/bin/cargo"),PathBuf::from("/usr/local/bin/cargo")]),
        "rustc"=>candidates.extend([home.join(".cargo/bin/rustc"),PathBuf::from("/opt/homebrew/bin/rustc"),PathBuf::from("/usr/local/bin/rustc")]),
        "rustup"=>candidates.extend([home.join(".cargo/bin/rustup"),PathBuf::from("/opt/homebrew/bin/rustup"),PathBuf::from("/usr/local/bin/rustup")]),
        _=>{}
    }
    for p in candidates{if p.is_file(){return Some(p)}}
    output("which",&[name]).filter(|s|!s.is_empty()).map(PathBuf::from)
}

fn conda_binary()->Option<PathBuf>{
    let home=home_dir();
    let candidates=[home.join("miniforge3/condabin/conda"),home.join("miniforge3/bin/conda"),home.join("miniconda3/condabin/conda"),home.join("miniconda3/bin/conda"),home.join("anaconda3/condabin/conda"),home.join("anaconda3/bin/conda"),PathBuf::from("/opt/homebrew/Caskroom/miniforge/base/bin/conda")];
    for p in candidates{if p.is_file(){return Some(p)}}
    output("which",&["conda"]).filter(|s|!s.is_empty()).map(PathBuf::from)
}

fn cmake_binary() -> Option<PathBuf> {
    let home=home_dir();
    let candidates=[
        PathBuf::from("/opt/homebrew/bin/cmake"),
        PathBuf::from("/usr/local/bin/cmake"),
        home.join("miniforge3/envs/chrono/bin/cmake"),
        home.join("miniforge3/bin/cmake"),
        home.join("miniconda3/envs/chrono/bin/cmake"),
        home.join("anaconda3/envs/chrono/bin/cmake"),
    ];
    for p in candidates { if p.is_file() { return Some(p); } }
    output("which", &["cmake"]).filter(|s|!s.is_empty()).map(PathBuf::from)
}

fn xcode_clt_path() -> Option<String> { output("/usr/bin/xcode-select", &["-p"]).filter(|s|!s.is_empty()) }

#[tauri::command]
fn dependency_action(dependency_id: String) -> Result<String,String> {
    if dependency_id == "xcode-clt" {
        if xcode_clt_path().is_some() { return Ok("Xcode Command Line Tools are already installed.".into()); }
        Command::new("/usr/bin/xcode-select").arg("--install").spawn().map_err(|e|format!("Could not open the macOS Command Line Tools installer: {e}"))?;
        return Ok("Opened the macOS Command Line Tools installer.".into());
    }
    let dep=dependency_specs()?.into_iter().find(|d|d.id==dependency_id).ok_or_else(||"Unknown dependency".to_string())?;
    Command::new("/usr/bin/open").arg(&dep.source_url).spawn().map_err(|e|format!("Could not open {}: {e}",dep.source_name))?;
    Ok(format!("Opened {}",dep.source_name))
}


#[tauri::command]
fn data_directory(app:AppHandle)->Result<String,String>{Ok(data_root(&app)?.to_string_lossy().to_string())}

#[tauri::command]
fn open_data_directory(app:AppHandle)->Result<String,String>{
    let dir=data_root(&app)?;
    Command::new("/usr/bin/open").arg(&dir).spawn().map_err(|e|format!("Could not open Physical Lab data directory: {e}"))?;
    Ok(dir.to_string_lossy().to_string())
}

#[tauri::command]
fn log_directory(app:AppHandle)->Result<String,String>{Ok(logs_dir(&app)?.to_string_lossy().to_string())}

#[tauri::command]
fn open_log_directory(app:AppHandle)->Result<String,String>{
    let dir=logs_dir(&app)?;
    Command::new("/usr/bin/open").arg(&dir).spawn().map_err(|e|format!("Could not open log directory: {e}"))?;
    Ok(dir.to_string_lossy().to_string())
}

#[tauri::command]
fn runtime_status(app: AppHandle) -> RuntimeStatus {
    let (python_ready, python_version, python_path) = python_info();
    let radia_file = radia_extension();
    let radia_python = radia_compatible_python();
    let radia_ok = radia_python.is_some();
    let pychrono = pychrono_runtime();
    let chrono = chrono_output(&app);
    let vampire = vampire_binary();
    let cmake = cmake_binary();
    let xcode = xcode_clt_path();
    let (pychrono_ready, pychrono_python, pychrono_detail) = match pychrono {
        Some((p, detail)) => (true, Some(p.to_string_lossy().into()), detail.replace('\n', " · ")),
        None => (false, None, "No working PyChrono environment found in PHYSICAL_LAB_PYCHRONO_PYTHON or common Conda chrono environments".into()),
    };
    RuntimeStatus {
        os: std::env::consts::OS.into(),
        arch: machine_arch(),
        python_ready, python_version, python_path,
        radia_ready: radia_ok,
        radia_detail: if radia_ok {
            match (radia_file,radia_python){(Some(ext),Some(py))=>format!("{} · compatible Python {}",ext.to_string_lossy(),py.to_string_lossy()),(Some(ext),None)=>ext.to_string_lossy().into(),_=>"RADIA import verified".into()}
        } else if radia_file.is_some() {
            "RADIA file exists but import/ABI verification failed for the preferred Python runtime".into()
        } else {
            "No compatible RADIA runtime found in RADIA_PYTHONPATH, RADIA_DEST, or common install locations".into()
        },
        pychrono_ready, pychrono_detail, pychrono_python,
        chrono_ready: chrono.is_some(),
        chrono_detail: chrono.map(|p|p.to_string_lossy().into()).unwrap_or_else(||"No Chrono::Modal C++ SDK ZIP found. PyChrono availability is tracked separately.".into()),
        vampire_ready: machine_arch()=="arm64" && vampire.is_some(),
        vampire_detail: if machine_arch()!="arm64" {
            "VAMPIRE builder is currently Apple-Silicon-only".into()
        } else {
            vampire.map(|p|p.to_string_lossy().into()).unwrap_or_else(||"~/.local/vampire-apple-silicon not installed".into())
        },
        cmake_ready: cmake.is_some(),
        cmake_detail: cmake.map(|p|p.to_string_lossy().into()).unwrap_or_else(||"CMake not found in PATH, Homebrew, or common Conda locations".into()),
        xcode_clt_ready: xcode.is_some(),
        xcode_clt_detail: xcode.unwrap_or_else(||"Xcode Command Line Tools not detected".into()),
    }
}

fn fragile_dependency_ready(app:&AppHandle, _spec:&ModuleSpec, vpy:Option<&Path>, dep:&str)->bool {
    match dep {
        "radia" => vpy.map(radia_import_ok).unwrap_or(false),
        "pychrono" => pychrono_runtime().is_some(),
        "chrono-modal" => chrono_output(app).is_some(),
        "vampire" => machine_arch()=="arm64" && vampire_binary().is_some(),
        _ => true,
    }
}

fn mode_readiness(app:&AppHandle, spec:&ModuleSpec, installed:bool)->(bool,bool) {
    if spec.kind!="lab" { return (false,false); }
    let supported=arch_supported(spec);
    let vpy=venv_python(app,&spec.id).ok();
    let source=source_dir(app,&spec.id).ok();
    let base_ready = supported && installed
        && vpy.as_ref().map(|p|p.is_file()&&python_meets(p.to_string_lossy().as_ref(),&spec.python_requires)).unwrap_or(false)
        && spec.entrypoint.as_ref().map(|e|source.as_ref().map(|p|p.join(e).is_file()).unwrap_or(false)).unwrap_or(false);
    if !base_ready { return (false,false); }
    let full_ready=spec.fragile_dependencies.iter().all(|d|fragile_dependency_ready(app,spec,vpy.as_deref(),d));
    (true,full_ready)
}

fn module_status(app: &AppHandle, state: &PhysicalLabState, spec: &ModuleSpec) -> ModuleStatus {
    let source = source_dir(app, &spec.id).ok();
    let installed = source.as_ref().map(|p| p.is_dir() && p.join("README.md").exists()).unwrap_or(false);
    let busy = state.busy.lock().map(|b| b.contains(&spec.id)).unwrap_or(false);
    let supported=arch_supported(spec);
    let (safe_ready,full_ready)=mode_readiness(app,spec,installed);
    let ready = if spec.kind == "lab" {
        safe_ready
    } else {
        supported && match spec.id.as_str() {
            "radia-runtime" => python_info().2.as_ref().map(|p|radia_import_ok(Path::new(p))).unwrap_or(false),
            "chrono-modal-runtime" => chrono_output(app).is_some(),
            "vampire-runtime" => vampire_binary().is_some(),
            _ => installed,
        }
    };
    let label = if !supported { "Unsupported on this Mac" } else if busy { "Working" } else if spec.kind=="lab" && safe_ready && !full_ready { "Safe mode ready" } else if ready { "Ready" } else if installed { if spec.kind=="runtime" {"Builder downloaded"} else {"Needs repair"} } else { "Not installed" };
    ModuleStatus { id: spec.id.clone(), installed, ready, safe_ready, full_ready, busy, state: label.into(), path: source.map(|p|p.to_string_lossy().into()) }
}

#[tauri::command]
fn module_statuses(app: AppHandle, state: State<'_, PhysicalLabState>) -> Result<Vec<ModuleStatus>, String> {
    let specs=module_specs()?; Ok(specs.iter().map(|s|module_status(&app,&state,s)).collect())
}

#[tauri::command]
async fn install_module(app: AppHandle, state: State<'_, PhysicalLabState>, module_id: String) -> Result<(), String> {
    let spec=module_spec(&module_id)?;
    {
        let mut busy=state.busy.lock().map_err(|_|"Busy-state lock failed".to_string())?;
        if !busy.insert(spec.id.clone()) { return Err(format!("{} is already being prepared", spec.name)); }
    }
    let task=task_id(&spec.id);
    emit_task(&app,&task,&spec.id,&spec.name,"Starting","Running",Some(1.0),"Physical Lab is preparing this module.",false,None);
    let result=install_inner(&app,&task,&spec).await;
    if let Ok(mut busy)=state.busy.lock(){busy.remove(&spec.id);}
    if let Ok(mut cancelled)=state.cancelled.lock(){cancelled.remove(&task);}
    match result {
        Ok(())=>{emit_task(&app,&task,&spec.id,&spec.name,"Complete","Complete",Some(100.0),"Module is ready.",true,None);Ok(())},
        Err(e) if e.to_ascii_lowercase().contains("cancelled")=>{emit_task(&app,&task,&spec.id,&spec.name,"Cancelled","Cancelled",None,"Task cancelled. Completed artifacts may remain and can be repaired or retried.",true,None);Err(e)},
        Err(e)=>{emit_task(&app,&task,&spec.id,&spec.name,"Failed","Failed",None,e.clone(),true,Some(e.clone()));Err(e)}
    }
}

#[tauri::command]
fn uninstall_module(app:AppHandle,state:State<'_,PhysicalLabState>,module_id:String)->Result<String,String>{
    let spec=module_spec(&module_id)?;
    {let busy=state.busy.lock().map_err(|_|"Busy-state lock failed".to_string())?;if busy.contains(&module_id){return Err(format!("{} is currently busy. Wait for the active task to finish before deleting it.",spec.name));}}
    {let mut servers=state.servers.lock().map_err(|_|"Server-state lock failed".to_string())?;if let Some(mut server)=servers.remove(&module_id){let _=server.child.kill();let _=server.child.wait();}}
    let root=module_root(&app,&module_id)?;
    if root.exists(){fs::remove_dir_all(&root).map_err(|e|format!("Could not delete {}: {e}",root.to_string_lossy()))?;}
    append_log(&app,&format!("UNINSTALL {} | removed managed module directory {}",spec.name,root.to_string_lossy()));
    if spec.kind=="runtime"{Ok(format!("Removed the downloaded {} builder from Physical Lab. Any external runtime/SDK it previously installed was left untouched.",spec.name))}else{Ok(format!("Removed {} source and isolated environment from Physical Lab.",spec.name))}
}

fn find_free_port() -> Result<u16,String> {
    let listener=TcpListener::bind(("127.0.0.1",0)).map_err(|e|e.to_string())?;
    Ok(listener.local_addr().map_err(|e|e.to_string())?.port())
}


fn ui_overlay_dir(app:&AppHandle)->Option<PathBuf>{
    if let Ok(resource_dir)=app.path().resource_dir(){
        let p=resource_dir.join("ui");
        if p.join("sitecustomize.py").is_file(){return Some(p)}
    }
    let dev=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/ui");
    if dev.join("sitecustomize.py").is_file(){return Some(dev)}
    None
}

fn ensure_advanced_experiment_hook(app:&AppHandle,spec:&ModuleSpec,source:&Path)->Result<(),String>{
    if !matches!(spec.id.as_str(),"numerical-methods"|"ising-monte-carlo"|"random-walk-monte-carlo"|"nonlinear-chaos"|"oscillation-integration"|"radia-magnet-studio"|"radiation-platform"){return Ok(())}
    let Some(entry)=spec.entrypoint.as_ref() else{return Ok(())};
    let path=source.join(entry);
    if !path.is_file(){return Ok(())}
    let marker="# PHYSICAL_LAB_ADVANCED_EXPERIMENT_SUITE_V1";
    let current=fs::read_to_string(&path).map_err(|e|format!("Could not inspect {} for Physical Lab enhancement: {e}",path.to_string_lossy()))?;
    if current.contains(marker){return Ok(())}
    let hook=r#"

# PHYSICAL_LAB_ADVANCED_EXPERIMENT_SUITE_V1
# Added only to Physical Lab's managed checkout. The upstream experiment remains intact.
try:
    from physical_lab_advanced import render_advanced_experiments as _pl_render_advanced_experiments
    _pl_render_advanced_experiments(globals())
except Exception as _pl_advanced_error:
    try:
        import streamlit as _pl_st
        _pl_st.warning(f"Physical Lab advanced experiment suite could not load: {_pl_advanced_error}")
    except Exception:
        pass
"#;
    let mut file=OpenOptions::new().append(true).open(&path).map_err(|e|format!("Could not enhance {}: {e}",path.to_string_lossy()))?;
    use std::io::Write;
    file.write_all(hook.as_bytes()).map_err(|e|format!("Could not write Physical Lab advanced hook: {e}"))?;
    append_log(app,&format!("ADVANCED SUITE | injected research enhancement hook into {}",path.to_string_lossy()));
    Ok(())
}

fn safe_engine_script(app:&AppHandle)->Result<PathBuf,String>{
    if let Ok(resource_dir)=app.path().resource_dir(){
        let p=resource_dir.join("safe_engine_server.py");
        if p.is_file(){return Ok(p)}
    }
    let dev=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("resources/safe_engine_server.py");
    if dev.is_file(){return Ok(dev)}
    Err("Physical Lab safe-mode engine resource is missing.".into())
}

fn spawn_safe_engine(app:&AppHandle,spec:&ModuleSpec,port:u16)->Result<Child,String>{
    let python=python_for_spec(spec).or_else(||python_info().2).ok_or_else(||"Safe mode requires a compatible Python 3 interpreter.".to_string())?;
    let script=safe_engine_script(app)?;
    let log_path=module_log_path(app,&spec.id,"safe")?;
    let log=OpenOptions::new().create(true).append(true).open(&log_path).map_err(|e|e.to_string())?;
    let err=log.try_clone().map_err(|e|e.to_string())?;
    append_log(app,&format!("Starting {} Safe server on port {}. Server log: {}",spec.name,port,log_path.to_string_lossy()));
    Command::new(python)
        .arg(script).args(["--module",&spec.id,"--port",&port.to_string()])
        .env("PYTHONUNBUFFERED","1")
        .stdout(Stdio::from(log)).stderr(Stdio::from(err))
        .spawn().map_err(|e|format!("Could not start {} Safe mode: {e}",spec.name))
}

#[tauri::command]
fn launch_module(app: AppHandle, state: State<'_, PhysicalLabState>, module_id: String, mode: Option<String>) -> Result<LaunchInfo, String> {
    let spec=module_spec(&module_id)?;
    if spec.kind!="lab" {return Err("Only physics-lab modules can be opened in the embedded lab view.".into())}
    let requested=mode.unwrap_or_else(||"safe".into()).to_ascii_lowercase();
    if requested!="safe" && requested!="full" {return Err("Mode must be 'safe' or 'full'.".into())}
    let status=module_status(&app,&state,&spec);
    if requested=="safe" && !status.safe_ready {return Err(format!("{} Safe mode is not ready. Install or repair the Lab first.",spec.name))}
    if requested=="full" && !status.full_ready {
        let deps=if spec.fragile_dependencies.is_empty(){"its Full runtime".into()}else{spec.fragile_dependencies.join(", ")};
        return Err(format!("{} Full mode is not ready because {} is unavailable. Safe mode can still be used.",spec.name,deps));
    }

    {
        let mut servers=state.servers.lock().map_err(|_|"Server-state lock failed".to_string())?;
        if let Some(existing)=servers.get_mut(&module_id) {
            if existing.child.try_wait().map_err(|e|e.to_string())?.is_none() && existing.mode==requested {
                return Ok(LaunchInfo{module_id:module_id.clone(),url:format!("http://127.0.0.1:{}",existing.port),port:existing.port,mode:requested});
            }
            if let Some(mut old)=servers.remove(&module_id){let _=old.child.kill();let _=old.child.wait();}
        }
    }

    let port=find_free_port()?;
    let mut child = if requested=="safe" && spec.safe_backend!="standard" {
        spawn_safe_engine(&app,&spec,port)?
    } else {
        let source=source_dir(&app,&module_id)?;
        ensure_advanced_experiment_hook(&app,&spec,&source)?;
        let entry=spec.entrypoint.clone().ok_or_else(||"Lab has no entrypoint".to_string())?;
        let vpy=venv_python(&app,&module_id)?;
        let radia_dir=radia_dir().unwrap_or_else(||home_dir().join("Desktop/Radia-master/cpp/gcc"));
        let mut pythonpath=String::new();
        if matches!(module_id.as_str(), "numerical-methods"|"ising-monte-carlo"|"random-walk-monte-carlo"|"nonlinear-chaos"|"oscillation-integration"|"radia-magnet-studio"|"radiation-platform"|"kerr-geodesics"|"solar-system-dynamics"|"honeycomb-lattice") {
            if let Some(ui_dir)=ui_overlay_dir(&app){pythonpath.push_str(&ui_dir.to_string_lossy());pythonpath.push(':');}
        }
        pythonpath.push_str(&source.to_string_lossy());
        if requested=="full" && radia_dir.is_dir(){pythonpath.push(':');pythonpath.push_str(&radia_dir.to_string_lossy());}
        if let Ok(existing)=std::env::var("PYTHONPATH"){if !existing.is_empty(){pythonpath.push(':');pythonpath.push_str(&existing);}}
        let data_dir=data_root(&app)?;
        let log_dir=logs_dir(&app)?;
        let mut cmd=Command::new(&vpy);
        cmd.current_dir(&source)
            .args(["-m","streamlit","run",&entry,"--server.address","127.0.0.1","--server.headless","true","--browser.gatherUsageStats","false","--server.port",&port.to_string()])
            .env("PYTHONUNBUFFERED","1")
            .env("PHYSICAL_LAB_ENGINE_MODE",&requested)
            .env("PHYSICAL_LAB_UI_PROFILE",&module_id)
            .env("PHYSICAL_LAB_UI_VERSION","3")
            .env("PHYSICAL_LAB_DATA_DIR",&data_dir)
            .env("PHYSICAL_LAB_LOG_DIR",&log_dir)
            .env("PHYSICAL_LAB_MODULE_ID",&module_id)
            .env("PHYSICAL_LAB_FRAGILE_DEPENDENCIES",spec.fragile_dependencies.join(","))
            .env("PATH", format!("{}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin", module_root(&app,&module_id)?.join(".venv/bin").to_string_lossy()))
            .env("PYTHONPATH",pythonpath);
        let log_path=module_log_path(&app,&module_id,&requested)?;
        let log=OpenOptions::new().create(true).append(true).open(&log_path).map_err(|e|e.to_string())?;
        let err=log.try_clone().map_err(|e|e.to_string())?;
        cmd.stdout(Stdio::from(log)).stderr(Stdio::from(err));
        append_log(&app,&format!("Starting {} {} server on port {}. Server log: {}",spec.name,requested,port,log_path.to_string_lossy()));
        if requested=="full" && radia_dir.is_dir(){cmd.env("RADIA_PYTHONPATH",radia_dir.to_string_lossy().to_string());}
        if let Some((pychrono_python,_))=pychrono_runtime(){cmd.env("PHYSICAL_LAB_PYCHRONO_PYTHON",pychrono_python);}
        cmd.spawn().map_err(|e|format!("Could not start {}: {e}",spec.name))?
    };
    let started=Instant::now();
    let mut ready=false;
    while started.elapsed()<Duration::from_secs(35){
        if TcpStream::connect(("127.0.0.1",port)).is_ok(){ready=true;break}
        if child.try_wait().map_err(|e|e.to_string())?.is_some(){break}
        thread::sleep(Duration::from_millis(250));
    }
    if !ready {let _=child.kill();let _=child.wait();return Err(format!("{} {} mode did not start its local server successfully.",spec.name,requested))}
    state.servers.lock().map_err(|_|"Server-state lock failed".to_string())?.insert(module_id.clone(),RunningServer{child,port,mode:requested.clone()});
    Ok(LaunchInfo{module_id,url:format!("http://127.0.0.1:{port}"),port,mode:requested})
}

#[tauri::command]
fn stop_module(state: State<'_, PhysicalLabState>, module_id: String) -> Result<(), String> {
    let mut servers=state.servers.lock().map_err(|_|"Server-state lock failed".to_string())?;
    if let Some(mut server)=servers.remove(&module_id){let _=server.child.kill();let _=server.child.wait();}
    Ok(())
}

pub fn run() {
    let app = tauri::Builder::default()
        .manage(PhysicalLabState::default())
        .invoke_handler(tauri::generate_handler![list_modules, list_dependencies, dependency_statuses, dependency_action, data_directory, open_data_directory, log_directory, open_log_directory, runtime_status, module_statuses, install_module, uninstall_module, launch_module, stop_module,
            research::create_workspace, research::list_workspaces, research::open_workspace, research::record_run_snapshot,
            research::import_measurement_dataset, research::list_datasets, research::list_serial_devices, research::capture_serial_measurement,
            research::analyze_dataset, research::validate_dataset_columns, research::lab_compatibility_matrix, research::repair_lab_environment,
            research::scientific_smoke_tests, research::pipeline_templates, research::save_pipeline, research::create_campaign,
            research::adapter_statuses, research::export_reproducibility_package, research::list_run_snapshots, research::compare_run_snapshots, research::list_campaigns, research::campaign_action,
            research::save_model_builder_bundle, model_builder::model_builder_choose_source, model_builder::model_builder_analyze, model_builder::model_builder_generate, model_builder::model_builder_run, model_builder::model_builder_validate, model_builder::model_builder_open_bundle, cancel_task])
        .build(tauri::generate_context!())
        .expect("error while building Physical Lab");

    app.run(|app_handle,event|{
        if let tauri::RunEvent::ExitRequested { .. } = event {
            let state=app_handle.state::<PhysicalLabState>();
            if let Ok(mut servers)=state.servers.lock(){
                for (_,mut server) in servers.drain(){let _=server.child.kill();let _=server.child.wait();}
            };
        }
    });
}
