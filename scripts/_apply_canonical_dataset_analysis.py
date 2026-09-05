#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "src-tauri/src/research.rs"
READ_VALIDATION = ROOT / "scripts/rust_canonical_read_paths_validation.py"
NEW_VALIDATION = ROOT / "scripts/rust_canonical_dataset_analysis_validation.py"
WORKFLOW = ROOT / ".github/workflows/source-integrity.yml"


def replace_rust_fn(text: str, name: str, replacement: str) -> str:
    marker = f"pub fn {name}("
    start = text.index(marker)
    attr = text.rfind("#[tauri::command]", 0, start)
    if attr < 0:
        raise RuntimeError(f"missing tauri attribute for {name}")
    brace = text.index("{", start)
    depth = 0
    end = None
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise RuntimeError(f"unterminated Rust function: {name}")
    return text[:attr] + replacement.rstrip() + "\n" + text[end:]


text = RESEARCH.read_text(encoding="utf-8")
if "io::{BufRead, BufReader}," not in text:
    text = text.replace(
        "    fs,\n    path::{Path, PathBuf},",
        "    fs,\n    io::{BufRead, BufReader},\n    path::{Path, PathBuf},",
        1,
    )

helper_marker = "fn dataset_record_from_dir("
if helper_marker not in text:
    insertion = r'''
fn dataset_record_from_dir(project_dir: &Path, dataset_id: &str) -> Result<(PathBuf, Value), String> {
    let root = project_dir.join("datasets");
    if !root.is_dir() {
        return Err(format!("Dataset not found: {dataset_id}"));
    }
    for entry in fs::read_dir(&root).map_err(|e| e.to_string())?.filter_map(Result::ok) {
        let folder = entry.path();
        let meta_path = folder.join("metadata.json");
        if !meta_path.is_file() {
            continue;
        }
        let meta = match read_json(&meta_path) {
            Ok(value) => value,
            Err(_) => continue,
        };
        let stored_id = meta
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or_else(|| folder.file_name().and_then(|value| value.to_str()).unwrap_or(""));
        if stored_id == dataset_id || folder.file_name().and_then(|value| value.to_str()) == Some(dataset_id) {
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
    let format = meta.get("format").and_then(Value::as_str).unwrap_or("").to_ascii_lowercase();
    if !format.is_empty() {
        let conventional = dataset_dir.join(format!("data.{format}"));
        if conventional.is_file() {
            return Ok(conventional);
        }
    }
    for entry in fs::read_dir(dataset_dir).map_err(|e| e.to_string())?.filter_map(Result::ok) {
        let path = entry.path();
        if path.is_file() && path.file_name().and_then(|value| value.to_str()) != Some("metadata.json") {
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

fn analyze_dataset_from_dir(project_dir: &Path, dataset_id: &str) -> Result<Vec<ColumnStats>, String> {
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

'''
    text = text.replace("fn list_run_snapshots_from_dir(", insertion + "fn list_run_snapshots_from_dir(", 1)

text = replace_rust_fn(
    text,
    "analyze_dataset",
    r'''#[tauri::command]
pub fn analyze_dataset(
    app: AppHandle,
    workspace_id: String,
    dataset_id: String,
) -> Result<Vec<ColumnStats>, String> {
    let (dir, _) = resolve_project_dir(&app, &workspace_id)?;
    analyze_dataset_from_dir(&dir, &dataset_id)
}''',
)

text = replace_rust_fn(
    text,
    "validate_dataset_columns",
    r'''#[tauri::command]
pub fn validate_dataset_columns(
    app: AppHandle,
    workspace_id: String,
    dataset_id: String,
    observed_column: String,
    reference_column: String,
) -> Result<ValidationResult, String> {
    let (dir, _) = resolve_project_dir(&app, &workspace_id)?;
    validate_dataset_columns_from_dir(&dir, &dataset_id, &observed_column, &reference_column)
}''',
)
RESEARCH.write_text(text, encoding="utf-8")

read_validation = READ_VALIDATION.read_text(encoding="utf-8")
read_validation = read_validation.replace('        "analyze_dataset",\n        "validate_dataset_columns",\n', '')
READ_VALIDATION.write_text(read_validation, encoding="utf-8")

