#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "scripts/local_ai_reference_validation.py"
text = path.read_text(encoding="utf-8")
old = 'assert "Taylor" in merged["pl_n_micro_n"]["meaning"]\n'
new = 'assert merged["pl_n_micro_n"]["unit"] == "Taylor terms"\nassert merged["pl_n_micro_n"]["meaning"].strip()\n'
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit("v0.63 validation assertion anchor missing")
path.write_text(text, encoding="utf-8")
print("v0.63 validation assertion: FIXED")
