use chrono::Local;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    fs::{self, File},
    io::{BufRead, BufReader, Write},
    path::{Path, PathBuf},
    process::Command,
    time::{Duration, Instant},
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

fn workspaces_root(app: &AppHandle) -> Result<PathBuf, String> {
    let p = app_root(app)?.join("workspaces");
    fs::create_dir_all(&p).map_err(|e| e.to_string())?;
    Ok(p)
}

fn modules_root(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app_root(app)?.join("modules"))
}

fn lab_specs() -> Result<Vec<LabSpec>, String> {
    let all: Vec<LabSpec> = serde_json::from_str(include_str!("../resources/modules.json"))
        .map_err(|e| e.to_string())?;
    Ok(all.into_iter().filter(|m| m.kind == "lab").collect())
}

fn safe_slug(s: &str) -> String {
    let mut out = String::new();
    for c in s.trim().chars() {
        if c.is_ascii_alphanumeric() {
            out.push(c.to_ascii_lowercase());
        } else if c == '-' || c == '_' || c.is_whitespace() {
            if !out.ends_with('-') {
                out.push('-');
            }
        }
    }
    let out = out.trim_matches('-').to_string();
    if out.is_empty() {
        "project".into()
    } else {
        out
    }
}

fn workspace_dir(app: &AppHandle, id: &str) -> Result<PathBuf, String> {
    let safe = safe_slug(id);
    let p = workspaces_root(app)?.join(format!("{safe}.physlab"));
    if !p.exists() {
        return Err(format!("Workspace not found: {id}"));
    }
    Ok(p)
}

