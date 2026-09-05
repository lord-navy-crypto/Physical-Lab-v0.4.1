//! Canonical desktop research facade for Physical Lab.
//!
//! New desktop projects live under the canonical `projects/*.physlab` Project
//! Kernel used by Experiment / Measurement / Evidence tooling. Read-only desktop
//! surfaces resolve canonical projects directly and never create compatibility
//! aliases. The pre-cutover research implementation is frozen in
//! `research_legacy_impl.rs`; write/computation paths that still delegate to that
//! implementation create an on-demand `workspaces/*.physlab` symlink only during
//! the compatibility period.
//!
//! Existing real legacy workspaces are never replaced or rewritten. They remain
//! readable as a fallback until explicit migration/retirement is complete.
//!
//! Self-check marker: legacy requirement evaluation still uses SpecifierSet in
//! `research_legacy_impl.rs`; this facade does not duplicate that logic.

#[path = "research_legacy_impl.rs"]
mod legacy;

use chrono::Local;
use serde_json::{json, Value};
use std::{
    collections::{HashMap, HashSet},
    fs,
    io::{BufRead, BufReader},
    path::{Path, PathBuf},
    process::Command,
};
use tauri::{AppHandle, Manager};

pub use legacy::{
    AdapterStatus, ColumnStats, CompatibilityRow, DatasetSummary, SmokeResult, ValidationResult,
    WorkspaceSummary,
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

fn legacy_root_path(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app_root(app)?.join("workspaces"))
}

fn legacy_root(app: &AppHandle) -> Result<PathBuf, String> {
    let path = legacy_root_path(app)?;
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
    let trim: &[_] = &['-', '.', '_'];
    let out = out.trim_matches(trim).to_string();
    if out.is_empty() {
        "project".into()
    } else {
        out
    }
}

fn now_iso() -> String {
    Local::now().to_rfc3339()
}

fn read_json(path: &Path) -> Result<Value, String> {
    serde_json::from_str(&fs::read_to_string(path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())
}

fn write_json(path: &Path, value: &Value) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let tmp = path.with_extension("tmp");
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
        .map(|it| it.filter_map(Result::ok).count())
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
        .trim_end_matches(".physlab");
    let id = project
        .get("slug")
        .or_else(|| project.get("id"))
        .and_then(Value::as_str)
        .unwrap_or(fallback)
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

fn canonical_identity_matches(path: &Path, document: &Value, workspace_id: &str) -> bool {
    let wanted = safe_slug(workspace_id);
    let folder = path
        .file_stem()
        .and_then(|value| value.to_str())
        .map(safe_slug)
        .unwrap_or_default();
    let slug = document
        .get("slug")
        .and_then(Value::as_str)
        .map(safe_slug)
        .unwrap_or_default();
    let project_id = document
        .get("project_id")
        .and_then(Value::as_str)
        .map(safe_slug)
        .unwrap_or_default();
    wanted == folder || wanted == slug || wanted == project_id
}

fn canonical_project_dir(app: &AppHandle, workspace_id: &str) -> Result<Option<PathBuf>, String> {
    let root = canonical_root(app)?;
    let direct = root.join(format!("{}.physlab", safe_slug(workspace_id)));
    if direct.join("project.json").is_file() {
        if let Ok(document) = read_json(&direct.join("project.json")) {
            if is_canonical(&document)
                && canonical_identity_matches(&direct, &document, workspace_id)
            {
                return Ok(Some(direct));
            }
        }
    }
    for entry in fs::read_dir(&root)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        let path = entry.path();
        if !path.is_dir() || !path.join("project.json").is_file() {
            continue;
        }
        let document = match read_json(&path.join("project.json")) {
            Ok(value) => value,
            Err(_) => continue,
        };
        if is_canonical(&document) && canonical_identity_matches(&path, &document, workspace_id) {
            return Ok(Some(path));
        }
    }
    Ok(None)
}

fn is_compatibility_alias(path: &Path) -> bool {
    fs::symlink_metadata(path)
        .map(|metadata| metadata.file_type().is_symlink())
        .unwrap_or(false)
}

