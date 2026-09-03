#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADV = ROOT / "src-tauri" / "resources" / "ui" / "physical_lab_advanced.py"
PROP = ROOT / "src-tauri" / "resources" / "ui" / "physical_lab_radia_radiation_propagation.py"


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}, expected 1")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


old_root = '''def _managed_radiation_paths() -> tuple[Path, Path]:\n    root = Path(os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()).expanduser()\n    if not str(root):\n        raise RuntimeError("PHYSICAL_LAB_DATA_DIR is unavailable")\n    module = root / "modules" / "radiation-platform"\n'''
new_root = '''def _managed_radiation_paths() -> tuple[Path, Path]:\n    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()\n    if not raw:\n        raise RuntimeError("PHYSICAL_LAB_DATA_DIR is unavailable")\n    root = Path(raw).expanduser().resolve()\n    module = root / "modules" / "radiation-platform"\n'''
replace_once(PROP, old_root, new_root, "data-root guard")

old_hook = '''        try:\n            from physical_lab_radia_tolerance import render_radia_tolerance_workspace\n            render_radia_tolerance_workspace(st, namespace)\n        except Exception as _pl_radia_tolerance_error:\n            st.warning(f"Physical Lab nonlinear RADIA tolerance workspace could not load: {_pl_radia_tolerance_error}")\n'''
new_hook = old_hook + '''        try:\n            from physical_lab_radia_radiation_propagation import render_radia_radiation_propagation\n            render_radia_radiation_propagation(st, namespace)\n        except Exception as _pl_radia_radiation_error:\n            st.warning(f"Physical Lab RADIA → Radiation tolerance propagation could not load: {_pl_radia_radiation_error}")\n'''
replace_once(ADV, old_hook, new_hook, "RADIA propagation hook")
print("v0.70 propagation integration applied")
