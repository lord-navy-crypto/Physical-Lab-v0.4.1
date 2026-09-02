#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")"
python3 scripts/self_check.py
node --check dist/app.js 2>/dev/null || true