fn legacy_project_dir(app: &AppHandle, workspace_id: &str) -> Result<Option<PathBuf>, String> {
    let root = legacy_root_path(app)?;
    if !root.is_dir() {
        return Ok(None);
    }
    let direct = root.join(format!("{}.physlab", safe_slug(workspace_id)));
    if direct.join("project.json").is_file() && !is_compatibility_alias(&direct) {
        return Ok(Some(direct));
    }
    for entry in fs::read_dir(&root)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        let path = entry.path();
        if is_compatibility_alias(&path) || !path.join("project.json").is_file() {
            continue;
        }
        let project = match read_json(&path.join("project.json")) {
            Ok(value) => value,
            Err(_) => continue,
        };
        let fallback = path
            .file_stem()
            .and_then(|value| value.to_str())
            .unwrap_or("project");
        let id = project
            .get("id")
            .or_else(|| project.get("slug"))
            .and_then(Value::as_str)
            .unwrap_or(fallback);
        if safe_slug(id) == safe_slug(workspace_id) {
            return Ok(Some(path));
        }
    }
    Ok(None)
}

fn resolve_project_dir(app: &AppHandle, workspace_id: &str) -> Result<(PathBuf, bool), String> {
    if let Some(path) = canonical_project_dir(app, workspace_id)? {
        return Ok((path, true));
    }
    if let Some(path) = legacy_project_dir(app, workspace_id)? {
        return Ok((path, false));
    }
    Err(format!("Physical Lab project not found: {workspace_id}"))
}

fn open_path(path: &Path) -> Result<(), String> {
    Command::new("/usr/bin/open")
        .arg(path)
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
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
    let Some(canonical) = canonical_project_dir(app, workspace_id)? else {
        return Ok(());
    };
    let alias = legacy_root(app)?.join(format!("{}.physlab", safe_slug(workspace_id)));
    // A real legacy workspace wins during the compatibility period. Never replace
    // it with an alias; the one-way bridge remains the safe migration path.
    if alias.exists() || alias.symlink_metadata().is_ok() {
        return Ok(());
    }
    create_alias(&alias, &canonical)
}

fn touch_canonical_after_write(app: &AppHandle, workspace_id: &str) -> Result<(), String> {
    let Some(project_dir) = canonical_project_dir(app, workspace_id)? else {
        return Ok(());
    };
    let path = project_dir.join("project.json");
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
    let Some(project_dir) = canonical_project_dir(app, workspace_id)? else {
        return Ok(());
    };
    let project = read_json(&project_dir.join("project.json"))?;
    if !is_canonical(&project) {
        return Ok(());
    }
    let digest = match dataset.sha256.as_deref() {
        Some(value) if value.len() == 64 => value.to_string(),
        _ => return Ok(()),
    };
    let source = PathBuf::from(&dataset.stored_file);
    if !source.is_file() {
        return Ok(());
    }
    let measurement_id = format!("meas-{}", &digest[..20]);
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
        index = json!({"schema":"physical-lab-measurement-index-v1","measurements":{},"updated_at":null});
    }
    let registered_at = index
        .get("measurements")
        .and_then(|value| value.get(&measurement_id))
        .and_then(|value| value.get("registered_at"))
        .and_then(Value::as_str)
        .map(str::to_string)
        .unwrap_or_else(now_iso);
    let relative_asset = asset
        .strip_prefix(&project_dir)
        .unwrap_or(&asset)
        .to_string_lossy()
        .replace('\\', "/");
    let record = json!({
        "schema":"physical-lab-measurement-v1",
        "measurement_id":measurement_id,
        "project_id":project.get("project_id").and_then(Value::as_str).unwrap_or(""),
        "profile":"desktop-data-bridge",
        "source_type":"desktop-data-bridge",
        "file_name":filename,
        "asset_path":relative_asset,
        "format":dataset.format,
        "size_bytes":source.metadata().map(|m| m.len()).unwrap_or(0),
        "sha256":digest,
        "instrument":dataset.sensor,
        "quantity":dataset.quantity,
        "unit":dataset.unit,
        "captured_at":dataset.created_at,
        "registered_at":registered_at,
        "notes":note,
        "preview":{"format":dataset.format,"preview":"Desktop Data Bridge asset; content is fingerprinted and interpretation remains with the selected Lab reader."},
        "boundary":"Desktop measurement evidence with file-integrity provenance only. Calibration status, sensor accuracy, traceability and experimental validation must be established separately."
    });
    write_json(&measurement_dir.join("measurement.json"), &record)?;
    if index
        .get("measurements")
        .and_then(Value::as_object)
        .is_none()
    {
        index["measurements"] = json!({});
    }
    let key = record
        .get("measurement_id")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    if let Some(rows) = index.get_mut("measurements").and_then(Value::as_object_mut) {
        rows.insert(key, record);
    }
    index["updated_at"] = Value::String(now_iso());
    write_json(&index_path, &index)
}

