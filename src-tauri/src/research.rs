//! Canonical desktop research facade for Physical Lab.
//!
//! The pre-cutover Rust research implementation is preserved byte-for-byte in
//! `research_legacy_impl.rs`. New desktop projects are created under the same
//! `projects/*.physlab` Project Kernel used by Experiment / Evidence tooling.
//! Compatibility symlinks let the mature desktop Data/Results/Campaign surfaces
//! keep using their existing code paths without creating a second project store.
//!
//! Existing real `workspaces/*.physlab` directories are never replaced. They
//! continue through the non-destructive legacy bridge until explicitly retired.

#[path = "research_legacy_impl.rs"]
mod legacy;

use chrono::Local;
use serde_json::{json, Value};
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};
use tauri::{AppHandle, Manager};

pub use legacy::{
    AdapterStatus, ColumnStats, CompatibilityRow, DatasetSummary, SmokeResult,
    ValidationResult, WorkspaceSummary,
};

const PROJECT_SCHEMA: &str = "physical-lab-project-v1";
const PROJECT_VERSION: u64 = 1;

fn app_root(app: &AppHandle) -> Result<PathBuf, String> {
    let path = app.path().app_data_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&path).map_err(|e| e.to_string())?;
    Ok(path)
}

fn canonical_root(app: &AppHandle) -> Result<PathBuf, String> {
    let path = app_root(app)?.join("projects");
    fs::create_dir_all(&path).map_err(|e| e.to_string())?;
    Ok(path)
}

fn legacy_root(app: &AppHandle) -> Result<PathBuf, String> {
    let path = app_root(app)?.join("workspaces");
    fs::create_dir_all(&path).map_err(|e| e.to_string())?;
    Ok(path)
}

fn safe_slug(value: &str) -> String {
    let mut out = String::new();
    for ch in value.trim().chars() {
        if ch.is_ascii_alphanumeric() {
            out.push(ch.to_ascii_lowercase());
        } else if ch == '-' || ch == '_' || ch == '.' || ch.is_whitespace() {
            if !out.ends_with('-') {
                out.push('-');
            }
        }
    }
    let out = out.trim_matches(['-', '.', '_']).to_string();
    if out.is_empty() { "project".into() } else { out }
}

