#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADV = ROOT / "src-tauri" / "resources" / "ui" / "physical_lab_advanced.py"

text = ADV.read_text(encoding="utf-8")
old = '''    if profile == "radia-magnet-studio":\n        try:\n            from physical_lab_radia_adapter import render_radia_forward_workspace\n            render_radia_forward_workspace(st, namespace)\n        except Exception as _pl_radia_adapter_error:\n            st.warning(f"Physical Lab RADIA Measurement Adapter could not load: {_pl_radia_adapter_error}")\n'''
new = old + '''        try:\n            from physical_lab_radia_tolerance import render_radia_tolerance_workspace\n            render_radia_tolerance_workspace(st, namespace)\n        except Exception as _pl_radia_tolerance_error:\n            st.warning(f"Physical Lab nonlinear RADIA tolerance workspace could not load: {_pl_radia_tolerance_error}")\n'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"RADIA adapter integration anchor count={count}, expected 1")
ADV.write_text(text.replace(old, new, 1), encoding="utf-8")
print("v0.69 nonlinear RADIA tolerance integration applied")