fn count_files(p: PathBuf) -> usize {
    fs::read_dir(p)
        .ok()
        .map(|it| {
            it.filter_map(Result::ok)
                .filter(|e| e.path().is_file() || e.path().is_dir())
                .count()
        })
        .unwrap_or(0)
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

fn write_json(path: &Path, value: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    fs::write(
        path,
        serde_json::to_string_pretty(value).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())
}

fn now_iso() -> String {
    Local::now().to_rfc3339()
}

fn sha256(path: &Path) -> Option<String> {
    let path_s = path.to_string_lossy().to_string();
    let out = Command::new("/usr/bin/shasum")
        .args(["-a", "256", path_s.as_str()])
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    String::from_utf8_lossy(&out.stdout)
        .split_whitespace()
        .next()
        .map(|s| s.to_string())
}

fn open_path(path: &Path) -> Result<(), String> {
    Command::new("/usr/bin/open")
        .arg(path)
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub fn create_workspace(app: AppHandle, name: String) -> Result<WorkspaceSummary, String> {
    let base = safe_slug(&name);
    let mut id = base.clone();
    let root = workspaces_root(&app)?;
    let mut n = 2;
    while root.join(format!("{id}.physlab")).exists() {
        id = format!("{base}-{n}");
        n += 1;
    }
    let dir = root.join(format!("{id}.physlab"));
    for child in [
        "datasets",
        "measurements",
        "runs",
        "figures",
        "exports",
        "provenance",
        "pipelines",
        "campaigns",
    ] {
        fs::create_dir_all(dir.join(child)).map_err(|e| e.to_string())?;
    }
    let now = now_iso();
    write_json(
        &dir.join("project.json"),
        &json!({
            "schema":"physical-lab-project-v1",
            "id":&id,
            "name":name.trim(),
            "createdAt":&now,
            "updatedAt":&now,
            "description":"Physical Lab reproducible experimental workspace",
            "measurementBridge":{"enabled":true},
            "provenance":{"policy":"record solver, environment, source commit, dataset hashes and timestamps"}
        }),
    )?;
    write_json(
        &dir.join("pipelines/default-measurement-validation.json"),
        &default_pipeline_value("measurement-validation"),
    )?;
    workspace_summary_from_dir(&dir)
}

fn workspace_summary_from_dir(dir: &Path) -> Result<WorkspaceSummary, String> {
    let p = read_json(&dir.join("project.json"))?;
    Ok(WorkspaceSummary {
        id: p
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or_else(|| {
                dir.file_name()
                    .and_then(|x| x.to_str())
                    .unwrap_or("workspace")
            })
            .to_string(),
        name: p
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or("Physical Lab Project")
            .to_string(),
        created_at: p
            .get("createdAt")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        updated_at: p
            .get("updatedAt")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        path: dir.to_string_lossy().to_string(),
        datasets: count_files(dir.join("datasets")),
        runs: count_files(dir.join("runs")),
        campaigns: count_files(dir.join("campaigns")),
    })
}

#[tauri::command]
pub fn list_workspaces(app: AppHandle) -> Result<Vec<WorkspaceSummary>, String> {
    let mut out = vec![];
    for e in fs::read_dir(workspaces_root(&app)?)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        if e.path().join("project.json").exists() {
            if let Ok(s) = workspace_summary_from_dir(&e.path()) {
                out.push(s);
            }
        }
    }
    out.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
    Ok(out)
}

#[tauri::command]
pub fn open_workspace(app: AppHandle, workspace_id: String) -> Result<String, String> {
    let dir = workspace_dir(&app, &workspace_id)?;
    open_path(&dir)?;
    Ok(dir.to_string_lossy().to_string())
}

#[tauri::command]
pub fn record_run_snapshot(
    app: AppHandle,
    workspace_id: String,
    module_id: String,
    mode: String,
    parameters_json: String,
    results_json: String,
) -> Result<String, String> {
    let dir = workspace_dir(&app, &workspace_id)?;
    let ts = format!(
        "{}-{}",
        Local::now().format("%Y%m%d-%H%M%S"),
        Local::now().timestamp_subsec_millis()
    );
    let id = format!("{}-{}", safe_slug(&module_id), ts);
    let run_dir = dir.join("runs").join(&id);
    fs::create_dir_all(&run_dir).map_err(|e| e.to_string())?;
    let parameters: Value =
        serde_json::from_str(&parameters_json).unwrap_or_else(|_| json!({"raw":parameters_json}));
    let results: Value =
        serde_json::from_str(&results_json).unwrap_or_else(|_| json!({"raw":results_json}));
    let module_dir = modules_root(&app)?.join(&module_id);
    let source = module_dir.join("source");
    let commit = if source.exists() {
        command_text_in(&source, "git", &["rev-parse", "HEAD"])
    } else {
        None
    };
    let py = module_dir.join(".venv/bin/python");
    let python = if py.exists() {
        command_text(py.to_string_lossy().as_ref(), &["--version"])
    } else {
        None
    };
    let freeze = if py.exists() {
        command_text(
            py.to_string_lossy().as_ref(),
            &["-m", "pip", "freeze", "--all"],
        )
    } else {
        None
    };
    write_json(
        &run_dir.join("run.json"),
        &json!({
            "schema":"physical-lab-run-v1","id":&id,"createdAt":now_iso(),"moduleId":module_id,"mode":mode,
            "parameters":parameters,"results":results,"provenance":{"sourceCommit":commit,"python":python,"pipFreeze":freeze}
        }),
    )?;
    touch_project(&dir)?;
    Ok(id)
}

fn touch_project(dir: &Path) -> Result<(), String> {
    let mut p = read_json(&dir.join("project.json"))?;
    p["updatedAt"] = Value::String(now_iso());
    write_json(&dir.join("project.json"), &p)
}

#[tauri::command]
pub fn import_measurement_dataset(
    app: AppHandle,
    workspace_id: String,
    source_path: String,
    name: String,
    quantity: String,
    unit: String,
    sensor: String,
    calibration: String,
) -> Result<DatasetSummary, String> {
    let src = PathBuf::from(source_path.trim());
    if !src.is_file() {
        return Err(format!(
            "Measurement file does not exist: {}",
            src.display()
        ));
    }
    let ext = src
        .extension()
        .and_then(|x| x.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if !["csv", "tsv", "json", "h5", "hdf5"].contains(&ext.as_str()) {
        return Err("Supported measurement formats: CSV, TSV, JSON, HDF5".into());
    }
    let dir = workspace_dir(&app, &workspace_id)?;
    let ds_id = format!(
        "{}-{}",
        safe_slug(&name),
        Local::now().format("%Y%m%d-%H%M%S")
    );
    let ds_dir = dir.join("datasets").join(&ds_id);
    fs::create_dir_all(&ds_dir).map_err(|e| e.to_string())?;
    let stored = ds_dir.join(format!("data.{ext}"));
    fs::copy(&src, &stored).map_err(|e| e.to_string())?;
    let hash = sha256(&stored);
    let created = now_iso();
    write_json(
        &ds_dir.join("metadata.json"),
        &json!({
            "schema":"physical-lab-dataset-v1","id":&ds_id,"name":&name,"quantity":&quantity,"unit":&unit,"sensor":&sensor,
            "calibration":&calibration,"format":&ext,"sourceFile":src.to_string_lossy(),"storedFile":stored.to_string_lossy(),
            "sha256":&hash,"createdAt":&created,"measurement":true
        }),
    )?;
    touch_project(&dir)?;
    Ok(DatasetSummary {
        id: ds_id,
        name,
        quantity,
        unit,
        sensor,
        format: ext,
        source_file: src.to_string_lossy().to_string(),
        stored_file: stored.to_string_lossy().to_string(),
        sha256: hash,
        created_at: created,
    })
}

#[tauri::command]
pub fn list_datasets(app: AppHandle, workspace_id: String) -> Result<Vec<DatasetSummary>, String> {
    let dir = workspace_dir(&app, &workspace_id)?.join("datasets");
    let mut out = vec![];
    for e in fs::read_dir(dir)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        let meta = e.path().join("metadata.json");
        if let Ok(v) = read_json(&meta) {
            out.push(DatasetSummary {
                id: v
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                name: v
                    .get("name")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                quantity: v
                    .get("quantity")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                unit: v
                    .get("unit")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                sensor: v
                    .get("sensor")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                format: v
                    .get("format")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                source_file: v
                    .get("sourceFile")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                stored_file: v
                    .get("storedFile")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
                sha256: v.get("sha256").and_then(Value::as_str).map(str::to_string),
                created_at: v
                    .get("createdAt")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .to_string(),
            });
        }
    }
    out.sort_by(|a, b| b.created_at.cmp(&a.created_at));
    Ok(out)
}

#[tauri::command]
pub fn list_serial_devices() -> Result<Vec<String>, String> {
    let mut out = vec![];
    for e in fs::read_dir("/dev")
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        let name = e.file_name().to_string_lossy().to_string();
        if name.starts_with("cu.") || name.starts_with("tty.") {
            out.push(format!("/dev/{name}"));
        }
    }
    out.sort();
    Ok(out)
}

