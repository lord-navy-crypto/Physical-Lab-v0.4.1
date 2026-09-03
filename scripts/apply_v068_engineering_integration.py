#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADV = ROOT / "src-tauri" / "resources" / "ui" / "physical_lab_advanced.py"

text = ADV.read_text(encoding="utf-8")
old = '''    try:\n        from physical_lab_visualization import visualization_context\n        with visualization_context(st, profile):\n            _render_profile_suite()\n    except Exception as _pl_visualization_error:\n        st.warning(f"Physical Lab Visualization Studio could not load: {_pl_visualization_error}")\n        _render_profile_suite()\n'''
new = '''    try:\n        from physical_lab_visualization import visualization_context\n        from physical_lab_visualization_engineering import engineering_visualization_context\n        with visualization_context(st, profile):\n            with engineering_visualization_context(st, profile):\n                _render_profile_suite()\n                try:\n                    from physical_lab_engineering import render_engineering_vvuq\n                    render_engineering_vvuq(st, profile, namespace)\n                except Exception as _pl_engineering_error:\n                    st.warning(f"Physical Lab Engineering V&V/UQ could not load: {_pl_engineering_error}")\n    except Exception as _pl_visualization_error:\n        st.warning(f"Physical Lab Visualization Studio could not load: {_pl_visualization_error}")\n        _render_profile_suite()\n        try:\n            from physical_lab_engineering import render_engineering_vvuq\n            render_engineering_vvuq(st, profile, namespace)\n        except Exception as _pl_engineering_error:\n            st.warning(f"Physical Lab Engineering V&V/UQ could not load: {_pl_engineering_error}")\n'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"advanced visualization anchor count={count}, expected 1")
ADV.write_text(text.replace(old, new, 1), encoding="utf-8")
print("v0.68 advanced engineering integration applied")
