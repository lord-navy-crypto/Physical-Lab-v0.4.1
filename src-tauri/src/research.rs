use chrono::Local;
use serde_json::{json, Value};
use std::{collections::HashSet, fs, path::{Path, PathBuf}};
use tauri::{AppHandle, Manager};

#[path = "research_legacy.rs"]
pub mod legacy;

pub use legacy::{AdapterStatus, ColumnStats, CompatibilityRow, DatasetSummary, SmokeResult, ValidationResult, WorkspaceSummary};

const CANONICAL_SCHEMA: &str = "physical-lab-project-v1";
const CANONICAL_VERSION: i64 = 1;

fn app_root(app: &AppHandle) -> Result<PathBuf, String> {
    let root = app.path().app_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    Ok(root)
}

fn projects_root(app: &AppHandle) -> Result<PathBuf, String> {
    let root = app_root(app)?.join("projects");
    fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    Ok(root)
}

fn compatibility_root(app: &AppHandle) -> Result<PathBuf, String> {
    let root = app_root(app)?.join("workspaces");
    fs::create_dir_all(&root).map_err(|e| e.to_string())?;
    Ok(root)
}

fn safe_slug(value: &str) -> String {
    let mut out = String::new();
    for c in value.trim().chars() {
        if c.is_ascii_alphanumeric() { out.push(c.to_ascii_lowercase()); }
        else if c == '-' || c == '_' || c.is_whitespace() {
            if !out.ends_with('-') { out.push('-'); }
        }
    }
    let out = out.trim_matches('-').to_string();
    if out.is_empty() { "project".into() } else { out }
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

fn write_json(path: &Path, value: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() { fs::create_dir_all(parent).map_err(|e| e.to_string())?; }
    fs::write(path, serde_json::to_string_pretty(value).map_err(|e| e.to_string())?).map_err(|e| e.to_string())
}

fn count_entries(path: PathBuf) -> usize {
    fs::read_dir(path).ok().map(|it| it.filter_map(Result::ok).count()).unwrap_or(0)
}

fn canonical_project(document: &Value) -> bool {
    document.get("schema").and_then(Value::as_str) == Some(CANONICAL_SCHEMA)
        && document.get("project_version").and_then(Value::as_i64) == Some(CANONICAL_VERSION)
        && document.get("project_id").and_then(Value::as_str).map(|x| x.starts_with("plproj-")).unwrap_or(false)
        && document.get("experiments").and_then(Value::as_object).is_some()
        && document.get("jobs").and_then(Value::as_object).is_some()
        && document.get("results").and_then(Value::as_object).is_some()
}

fn project_id(document: &Value) -> Option<String> {
    document.get("project_id").and_then(Value::as_str).map(str::to_string)
}

fn canonical_dir_by_id(app: &AppHandle, id: &str) -> Result<PathBuf, String> {
    for entry in fs::read_dir(projects_root(app)?).map_err(|e| e.to_string())?.filter_map(Result::ok) {
        let dir = entry.path();
        let project_json = dir.join("project.json");
        if !project_json.is_file() { continue; }
        if let Ok(document) = read_json(&project_json) {
            if canonical_project(&document) && project_id(&document).as_deref() == Some(id) {
                return Ok(dir);
            }
        }
    }
    Err(format!("Canonical project not found: {id}"))
}

#[cfg(unix)]
fn ensure_compatibility_link(app: &AppHandle, id: &str, canonical: &Path) -> Result<(), String> {
    use std::os::unix::fs::symlink;
    let link = compatibility_root(app)?.join(format!("{}.physlab", safe_slug(id)));
    if let Ok(meta) = fs::symlink_metadata(&link) {
        if meta.file_type().is_symlink() {
            let target = fs::read_link(&link).map_err(|e| e.to_string())?;
            let resolved = if target.is_absolute() { target } else { link.parent().unwrap_or(Path::new(".")).join(target) };
            if resolved.canonicalize().ok().as_deref() == canonical.canonicalize().ok().as_deref() { return Ok(()); }
            fs::remove_file(&link).map_err(|e| e.to_string())?;
        } else {
            return Err(format!("Compatibility handle collision: {}", link.display()));
        }
    }
    symlink(canonical, &link).map_err(|e| format!("Could not create canonical project compatibility link {}: {e}", link.display()))
}

#[cfg(not(unix))]
fn ensure_compatibility_link(_app: &AppHandle, _id: &str, _canonical: &Path) -> Result<(), String> {
    Err("Physical Lab desktop Project compatibility links require a Unix-like platform.".into())
}

fn prepare_workspace_handle(app: &AppHandle, id: &str) -> Result<Option<PathBuf>, String> {
    match canonical_dir_by_id(app, id) {
        Ok(dir) => {
            ensure_compatibility_link(app, id, &dir)?;
            Ok(Some(dir))
        }
        Err(_) => Ok(None),
    }
}

fn sync_canonical_timestamp(dir: Option<&Path>) -> Result<(), String> {
    let Some(dir) = dir else { return Ok(()); };
    let path = dir.join("project.json");
    let mut document = read_json(&path)?;
    if !canonical_project(&document) { return Ok(()); }
    let shell = document.get("updatedAt").and_then(Value::as_str).unwrap_or("").to_string();
    let canonical = document.get("updated_at").and_then(Value::as_str).unwrap_or("").to_string();
    let chosen = if shell > canonical { shell } else if !canonical.is_empty() { canonical } else { Local::now().to_rfc3339() };
    document["updated_at"] = Value::String(chosen.clone());
    document["updatedAt"] = Value::String(chosen);
    write_json(&path, &document)
}

fn latest_timestamp(document: &Value) -> String {
    let canonical = document.get("updated_at").and_then(Value::as_str).unwrap_or("");
    let shell = document.get("updatedAt").and_then(Value::as_str).unwrap_or("");
    if shell > canonical { shell.to_string() } else { canonical.to_string() }
}

fn summary_from_canonical(app: &AppHandle, dir: &Path, document: &Value) -> Result<WorkspaceSummary, String> {
    let id = project_id(document).ok_or_else(|| "canonical project is missing project_id".to_string())?;
    ensure_compatibility_link(app, &id, dir)?;
    Ok(WorkspaceSummary {
        id,
        name: document.get("name").and_then(Value::as_str).unwrap_or("Physical Lab Project").to_string(),
        created_at: document.get("created_at").and_then(Value::as_str)
            .or_else(|| document.get("createdAt").and_then(Value::as_str)).unwrap_or("").to_string(),
        updated_at: latest_timestamp(document),
        path: dir.to_string_lossy().to_string(),
        datasets: count_entries(dir.join("datasets")),
        runs: count_entries(dir.join("runs")),
        campaigns: count_entries(dir.join("campaigns")),
    })
}

fn bridged_legacy_sources(canonical_dirs: &[PathBuf]) -> HashSet<String> {
    let mut out = HashSet::new();
    for dir in canonical_dirs {
        let bridge = dir.join("provenance/legacy-workspace-bridge.json");
        if let Ok(value) = read_json(&bridge) {
            if let Some(path) = value.get("legacy").and_then(|x| x.get("source_path")).and_then(Value::as_str) {
                out.insert(path.to_string());
            }
        }
    }
    out
}

#[tauri::command]
pub fn create_workspace(app: AppHandle, name: String) -> Result<WorkspaceSummary, String> {
    let root = projects_root(&app)?;
    let base = safe_slug(&name);
    let mut slug = base.clone();
    let mut n = 2usize;
    while root.join(format!("{slug}.physlab")).exists() {
        slug = format!("{base}-{n}");
        n += 1;
    }
    let dir = root.join(format!("{slug}.physlab"));
    for child in [
        "experiments", "jobs", "results", "measurements", "calibration", "reports", "provenance",
        "datasets", "runs", "figures", "exports", "pipelines", "campaigns"
    ] {
        fs::create_dir_all(dir.join(child)).map_err(|e| e.to_string())?;
    }
    let now = Local::now().to_rfc3339();
    let project_id = format!("plproj-shell-{}-{}", Local::now().timestamp_micros(), std::process::id());
    let document = json!({
        "schema": CANONICAL_SCHEMA,
        "project_version": CANONICAL_VERSION,
        "project_id": project_id,
        "name": name.trim(),
        "slug": slug,
        "description": "Physical Lab reproducible engineering-physics project",
        "research_question": "",
        "created_at": now,
        "updated_at": now,
        "profiles": [],
        "experiments": {},
        "jobs": {},
        "results": {},
        "reports": [],
        "migration": {"current_version": CANONICAL_VERSION, "history": []},
        "boundary": "Canonical project metadata and provenance index. Desktop datasets/runs/campaigns remain operational records until explicitly registered as measurement, experiment, job, result or other evidence by the corresponding Physical Lab kernel.",
        "desktop_shell": {
            "storage": "canonical-projects",
            "operational_directories": ["datasets", "runs", "figures", "exports", "pipelines", "campaigns"],
            "compatibility_link": true
        },
        "id": project_id,
        "createdAt": now,
        "updatedAt": now
    });
    write_json(&dir.join("project.json"), &document)?;
    ensure_compatibility_link(&app, document["project_id"].as_str().unwrap_or(""), &dir)?;
    let _ = legacy::save_pipeline(app.clone(), document["project_id"].as_str().unwrap_or("").to_string(), "measurement-validation".into());
    sync_canonical_timestamp(Some(&dir))?;
    let refreshed = read_json(&dir.join("project.json"))?;
    summary_from_canonical(&app, &dir, &refreshed)
}

#[tauri::command]
pub fn list_workspaces(app: AppHandle) -> Result<Vec<WorkspaceSummary>, String> {
    let mut output = Vec::new();
    let mut canonical_dirs = Vec::new();
    for entry in fs::read_dir(projects_root(&app)?).map_err(|e| e.to_string())?.filter_map(Result::ok) {
        let dir = entry.path();
        let project_json = dir.join("project.json");
        if !project_json.is_file() { continue; }
        let Ok(document) = read_json(&project_json) else { continue; };
        if !canonical_project(&document) { continue; }
        if let Ok(summary) = summary_from_canonical(&app, &dir, &document) {
            canonical_dirs.push(dir);
            output.push(summary);
        }
    }

    let bridged = bridged_legacy_sources(&canonical_dirs);
    if let Ok(legacy_rows) = legacy::list_workspaces(app.clone()) {
        for row in legacy_rows {
            let path = PathBuf::from(&row.path);
            let is_link = fs::symlink_metadata(&path).map(|m| m.file_type().is_symlink()).unwrap_or(false);
            if is_link || bridged.contains(&row.path) { continue; }
            output.push(row);
        }
    }
    output.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
    Ok(output)
}

#[tauri::command]
pub fn open_workspace(app: AppHandle, workspace_id: String) -> Result<String, String> {
    if let Ok(dir) = canonical_dir_by_id(&app, &workspace_id) {
        ensure_compatibility_link(&app, &workspace_id, &dir)?;
        #[cfg(target_os = "macos")]
        {
            std::process::Command::new("/usr/bin/open").arg(&dir).spawn().map_err(|e| e.to_string())?;
        }
        return Ok(dir.to_string_lossy().to_string());
    }
    legacy::open_workspace(app, workspace_id)
}

#[tauri::command]
pub fn record_run_snapshot(app: AppHandle, workspace_id: String, module_id: String, mode: String, parameters_json: String, results_json: String) -> Result<String, String> {
    let canonical = prepare_workspace_handle(&app, &workspace_id)?;
    let result = legacy::record_run_snapshot(app, workspace_id, module_id, mode, parameters_json, results_json)?;
    sync_canonical_timestamp(canonical.as_deref())?;
    Ok(result)
}

#[tauri::command]
pub fn import_measurement_dataset(app: AppHandle, workspace_id: String, source_path: String, name: String, quantity: String, unit: String, sensor: String, calibration: String) -> Result<DatasetSummary, String> {
    let canonical = prepare_workspace_handle(&app, &workspace_id)?;
    let result = legacy::import_measurement_dataset(app, workspace_id, source_path, name, quantity, unit, sensor, calibration)?;
    sync_canonical_timestamp(canonical.as_deref())?;
    Ok(result)
}

#[tauri::command]
pub fn list_datasets(app: AppHandle, workspace_id: String) -> Result<Vec<DatasetSummary>, String> {
    prepare_workspace_handle(&app, &workspace_id)?;
    legacy::list_datasets(app, workspace_id)
}

#[tauri::command]
pub fn list_serial_devices() -> Result<Vec<String>, String> { legacy::list_serial_devices() }

#[tauri::command]
pub fn capture_serial_measurement(app: AppHandle, workspace_id: String, device: String, baud: u32, seconds: u64, name: String, quantity: String, unit: String, sensor: String) -> Result<DatasetSummary, String> {
    let canonical = prepare_workspace_handle(&app, &workspace_id)?;
    let result = legacy::capture_serial_measurement(app, workspace_id, device, baud, seconds, name, quantity, unit, sensor)?;
    sync_canonical_timestamp(canonical.as_deref())?;
    Ok(result)
}

#[tauri::command]
pub fn analyze_dataset(app: AppHandle, workspace_id: String, dataset_id: String) -> Result<Vec<ColumnStats>, String> {
    prepare_workspace_handle(&app, &workspace_id)?;
    legacy::analyze_dataset(app, workspace_id, dataset_id)
}

#[tauri::command]
pub fn validate_dataset_columns(app: AppHandle, workspace_id: String, dataset_id: String, observed_column: String, reference_column: String) -> Result<ValidationResult, String> {
    prepare_workspace_handle(&app, &workspace_id)?;
    legacy::validate_dataset_columns(app, workspace_id, dataset_id, observed_column, reference_column)
}

#[tauri::command]
pub fn lab_compatibility_matrix(app: AppHandle) -> Result<Vec<CompatibilityRow>, String> { legacy::lab_compatibility_matrix(app) }

#[tauri::command]
pub fn repair_lab_environment(app: AppHandle, module_id: String) -> Result<String, String> { legacy::repair_lab_environment(app, module_id) }

#[tauri::command]
pub fn scientific_smoke_tests(app: AppHandle) -> Result<Vec<SmokeResult>, String> { legacy::scientific_smoke_tests(app) }

#[tauri::command]
pub fn pipeline_templates() -> Vec<Value> { legacy::pipeline_templates() }

#[tauri::command]
pub fn save_pipeline(app: AppHandle, workspace_id: String, kind: String) -> Result<String, String> {
    let canonical = prepare_workspace_handle(&app, &workspace_id)?;
    let result = legacy::save_pipeline(app, workspace_id, kind)?;
    sync_canonical_timestamp(canonical.as_deref())?;
    Ok(result)
}

#[tauri::command]
pub fn create_campaign(app: AppHandle, workspace_id: String, module_id: String, parameter: String, start: f64, stop: f64, points: u32, max_parallel: u32) -> Result<String, String> {
    let canonical = prepare_workspace_handle(&app, &workspace_id)?;
    let result = legacy::create_campaign(app, workspace_id, module_id, parameter, start, stop, points, max_parallel)?;
    sync_canonical_timestamp(canonical.as_deref())?;
    Ok(result)
}

#[tauri::command]
pub fn adapter_statuses(app: AppHandle) -> Result<Vec<AdapterStatus>, String> { legacy::adapter_statuses(app) }

#[tauri::command]
pub fn export_reproducibility_package(app: AppHandle, workspace_id: String) -> Result<String, String> {
    let canonical = prepare_workspace_handle(&app, &workspace_id)?;
    let result = legacy::export_reproducibility_package(app, workspace_id)?;
    sync_canonical_timestamp(canonical.as_deref())?;
    Ok(result)
}

#[tauri::command]
pub fn list_run_snapshots(app: AppHandle, workspace_id: String) -> Result<Vec<Value>, String> {
    prepare_workspace_handle(&app, &workspace_id)?;
    legacy::list_run_snapshots(app, workspace_id)
}

#[tauri::command]
pub fn compare_run_snapshots(app: AppHandle, workspace_id: String, run_a: String, run_b: String) -> Result<Value, String> {
    prepare_workspace_handle(&app, &workspace_id)?;
    legacy::compare_run_snapshots(app, workspace_id, run_a, run_b)
}

#[tauri::command]
pub fn list_campaigns(app: AppHandle, workspace_id: String) -> Result<Vec<Value>, String> {
    prepare_workspace_handle(&app, &workspace_id)?;
    legacy::list_campaigns(app, workspace_id)
}

#[tauri::command]
pub fn campaign_action(app: AppHandle, workspace_id: String, campaign_id: String, action: String) -> Result<Value, String> {
    let canonical = prepare_workspace_handle(&app, &workspace_id)?;
    let result = legacy::campaign_action(app, workspace_id, campaign_id, action)?;
    sync_canonical_timestamp(canonical.as_deref())?;
    Ok(result)
}
