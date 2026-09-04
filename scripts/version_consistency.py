#!/usr/bin/env python3
"""Fail fast when Physical Lab release metadata drifts across build systems."""
from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def main() -> None:
    canonical = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", canonical):
        raise SystemExit(f"VERSION must be SemVer MAJOR.MINOR.PATCH, found: {canonical!r}")

    package_version = read_json("package.json")["version"]
    tauri_version = read_json("src-tauri/tauri.conf.json")["version"]
    cargo = tomllib.loads((ROOT / "src-tauri/Cargo.toml").read_text(encoding="utf-8"))
    cargo_version = cargo["package"]["version"]

    observed = {
        "VERSION": canonical,
        "package.json": package_version,
        "src-tauri/tauri.conf.json": tauri_version,
        "src-tauri/Cargo.toml": cargo_version,
    }
    mismatched = {name: value for name, value in observed.items() if value != canonical}
    if mismatched:
        detail = ", ".join(f"{name}={value}" for name, value in mismatched.items())
        raise SystemExit(f"Physical Lab version drift: expected {canonical}; {detail}")

    workflow = (ROOT / ".github/workflows/macos-universal2-build.yml").read_text(encoding="utf-8")
    if "steps.release_version.outputs.version" not in workflow:
        raise SystemExit("Universal2 workflow must derive artifact names from the resolved release version")
    if re.search(r"Physical-Lab-v\d+\.\d+\.\d+-Universal2", workflow):
        raise SystemExit("Universal2 workflow contains a hard-coded release artifact version")

    release_script = (ROOT / "PACKAGE_RELEASE_DMG.command").read_text(encoding="utf-8")
    if "tauri.conf.json" not in release_script or "VERSION" not in release_script:
        raise SystemExit("PACKAGE_RELEASE_DMG.command must remain source-version driven")

    print(f"Physical Lab version consistency: PASS ({canonical})")
    for name, value in observed.items():
        print(f"  {name}: {value}")
    print("  Universal2 artifact naming: source-driven")


if __name__ == "__main__":
    main()