fn list_datasets_from_dir(project_dir: &Path) -> Result<Vec<DatasetSummary>, String> {
    let root = project_dir.join("datasets");
    if !root.is_dir() {
        return Ok(Vec::new());
    }
    let mut output = Vec::new();
    for entry in fs::read_dir(root)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        let meta_path = entry.path().join("metadata.json");
        if !meta_path.is_file() {
            continue;
        }
        let value = match read_json(&meta_path) {
            Ok(value) => value,
            Err(_) => continue,
        };
        output.push(DatasetSummary {
            id: value
                .get("id")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            name: value
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            quantity: value
                .get("quantity")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            unit: value
                .get("unit")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            sensor: value
                .get("sensor")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            format: value
                .get("format")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            source_file: value
                .get("sourceFile")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            stored_file: value
                .get("storedFile")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
            sha256: value
                .get("sha256")
                .and_then(Value::as_str)
                .map(str::to_string),
            created_at: value
                .get("createdAt")
                .or_else(|| value.get("created_at"))
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string(),
        });
    }
    output.sort_by(|a, b| b.created_at.cmp(&a.created_at));
    Ok(output)
}

fn dataset_record_from_dir(
    project_dir: &Path,
    dataset_id: &str,
) -> Result<(PathBuf, Value), String> {
    let root = project_dir.join("datasets");
    if !root.is_dir() {
        return Err(format!("Dataset not found: {dataset_id}"));
    }
    for entry in fs::read_dir(&root)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        let folder = entry.path();
        let meta_path = folder.join("metadata.json");
        if !meta_path.is_file() {
            continue;
        }
        let meta = match read_json(&meta_path) {
            Ok(value) => value,
            Err(_) => continue,
        };
        let stored_id = meta.get("id").and_then(Value::as_str).unwrap_or_else(|| {
            folder
                .file_name()
                .and_then(|value| value.to_str())
                .unwrap_or("")
        });
        if stored_id == dataset_id
            || folder.file_name().and_then(|value| value.to_str()) == Some(dataset_id)
        {
            return Ok((folder, meta));
        }
    }
    Err(format!("Dataset not found: {dataset_id}"))
}

fn dataset_numeric_path(dataset_dir: &Path, meta: &Value) -> Result<PathBuf, String> {
    if let Some(raw) = meta.get("storedFile").and_then(Value::as_str) {
        let stored = PathBuf::from(raw);
        if stored.is_file() {
            return Ok(stored);
        }
    }
    let format = meta
        .get("format")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_ascii_lowercase();
    if !format.is_empty() {
        let conventional = dataset_dir.join(format!("data.{format}"));
        if conventional.is_file() {
            return Ok(conventional);
        }
    }
    for entry in fs::read_dir(dataset_dir)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        let path = entry.path();
        if path.is_file()
            && path.file_name().and_then(|value| value.to_str()) != Some("metadata.json")
        {
            return Ok(path);
        }
    }
    Err("Dataset path missing".into())
}