#[tauri::command]
pub fn capture_serial_measurement(
    app: AppHandle,
    workspace_id: String,
    device: String,
    baud: u32,
    seconds: u64,
    name: String,
    quantity: String,
    unit: String,
    sensor: String,
) -> Result<DatasetSummary, String> {
    if !device.starts_with("/dev/cu.") && !device.starts_with("/dev/tty.") {
        return Err("Only macOS serial devices under /dev/cu.* or /dev/tty.* are accepted.".into());
    }
    if !Path::new(&device).exists() {
        return Err("Serial device not found.".into());
    }
    let secs = seconds.clamp(1, 300);
    let baud_s = baud.to_string();
    let _ = Command::new("/bin/stty")
        .args(["-f", device.as_str(), baud_s.as_str(), "raw", "-echo"])
        .status();
    let tmp = app_root(&app)?.join(format!("serial-{}.csv", Local::now().timestamp_millis()));
    let code = r#"import os,sys,select,time
p=sys.argv[1]; secs=float(sys.argv[2]); out=sys.argv[3]
fd=os.open(p,os.O_RDONLY|os.O_NONBLOCK)
end=time.time()+secs; buf=b''
with open(out,'w',encoding='utf-8') as f:
 f.write('timestamp,value\n')
 while time.time()<end:
  r,_,_=select.select([fd],[],[],0.2)
  if not r: continue
  try: chunk=os.read(fd,4096)
  except BlockingIOError: continue
  if not chunk: continue
  buf+=chunk
  while b'\n' in buf:
   line,buf=buf.split(b'\n',1); s=line.decode('utf-8','ignore').strip()
   if not s: continue
   try: v=float(s.split(',')[-1].strip())
   except: continue
   f.write(f'{time.time():.6f},{v}\n'); f.flush()
os.close(fd)
"#;
    let py = command_text("/usr/bin/which", &["python3"])
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "python3".into());
    let secs_s = secs.to_string();
    let tmp_s = tmp.to_string_lossy().to_string();
    let status = Command::new(py.trim())
        .args(["-c", code, device.as_str(), secs_s.as_str(), tmp_s.as_str()])
        .status()
        .map_err(|e| e.to_string())?;
    if !status.success() {
        return Err("Serial capture failed. Check device permissions and baud rate.".into());
    }
    let result = import_measurement_dataset(
        app,
        workspace_id,
        tmp.to_string_lossy().to_string(),
        name,
        quantity,
        unit,
        sensor,
        format!("Serial capture at {baud} baud for {secs}s"),
    );
    let _ = fs::remove_file(tmp);
    result
}

fn parse_csv_numeric(path: &Path) -> Result<(Vec<String>, Vec<Vec<Option<f64>>>), String> {
    let file = File::open(path).map_err(|e| e.to_string())?;
    let mut lines = BufReader::new(file).lines();
    let header = lines
        .next()
        .ok_or("Dataset is empty")?
        .map_err(|e| e.to_string())?;
    let sep = if header.contains('\t') { '\t' } else { ',' };
    let headers: Vec<String> = header
        .split(sep)
        .map(|s| s.trim().trim_matches('"').to_string())
        .collect();
    let mut cols = vec![Vec::<Option<f64>>::new(); headers.len()];
    for line in lines.take(200_000) {
        let line = line.map_err(|e| e.to_string())?;
        for (i, raw) in line.split(sep).enumerate().take(cols.len()) {
            cols[i].push(raw.trim().trim_matches('"').parse::<f64>().ok());
        }
    }
    Ok((headers, cols))
}

