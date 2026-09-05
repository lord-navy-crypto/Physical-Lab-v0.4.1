#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src-tauri/resources/ui/physical_lab_model_builder.py"


def load_core():
    spec = importlib.util.spec_from_file_location("pl_model_builder", CORE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    core = load_core()
    with tempfile.TemporaryDirectory(prefix="pl-model-builder-") as td:
        root = Path(td)
        marker = root / "executed.txt"
        static_source = root / "static_model.py"
        static_source.write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n\ndef simulate(length=1.0, angle=0.2, samples=5):\n    return {{'time': list(range(int(samples))), 'position': [length * angle for _ in range(int(samples))]}}\n",
            encoding="utf-8",
        )
        analysis = core.analyze_source(str(static_source))
        assert analysis["schema"] == "physical-lab-model-analysis-v1"
        assert analysis["candidate_entry"] == "simulate"
        assert analysis["candidate_model_spec"]["schema"] == "physical-lab-model-spec-v1"
        assert not marker.exists(), "static analysis executed the student source"
        spec = analysis["candidate_model_spec"]
        spec["metadata"]["description"] = "Deterministic fixture"
        for row in spec["parameters"]:
            if row["name"] == "length":
                row.update({"unit": "m", "control": "slider", "min": 0.1, "max": 10.0})
            elif row["name"] == "angle":
                row.update({"unit": "rad", "control": "slider", "min": -1.0, "max": 1.0})
            elif row["name"] == "samples":
                row.update({"control": "number"})
        bundle = core.generate_bundle(str(static_source), spec, str(root / "bundles"))
        bundle_path = Path(bundle["bundle_path"])
        assert not marker.exists(), "bundle generation executed the student source"
        for name in ("original_model.py", "adapter.py", "model.json", "ui.json", "tests.json", "provenance.json"):
            assert (bundle_path / name).is_file(), name
        provenance = json.loads((bundle_path / "provenance.json").read_text())
        assert provenance["generation_policy"] == "wrapper-not-rewrite"
        assert provenance["original_source_modified"] is False

        preview = core.run_bundle(str(bundle_path), {"length": 2.0, "angle": 0.5, "samples": 4})
        assert marker.exists(), "explicit preview did not execute the source snapshot"
        assert preview["outputs"]["time"] == [0, 1, 2, 3]
        assert preview["outputs"]["position"] == [1.0, 1.0, 1.0, 1.0]
        check = core.validate_adapter(str(bundle_path), {"length": 2.0, "angle": 0.5, "samples": 4})
        assert check["schema"] == "physical-lab-model-adapter-validation-v1"
        assert check["equivalent"] is True
        assert check["max_abs_diff"] == 0.0
        assert "not scientific validation" in check["boundary"]

        mapping_source = root / "mapping_model.py"
        mapping_source.write_text(
            "def simulate(parameters):\n    x = float(parameters['x'])\n    return {'y': x * x}\n",
            encoding="utf-8",
        )
        mapping = core.analyze_source(str(mapping_source))
        assert mapping["candidate_model_spec"]["compute"]["calling_convention"] == "mapping"

        risk_source = root / "risk.py"
        risk_source.write_text("import subprocess\n\ndef compute(x=1):\n    return x\n", encoding="utf-8")
        risk = core.analyze_source(str(risk_source))
        assert any(row["kind"] == "execution-risk" for row in risk["warnings"])

        bad_spec = json.loads(json.dumps(spec))
        bad_spec["parameters"][0]["control"] = "slider"
        bad_spec["parameters"][0]["min"] = None
        try:
            core.validate_model_spec(bad_spec)
        except ValueError as exc:
            assert "requires explicit min and max" in str(exc)
        else:
            raise AssertionError("slider without explicit range was accepted")

    source = CORE.read_text(encoding="utf-8")
    for forbidden in ("scientifically correct", "certified", "automatic truth", "rewrite the student's science"):
        assert forbidden not in source.lower()
    print("Research Model Builder deterministic validation: PASS")
    print("- static AST analysis does not execute student source")
    print("- generation preserves source and creates adapter/ModelSpec/UI/tests/provenance")
    print("- explicit preview runs the bundled source snapshot")
    print("- original↔adapter equivalence validation passes")
    print("- mapping and keyword-argument calling conventions covered")
    print("- risky imports are surfaced as review warnings")
    print("- sliders require explicit human-confirmed ranges")
    print("Boundary: adapter equivalence is interface validation, not scientific validation or certification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