fn parse_csv_numeric(path: &Path) -> Result<(Vec<String>, Vec<Vec<Option<f64>>>), String> {
    let file = fs::File::open(path).map_err(|e| e.to_string())?;
    let mut lines = BufReader::new(file).lines();
    let header = lines
        .next()
        .ok_or("Dataset is empty")?
        .map_err(|e| e.to_string())?;
    let sep = if header.contains('\t') { '\t' } else { ',' };
    let headers: Vec<String> = header
        .split(sep)
        .map(|value| value.trim().trim_matches('"').to_string())
        .collect();
    let mut cols = vec![Vec::<Option<f64>>::new(); headers.len()];
    for line in lines.take(200_000) {
        let line = line.map_err(|e| e.to_string())?;
        for (index, raw) in line.split(sep).enumerate().take(cols.len()) {
            cols[index].push(raw.trim().trim_matches('"').parse::<f64>().ok());
        }
    }
    Ok((headers, cols))
}

fn analyze_dataset_from_dir(
    project_dir: &Path,
    dataset_id: &str,
) -> Result<Vec<ColumnStats>, String> {
    let (dataset_dir, meta) = dataset_record_from_dir(project_dir, dataset_id)?;
    let format = meta
        .get("format")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_ascii_lowercase();
    if format != "csv" && format != "tsv" {
        return Err("Numeric Result Center currently analyzes CSV/TSV directly; JSON/HDF5 remain preserved for Lab-specific readers.".into());
    }
    let path = dataset_numeric_path(&dataset_dir, &meta)?;
    let (headers, cols) = parse_csv_numeric(&path)?;
    let mut out = Vec::new();
    for (header, column) in headers.into_iter().zip(cols.into_iter()) {
        let values: Vec<f64> = column
            .into_iter()
            .flatten()
            .filter(|value| value.is_finite())
            .collect();
        if values.is_empty() {
            continue;
        }
        let n = values.len();
        let mean = values.iter().sum::<f64>() / n as f64;
        let variance = if n > 1 {
            values
                .iter()
                .map(|value| (value - mean) * (value - mean))
                .sum::<f64>()
                / (n - 1) as f64
        } else {
            0.0
        };
        let std_dev = variance.sqrt();
        let half = if n > 1 {
            1.96 * std_dev / (n as f64).sqrt()
        } else {
            0.0
        };
        out.push(ColumnStats {
            column: header,
            n,
            mean,
            std_dev,
            ci95_low: mean - half,
            ci95_high: mean + half,
            min: values.iter().cloned().fold(f64::INFINITY, f64::min),
            max: values.iter().cloned().fold(f64::NEG_INFINITY, f64::max),
        });
    }
    Ok(out)
}