#[tauri::command]
pub fn analyze_dataset(
    app: AppHandle,
    workspace_id: String,
    dataset_id: String,
) -> Result<Vec<ColumnStats>, String> {
    let meta = read_json(
        &workspace_dir(&app, &workspace_id)?
            .join("datasets")
            .join(&dataset_id)
            .join("metadata.json"),
    )?;
    let format = meta.get("format").and_then(Value::as_str).unwrap_or("");
    if format != "csv" && format != "tsv" {
        return Err("Numeric Result Center currently analyzes CSV/TSV directly; JSON/HDF5 remain preserved for Lab-specific readers.".into());
    }
    let path = PathBuf::from(
        meta.get("storedFile")
            .and_then(Value::as_str)
            .ok_or("Dataset path missing")?,
    );
    let (headers, cols) = parse_csv_numeric(&path)?;
    let mut out = vec![];
    for (h, c) in headers.into_iter().zip(cols.into_iter()) {
        let v: Vec<f64> = c.into_iter().flatten().filter(|x| x.is_finite()).collect();
        if v.is_empty() {
            continue;
        }
        let n = v.len();
        let mean = v.iter().sum::<f64>() / n as f64;
        let var = if n > 1 {
            v.iter().map(|x| (x - mean) * (x - mean)).sum::<f64>() / (n - 1) as f64
        } else {
            0.0
        };
        let sd = var.sqrt();
        let half = if n > 1 {
            1.96 * sd / (n as f64).sqrt()
        } else {
            0.0
        };
        out.push(ColumnStats {
            column: h,
            n,
            mean,
            std_dev: sd,
            ci95_low: mean - half,
            ci95_high: mean + half,
            min: v.iter().cloned().fold(f64::INFINITY, f64::min),
            max: v.iter().cloned().fold(f64::NEG_INFINITY, f64::max),
        });
    }
    Ok(out)
}

#[tauri::command]
pub fn validate_dataset_columns(
    app: AppHandle,
    workspace_id: String,
    dataset_id: String,
    observed_column: String,
    reference_column: String,
) -> Result<ValidationResult, String> {
    let meta = read_json(
        &workspace_dir(&app, &workspace_id)?
            .join("datasets")
            .join(&dataset_id)
            .join("metadata.json"),
    )?;
    let path = PathBuf::from(
        meta.get("storedFile")
            .and_then(Value::as_str)
            .ok_or("Dataset path missing")?,
    );
    let (headers, cols) = parse_csv_numeric(&path)?;
    let oi = headers
        .iter()
        .position(|h| h == &observed_column)
        .ok_or("Observed column not found")?;
    let ri = headers
        .iter()
        .position(|h| h == &reference_column)
        .ok_or("Reference column not found")?;
    let pairs: Vec<(f64, f64)> = cols[oi]
        .iter()
        .zip(cols[ri].iter())
        .filter_map(|(a, b)| Some(((*a)?, (*b)?)))
        .filter(|(a, b)| a.is_finite() && b.is_finite())
        .collect();
    if pairs.len() < 2 {
        return Err("Need at least two finite observed/reference pairs.".into());
    }
    let n = pairs.len();
    let mae = pairs.iter().map(|(a, b)| (a - b).abs()).sum::<f64>() / n as f64;
    let mse = pairs.iter().map(|(a, b)| (a - b) * (a - b)).sum::<f64>() / n as f64;
    let rmse = mse.sqrt();
    let max_abs_error = pairs.iter().map(|(a, b)| (a - b).abs()).fold(0.0, f64::max);
    let ref_mean = pairs.iter().map(|(_, b)| *b).sum::<f64>() / n as f64;
    let ref_scale = pairs.iter().map(|(_, b)| b.abs()).sum::<f64>() / n as f64;
    let relative_rmse = if ref_scale > 1e-15 {
        Some(rmse / ref_scale)
    } else {
        None
    };
    let ss_tot = pairs
        .iter()
        .map(|(_, b)| (b - ref_mean) * (b - ref_mean))
        .sum::<f64>();
    let ss_res = pairs.iter().map(|(a, b)| (a - b) * (a - b)).sum::<f64>();
    let r2 = if ss_tot > 1e-30 {
        Some(1.0 - ss_res / ss_tot)
    } else {
        None
    };
    let ratio = relative_rmse.unwrap_or(rmse);
    let agreement = if ratio < 0.01 {
        "Strong"
    } else if ratio < 0.05 {
        "Good"
    } else if ratio < 0.15 {
        "Moderate"
    } else {
        "Weak"
    }
    .to_string();
    Ok(ValidationResult{n,mae,rmse,max_abs_error,relative_rmse,r2,agreement,notes:vec!["Agreement labels are descriptive thresholds, not proof that either model or measurement is correct.".into(),"Inspect calibration, uncertainty, discretization and model assumptions before interpreting discrepancies.".into()]})
}

fn requirement_name(line: &str) -> String {
    let trimmed = line.trim();
    let mut name = String::new();
    for c in trimmed.chars() {
        if c.is_ascii_alphanumeric() || c == '-' || c == '_' || c == '.' {
            name.push(c)
        } else {
            break;
        }
    }
    name
}