fn now_iso() -> String {
    Local::now().to_rfc3339()
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = fs::read_to_string(path).map_err(|e| e.to_string())?;
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

fn write_json(path: &Path, value: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let tmp = path.with_extension(format!(
        "{}tmp",
        path.extension().and_then(|x| x.to_str()).unwrap_or("")
    ));
    fs::write(
        &tmp,
        serde_json::to_string_pretty(value).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    fs::rename(&tmp, path).map_err(|e| e.to_string())
}

fn count_entries(path: PathBuf) -> usize {
    fs::read_dir(path)
        .ok()
        .map(|iter| iter.filter_map(Result::ok).count())
        .unwrap_or(0)
}

fn is_canonical(document: &Value) -> bool {
    document.get("schema").and_then(Value::as_str) == Some(PROJECT_SCHEMA)
        && document.get("project_version").and_then(Value::as_u64) == Some(PROJECT_VERSION)
        && document
            .get("project_id")
            .and_then(Value::as_str)
            .map(|value| value.starts_with("plproj-"))
            .unwrap_or(false)
}

fn summary_from_dir(path: &Path) -> Result<WorkspaceSummary, String> {
    let project = read_json(&path.join("project.json"))?;
    let fallback = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("project")
        .trim_end_matches(".physlab")
        .to_string();
    let id = project
        .get("slug")
        .or_else(|| project.get("id"))
        .and_then(Value::as_str)
        .unwrap_or(&fallback)
        .to_string();
    Ok(WorkspaceSummary {
        id,
        name: project
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or("Physical Lab Project")
            .to_string(),
        created_at: project
            .get("created_at")
            .or_else(|| project.get("createdAt"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        updated_at: project
            .get("updated_at")
            .or_else(|| project.get("updatedAt"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        path: path.to_string_lossy().to_string(),
        datasets: count_entries(path.join("datasets")),
        runs: count_entries(path.join("runs")),
        campaigns: count_entries(path.join("campaigns")),
    })
}

#[cfg(unix)]
fn create_alias(alias: &Path, target: &Path) -> Result<(), String> {
    use std::os::unix::fs::symlink;
    if alias.exists() || alias.symlink_metadata().is_ok() {
        return Ok(());
    }
    symlink(target, alias).map_err(|e| format!("Could not create project compatibility alias: {e}"))
}

#[cfg(not(unix))]
fn create_alias(_alias: &Path, _target: &Path) -> Result<(), String> {
    Ok(())
}

fn ensure_alias_for_id(app: &AppHandle, workspace_id: &str) -> Result<(), String> {
    let id = safe_slug(workspace_id);
    let canonical = canonical_root(app)?.join(format!("{id}.physlab"));
    if !canonical.is_dir() {
        return Ok(());
    }
    let alias = legacy_root(app)?.join(format!("{id}.physlab"));
    // A real legacy workspace wins during the compatibility period. Never
    // replace it with an alias; its one-way bridge remains the safe migration path.
    if alias.exists() || alias.symlink_metadata().is_ok() {
        return Ok(());
    }
    create_alias(&alias, &canonical)
}

fn ensure_all_aliases(app: &AppHandle) -> Result<(), String> {
    let root = canonical_root(app)?;
    for entry in fs::read_dir(root).map_err(|e| e.to_string())?.filter_map(Result::ok) {
        let path = entry.path();
        if !path.is_dir() || !path.join("project.json").is_file() {
            continue;
        }
        let document = match read_json(&path.join("project.json")) {
            Ok(value) => value,
            Err(_) => continue,
        };
        if !is_canonical(&document) {
            continue;
        }
        let slug = document
            .get("slug")
            .and_then(Value::as_str)
            .unwrap_or_else(|| path.file_stem().and_then(|x| x.to_str()).unwrap_or("project"));
        let _ = ensure_alias_for_id(app, slug);
    }
    Ok(())
}

fn alias_targets_canonical(app: &AppHandle, workspace_id: &str) -> Result<bool, String> {
    let id = safe_slug(workspace_id);
    let canonical = canonical_root(app)?.join(format!("{id}.physlab"));
    if !canonical.is_dir() {
        return Ok(false);
    }
    let alias = legacy_root(app)?.join(format!("{id}.physlab"));
    let metadata = match fs::symlink_metadata(alias) {
        Ok(value) => value,
        Err(_) => return Ok(false),
    };
    Ok(metadata.file_type().is_symlink())
}

fn touch_canonical_after_write(app: &AppHandle, workspace_id: &str) -> Result<(), String> {
    if !alias_targets_canonical(app, workspace_id)? {
        return Ok(());
    }
    let id = safe_slug(workspace_id);
    let path = canonical_root(app)?.join(format!("{id}.physlab/project.json"));
    let mut project = read_json(&path)?;
    if !is_canonical(&project) {
        return Ok(());
    }
    project["updated_at"] = Value::String(now_iso());
    if let Some(object) = project.as_object_mut() {
        object.remove("updatedAt");
    }
    write_json(&path, &project)
}

fn register_desktop_measurement(
    app: &AppHandle,
    workspace_id: &str,
    dataset: &DatasetSummary,
    note: &str,
) -> Result<(), String> {
    if !alias_targets_canonical(app, workspace_id)? {
        return Ok(());
    }
    let id = safe_slug(workspace_id);
    let project_dir = canonical_root(app)?.join(format!("{id}.physlab"));
    let project = read_json(&project_dir.join("project.json"))?;
    if !is_canonical(&project) {
        return Ok(());
    }
    let digest = match dataset.sha256.as_deref() {
        Some(value) if value.len() == 64 => value.to_string(),
        _ => return Ok(()),
    };
    let measurement_id = format!("meas-{}", &digest[..20]);
    let source = PathBuf::from(&dataset.stored_file);
    if !source.is_file() {
        return Ok(());
    }
    let filename = source
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("measurement.dat")
        .to_string();
    let measurement_dir = project_dir.join("measurements").join(&measurement_id);
    fs::create_dir_all(&measurement_dir).map_err(|e| e.to_string())?;
    let asset = measurement_dir.join(&filename);
    if !asset.exists() {
        fs::copy(&source, &asset).map_err(|e| e.to_string())?;
    }
    let index_path = project_dir.join("measurements/index.json");
    let mut index = if index_path.is_file() {
        read_json(&index_path).unwrap_or_else(|_| json!({}))
    } else {
        json!({})
    };
    if index.get("schema").and_then(Value::as_str) != Some("physical-lab-measurement-index-v1") {
        index = json!({
            "schema": "physical-lab-measurement-index-v1",
            "measurements": {},
            "updated_at": null
        });
    }
    let previous_registered = index
        .get("measurements")
        .and_then(|value| value.get(&measurement_id))
        .and_then(|value| value.get("registered_at"))
        .and_then(Value::as_str)
        .map(str::to_string);
    let registered_at = previous_registered.unwrap_or_else(now_iso);
    let relative_asset = asset
        .strip_prefix(&project_dir)
        .unwrap_or(&asset)
        .to_string_lossy()
        .replace('\\', "/");
    let record = json!({
        "schema": "physical-lab-measurement-v1",
        "measurement_id": measurement_id,
        "project_id": project.get("project_id").and_then(Value::as_str).unwrap_or(""),
        "profile": "desktop-data-bridge",
        "source_type": "desktop-data-bridge",
        "file_name": filename,
        "asset_path": relative_asset,
        "format": dataset.format,
        "size_bytes": source.metadata().map(|m| m.len()).unwrap_or(0),
        "sha256": digest,
        "instrument": dataset.sensor,
        "quantity": dataset.quantity,
        "unit": dataset.unit,
        "captured_at": dataset.created_at,
        "registered_at": registered_at,
        "notes": note,
        "preview": {
            "format": dataset.format,
            "preview": "Desktop Data Bridge asset; content is fingerprinted and interpretation remains with the selected Lab reader."
        },
        "boundary": "Desktop measurement evidence with file-integrity provenance only. Calibration status, sensor accuracy, traceability and experimental validation must be established separately."
    });
    write_json(&measurement_dir.join("measurement.json"), &record)?;
    if index.get("measurements").and_then(Value::as_object).is_none() {
        index["measurements"] = json!({});
    }
    if let Some(measurements) = index.get_mut("measurements").and_then(Value::as_object_mut) {
        measurements.insert(
            record.get("measurement_id").and_then(Value::as_str).unwrap_or("").to_string(),
            record,
        );
    }
    index["updated_at"] = Value::String(now_iso());
    write_json(&index_path, &index)
}

#[tauri::command]
pub fn create_workspace(app: AppHandle, name: String) -> Result<WorkspaceSummary, String> {
    let base = safe_slug(&name);
    let canonical = canonical_root(&app)?;
    let legacy = legacy_root(&app)?;
    let mut id = base.clone();
    let mut n = 2u32;
    while canonical.join(format!("{id}.physlab")).exists()
        || legacy.join(format!("{id}.physlab")).exists()
        || legacy.join(format!("{id}.physlab")).symlink_metadata().is_ok()
    {
        id = format!("{base}-{n}");
        n += 1;
    }
    let dir = canonical.join(format!("{id}.physlab"));
    for child in [
        "experiments", "jobs", "results", "measurements", "calibration", "reports", "provenance",
        "datasets", "runs", "figures", "exports", "pipelines", "campaigns",
    ] {
        fs::create_dir_all(dir.join(child)).map_err(|e| e.to_string())?;
    }
    let now = now_iso();
    let project_id = format!(
        "plproj-shell-{}-{}",
        Local::now().timestamp_micros(),
        id
    );
    write_json(
        &dir.join("project.json"),
        &json!({
            "schema": PROJECT_SCHEMA,
            "project_version": PROJECT_VERSION,
            "project_id": project_id,
            "name": name.trim(),
            "slug": id,
            "description": "Physical Lab reproducible experimental workspace",
            "research_question": "",
            "created_at": now,
            "updated_at": now,
            "profiles": [],
            "experiments": {},
            "jobs": {},
            "results": {},
            "reports": [],
            "migration": {"current_version": PROJECT_VERSION, "history": []},
            "boundary": "Project metadata and provenance index only. Scientific validity remains governed by each experiment, solver, measurement and V&V record; project membership does not certify a result."
        }),
    )?;
    write_json(
        &dir.join("pipelines/default-measurement-validation.json"),
        &json!({
            "schema": "physical-lab-pipeline-v1",
            "name": "Measurement → Validation",
            "steps": [
                {"id":"measurement","type":"dataset","label":"Measurement dataset","status":"input"},
                {"id":"analysis","type":"results","label":"Statistics / uncertainty","status":"ready"},
                {"id":"validation","type":"validation","label":"Observed vs reference","status":"ready"}
            ],
            "note": "Desktop pipeline metadata only; no simulation result is automatically promoted into canonical Experiment/Result evidence."
        }),
    )?;
    let alias = legacy.join(format!("{id}.physlab"));
    create_alias(&alias, &dir)?;
    summary_from_dir(&alias)
}

#[tauri::command]
pub fn list_workspaces(app: AppHandle) -> Result<Vec<WorkspaceSummary>, String> {
    ensure_all_aliases(&app)?;
    let mut rows = Vec::new();
    for entry in fs::read_dir(legacy_root(&app)?).map_err(|e| e.to_string())?.filter_map(Result::ok) {
        let path = entry.path();
        if path.join("project.json").is_file() {
            if let Ok(summary) = summary_from_dir(&path) {
                rows.push(summary);
            }
        }
    }
    rows.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
    Ok(rows)
}

#[tauri::command]
pub fn open_workspace(app: AppHandle, workspace_id: String) -> Result<String, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    legacy::open_workspace(app, workspace_id)
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
    ensure_alias_for_id(&app, &workspace_id)?;
    let id = legacy::record_run_snapshot(
        app.clone(), workspace_id.clone(), module_id, mode, parameters_json, results_json,
    )?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(id)
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
    ensure_alias_for_id(&app, &workspace_id)?;
    let dataset = legacy::import_measurement_dataset(
        app.clone(), workspace_id.clone(), source_path, name, quantity, unit, sensor, calibration.clone(),
    )?;
    register_desktop_measurement(
        &app,
        &workspace_id,
        &dataset,
        &format!(
            "Registered by Physical Lab desktop Data Bridge. Calibration/note field preserved as user metadata: {}",
            calibration
        ),
    )?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(dataset)
}

#[tauri::command]
pub fn list_datasets(app: AppHandle, workspace_id: String) -> Result<Vec<DatasetSummary>, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    legacy::list_datasets(app, workspace_id)
}

#[tauri::command]
pub fn list_serial_devices() -> Result<Vec<String>, String> {
    legacy::list_serial_devices()
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
    ensure_alias_for_id(&app, &workspace_id)?;
    let dataset = legacy::capture_serial_measurement(
        app.clone(), workspace_id.clone(), device, baud, seconds, name, quantity, unit, sensor,
    )?;
    register_desktop_measurement(
        &app,
        &workspace_id,
        &dataset,
        &format!("Serial capture recorded by desktop Data Bridge at {baud} baud for {} s.", seconds.clamp(1, 300)),
    )?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(dataset)
}

#[tauri::command]
pub fn analyze_dataset(app: AppHandle, workspace_id: String, dataset_id: String) -> Result<Vec<ColumnStats>, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    legacy::analyze_dataset(app, workspace_id, dataset_id)
}

#[tauri::command]
pub fn validate_dataset_columns(
    app: AppHandle,
    workspace_id: String,
    dataset_id: String,
    observed_column: String,
    reference_column: String,
) -> Result<ValidationResult, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    legacy::validate_dataset_columns(app, workspace_id, dataset_id, observed_column, reference_column)
}

#[tauri::command]
pub fn lab_compatibility_matrix(app: AppHandle) -> Result<Vec<CompatibilityRow>, String> {
    legacy::lab_compatibility_matrix(app)
}

#[tauri::command]
pub fn repair_lab_environment(app: AppHandle, module_id: String) -> Result<String, String> {
    legacy::repair_lab_environment(app, module_id)
}

#[tauri::command]
pub fn scientific_smoke_tests(app: AppHandle) -> Result<Vec<SmokeResult>, String> {
    legacy::scientific_smoke_tests(app)
}

#[tauri::command]
pub fn pipeline_templates() -> Vec<Value> {
    legacy::pipeline_templates()
}

#[tauri::command]
pub fn save_pipeline(app: AppHandle, workspace_id: String, kind: String) -> Result<String, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    let id = legacy::save_pipeline(app.clone(), workspace_id.clone(), kind)?;
    touch_canonical_after_write(&app, &workspace_id)?;
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
    ensure_alias_for_id(&app, &workspace_id)?;
    let id = legacy::create_campaign(
        app.clone(), workspace_id.clone(), module_id, parameter, start, stop, points, max_parallel,
    )?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(id)
}

#[tauri::command]
pub fn adapter_statuses(app: AppHandle) -> Result<Vec<AdapterStatus>, String> {
    legacy::adapter_statuses(app)
}

#[tauri::command]
pub fn export_reproducibility_package(app: AppHandle, workspace_id: String) -> Result<String, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    let path = legacy::export_reproducibility_package(app.clone(), workspace_id.clone())?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(path)
}

#[tauri::command]
pub fn list_run_snapshots(app: AppHandle, workspace_id: String) -> Result<Vec<Value>, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    legacy::list_run_snapshots(app, workspace_id)
}

#[tauri::command]
pub fn compare_run_snapshots(
    app: AppHandle,
    workspace_id: String,
    run_a: String,
    run_b: String,
) -> Result<Value, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    legacy::compare_run_snapshots(app, workspace_id, run_a, run_b)
}

#[tauri::command]
pub fn list_campaigns(app: AppHandle, workspace_id: String) -> Result<Vec<Value>, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    legacy::list_campaigns(app, workspace_id)
}

#[tauri::command]
pub fn campaign_action(
    app: AppHandle,
    workspace_id: String,
    campaign_id: String,
    action: String,
) -> Result<Value, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    let value = legacy::campaign_action(app.clone(), workspace_id.clone(), campaign_id, action)?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(value)
}
