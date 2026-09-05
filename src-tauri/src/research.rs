//! Canonical desktop research facade for Physical Lab.
//!
//! New desktop projects live under the canonical `projects/*.physlab` Project
//! Kernel used by Experiment / Measurement / Evidence tooling. Read-only desktop
//! surfaces resolve canonical projects directly and never create compatibility
//! aliases. Non-Project desktop support lives in `research_runtime_support.rs`.
//! The pre-cutover `research_legacy_impl.rs` stays frozen only as a compatibility
//! and regression fixture and is not compiled into the desktop runtime.
//! Project reads/writes resolve canonical projects directly; no compatibility
//! symlink is created or required.
//!
//! Existing real legacy workspaces are never replaced or rewritten. They remain
//! directly readable as a fallback and eligible for the explicit non-destructive
//! Project Kernel bridge.
//!
//! Self-check marker: runtime requirement evaluation uses SpecifierSet in
//! `research_runtime_support.rs`; this facade does not duplicate that logic.

#[path = "research_runtime_support.rs"]
mod runtime_support;

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

pub use runtime_support::{
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

fn sha256_file(path: &Path) -> Option<String> {
    let path_text = path.to_string_lossy().to_string();
    let output = Command::new("/usr/bin/shasum")
        .args(["-a", "256", path_text.as_str()])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    String::from_utf8_lossy(&output.stdout)
        .split_whitespace()
        .next()
        .map(str::to_string)
}

fn import_measurement_dataset_to_dir(
    project_dir: &Path,
    canonical: bool,
    source_path: &str,
    name: &str,
    quantity: &str,
    unit: &str,
    sensor: &str,
    calibration: &str,
) -> Result<DatasetSummary, String> {
    let source = PathBuf::from(source_path.trim());
    if !source.is_file() {
        return Err(format!(
            "Measurement file does not exist: {}",
            source.display()
        ));
    }
    let extension = source
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if !["csv", "tsv", "json", "h5", "hdf5"].contains(&extension.as_str()) {
        return Err("Supported measurement formats: CSV, TSV, JSON, HDF5".into());
    }
    let dataset_id = format!(
        "{}-{}",
        safe_slug(name),
        Local::now().format("%Y%m%d-%H%M%S")
    );
    let dataset_dir = project_dir.join("datasets").join(&dataset_id);
    fs::create_dir_all(&dataset_dir).map_err(|e| e.to_string())?;
    let stored = dataset_dir.join(format!("data.{extension}"));
    fs::copy(&source, &stored).map_err(|e| e.to_string())?;
    let digest = sha256_file(&stored);
    let created_at = now_iso();
    write_json(
        &dataset_dir.join("metadata.json"),
        &json!({
            "schema":"physical-lab-dataset-v1",
            "id":&dataset_id,
            "name":name,
            "quantity":quantity,
            "unit":unit,
            "sensor":sensor,
            "calibration":calibration,
            "format":&extension,
            "sourceFile":source.to_string_lossy(),
            "storedFile":stored.to_string_lossy(),
            "sha256":&digest,
            "createdAt":&created_at,
            "measurement":true
        }),
    )?;
    touch_project_after_direct_write(project_dir, canonical)?;
    Ok(DatasetSummary {
        id: dataset_id,
        name: name.to_string(),
        quantity: quantity.to_string(),
        unit: unit.to_string(),
        sensor: sensor.to_string(),
        format: extension,
        source_file: source.to_string_lossy().to_string(),
        stored_file: stored.to_string_lossy().to_string(),
        sha256: digest,
        created_at,
    })
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

fn modules_root_for_research(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app_root(app)?.join("modules"))
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

fn touch_project_after_direct_write(project_dir: &Path, canonical: bool) -> Result<(), String> {
    let path = project_dir.join("project.json");
    let mut project = read_json(&path)?;
    if canonical && is_canonical(&project) {
        project["updated_at"] = Value::String(now_iso());
        if let Some(object) = project.as_object_mut() {
            object.remove("updatedAt");
        }
    } else {
        project["updatedAt"] = Value::String(now_iso());
    }
    write_json(&path, &project)
}

fn pipeline_template_value(kind: &str) -> Value {
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
        _ => json!({"schema":"physical-lab-pipeline-v1","name":"Measurement → Validation","steps":[
            {"id":"measurement","type":"dataset","label":"Measurement dataset","status":"input"},
            {"id":"analysis","type":"results","label":"Statistics / uncertainty","status":"ready"},
            {"id":"validation","type":"validation","label":"Observed vs reference","status":"ready"}
        ]}),
    }
}

fn record_run_snapshot_to_dir(
    app: &AppHandle,
    project_dir: &Path,
    canonical: bool,
    module_id: &str,
    mode: &str,
    parameters_json: String,
    results_json: String,
) -> Result<String, String> {
    let ts = format!(
        "{}-{}",
        Local::now().format("%Y%m%d-%H%M%S"),
        Local::now().timestamp_subsec_millis()
    );
    let id = format!("{}-{}", safe_slug(module_id), ts);
    let run_dir = project_dir.join("runs").join(&id);
    fs::create_dir_all(&run_dir).map_err(|e| e.to_string())?;
    let parameters: Value =
        serde_json::from_str(&parameters_json).unwrap_or_else(|_| json!({"raw":parameters_json}));
    let results: Value =
        serde_json::from_str(&results_json).unwrap_or_else(|_| json!({"raw":results_json}));
    let module_dir = modules_root_for_research(app)?.join(module_id);
    let source = module_dir.join("source");
    let source_commit = if source.exists() {
        command_text_in(&source, "git", &["rev-parse", "HEAD"])
    } else {
        None
    };
    let python_path = module_dir.join(".venv/bin/python");
    let python = if python_path.exists() {
        command_text(python_path.to_string_lossy().as_ref(), &["--version"])
    } else {
        None
    };
    let pip_freeze = if python_path.exists() {
        command_text(
            python_path.to_string_lossy().as_ref(),
            &["-m", "pip", "freeze", "--all"],
        )
    } else {
        None
    };
    write_json(
        &run_dir.join("run.json"),
        &json!({
            "schema":"physical-lab-run-v1",
            "id":&id,
            "createdAt":now_iso(),
            "moduleId":module_id,
            "mode":mode,
            "parameters":parameters,
            "results":results,
            "provenance":{"sourceCommit":source_commit,"python":python,"pipFreeze":pip_freeze}
        }),
    )?;
    touch_project_after_direct_write(project_dir, canonical)?;
    Ok(id)
}

fn save_pipeline_to_dir(project_dir: &Path, canonical: bool, kind: &str) -> Result<String, String> {
    let value = pipeline_template_value(kind);
    let id = format!(
        "{}-{}",
        safe_slug(kind),
        Local::now().format("%Y%m%d-%H%M%S")
    );
    write_json(
        &project_dir.join("pipelines").join(format!("{id}.json")),
        &value,
    )?;
    touch_project_after_direct_write(project_dir, canonical)?;
    Ok(id)
}

fn research_lab_id_name_pairs() -> Result<Vec<(String, String)>, String> {
    let all: Vec<Value> = serde_json::from_str(include_str!("../resources/modules.json"))
        .map_err(|e| e.to_string())?;
    Ok(all
        .into_iter()
        .filter(|value| value.get("kind").and_then(Value::as_str) == Some("lab"))
        .filter_map(|value| {
            let id = value.get("id")?.as_str()?.to_string();
            let name = value.get("name")?.as_str()?.to_string();
            Some((id, name))
        })
        .collect())
}

fn export_reproducibility_package_from_dir(
    app: &AppHandle,
    project_dir: &Path,
    workspace_id: &str,
) -> Result<String, String> {
    let provenance = project_dir.join("provenance");
    fs::create_dir_all(&provenance).map_err(|e| e.to_string())?;
    let mut modules = Vec::new();
    let modules_root = modules_root_for_research(app)?;
    for (id, name) in research_lab_id_name_pairs()? {
        let module_dir = modules_root.join(&id);
        let source = module_dir.join("source");
        let python_path = module_dir.join(".venv/bin/python");
        modules.push(json!({
            "id":id,
            "name":name,
            "sourceCommit":if source.exists(){command_text_in(&source,"git",&["rev-parse","HEAD"])}else{None},
            "python":if python_path.exists(){command_text(python_path.to_string_lossy().as_ref(), &["--version"])}else{None},
            "pipFreeze":if python_path.exists(){command_text(python_path.to_string_lossy().as_ref(), &["-m","pip","freeze","--all"])}else{None}
        }));
    }
    write_json(
        &provenance.join("environment.json"),
        &json!({
            "createdAt":now_iso(),
            "machine":{
                "arch":command_text("uname", &["-m"]),
                "os":command_text("sw_vers", &["-productVersion"]),
                "build":command_text("sw_vers", &["-buildVersion"])
            },
            "modules":modules
        }),
    )?;
    let export_dir = app_root(app)?.join("exports");
    fs::create_dir_all(&export_dir).map_err(|e| e.to_string())?;
    let output = export_dir.join(format!(
        "{}-reproducible-{}.zip",
        safe_slug(workspace_id),
        Local::now().format("%Y%m%d-%H%M%S")
    ));
    let project_text = project_dir.to_string_lossy().to_string();
    let output_text = output.to_string_lossy().to_string();
    let base_name = project_dir
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("workspace")
        .to_string();
    let status = Command::new("/usr/bin/ditto")
        .args([
            "-c",
            "-k",
            "--sequesterRsrc",
            "--keepParent",
            project_text.as_str(),
            output_text.as_str(),
        ])
        .status()
        .or_else(|_| {
            Command::new("/usr/bin/zip")
                .current_dir(project_dir.parent().unwrap_or(project_dir))
                .args(["-r", output_text.as_str(), base_name.as_str()])
                .status()
        })
        .map_err(|e| e.to_string())?;
    if !status.success() {
        return Err("Reproducibility archive creation failed".into());
    }
    Ok(output.to_string_lossy().to_string())
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

fn create_campaign_to_dir(
    project_dir: &Path,
    canonical: bool,
    module_id: &str,
    parameter: &str,
    start: f64,
    stop: f64,
    points: u32,
    max_parallel: u32,
) -> Result<String, String> {
    if points < 2 || points > 10_000 {
        return Err("Campaign points must be between 2 and 10000.".into());
    }
    let id = format!(
        "{}-campaign-{}",
        safe_slug(module_id),
        Local::now().format("%Y%m%d-%H%M%S")
    );
    let values: Vec<f64> = (0..points)
        .map(|index| start + (stop - start) * (index as f64) / ((points - 1) as f64))
        .collect();
    let jobs: Vec<Value> = values
        .iter()
        .enumerate()
        .map(|(index, value)| {
            json!({
                "id":format!("run-{:04}", index + 1),
                "parameter":parameter,
                "value":value,
                "status":"queued"
            })
        })
        .collect();
    write_json(
        &project_dir.join("campaigns").join(format!("{id}.json")),
        &json!({
            "schema":"physical-lab-campaign-v1",
            "id":&id,
            "createdAt":now_iso(),
            "moduleId":module_id,
            "parameter":parameter,
            "start":start,
            "stop":stop,
            "points":points,
            "maxParallel":max_parallel.clamp(1, 8),
            "queueState":"ready",
            "jobs":jobs,
            "execution":"queue-and-handoff",
            "note":"Campaign parameters are persisted reproducibly. Current Lab UIs remain solver owners until module-specific parameter adapters are added."
        }),
    )?;
    touch_project_after_direct_write(project_dir, canonical)?;
    Ok(id)
}

fn campaign_action_in_dir(
    project_dir: &Path,
    canonical: bool,
    campaign_id: &str,
    action: &str,
) -> Result<Value, String> {
    let path = project_dir
        .join("campaigns")
        .join(format!("{campaign_id}.json"));
    let mut value = read_json(&path)?;
    match action {
        "pause" => value["queueState"] = Value::String("paused".into()),
        "resume" => value["queueState"] = Value::String("ready".into()),
        "retry-failed" => {
            if let Some(jobs) = value.get_mut("jobs").and_then(Value::as_array_mut) {
                for job in jobs {
                    if job.get("status").and_then(Value::as_str) == Some("failed") {
                        job["status"] = Value::String("queued".into());
                    }
                }
            }
        }
        "reset" => {
            if let Some(jobs) = value.get_mut("jobs").and_then(Value::as_array_mut) {
                for job in jobs {
                    job["status"] = Value::String("queued".into());
                }
            }
        }
        _ => return Err("Supported campaign actions: pause, resume, retry-failed, reset".into()),
    }
    value["updatedAt"] = Value::String(now_iso());
    write_json(&path, &value)?;
    if canonical {
        touch_project_after_direct_write(project_dir, true)?;
    }
    Ok(value)
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

fn capture_serial_measurement_to_dir(
    app: &AppHandle,
    project_dir: &Path,
    canonical: bool,
    device: &str,
    baud: u32,
    seconds: u64,
    name: &str,
    quantity: &str,
    unit: &str,
    sensor: &str,
) -> Result<DatasetSummary, String> {
    if !device.starts_with("/dev/cu.") && !device.starts_with("/dev/tty.") {
        return Err("Only macOS serial devices under /dev/cu.* or /dev/tty.* are accepted.".into());
    }
    if !Path::new(device).exists() {
        return Err("Serial device not found.".into());
    }
    let secs = seconds.clamp(1, 300);
    let baud_text = baud.to_string();
    let _ = Command::new("/bin/stty")
        .args(["-f", device, baud_text.as_str(), "raw", "-echo"])
        .status();
    let temporary = app_root(app)?.join(format!("serial-{}.csv", Local::now().timestamp_millis()));
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
    let python = command_text("/usr/bin/which", &["python3"])
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "python3".into());
    let secs_text = secs.to_string();
    let temporary_text = temporary.to_string_lossy().to_string();
    let status = Command::new(python.trim())
        .args([
            "-c",
            code,
            device,
            secs_text.as_str(),
            temporary_text.as_str(),
        ])
        .status()
        .map_err(|e| e.to_string())?;
    if !status.success() {
        let _ = fs::remove_file(&temporary);
        return Err("Serial capture failed. Check device permissions and baud rate.".into());
    }
    let result = import_measurement_dataset_to_dir(
        project_dir,
        canonical,
        temporary.to_string_lossy().as_ref(),
        name,
        quantity,
        unit,
        sensor,
        &format!("Serial capture at {baud} baud for {secs}s"),
    );
    let _ = fs::remove_file(&temporary);
    result
}

fn save_model_builder_bundle_to_dir(
    app: &AppHandle,
    workspace_id: &str,
    bundle_path: &str,
) -> Result<Value, String> {
    let (project_dir, canonical) = resolve_project_dir(app, workspace_id)?;
    if !canonical {
        return Err("Research Model Builder saves only to canonical .physlab Projects. Migrate the legacy workspace first.".into());
    }
    let allowed_root = app_root(app)?.join("model-builder").join("bundles");
    let allowed_root = allowed_root.canonicalize().map_err(|e| e.to_string())?;
    let source = PathBuf::from(bundle_path)
        .canonicalize()
        .map_err(|e| e.to_string())?;
    if !source.is_dir() || !source.starts_with(&allowed_root) {
        return Err("Only bundles generated by this Physical Lab Model Builder can be saved to a Project.".into());
    }
    let provenance = read_json(&source.join("provenance.json"))?;
    if provenance.get("schema").and_then(Value::as_str) != Some("physical-lab-model-bundle-v1") {
        return Err("Model bundle provenance schema is invalid.".into());
    }
    let model_spec = read_json(&source.join("model.json"))?;
    if model_spec.get("schema").and_then(Value::as_str) != Some("physical-lab-model-spec-v1") {
        return Err("Model bundle ModelSpec schema is invalid.".into());
    }
    let bundle_id = provenance
        .get("bundle_id")
        .and_then(Value::as_str)
        .map(safe_slug)
        .filter(|value| !value.is_empty())
        .ok_or("Model bundle id is missing")?;
    let destination = project_dir.join("models").join(&bundle_id);
    fs::create_dir_all(&destination).map_err(|e| e.to_string())?;
    for filename in [
        "original_model.py",
        "adapter.py",
        "model.json",
        "ui.json",
        "tests.json",
        "provenance.json",
    ] {
        let input = source.join(filename);
        if !input.is_file() {
            return Err(format!("Generated model bundle is missing {filename}"));
        }
        fs::copy(&input, destination.join(filename)).map_err(|e| e.to_string())?;
    }
    let project = read_json(&project_dir.join("project.json"))?;
    let record = json!({
        "schema":"physical-lab-research-model-v1",
        "bundle_id":bundle_id,
        "project_id":project.get("project_id").and_then(Value::as_str).unwrap_or(""),
        "name":model_spec.get("metadata").and_then(|value| value.get("name")).and_then(Value::as_str).unwrap_or("Research Model"),
        "description":model_spec.get("metadata").and_then(|value| value.get("description")).and_then(Value::as_str).unwrap_or(""),
        "entry_function":model_spec.get("compute").and_then(|value| value.get("entry_function")).and_then(Value::as_str).unwrap_or(""),
        "source_sha256":provenance.get("source_sha256"),
        "adapter_sha256":provenance.get("adapter_sha256"),
        "model_spec_sha256":provenance.get("model_spec_sha256"),
        "stored_path":format!("models/{bundle_id}"),
        "registered_at":now_iso(),
        "generation_policy":"wrapper-not-rewrite",
        "boundary":"Project membership records provenance and a reviewable model bundle. It does not establish scientific validity, experimental validation, safety, compliance or certification."
    });
    let index_path = project_dir.join("models").join("index.json");
    let mut index = if index_path.is_file() {
        read_json(&index_path).unwrap_or_else(|_| json!({}))
    } else {
        json!({})
    };
    if index.get("schema").and_then(Value::as_str) != Some("physical-lab-model-index-v1") {
        index = json!({"schema":"physical-lab-model-index-v1","models":{},"updated_at":null});
    }
    if index.get("models").and_then(Value::as_object).is_none() {
        index["models"] = json!({});
    }
    if let Some(rows) = index.get_mut("models").and_then(Value::as_object_mut) {
        rows.insert(bundle_id.clone(), record.clone());
    }
    index["updated_at"] = Value::String(now_iso());
    write_json(&index_path, &index)?;
    touch_project_after_direct_write(&project_dir, true)?;
    Ok(record)
}

#[tauri::command]
pub fn save_model_builder_bundle(
    app: AppHandle,
    workspace_id: String,
    bundle_path: String,
) -> Result<Value, String> {
    save_model_builder_bundle_to_dir(&app, &workspace_id, &bundle_path)
}

#[tauri::command]
pub fn create_workspace(app: AppHandle, name: String) -> Result<WorkspaceSummary, String> {
    let base = safe_slug(&name);
    let canonical = canonical_root(&app)?;
    let legacy = legacy_root_path(&app)?;
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
        "models",
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
    let (dir, canonical) = resolve_project_dir(&app, &workspace_id)?;
    record_run_snapshot_to_dir(
        &app,
        &dir,
        canonical,
        &module_id,
        &mode,
        parameters_json,
        results_json,
    )
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
    let (dir, canonical) = resolve_project_dir(&app, &workspace_id)?;
    let dataset = import_measurement_dataset_to_dir(
        &dir,
        canonical,
        &source_path,
        &name,
        &quantity,
        &unit,
        &sensor,
        &calibration,
    )?;
    if canonical {
        register_desktop_measurement(
            &app,
            &workspace_id,
            &dataset,
            &format!(
                "Registered by Physical Lab desktop Data Bridge. Calibration/note field preserved as user metadata: {calibration}"
            ),
        )?;
    }
    Ok(dataset)
}

#[tauri::command]
pub fn list_datasets(app: AppHandle, workspace_id: String) -> Result<Vec<DatasetSummary>, String> {
    let (dir, _) = resolve_project_dir(&app, &workspace_id)?;
    list_datasets_from_dir(&dir)
}

#[tauri::command]
pub fn list_serial_devices() -> Result<Vec<String>, String> {
    let mut output = Vec::new();
    for entry in fs::read_dir("/dev")
        .map_err(|e| e.to_string())?
        .filter_map(Result::ok)
    {
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with("cu.") || name.starts_with("tty.") {
            output.push(format!("/dev/{name}"));
        }
    }
    output.sort();
    Ok(output)
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
    let (dir, canonical) = resolve_project_dir(&app, &workspace_id)?;
    let secs = seconds.clamp(1, 300);
    let dataset = capture_serial_measurement_to_dir(
        &app, &dir, canonical, &device, baud, seconds, &name, &quantity, &unit, &sensor,
    )?;
    if canonical {
        register_desktop_measurement(
            &app,
            &workspace_id,
            &dataset,
            &format!("Serial capture recorded by desktop Data Bridge at {baud} baud for {secs} s."),
        )?;
        touch_project_after_direct_write(&dir, true)?;
    }
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
    runtime_support::lab_compatibility_matrix(app)
}

#[tauri::command]
pub fn repair_lab_environment(app: AppHandle, module_id: String) -> Result<String, String> {
    runtime_support::repair_lab_environment(app, module_id)
}

#[tauri::command]
pub fn scientific_smoke_tests(app: AppHandle) -> Result<Vec<SmokeResult>, String> {
    runtime_support::scientific_smoke_tests(app)
}

#[tauri::command]
pub fn pipeline_templates() -> Vec<Value> {
    vec![
        pipeline_template_value("accelerator-measurement"),
        pipeline_template_value("oscillation-modal"),
        pipeline_template_value("atomistic-magnetism"),
        pipeline_template_value("measurement-validation"),
    ]
}

#[tauri::command]
pub fn save_pipeline(app: AppHandle, workspace_id: String, kind: String) -> Result<String, String> {
    let (dir, canonical) = resolve_project_dir(&app, &workspace_id)?;
    save_pipeline_to_dir(&dir, canonical, &kind)
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
    let (dir, canonical) = resolve_project_dir(&app, &workspace_id)?;
    create_campaign_to_dir(
        &dir,
        canonical,
        &module_id,
        &parameter,
        start,
        stop,
        points,
        max_parallel,
    )
}

#[tauri::command]
pub fn adapter_statuses(app: AppHandle) -> Result<Vec<AdapterStatus>, String> {
    runtime_support::adapter_statuses(app)
}

#[tauri::command]
pub fn export_reproducibility_package(
    app: AppHandle,
    workspace_id: String,
) -> Result<String, String> {
    let (dir, _) = resolve_project_dir(&app, &workspace_id)?;
    export_reproducibility_package_from_dir(&app, &dir, &workspace_id)
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
    let (dir, canonical) = resolve_project_dir(&app, &workspace_id)?;
    campaign_action_in_dir(&dir, canonical, &campaign_id, &action)
}