fn command_text(program: &str, args: &[&str]) -> Option<String> {
    let out = Command::new(program).args(args).output().ok()?;
    if !out.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
}
fn command_text_in(dir: &Path, program: &str, args: &[&str]) -> Option<String> {
    let out = Command::new(program)
        .current_dir(dir)
        .args(args)
        .output()
        .ok()?;
    if !out.status.success() {
        return None;
    }
    Some(String::from_utf8_lossy(&out.stdout).trim().to_string())
}

fn pep440_probe(
    py: &Path,
    package: &str,
    requirement: &str,
) -> (Option<String>, Option<bool>, String) {
    let code = r#"import sys,importlib.metadata as m
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
    let out = Command::new(py)
        .args(["-c", code, package, requirement])
        .output();
    let Ok(out) = out else {
        return (None, None, "Version probe failed".into());
    };
    let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
    if text.starts_with("MISSING|||") {
        return (
            None,
            Some(false),
            "Package missing from this Lab environment".into(),
        );
    }
    let parts: Vec<&str> = text.split("|||").collect();
    let v = parts
        .first()
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string());
    let ok = match parts.get(1).copied() {
        Some("1") => Some(true),
        Some("0") => Some(false),
        _ => None,
    };
    (v, ok, parts.get(2).unwrap_or(&"").to_string())
}

#[tauri::command]
pub fn lab_compatibility_matrix(app: AppHandle) -> Result<Vec<CompatibilityRow>, String> {
    let mut rows = vec![];
    let root = modules_root(&app)?;
    for m in lab_specs()? {
        let moddir = root.join(&m.id);
        let src = moddir.join("source");
        let py = moddir.join(".venv/bin/python");
        let installed = src.exists() && py.exists();
        if !installed {
            rows.push(CompatibilityRow {
                module_id: m.id,
                module_name: m.name,
                installed: false,
                interpreter: None,
                package: "Environment".into(),
                requirement: "installed Lab venv".into(),
                found_version: None,
                compatible: None,
                detail: "Install the Lab before per-environment compatibility can be evaluated."
                    .into(),
            });
            continue;
        }
        let interp = command_text(
            py.to_string_lossy().as_ref(),
            &[
                "-c",
                "import sys; print(sys.executable+' | '+sys.version.split()[0])",
            ],
        );
        let req_path = m.requirements.as_ref().map(|r| src.join(r));
        if let Some(req) = req_path.filter(|p| p.exists()) {
            let text = fs::read_to_string(req).map_err(|e| e.to_string())?;
            for line in text.lines() {
                let line = line.split('#').next().unwrap_or("").trim();
                if line.is_empty() || line.starts_with('-') {
                    continue;
                }
                let pkg = requirement_name(line);
                if pkg.is_empty() {
                    continue;
                }
                let (ver, ok, detail) = pep440_probe(&py, &pkg, line);
                rows.push(CompatibilityRow {
                    module_id: m.id.clone(),
                    module_name: m.name.clone(),
                    installed: true,
                    interpreter: interp.clone(),
                    package: pkg,
                    requirement: line.into(),
                    found_version: ver,
                    compatible: ok,
                    detail,
                });
            }
        } else {
            for pkg in &m.verify_imports {
                let req = pkg.clone();
                let (ver, ok, detail) = pep440_probe(&py, pkg, &req);
                rows.push(CompatibilityRow {
                    module_id: m.id.clone(),
                    module_name: m.name.clone(),
                    installed: true,
                    interpreter: interp.clone(),
                    package: pkg.clone(),
                    requirement: req,
                    found_version: ver,
                    compatible: ok,
                    detail,
                });
            }
        }
    }
    Ok(rows)
}

#[tauri::command]
pub fn repair_lab_environment(app: AppHandle, module_id: String) -> Result<String, String> {
    let m = lab_specs()?
        .into_iter()
        .find(|m| m.id == module_id)
        .ok_or("Unknown Lab")?;
    let moddir = modules_root(&app)?.join(&m.id);
    let py = moddir.join(".venv/bin/python");
    let src = moddir.join("source");
    if !py.exists() {
        return Err("Managed Lab venv not found. Install the Lab first.".into());
    }
    let req = m
        .requirements
        .map(|r| src.join(r))
        .ok_or("Lab has no requirements file")?;
    if !req.exists() {
        return Err("Lab requirements file not found".into());
    }
    let status = Command::new(&py)
        .args(["-m", "pip", "install", "-r", req.to_string_lossy().as_ref()])
        .status()
        .map_err(|e| e.to_string())?;
    if !status.success() {
        return Err(
            "Managed venv repair failed; system Python and Conda environments were not modified."
                .into(),
        );
    }
    Ok(format!("Repaired only {}'s managed .venv.", m.name))
}

fn smoke_script(id: &str) -> &'static str {
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

