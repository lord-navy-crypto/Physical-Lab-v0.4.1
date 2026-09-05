#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compact(text: str) -> str:
    return "".join(text.split())


def main() -> int:
    lib = (ROOT / "src-tauri/src/lib.rs").read_text(encoding="utf-8")
    rust = (ROOT / "src-tauri/src/model_builder.rs").read_text(encoding="utf-8")
    research = (ROOT / "src-tauri/src/research.rs").read_text(encoding="utf-8")
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    js = (ROOT / "web/app.js").read_text(encoding="utf-8")
    conf = json.loads((ROOT / "src-tauri/tauri.conf.json").read_text(encoding="utf-8"))

    assert "mod model_builder;" in lib
    handler = compact(lib)
    for token in (
        "model_builder::model_builder_choose_source",
        "model_builder::model_builder_analyze",
        "model_builder::model_builder_generate",
        "model_builder::model_builder_run",
        "model_builder::model_builder_validate",
        "model_builder::model_builder_open_bundle",
        "research::save_model_builder_bundle",
    ):
        assert token in handler, token

    for token in (
        "EXECUTION_TIMEOUT_SECS",
        "MAX_CAPTURE_BYTES",
        "if !trusted",
        "stdin(Stdio::null())",
        'Command::new("/usr/bin/osascript")',
        "physical_lab_model_builder.py",
    ):
        assert token in rust, token
    assert ".arg(\"-c\")" not in rust, "Model Builder desktop execution must not invoke a shell command string"

    for token in (
        "physical-lab-model-index-v1",
        "physical-lab-model-bundle-v1",
        'join("models")',
        "save_model_builder_bundle",
        "Project membership records provenance",
    ):
        assert token in research, token

    assert 'data-view="modelbuilder"' in html
    for token in (
        'id="modelBuilderView"',
        'id="modelBuilderSource"',
        'id="modelBuilderAnalyze"',
        'id="modelBuilderParameterReview"',
        'id="modelBuilderSpec"',
        'id="modelBuilderGenerate"',
        'id="modelBuilderTrusted"',
        'id="modelBuilderPreview"',
        'id="modelBuilderValidate"',
        'id="modelBuilderSave"',
    ):
        assert token in html, token

    for token in (
        "analyzeResearchModel",
        "generateResearchModel",
        "runResearchModelPreview",
        "validateResearchModelAdapter",
        "saveResearchModelToProject",
        "renderModelBuilder",
        "collectModelBuilderParameters",
        "syncModelSpecFromReview",
        "model_builder_choose_source",
        "model_builder_analyze",
        "model_builder_generate",
        "model_builder_run",
        "model_builder_validate",
        "save_model_builder_bundle",
    ):
        assert token in js, token
    assert "trust this local Python source" in html
    assert "Adapter equivalence" in html

    resources = conf["bundle"]["resources"]
    assert "resources/ui/physical_lab_model_builder.py" in resources

    print("Research Model Builder wiring validation: PASS")
    print("- native desktop navigation + deterministic ModelSpec review UI wired")
    print("- static analyze/generate bridge wired")
    print("- explicit trusted preview/adapter validation wired")
    print("- canonical Project model-bundle save wired")
    print("- packaged Python core resource wired")
    print("Boundary: MVP is local trusted-code tooling; public arbitrary-code execution is not implemented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
