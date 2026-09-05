use serde_json::Value;
use std::{
    fs,
    fs::OpenOptions,
    io::Read,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::{AppHandle, Manager};

const EXECUTION_TIMEOUT_SECS: u64 = 20;
const MAX_CAPTURE_BYTES: u64 = 8 * 1024 * 1024;

fn builder_root(app: &AppHandle) -> Result<PathBuf, String> {
    let path = app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?
        .join("model-builder");
    fs::create_dir_all(path.join("bundles")).map_err(|e| e.to_string())?;
    fs::create_dir_all(path.join("logs")).map_err(|e| e.to_string())?;
    Ok(path)
}

fn builder_script(app: &AppHandle) -> Result<PathBuf, String> {
    if let Ok(resource) = app.path().resource_dir() {
        let path = resource.join("ui/physical_lab_model_builder.py");
        if path.is_file() {
            return Ok(path);
        }
    }
    let dev = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("resources/ui/physical_lab_model_builder.py");
    if dev.is_file() {
        return Ok(dev);
    }
    Err("Physical Lab Model Builder core resource is unavailable.".into())
}

fn python_candidate() -> Result<String, String> {
    let candidates = [
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        "/usr/bin/python3",
        "python3",
    ];
    for candidate in candidates {
        if Command::new(candidate)
            .arg("--version")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .map(|status| status.success())
            .unwrap_or(false)
        {
            return Ok(candidate.to_string());
        }
    }
    Err("Compatible Python 3 was not found for Research Model Builder.".into())
}

fn unique_capture_path(root: &Path, label: &str) -> PathBuf {
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_nanos())
        .unwrap_or(0);
    root.join("logs").join(format!("{label}-{stamp}.log"))
}

fn read_bounded(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path).map_err(|e| e.to_string())?;
    let mut buffer = Vec::new();
    file.take(MAX_CAPTURE_BYTES + 1)
        .read_to_end(&mut buffer)
        .map_err(|e| e.to_string())?;
    if buffer.len() as u64 > MAX_CAPTURE_BYTES {
        return Err("Model Builder output exceeded the 8 MB safety limit.".into());
    }
    Ok(String::from_utf8_lossy(&buffer).trim().to_string())
}

fn run_builder_cli(
    app: &AppHandle,
    args: Vec<String>,
    allow_source_execution: bool,
) -> Result<Value, String> {
    if allow_source_execution && !args.iter().any(|value| value == "run" || value == "validate") {
        return Err("Internal Model Builder execution policy mismatch.".into());
    }
    let root = builder_root(app)?;
    let stdout_path = unique_capture_path(&root, "stdout");
    let stderr_path = unique_capture_path(&root, "stderr");
    let stdout = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&stdout_path)
        .map_err(|e| e.to_string())?;
    let stderr = OpenOptions::new()
        .create(true)
        .write(true)
        .truncate(true)
        .open(&stderr_path)
        .map_err(|e| e.to_string())?;
    let mut command = Command::new(python_candidate()?);
    command
        .arg(builder_script(app)?)
        .args(&args)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::from(stderr))
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONDONTWRITEBYTECODE", "1");
    let mut child = command.spawn().map_err(|e| e.to_string())?;
    let started = Instant::now();
    let status = loop {
        match child.try_wait().map_err(|e| e.to_string())? {
            Some(status) => break status,
            None if started.elapsed() >= Duration::from_secs(EXECUTION_TIMEOUT_SECS) => {
                let _ = child.kill();
                let _ = child.wait();
                let _ = fs::remove_file(&stdout_path);
                let stderr_text = read_bounded(&stderr_path).unwrap_or_default();
                let _ = fs::remove_file(&stderr_path);
                return Err(format!(
                    "Research Model Builder stopped the local process after {EXECUTION_TIMEOUT_SECS} seconds. {stderr_text}"
                ));
            }
            None => thread::sleep(Duration::from_millis(50)),
        }
    };
    let stdout_text = read_bounded(&stdout_path)?;
    let stderr_text = read_bounded(&stderr_path).unwrap_or_default();
    let _ = fs::remove_file(&stdout_path);
    let _ = fs::remove_file(&stderr_path);
    if !status.success() {
        let detail = if stderr_text.is_empty() {
            stdout_text
        } else {
            stderr_text
        };
        return Err(if detail.is_empty() {
            format!("Research Model Builder process exited with {status}")
        } else {
            detail
        });
    }
    serde_json::from_str(&stdout_text).map_err(|e| format!("Model Builder returned invalid JSON: {e}"))
}

#[tauri::command]
pub fn model_builder_analyze(app: AppHandle, source_path: String) -> Result<Value, String> {
    run_builder_cli(
        &app,
        vec!["analyze".into(), "--source".into(), source_path],
        false,
    )
}

#[tauri::command]
pub fn model_builder_generate(
    app: AppHandle,
    source_path: String,
    model_spec: Value,
) -> Result<Value, String> {
    let output_root = builder_root(&app)?.join("bundles");
    run_builder_cli(
        &app,
        vec![
            "generate".into(),
            "--source".into(),
            source_path,
            "--spec-json".into(),
            serde_json::to_string(&model_spec).map_err(|e| e.to_string())?,
            "--output-root".into(),
            output_root.to_string_lossy().to_string(),
        ],
        false,
    )
}

#[tauri::command]
pub fn model_builder_run(
    app: AppHandle,
    bundle_path: String,
    parameters: Value,
    trusted: bool,
) -> Result<Value, String> {
    if !trusted {
        return Err("Preview is disabled until you explicitly confirm that you trust this local Python source.".into());
    }
    run_builder_cli(
        &app,
        vec![
            "run".into(),
            "--bundle".into(),
            bundle_path,
            "--parameters-json".into(),
            serde_json::to_string(&parameters).map_err(|e| e.to_string())?,
        ],
        true,
    )
}

#[tauri::command]
pub fn model_builder_validate(
    app: AppHandle,
    bundle_path: String,
    parameters: Value,
    trusted: bool,
) -> Result<Value, String> {
    if !trusted {
        return Err("Adapter validation is disabled until you explicitly confirm that you trust this local Python source.".into());
    }
    run_builder_cli(
        &app,
        vec![
            "validate".into(),
            "--bundle".into(),
            bundle_path,
            "--parameters-json".into(),
            serde_json::to_string(&parameters).map_err(|e| e.to_string())?,
        ],
        true,
    )
}

#[tauri::command]
pub fn model_builder_open_bundle(app: AppHandle, bundle_path: String) -> Result<(), String> {
    let root = builder_root(&app)?.canonicalize().map_err(|e| e.to_string())?;
    let target = PathBuf::from(bundle_path)
        .canonicalize()
        .map_err(|e| e.to_string())?;
    if !target.starts_with(root.join("bundles")) || !target.is_dir() {
        return Err("Only generated Research Model Builder bundles can be opened from this command.".into());
    }
    Command::new("/usr/bin/open")
        .arg(target)
        .spawn()
        .map_err(|e| e.to_string())?;
    Ok(())
}