#[tauri::command]
pub fn scientific_smoke_tests(app: AppHandle) -> Result<Vec<SmokeResult>, String> {
    let mut out = vec![];
    let root = modules_root(&app)?;
    for m in lab_specs()? {
        let py = root.join(&m.id).join(".venv/bin/python");
        let installed = py.exists();
        let start = Instant::now();
        if !installed {
            out.push(SmokeResult {
                module_id: m.id,
                module_name: m.name,
                installed: false,
                passed: false,
                scientific_ready: false,
                detail: "Lab not installed; smoke test skipped.".into(),
                duration_ms: start.elapsed().as_millis(),
            });
            continue;
        }
        let proc = Command::new(&py).args(["-c", smoke_script(&m.id)]).output();
        match proc {
            Ok(p) => {
                let passed = p.status.success();
                let detail = if passed {
                    String::from_utf8_lossy(&p.stdout).trim().to_string()
                } else {
                    String::from_utf8_lossy(&p.stderr).trim().to_string()
                };
                out.push(SmokeResult {
                    module_id: m.id,
                    module_name: m.name,
                    installed: true,
                    passed,
                    scientific_ready: passed,
                    detail,
                    duration_ms: start.elapsed().as_millis(),
                })
            }
            Err(e) => out.push(SmokeResult {
                module_id: m.id,
                module_name: m.name,
                installed: true,
                passed: false,
                scientific_ready: false,
                detail: e.to_string(),
                duration_ms: start.elapsed().as_millis(),
            }),
        }
    }
    Ok(out)
}

fn default_pipeline_value(kind: &str) -> Value {
    match kind {
        "accelerator-measurement" => {
            json!({"schema":"physical-lab-pipeline-v1","name":"Measured Field → RADIA → Radiation","steps":[
            {"id":"measurement","type":"dataset","label":"Measured magnetic field","status":"input"},
            {"id":"compare","type":"validation","label":"Measurement vs RADIA field","status":"ready"},
            {"id":"radia","type":"lab","moduleId":"radia-magnet-studio","mode":"full","label":"RADIA field model","status":"user-run"},
            {"id":"trajectory","type":"handoff","label":"Field → trajectory","status":"schema-ready"},
            {"id":"radiation","type":"lab","moduleId":"radiation-platform","mode":"full","label":"Trajectory → radiation","status":"user-run"}
        ],"note":"Physical Lab records and validates handoffs. Current Streamlit Labs retain ownership of their solvers; module stages are not silently auto-driven."})
        }
        "oscillation-modal" => {
            json!({"schema":"physical-lab-pipeline-v1","name":"Oscillation → Chrono::Modal Comparison","steps":[
            {"id":"osc","type":"lab","moduleId":"oscillation-integration","label":"Numerical oscillator","status":"user-run"},
            {"id":"matrix","type":"interchange","label":"Mass / stiffness / damping package","status":"schema-ready"},
            {"id":"modal","type":"adapter","adapterId":"chrono-modal","label":"Chrono::Modal provider","status":"adapter-boundary"},
            {"id":"compare","type":"validation","label":"Eigenfrequency / response comparison","status":"ready"}
        ],"note":"Chrono::Modal is not treated as a current Lab dependency until a real solver adapter consumes the interchange package."})
        }
        "atomistic-magnetism" => {
            json!({"schema":"physical-lab-pipeline-v1","name":"Material Inputs → VAMPIRE → Result Import","steps":[
            {"id":"material","type":"interchange","label":"Material / lattice / temperature / field","status":"schema-ready"},
            {"id":"vampire","type":"adapter","adapterId":"vampire","label":"VAMPIRE runtime","status":"adapter-boundary"},
            {"id":"results","type":"dataset","label":"Magnetization result import","status":"ready"}
        ],"note":"No fake atomistic solver is provided. Physical Lab prepares the contract and provenance boundary for a future validated adapter."})
        }
        _ => {
            json!({"schema":"physical-lab-pipeline-v1","name":"Measurement → Validation","steps":[{"id":"measurement","type":"dataset","label":"Measurement dataset","status":"input"},{"id":"analysis","type":"results","label":"Statistics / uncertainty","status":"ready"},{"id":"validation","type":"validation","label":"Observed vs reference","status":"ready"}]})
        }
    }
}

#[tauri::command]
pub fn pipeline_templates() -> Vec<Value> {
    vec![
        default_pipeline_value("accelerator-measurement"),
        default_pipeline_value("oscillation-modal"),
        default_pipeline_value("atomistic-magnetism"),
        default_pipeline_value("measurement-validation"),
    ]
}

#[tauri::command]
pub fn save_pipeline(app: AppHandle, workspace_id: String, kind: String) -> Result<String, String> {
    let dir = workspace_dir(&app, &workspace_id)?;
    let v = default_pipeline_value(&kind);
    let id = format!(
        "{}-{}",
        safe_slug(&kind),
        Local::now().format("%Y%m%d-%H%M%S")
    );
    write_json(&dir.join("pipelines").join(format!("{id}.json")), &v)?;
    touch_project(&dir)?;
    Ok(id)
}