fn validate_dataset_columns_from_dir(
    project_dir: &Path,
    dataset_id: &str,
    observed_column: &str,
    reference_column: &str,
) -> Result<ValidationResult, String> {
    let (dataset_dir, meta) = dataset_record_from_dir(project_dir, dataset_id)?;
    let path = dataset_numeric_path(&dataset_dir, &meta)?;
    let (headers, cols) = parse_csv_numeric(&path)?;
    let observed_index = headers
        .iter()
        .position(|header| header == observed_column)
        .ok_or("Observed column not found")?;
    let reference_index = headers
        .iter()
        .position(|header| header == reference_column)
        .ok_or("Reference column not found")?;
    let pairs: Vec<(f64, f64)> = cols[observed_index]
        .iter()
        .zip(cols[reference_index].iter())
        .filter_map(|(observed, reference)| Some(((*observed)?, (*reference)?)))
        .filter(|(observed, reference)| observed.is_finite() && reference.is_finite())
        .collect();
    if pairs.len() < 2 {
        return Err("Need at least two finite observed/reference pairs.".into());
    }
    let n = pairs.len();
    let mae = pairs
        .iter()
        .map(|(observed, reference)| (observed - reference).abs())
        .sum::<f64>()
        / n as f64;
    let mse = pairs
        .iter()
        .map(|(observed, reference)| (observed - reference) * (observed - reference))
        .sum::<f64>()
        / n as f64;
    let rmse = mse.sqrt();
    let max_abs_error = pairs
        .iter()
        .map(|(observed, reference)| (observed - reference).abs())
        .fold(0.0, f64::max);
    let reference_mean = pairs.iter().map(|(_, reference)| *reference).sum::<f64>() / n as f64;
    let reference_scale = pairs
        .iter()
        .map(|(_, reference)| reference.abs())
        .sum::<f64>()
        / n as f64;
    let relative_rmse = if reference_scale > 1e-15 {
        Some(rmse / reference_scale)
    } else {
        None
    };
    let ss_tot = pairs
        .iter()
        .map(|(_, reference)| (reference - reference_mean) * (reference - reference_mean))
        .sum::<f64>();
    let ss_res = pairs
        .iter()
        .map(|(observed, reference)| (observed - reference) * (observed - reference))
        .sum::<f64>();
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
    Ok(ValidationResult {
        n,
        mae,
        rmse,
        max_abs_error,
        relative_rmse,
        r2,
        agreement,
        notes: vec![
            "Agreement labels are descriptive thresholds, not proof that either model or measurement is correct.".into(),
            "Inspect calibration, uncertainty, discretization and model assumptions before interpreting discrepancies.".into(),
        ],
    })
}

