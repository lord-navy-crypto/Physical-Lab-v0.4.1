#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Physical Lab desktop bundles must be built on macOS."
  exit 1
fi

if ! xcode-select -p >/dev/null 2>&1; then
  echo "Apple Command Line Tools are required."
  xcode-select --install || true
  echo "Finish the Apple installer, then run BUILD_PHYSICAL_LAB.command again."
  exit 1
fi

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Installing Node.js with Homebrew..."
    brew install node
  else
    echo "Node.js is required. Install Node.js or Homebrew, then rerun this builder."
    exit 1
  fi
fi

if ! command -v cargo >/dev/null 2>&1; then
  echo "Installing the Rust toolchain with rustup..."
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
  source "$HOME/.cargo/env"
fi

python3 scripts/prepare.py
npm install
rustup target add aarch64-apple-darwin x86_64-apple-darwin
npm run desktop:build -- --target universal-apple-darwin

echo ""
echo "Physical Lab build complete."
echo "App and DMG are under: src-tauri/target/universal-apple-darwin/release/bundle/"