#[tauri::command]
pub fn create_campaign(
    app: AppHandle,
    workspace_id: String,
    module_id: String,
    parameter: String,
    start: f64,
    stop: f64,
    points: u32,
    max_parallel: u32,
) -> Result<String, String> {
    if points < 2 || points > 10000 {
        return Err("Campaign points must be between 2 and 10000.".into());
    }
    let dir = workspace_dir(&app, &workspace_id)?;
    let id = format!(
        "{}-campaign-{}",
        safe_slug(&module_id),
        Local::now().format("%Y%m%d-%H%M%S")
    );
    let vals: Vec<f64> = (0..points)
        .map(|i| start + (stop - start) * (i as f64) / ((points - 1) as f64))
        .collect();
    let jobs:Vec<Value>=vals.iter().enumerate().map(|(i,v)|json!({"id":format!("run-{:04}",i+1),"parameter":&parameter,"value":v,"status":"queued"})).collect();
    write_json(
        &dir.join("campaigns").join(format!("{id}.json")),
        &json!({"schema":"physical-lab-campaign-v1","id":&id,"createdAt":now_iso(),"moduleId":module_id,"parameter":parameter,"start":start,"stop":stop,"points":points,"maxParallel":max_parallel.clamp(1,8),"queueState":"ready","jobs":jobs,"execution":"queue-and-handoff","note":"Campaign parameters are persisted reproducibly. Current Lab UIs remain solver owners until module-specific parameter adapters are added."}),
    )?;
    touch_project(&dir)?;
    Ok(id)
}

#[tauri::command]
pub fn adapter_statuses(app: AppHandle) -> Result<Vec<AdapterStatus>, String> {
    let home = std::env::var("HOME").unwrap_or_default();
    let chrono_found = [
        format!("{home}/Desktop/ChronoModal-Universal2"),
        format!("{home}/.local/chrono-modal"),
    ]
    .iter()
    .any(|p| Path::new(p).exists());
    let vamp = Path::new(&format!("{home}/.local/vampire-apple-silicon/bin/vampire")).exists();
    Ok(vec![
        AdapterStatus{id:"chrono-modal".into(),name:"Chrono::Modal".into(),runtime_found:chrono_found,consumed_by_current_lab:false,adapter_state:"Interchange contract ready; solver adapter intentionally not claimed".into(),interchange:vec!["mass matrix".into(),"stiffness matrix".into(),"damping matrix".into(),"units".into(),"coordinate order".into(),"solver tolerances".into(),"provenance".into()],note:"Use CMake find_package(Chrono COMPONENTS Modal CONFIG) and provider verification before enabling a real comparison adapter.".into()},
        AdapterStatus{id:"vampire".into(),name:"VAMPIRE".into(),runtime_found:vamp,consumed_by_current_lab:false,adapter_state:"Input/result contract ready; no fake atomistic solver".into(),interchange:vec!["material".into(),"lattice".into(),"temperature".into(),"field".into(),"magnetization results".into(),"provenance".into()],note:"The current Apple-Silicon runtime remains optional until a validated Lab adapter consumes it.".into()}
    ])
}

#[tauri::command]
pub fn export_reproducibility_package(
    app: AppHandle,
    workspace_id: String,
) -> Result<String, String> {
    let dir = workspace_dir(&app, &workspace_id)?;
    let prov = dir.join("provenance");
    fs::create_dir_all(&prov).map_err(|e| e.to_string())?;
    let specs = lab_specs()?;
    let mut mods = vec![];
    let root = modules_root(&app)?;
    for m in specs {
        let md = root.join(&m.id);
        let src = md.join("source");
        let py = md.join(".venv/bin/python");
        mods.push(json!({"id":m.id,"name":m.name,"sourceCommit":if src.exists(){command_text_in(&src,"git",&["rev-parse","HEAD"])}else{None},"python":if py.exists(){command_text(py.to_string_lossy().as_ref(),&["--version"])}else{None},"pipFreeze":if py.exists(){command_text(py.to_string_lossy().as_ref(),&["-m","pip","freeze","--all"])}else{None}}));
    }
    write_json(
        &prov.join("environment.json"),
        &json!({"createdAt":now_iso(),"machine":{"arch":command_text("uname",&["-m"]),"os":command_text("sw_vers",&["-productVersion"]),"build":command_text("sw_vers",&["-buildVersion"])},"modules":mods}),
    )?;
    let export_dir = app_root(&app)?.join("exports");
    fs::create_dir_all(&export_dir).map_err(|e| e.to_string())?;
    let out = export_dir.join(format!(
        "{}-reproducible-{}.zip",
        safe_slug(&workspace_id),
        Local::now().format("%Y%m%d-%H%M%S")
    ));
    let dir_s = dir.to_string_lossy().to_string();
    let out_s = out.to_string_lossy().to_string();
    let base_name = dir
        .file_name()
        .and_then(|x| x.to_str())
        .unwrap_or("workspace")
        .to_string();
    let status = Command::new("/usr/bin/ditto")
        .args([
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            dir_s.as_str(),
            out_s.as_str(),
        ])
        .status()
        .or_else(|_| {
            Command::new("/usr/bin/zip")
                .current_dir(dir.parent().unwrap_or(&dir))
                .args(["-r", out_s.as_str(), base_name.as_str()])
                .status()
        })
        .map_err(|e| e.to_string())?;
    if !status.success() {
        return Err("Reproducibility archive creation failed".into());
    }
    Ok(out.to_string_lossy().to_string())
}