fn list_run_snapshots_from_dir(project_dir: &Path) -> Result<Vec<Value>, String> {
    let root = project_dir.join("runs");
    if !root.is_dir() {
        return Ok(Vec::new());
    }
    let mut output = Vec::new();
    for entry in fs::read_dir(root)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        let path = entry.path().join("run.json");
        if let Ok(value) = read_json(&path) {
            output.push(value);
        }
    }
    output.sort_by(|a, b| {
        b.get("createdAt")
            .or_else(|| b.get("created_at"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .cmp(
                a.get("createdAt")
                    .or_else(|| a.get("created_at"))
                    .and_then(Value::as_str)
                    .unwrap_or(""),
            )
    });
    Ok(output)
}

fn flatten_json(prefix: &str, value: &Value, output: &mut HashMap<String, String>) {
    match value {
        Value::Object(map) => {
            for (key, child) in map {
                let path = if prefix.is_empty() {
                    key.clone()
                } else {
                    format!("{prefix}.{key}")
                };
                flatten_json(&path, child, output);
            }
        }
        Value::Array(values) => {
            output.insert(prefix.into(), format!("[{} items]", values.len()));
        }
        _ => {
            output.insert(prefix.into(), value.to_string());
        }
    }
}

fn compare_run_snapshots_from_dir(
    project_dir: &Path,
    run_a: &str,
    run_b: &str,
) -> Result<Value, String> {
    let base = project_dir.join("runs");
    let a = read_json(&base.join(run_a).join("run.json"))?;
    let b = read_json(&base.join(run_b).join("run.json"))?;
    let mut flat_a = HashMap::new();
    let mut flat_b = HashMap::new();
    flatten_json("", &a, &mut flat_a);
    flatten_json("", &b, &mut flat_b);
    let mut keys: Vec<String> = flat_a.keys().chain(flat_b.keys()).cloned().collect();
    keys.sort();
    keys.dedup();
    let differences: Vec<Value> = keys
        .into_iter()
        .filter_map(|key| {
            let left = flat_a.get(&key);
            let right = flat_b.get(&key);
            if left == right {
                None
            } else {
                Some(json!({"field":key,"a":left,"b":right}))
            }
        })
        .collect();
    let count = differences.len();
    Ok(json!({"runA":run_a,"runB":run_b,"differences":differences,"differenceCount":count}))
}

fn list_campaigns_from_dir(project_dir: &Path) -> Result<Vec<Value>, String> {
    let root = project_dir.join("campaigns");
    if !root.is_dir() {
        return Ok(Vec::new());
    }
    let mut output = Vec::new();
    for entry in fs::read_dir(root)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        let path = entry.path();
        if path.extension().and_then(|value| value.to_str()) != Some("json") {
            continue;
        }
        if let Ok(value) = read_json(&path) {
            output.push(value);
        }
    }
    output.sort_by(|a, b| {
        b.get("createdAt")
            .or_else(|| b.get("created_at"))
            .and_then(Value::as_str)
            .unwrap_or("")
            .cmp(
                a.get("createdAt")
                    .or_else(|| a.get("created_at"))
                    .and_then(Value::as_str)
                    .unwrap_or(""),
            )
    });
    Ok(output)
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
        || legacy
            .join(format!("{id}.physlab"))
            .symlink_metadata()
            .is_ok()
    {
        id = format!("{base}-{n}");
        n += 1;
    }
    let dir = canonical.join(format!("{id}.physlab"));
    for child in [
        "experiments",
        "jobs",
        "results",
        "measurements",
        "calibration",
        "reports",
        "provenance",
        "datasets",
        "runs",
        "figures",
        "exports",
        "pipelines",
        "campaigns",
    ] {
        fs::create_dir_all(dir.join(child)).map_err(|e| e.to_string())?;
    }
    let now = now_iso();
    let project_id = format!("plproj-shell-{}-{}", Local::now().timestamp_micros(), id);
    write_json(
        &dir.join("project.json"),
        &json!({
            "schema":PROJECT_SCHEMA,
            "project_version":PROJECT_VERSION,
            "project_id":project_id,
            "name":name.trim(),
            "slug":id,
            "description":"Physical Lab reproducible experimental workspace",
            "research_question":"",
            "created_at":now,
            "updated_at":now,
            "profiles":[],
            "experiments":{},
            "jobs":{},
            "results":{},
            "reports":[],
            "migration":{"current_version":PROJECT_VERSION,"history":[]},
            "boundary":"Project metadata and provenance index only. Scientific validity remains governed by each experiment, solver, measurement and V&V record; project membership does not certify a result."
        }),
    )?;
    write_json(
        &dir.join("pipelines/default-measurement-validation.json"),
        &json!({
            "schema":"physical-lab-pipeline-v1",
            "name":"Measurement → Validation",
            "steps":[
                {"id":"measurement","type":"dataset","label":"Measurement dataset","status":"input"},
                {"id":"analysis","type":"results","label":"Statistics / uncertainty","status":"ready"},
                {"id":"validation","type":"validation","label":"Observed vs reference","status":"ready"}
            ],
            "note":"Desktop pipeline metadata only; no simulation result is automatically promoted into canonical Experiment/Result evidence."
        }),
    )?;
    let alias = legacy.join(format!("{id}.physlab"));
    create_alias(&alias, &dir)?;
    summary_from_dir(&dir)
}

#[tauri::command]
pub fn list_workspaces(app: AppHandle) -> Result<Vec<WorkspaceSummary>, String> {
    let mut rows = Vec::new();
    let mut seen = HashSet::new();
    for entry in fs::read_dir(canonical_root(&app)?)
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
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
        if let Ok(summary) = summary_from_dir(&path) {
            seen.insert(safe_slug(&summary.id));
            rows.push(summary);
        }
    }
    let legacy = legacy_root_path(&app)?;
    if legacy.is_dir() {
        for entry in fs::read_dir(&legacy)
            .map_err(|e| e.to_string())?
            .filter_map(Result::ok)
        {
            let path = entry.path();
            if is_compatibility_alias(&path) || !path.join("project.json").is_file() {
                continue;
            }
            if let Ok(summary) = summary_from_dir(&path) {
                if seen.insert(safe_slug(&summary.id)) {
                    rows.push(summary);
                }
            }
        }
    }
    rows.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
    Ok(rows)
}