NEW_VALIDATION.write_text(r'''#!/usr/bin/env python3
"""Acceptance checks for canonical Rust dataset analysis/validation paths."""
from __future__ import annotations

import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src-tauri/src/research.rs"
LEGACY = ROOT / "src-tauri/src/research_legacy_impl.rs"


def function_block(text: str, name: str) -> str:
    marker = f"fn {name}("
    start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    raise AssertionError(f"unterminated Rust function: {name}")


def compact(text: str) -> str:
    return "".join(text.split())


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")

    for helper in (
        "dataset_record_from_dir",
        "dataset_numeric_path",
        "parse_csv_numeric",
        "analyze_dataset_from_dir",
        "validate_dataset_columns_from_dir",
    ):
        assert f"fn {helper}(" in source, helper

    analyze = function_block(source, "analyze_dataset")
    validate = function_block(source, "validate_dataset_columns")
    for block, helper in ((analyze, "analyze_dataset_from_dir"), (validate, "validate_dataset_columns_from_dir")):
        assert "resolve_project_dir" in block
        assert helper in block
        assert "ensure_alias_for_id" not in block
        assert "legacy::" not in block

    # Preserve the legacy statistical definitions and descriptive thresholds.
    new_analysis = compact(function_block(source, "analyze_dataset_from_dir"))
    old_analysis = compact(function_block(legacy, "analyze_dataset"))
    for token in (
        "/(n-1)asf64",
        "1.96*",
        "ci95_low",
        "ci95_high",
        "f64::INFINITY",
        "f64::NEG_INFINITY",
        "200_000",
    ):
        assert token in new_analysis, token
        assert token in old_analysis, token

    new_validation = compact(function_block(source, "validate_dataset_columns_from_dir"))
    old_validation = compact(function_block(legacy, "validate_dataset_columns"))
    for token in (
        "relative_rmse",
        "1e-15",
        "1e-30",
        "1.0-ss_res/ss_tot",
        'ratio<0.01',
        'ratio<0.05',
        'ratio<0.15',
        '"Strong"',
        '"Good"',
        '"Moderate"',
        '"Weak"',
        "Agreementlabelsaredescriptivethresholds,notproofthateithermodelormeasurementiscorrect.",
    ):
        assert token in new_validation, token
        assert token in old_validation, token

    # Independent numeric fixture for the unchanged definitions.
    observed = [1.0, 2.0, 3.0, 4.0]
    reference = [1.0, 2.2, 2.8, 4.1]
    errors = [a - b for a, b in zip(observed, reference)]
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    ref_scale = sum(abs(v) for v in reference) / len(reference)
    ratio = rmse / ref_scale
    assert abs(mae - 0.125) < 1e-15
    assert 0.05 < ratio < 0.15
    assert ("Strong" if ratio < 0.01 else "Good" if ratio < 0.05 else "Moderate" if ratio < 0.15 else "Weak") == "Moderate"

    print("Physical Lab Rust canonical dataset analysis: PASS")
    print("- analyze_dataset: canonical/legacy direct project resolver, no alias")
    print("- validate_dataset_columns: canonical/legacy direct project resolver, no alias")
    print("- sample SD + 95% CI definition preserved")
    print("- MAE/RMSE/relative RMSE/R2 definitions preserved")
    print("- descriptive agreement thresholds preserved")
    print("Boundary: descriptive agreement is not proof of model correctness, measurement correctness, verification, or validation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''', encoding="utf-8")

workflow = WORKFLOW.read_text(encoding="utf-8")
if "scripts/rust_canonical_dataset_analysis_validation.py" not in workflow:
    workflow = workflow.replace(
        "scripts/rust_canonical_read_paths_validation.py scripts/experiment_kernel_compute_validation.py",
        "scripts/rust_canonical_read_paths_validation.py scripts/rust_canonical_dataset_analysis_validation.py scripts/experiment_kernel_compute_validation.py",
        1,
    )
    workflow = workflow.replace(
        "          python scripts/rust_canonical_read_paths_validation.py\n          python scripts/experiment_kernel_compute_validation.py",
        "          python scripts/rust_canonical_read_paths_validation.py\n          python scripts/rust_canonical_dataset_analysis_validation.py\n          python scripts/experiment_kernel_compute_validation.py",
        1,
    )
WORKFLOW.write_text(workflow, encoding="utf-8")
