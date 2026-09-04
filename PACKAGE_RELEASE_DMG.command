#!/bin/zsh
set -euo pipefail

# Physical Lab — one-click Universal2 DMG packager
# Source-versioned release builder; release metadata is validated before packaging.

export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.cargo/bin:$HOME/miniforge3/bin:$HOME/miniforge3/condabin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DOWNLOADS="$HOME/Downloads"
DESKTOP="$HOME/Desktop"
RELEASE_DIR="$DESKTOP/Physical Lab Release"
mkdir -p "$RELEASE_DIR"

stamp="$(date +%Y%m%d-%H%M%S)"
LOG="$RELEASE_DIR/Physical-Lab-DMG-build-$stamp.log"

fail() {
  echo ""
  echo "============================================================"
  echo "DMG BUILD FAILED"
  echo "============================================================"
  echo "$1"
  echo ""
  echo "Full log:"
  echo "$LOG"
  echo ""
  open "$RELEASE_DIR" >/dev/null 2>&1 || true
  exit 1
}

on_error() {
  code=$?
  echo "" | tee -a "$LOG"
  echo "Build stopped with exit code $code." | tee -a "$LOG"
  echo "Full log: $LOG" | tee -a "$LOG"
  open "$RELEASE_DIR" >/dev/null 2>&1 || true
  exit "$code"
}
trap on_error ERR

say() {
  echo ""
  echo "==> $1"
}

# Resolve the source tree without asking the user to hunt for paths.
ROOT="${PHYSICAL_LAB_SOURCE:-}"
if [[ -n "$ROOT" && ! -d "$ROOT" ]]; then
  fail "PHYSICAL_LAB_SOURCE points to a missing directory: $ROOT"
fi

if [[ -z "$ROOT" && -f "$SCRIPT_DIR/package.json" && -f "$SCRIPT_DIR/src-tauri/tauri.conf.json" ]]; then
  ROOT="$SCRIPT_DIR"
fi

if [[ -z "$ROOT" && -d "$DOWNLOADS/Physical-Lab-v0.4.1" ]]; then
  ROOT="$DOWNLOADS/Physical-Lab-v0.4.1"
fi

if [[ -z "$ROOT" ]]; then
  latest_dir="$(python3 - "$DOWNLOADS" <<'PYSEL'
from pathlib import Path
import re, sys
base=Path(sys.argv[1])
def version_key(p):
    m=re.search(r"Physical-Lab-v(\d+(?:\.\d+)*)$", p.name)
    return tuple(int(x) for x in m.group(1).split('.')) if m else (-1,)
items=[p for p in base.glob('Physical-Lab-v*') if p.is_dir() and version_key(p)!=(-1,)]
print(max(items,key=version_key) if items else '')
PYSEL
)"
  if [[ -n "$latest_dir" ]]; then
    ROOT="$latest_dir"
  fi
fi

# If the source is still zipped in Downloads, unpack it automatically.
if [[ -z "$ROOT" ]]; then
  latest_zip="$(python3 - "$DOWNLOADS" <<'PYSEL'
from pathlib import Path
import re, sys
base=Path(sys.argv[1])
def version_key(p):
    m=re.search(r"Physical-Lab-v(\d+(?:\.\d+)*)-source\.zip$", p.name)
    return tuple(int(x) for x in m.group(1).split('.')) if m else (-1,)
items=[p for p in base.glob('Physical-Lab-v*-source.zip') if p.is_file() and version_key(p)!=(-1,)]
print(max(items,key=version_key) if items else '')
PYSEL
)"
  if [[ -n "$latest_zip" ]]; then
    say "Extracting Physical Lab source"
    unzip -q "$latest_zip" -d "$DOWNLOADS"
    guessed="$(basename "$latest_zip" -source.zip)"
    if [[ -n "$guessed" && -d "$DOWNLOADS/$guessed" ]]; then
      ROOT="$DOWNLOADS/$guessed"
    fi
  fi
fi

[[ -n "$ROOT" ]] || fail "Could not find a Physical-Lab-v* source folder or source ZIP in ~/Downloads."
[[ -f "$ROOT/package.json" ]] || fail "Not a Physical Lab source tree: $ROOT"
[[ -f "$ROOT/src-tauri/tauri.conf.json" ]] || fail "Missing src-tauri/tauri.conf.json in $ROOT"

cd "$ROOT"

# Mirror terminal output into a persistent release log.
exec > >(tee -a "$LOG") 2>&1

say "Physical Lab DMG Packager"
echo "Source:  $ROOT"
echo "Log:     $LOG"
echo "Release: $RELEASE_DIR"