#[tauri::command]
pub fn open_workspace(app: AppHandle, workspace_id: String) -> Result<String, String> {
    let (dir, _) = resolve_project_dir(&app, &workspace_id)?;
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
    ensure_alias_for_id(&app, &workspace_id)?;
    let out = legacy::record_run_snapshot(
        app.clone(),
        workspace_id.clone(),
        module_id,
        mode,
        parameters_json,
        results_json,
    )?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(out)
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
        app.clone(),
        workspace_id.clone(),
        source_path,
        name,
        quantity,
        unit,
        sensor,
        calibration.clone(),
    )?;
    register_desktop_measurement(
        &app,
        &workspace_id,
        &dataset,
        &format!("Registered by Physical Lab desktop Data Bridge. Calibration/note field preserved as user metadata: {calibration}"),
    )?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(dataset)
}

#[tauri::command]
pub fn list_datasets(app: AppHandle, workspace_id: String) -> Result<Vec<DatasetSummary>, String> {
    let (dir, _) = resolve_project_dir(&app, &workspace_id)?;
    list_datasets_from_dir(&dir)
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
        app.clone(),
        workspace_id.clone(),
        device,
        baud,
        seconds,
        name,
        quantity,
        unit,
        sensor,
    )?;
    register_desktop_measurement(
        &app,
        &workspace_id,
        &dataset,
        &format!(
            "Serial capture recorded by desktop Data Bridge at {baud} baud for {} s.",
            seconds.clamp(1, 300)
        ),
    )?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(dataset)
}

#[tauri::command]
pub fn analyze_dataset(
    app: AppHandle,
    workspace_id: String,
    dataset_id: String,
) -> Result<Vec<ColumnStats>, String> {
    let (dir, _) = resolve_project_dir(&app, &workspace_id)?;
    analyze_dataset_from_dir(&dir, &dataset_id)
}

#[tauri::command]
pub fn validate_dataset_columns(
    app: AppHandle,
    workspace_id: String,
    dataset_id: String,
    observed_column: String,
    reference_column: String,
) -> Result<ValidationResult, String> {
    let (dir, _) = resolve_project_dir(&app, &workspace_id)?;
    validate_dataset_columns_from_dir(&dir, &dataset_id, &observed_column, &reference_column)
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
    let out = legacy::save_pipeline(app.clone(), workspace_id.clone(), kind)?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(out)
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
    let out = legacy::create_campaign(
        app.clone(),
        workspace_id.clone(),
        module_id,
        parameter,
        start,
        stop,
        points,
        max_parallel,
    )?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(out)
}

#[tauri::command]
pub fn adapter_statuses(app: AppHandle) -> Result<Vec<AdapterStatus>, String> {
    legacy::adapter_statuses(app)
}

#[tauri::command]
pub fn export_reproducibility_package(
    app: AppHandle,
    workspace_id: String,
) -> Result<String, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    let out = legacy::export_reproducibility_package(app.clone(), workspace_id.clone())?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(out)
}

#[tauri::command]
pub fn list_run_snapshots(app: AppHandle, workspace_id: String) -> Result<Vec<Value>, String> {
    let (dir, _) = resolve_project_dir(&app, &workspace_id)?;
    list_run_snapshots_from_dir(&dir)
}

#[tauri::command]
pub fn compare_run_snapshots(
    app: AppHandle,
    workspace_id: String,
    run_a: String,
    run_b: String,
) -> Result<Value, String> {
    let (dir, _) = resolve_project_dir(&app, &workspace_id)?;
    compare_run_snapshots_from_dir(&dir, &run_a, &run_b)
}

#[tauri::command]
pub fn list_campaigns(app: AppHandle, workspace_id: String) -> Result<Vec<Value>, String> {
    let (dir, _) = resolve_project_dir(&app, &workspace_id)?;
    list_campaigns_from_dir(&dir)
}

#[tauri::command]
pub fn campaign_action(
    app: AppHandle,
    workspace_id: String,
    campaign_id: String,
    action: String,
) -> Result<Value, String> {
    ensure_alias_for_id(&app, &workspace_id)?;
    let out = legacy::campaign_action(app.clone(), workspace_id.clone(), campaign_id, action)?;
    touch_canonical_after_write(&app, &workspace_id)?;
    Ok(out)
}