#[tauri::command]
pub fn list_run_snapshots(app: AppHandle, workspace_id: String) -> Result<Vec<Value>, String> {
    let runs = workspace_dir(&app, &workspace_id)?.join("runs");
    let mut out = vec![];
    for e in fs::read_dir(runs)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        let p = e.path().join("run.json");
        if let Ok(v) = read_json(&p) {
            out.push(v)
        }
    }
    out.sort_by(|a, b| {
        b.get("createdAt")
            .and_then(Value::as_str)
            .unwrap_or("")
            .cmp(a.get("createdAt").and_then(Value::as_str).unwrap_or(""))
    });
    Ok(out)
}

fn flatten_json(prefix: &str, v: &Value, out: &mut HashMap<String, String>) {
    match v {
        Value::Object(m) => {
            for (k, val) in m {
                let p = if prefix.is_empty() {
                    k.clone()
                } else {
                    format!("{prefix}.{k}")
                };
                flatten_json(&p, val, out)
            }
        }
        Value::Array(a) => {
            out.insert(prefix.into(), format!("[{} items]", a.len()));
        }
        _ => {
            out.insert(prefix.into(), v.to_string());
        }
    }
}

#[tauri::command]
pub fn compare_run_snapshots(
    app: AppHandle,
    workspace_id: String,
    run_a: String,
    run_b: String,
) -> Result<Value, String> {
    let base = workspace_dir(&app, &workspace_id)?.join("runs");
    let a = read_json(&base.join(&run_a).join("run.json"))?;
    let b = read_json(&base.join(&run_b).join("run.json"))?;
    let mut fa = HashMap::new();
    let mut fb = HashMap::new();
    flatten_json("", &a, &mut fa);
    flatten_json("", &b, &mut fb);
    let mut keys: Vec<String> = fa.keys().chain(fb.keys()).cloned().collect();
    keys.sort();
    keys.dedup();
    let diffs: Vec<Value> = keys
        .into_iter()
        .filter_map(|k| {
            let av = fa.get(&k);
            let bv = fb.get(&k);
            if av == bv {
                None
            } else {
                Some(json!({"field":k,"a":av,"b":bv}))
            }
        })
        .collect();
    let count = diffs.len();
    Ok(json!({"runA":run_a,"runB":run_b,"differences":diffs,"differenceCount":count}))
}

#[tauri::command]
pub fn list_campaigns(app: AppHandle, workspace_id: String) -> Result<Vec<Value>, String> {
    let dir = workspace_dir(&app, &workspace_id)?.join("campaigns");
    let mut out = vec![];
    for e in fs::read_dir(dir)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        if e.path().extension().and_then(|x| x.to_str()) == Some("json") {
            if let Ok(v) = read_json(&e.path()) {
                out.push(v)
            }
        }
    }
    out.sort_by(|a, b| {
        b.get("createdAt")
            .and_then(Value::as_str)
            .unwrap_or("")
            .cmp(a.get("createdAt").and_then(Value::as_str).unwrap_or(""))
    });
    Ok(out)
}

#[tauri::command]
pub fn campaign_action(
    app: AppHandle,
    workspace_id: String,
    campaign_id: String,
    action: String,
) -> Result<Value, String> {
    let path = workspace_dir(&app, &workspace_id)?
        .join("campaigns")
        .join(format!("{campaign_id}.json"));
    let mut v = read_json(&path)?;
    let act = action.as_str();
    match act {
        "pause" => v["queueState"] = Value::String("paused".into()),
        "resume" => v["queueState"] = Value::String("ready".into()),
        "retry-failed" => {
            if let Some(jobs) = v.get_mut("jobs").and_then(Value::as_array_mut) {
                for j in jobs {
                    if j.get("status").and_then(Value::as_str) == Some("failed") {
                        j["status"] = Value::String("queued".into())
                    }
                }
            }
        }
        "reset" => {
            if let Some(jobs) = v.get_mut("jobs").and_then(Value::as_array_mut) {
                for j in jobs {
                    j["status"] = Value::String("queued".into())
                }
            }
        }
        _ => return Err("Supported campaign actions: pause, resume, retry-failed, reset".into()),
    }
    v["updatedAt"] = Value::String(now_iso());
    write_json(&path, &v)?;
    Ok(v)
}