[[ "$(uname -s)" == "Darwin" ]] || fail "This packager must run on macOS."
[[ "$(uname -m)" == "arm64" || "$(uname -m)" == "x86_64" ]] || fail "Unsupported Mac architecture: $(uname -m)"

say "Preflight"
xcode-select -p >/dev/null 2>&1 || fail "Apple Command Line Tools are not configured."
for cmd in python3 node npm rustup cargo lipo shasum; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing required build command: $cmd"
done

echo "Python: $(python3 --version 2>&1)"
echo "Node:   $(node --version 2>&1)"
echo "npm:    $(npm --version 2>&1)"
echo "Rust:   $(rustc --version 2>&1 || true)"
echo "Cargo:  $(cargo --version 2>&1)"
echo "Xcode:  $(xcode-select -p)"

VERSION="$(python3 - <<'PY'
import json
from pathlib import Path
cfg=json.loads(Path('src-tauri/tauri.conf.json').read_text())
print(cfg.get('version','unknown'))
PY
)"
PRODUCT="$(python3 - <<'PY'
import json
from pathlib import Path
cfg=json.loads(Path('src-tauri/tauri.conf.json').read_text())
print(cfg.get('productName','Physical Lab'))
PY
)"

echo "Product: $PRODUCT"
echo "Version: $VERSION"

say "Release metadata consistency"
python3 scripts/version_consistency.py

say "Source self-check"
if [[ -f scripts/self_check.py ]]; then
  python3 scripts/self_check.py
fi
python3 scripts/prepare.py

say "JavaScript / Tauri CLI dependencies"
npm install --no-audit --no-fund

say "Universal2 Rust targets"
rustup target add aarch64-apple-darwin x86_64-apple-darwin

say "Building Universal2 macOS app + DMG"
npm run desktop:build -- --target universal-apple-darwin

BUNDLE="$ROOT/src-tauri/target/universal-apple-darwin/release/bundle"
APP="$BUNDLE/macos/$PRODUCT.app"
DMG_DIR="$BUNDLE/dmg"

[[ -d "$APP" ]] || fail "Build finished but app bundle was not found at: $APP"
[[ -d "$DMG_DIR" ]] || fail "Build finished but DMG output directory was not found at: $DMG_DIR"

EXE="$APP/Contents/MacOS/$PRODUCT"
if [[ ! -f "$EXE" ]]; then
  EXE="$(find "$APP/Contents/MacOS" -maxdepth 1 -type f | head -n 1 || true)"
fi
[[ -n "$EXE" && -f "$EXE" ]] || fail "Could not locate the app executable for architecture verification."

say "Verifying Universal2 app"
ARCHS="$(lipo -archs "$EXE")"
echo "Executable: $EXE"
echo "Architectures: $ARCHS"
[[ " $ARCHS " == *" arm64 "* ]] || fail "The packaged app is missing arm64. Found: $ARCHS"
[[ " $ARCHS " == *" x86_64 "* ]] || fail "The packaged app is missing x86_64. Found: $ARCHS"

DMG="$(find "$DMG_DIR" -maxdepth 1 -type f -name '*.dmg' -print | sort | tail -n 1 || true)"
[[ -n "$DMG" && -f "$DMG" ]] || fail "Tauri did not produce a .dmg file in $DMG_DIR"

FINAL_DMG="$RELEASE_DIR/Physical-Lab-v${VERSION}-Universal2.dmg"
cp -f "$DMG" "$FINAL_DMG"

SHA="$(shasum -a 256 "$FINAL_DMG" | awk '{print $1}')"
SHA_FILE="$RELEASE_DIR/Physical-Lab-v${VERSION}-Universal2.sha256.txt"
printf '%s  %s\n' "$SHA" "$(basename "$FINAL_DMG")" > "$SHA_FILE"

say "Release package ready"
echo ""
echo "DMG:"
echo "$FINAL_DMG"
echo ""
echo "SHA-256:"
echo "$SHA"
echo ""
echo "Build log:"
echo "$LOG"
echo ""
echo "Architectures: $ARCHS"
echo ""
echo "IMPORTANT FOR PUBLIC DISTRIBUTION:"
echo "This script builds the DMG. If you have not signed with an Apple Developer ID and notarized it,"
echo "other Macs may show a Gatekeeper warning. The DMG itself is still suitable for local/testing release."

open "$RELEASE_DIR"
open -R "$FINAL_DMG" >/dev/null 2>&1 || true

printf '\n============================================================\n'
printf ' PHYSICAL LAB DMG READY\n'
printf '============================================================\n'
printf '%s\n' "$FINAL_DMG"
