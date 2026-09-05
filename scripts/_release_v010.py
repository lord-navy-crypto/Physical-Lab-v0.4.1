#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD = "0.9.0"
NEW = "0.10.0"
DATE = "2026-09-05"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one release anchor in {path}: found {count}: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    version_path = ROOT / "VERSION"
    if version_path.read_text(encoding="utf-8").strip() != OLD:
        raise RuntimeError("VERSION is not the expected pre-release 0.9.0")
    version_path.write_text(NEW + "\n", encoding="utf-8")

    package_path = ROOT / "package.json"
    package = json.loads(package_path.read_text(encoding="utf-8"))
    if package.get("version") != OLD:
        raise RuntimeError("package.json is not at 0.9.0")
    package["version"] = NEW
    package_path.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    cargo = ROOT / "src-tauri" / "Cargo.toml"
    replace_once(cargo, f'version = "{OLD}"', f'version = "{NEW}"')

    tauri_path = ROOT / "src-tauri" / "tauri.conf.json"
    tauri = json.loads(tauri_path.read_text(encoding="utf-8"))
    if tauri.get("version") != OLD:
        raise RuntimeError("tauri.conf.json is not at 0.9.0")
    tauri["version"] = NEW
    tauri_path.write_text(json.dumps(tauri, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    readme = ROOT / "README.md"
    replace_once(readme, f"# Physical Lab v{OLD} —", f"# Physical Lab v{NEW} —")

    changelog = ROOT / "CHANGELOG.md"
    replace_once(
        changelog,
        "## [Unreleased]\n\n### Added — Evidence-First Engineering Systems\n",
        f"## [Unreleased]\n\nNo unreleased changes.\n\n## [{NEW}] - {DATE}\n\n### Added — Evidence-First Engineering Systems\n",
    )
    text = changelog.read_text(encoding="utf-8")
    link = f"[{NEW}]: https://github.com/lord-navy-crypto/Physical-Lab-v0.4.1/compare/Physical-Lab-v0.9.0...Physical-Lab-v{NEW}\n"
    if f"[{NEW}]:" in text:
        raise RuntimeError("0.10.0 release link already exists")
    marker = "[0.9.0]:"
    pos = text.find(marker)
    if pos < 0:
        raise RuntimeError("0.9.0 changelog link anchor missing")
    text = text[:pos] + link + text[pos:]
    changelog.write_text(text, encoding="utf-8")

    validator = ROOT / "scripts" / "v010_release_readiness_validation.py"
    text = validator.read_text(encoding="utf-8")
    old = '    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()\n    assert version == "0.9.0", f"release-hardening branch must remain pre-bump; found {version}"\n'
    new = '''    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()\n    assert version in {"0.9.0", "0.10.0"}, f"unexpected v0.10 milestone version: {version}"\n'''
    if text.count(old) != 1:
        raise RuntimeError("release validator version-state anchor drifted")
    text = text.replace(old, new, 1)
    old = '    assert "## [Unreleased]" in changelog\n'
    new = '''    assert "## [Unreleased]" in changelog\n    if version == "0.10.0":\n        assert "## [0.10.0] - 2026-09-05" in changelog\n        first_line = readme.splitlines()[0] if readme.splitlines() else ""\n        assert "Physical Lab v0.10.0" in first_line\n        assert "No unreleased changes." in changelog\n    else:\n        assert "## [0.10.0] - 2026-09-05" not in changelog\n'''
    if text.count(old) != 1:
        raise RuntimeError("release validator changelog-state anchor drifted")
    text = text.replace(old, new, 1)
    text = text.replace(
        '    print("- source version remains 0.9.0 pending dedicated release bump: PASS")',
        '    print(f"- v0.10 milestone release state ({version}): PASS")',
        1,
    )
    validator.write_text(text, encoding="utf-8")

    print("Physical Lab v0.10.0 guarded release metadata update: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
