#!/usr/bin/env python3
"""One-time integration patch for Physical Lab v0.6 phase 2.

Wires the RADIA measurement adapter and read-only Local AI bridge into the
existing Physical Lab UI without replacing upstream scientific solvers.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
RADIA_RUNTIME_REVISION = "7ff3b2dc26cbcccfcb0aaf3c4a290ebd83439698"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected exactly one patch anchor in {path.relative_to(ROOT)}; found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


advanced = ROOT / "src-tauri/resources/ui/physical_lab_advanced.py"
old_hook = '''    try:\n        from physical_lab_digital_twin_ui import render_digital_twin_workspace\n        render_digital_twin_workspace(st, profile)\n    except Exception as _pl_digital_twin_error:\n        st.warning(f"Physical Lab Measurement Digital Twin could not load: {_pl_digital_twin_error}")\n    _render_run_vault(st, profile)\n'''
new_hook = '''    try:\n        from physical_lab_digital_twin_ui import render_digital_twin_workspace\n        render_digital_twin_workspace(st, profile)\n    except Exception as _pl_digital_twin_error:\n        st.warning(f"Physical Lab Measurement Digital Twin could not load: {_pl_digital_twin_error}")\n    if profile == "radia-magnet-studio":\n        try:\n            from physical_lab_radia_adapter import render_radia_forward_workspace\n            render_radia_forward_workspace(st, namespace)\n        except Exception as _pl_radia_adapter_error:\n            st.warning(f"Physical Lab RADIA Measurement Adapter could not load: {_pl_radia_adapter_error}")\n    try:\n        from physical_lab_local_ai import render_local_ai_assistant\n        render_local_ai_assistant(st, profile, namespace)\n    except Exception as _pl_local_ai_error:\n        st.warning(f"Physical Lab Local AI Assistant could not load: {_pl_local_ai_error}")\n    _render_run_vault(st, profile)\n'''
replace_once(advanced, old_hook, new_hook)

conf_path = ROOT / "src-tauri/tauri.conf.json"
conf = json.loads(conf_path.read_text(encoding="utf-8"))
resources = conf["bundle"]["resources"]
resources["resources/ui/physical_lab_radia_adapter.py"] = "ui/physical_lab_radia_adapter.py"
resources["resources/ui/physical_lab_local_ai.py"] = "ui/physical_lab_local_ai.py"
conf_path.write_text(json.dumps(conf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

mods_path = ROOT / "src-tauri/resources/modules.json"
mods = json.loads(mods_path.read_text(encoding="utf-8"))
radia_runtime = next((m for m in mods if m.get("id") == "radia-runtime"), None)
if not radia_runtime:
    raise SystemExit("radia-runtime module missing")
radia_runtime["revision"] = RADIA_RUNTIME_REVISION
mods_path.write_text(json.dumps(mods, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

workflow = ROOT / ".github/workflows/full-mode-acceptance.yml"
workflow_text = workflow.read_text(encoding="utf-8")
if "physical_lab_radia_adapter.py" not in workflow_text:
    replace_once(
        workflow,
        "      - 'src-tauri/resources/ui/physical_lab_digital_twin.py'\n",
        "      - 'src-tauri/resources/ui/physical_lab_digital_twin.py'\n      - 'src-tauri/resources/ui/physical_lab_radia_adapter.py'\n",
    )

self_check = ROOT / "scripts/self_check.py"
append = '''\n# v0.6 phase 2: real RADIA measurement adapter + optional local AI explanation bridge\nradia_adapter=(root/'src-tauri/resources/ui/physical_lab_radia_adapter.py').read_text()\nlocal_ai=(root/'src-tauri/resources/ui/physical_lab_local_ai.py').read_text()\nadvanced_text=(root/'src-tauri/resources/ui/physical_lab_advanced.py').read_text()\nconf=json.loads((root/'src-tauri/tauri.conf.json').read_text())\nmods=json.loads((root/'src-tauri/resources/modules.json').read_text())\nfull_mode=(root/'.github/workflows/full-mode-acceptance.yml').read_text()\nassert 'run_current_radia_forward_model' in radia_adapter\nassert 'run_bounded_radia_parameter_profile' in radia_adapter\nassert 'PHYSICAL_LAB_ENGINE_MODE' in radia_adapter\nassert 'OpenPenguin private runtime' in local_ai and '127.0.0.1:11435' in local_ai\nassert 'External Ollama' in local_ai and '127.0.0.1:11434' in local_ai\nassert 'ask_local_model' in local_ai and '/api/chat' in local_ai\nassert 'render_radia_forward_workspace(st, namespace)' in advanced_text\nassert 'render_local_ai_assistant(st, profile, namespace)' in advanced_text\nassert 'resources/ui/physical_lab_radia_adapter.py' in conf['bundle']['resources']\nassert 'resources/ui/physical_lab_local_ai.py' in conf['bundle']['resources']\nmanaged_runtime=next(m for m in mods if m['id']=='radia-runtime')['revision']\nassert managed_runtime == '7ff3b2dc26cbcccfcb0aaf3c4a290ebd83439698'\nassert managed_runtime in radia_adapter\nassert managed_runtime in full_mode\nprint('RADIA Measurement Adapter: configured')\nprint('Managed RADIA runtime pin == Full-mode tested revision:', managed_runtime)\nprint('Local AI Assistant: local-only read-only bridge configured')\n'''
text = self_check.read_text(encoding="utf-8")
if "Local AI Assistant: local-only read-only bridge configured" not in text:
    self_check.write_text(text + append, encoding="utf-8")

readme = ROOT / "README.md"
readme_text = readme.read_text(encoding="utf-8")
section = '''\n## Optional Local AI Assistant\n\nPhysical Lab can use a **local-only, read-only AI explanation layer** without making AI part of the scientific solver. The assistant discovers either the private OpenPenguin/Ollama runtime at `127.0.0.1:11435` or an existing Ollama service at `127.0.0.1:11434`, sends a bounded structured snapshot of the current Lab state, and can explain parameters, units, assumptions, diagnostics and possible next experiments. It cannot modify parameters, download models, execute model-generated code, or contact a cloud endpoint. Physical Lab remains fully functional when no local model is running.\n\nFor RADIA Magnet Studio Full mode, the **RADIA Measurement Adapter** can evaluate the current managed magnet model at explicit measurement coordinates and write lineage-tracked `Bx/By/Bz/Bperp` columns into a derived `.physlab` dataset. A bounded one-parameter profile can repeatedly run the real RADIA forward model over explicit `gap_mm`, `br_t`, or `z_offset_mm` candidates. The best result means only the lowest RMSE on that finite grid; it is not presented as a posterior distribution or global optimum.\n\n'''
if "## Optional Local AI Assistant" not in readme_text:
    marker = "## Measurement Digital Twin\n"
    if marker not in readme_text:
        raise SystemExit("README Measurement Digital Twin anchor missing")
    readme.write_text(readme_text.replace(marker, section + marker, 1), encoding="utf-8")

print("v0.6 phase 2 Local AI + RADIA adapter integration: APPLIED")
