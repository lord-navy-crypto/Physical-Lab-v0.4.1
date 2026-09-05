#!/usr/bin/env python3
"""Acceptance checks for canonical-native desktop serial capture."""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src-tauri/src/research.rs"
LEGACY = ROOT / "src-tauri/src/research_legacy_impl.rs"

def compact(value: str) -> str:
    return "".join(value.split())

def function_block(text: str, name: str) -> str:
    marker = f"fn {name}("
    start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{": depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0: return text[start:index + 1]
    raise AssertionError(name)

def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")

    list_new = compact(function_block(source, "list_serial_devices"))
    list_old = compact(function_block(legacy, "list_serial_devices"))
    for token in ('fs::read_dir("/dev")', 'name.starts_with("cu.")', 'name.starts_with("tty.")', 'output.sort()'):
        assert token in list_new, token
    for token in ('fs::read_dir("/dev")', 'name.starts_with("cu.")', 'name.starts_with("tty.")', 'out.sort()'):
        assert token in list_old, token
    assert "legacy::" not in list_new

    command = compact(function_block(source, "capture_serial_measurement"))
    for token in (
        'resolve_project_dir(&app,&workspace_id)',
        'capture_serial_measurement_to_dir',
        'ifcanonical',
        'register_desktop_measurement',
        'touch_project_after_direct_write(&dir,true)',
    ):
        assert token in command, token
    assert "ensure_alias_for_id" not in command
    assert "legacy::" not in command

    helper = compact(function_block(source, "capture_serial_measurement_to_dir"))
    legacy_capture = compact(function_block(legacy, "capture_serial_measurement"))
    for token in (
        '!device.starts_with("/dev/cu.")&&!device.starts_with("/dev/tty.")',
        '"OnlymacOSserialdevicesunder/dev/cu.*or/dev/tty.*areaccepted."',
        'Path::new(device).exists()',
        'seconds.clamp(1,300)',
        'Command::new("/bin/stty")',
        '"-f",device',
        '"raw","-echo"',
        'Local::now().timestamp_millis()',
        "fd=os.open(p,os.O_RDONLY|os.O_NONBLOCK)",
        "select.select([fd],[],[],0.2)",
        "f.write('timestamp,value\\n')",
        "float(s.split(',')[-1].strip())",
        'command_text("/usr/bin/which",&["python3"])',
        '"Serialcapturefailed.Checkdevicepermissionsandbaudrate."',
        'import_measurement_dataset_to_dir',
        'format!("Serialcaptureat{baud}baudfor{secs}s")',
        'fs::remove_file(&temporary)',
    ):
        assert token in helper, token

    for token in (
        '!device.starts_with("/dev/cu.")&&!device.starts_with("/dev/tty.")',
        '"OnlymacOSserialdevicesunder/dev/cu.*or/dev/tty.*areaccepted."',
        'Path::new(&device).exists()',
        'seconds.clamp(1,300)',
        'Command::new("/bin/stty")',
        '"-f",device.as_str()',
        '"raw","-echo"',
        'Local::now().timestamp_millis()',
        "fd=os.open(p,os.O_RDONLY|os.O_NONBLOCK)",
        "select.select([fd],[],[],0.2)",
        "f.write('timestamp,value\\n')",
        "float(s.split(',')[-1].strip())",
        'command_text("/usr/bin/which",&["python3"])',
        '"Serialcapturefailed.Checkdevicepermissionsandbaudrate."',
        'format!("Serialcaptureat{baud}baudfor{secs}s")',
        'fs::remove_file(tmp)',
    ):
        assert token in legacy_capture, token

    registration = compact(function_block(source, "register_desktop_measurement"))
    assert '"physical-lab-measurement-v1"' in registration
    assert '"source_type":"desktop-data-bridge"' in registration
    assert 'Calibrationstatus,sensoraccuracy,traceabilityandexperimentalvalidationmustbeestablishedseparately.' in registration

    assert source.count("ensure_alias_for_id(") == 1
    print("Physical Lab Rust canonical serial capture: PASS")
    print("- macOS /dev/cu.* and /dev/tty.* device boundary preserved")
    print("- 1–300 s clamp, stty setup and non-blocking capture preserved")
    print("- timestamp,value CSV acquisition contract preserved")
    print("- serial capture imports directly into canonical/legacy project datasets")
    print("- canonical capture registers Measurement Evidence")
    print("- no project command calls ensure_alias_for_id")
    print("Boundary: serial acquisition plus file hashing/registration does not establish sensor accuracy, calibration traceability, experimental validation, or scientific truth.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
