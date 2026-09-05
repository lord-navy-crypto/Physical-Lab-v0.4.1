#!/usr/bin/env python3
"""Physical Lab Research Model Builder core.

The builder preserves the student's original scientific source by default. Static
analysis never imports or executes the uploaded file. Generation copies the source
into a model bundle and creates a deterministic adapter + ModelSpec around it.
Execution is a separate, explicit local action.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MODEL_SPEC_SCHEMA = "physical-lab-model-spec-v1"
BUNDLE_SCHEMA = "physical-lab-model-bundle-v1"
VALIDATION_SCHEMA = "physical-lab-model-adapter-validation-v1"
MAX_SOURCE_BYTES = 2_000_000
PREFERRED_ENTRY_NAMES = ("simulate", "run_simulation", "run_model", "compute", "model")
RISK_IMPORTS = {
    "os": "operating-system access",
    "subprocess": "process execution",
    "socket": "network sockets",
    "ctypes": "native-memory/native-library access",
    "shutil": "filesystem mutation",
    "requests": "network access",
    "urllib": "network access",
    "http": "network access",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_path(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if path.suffix.lower() != ".py":
        raise ValueError("Research Model Builder MVP accepts one .py source file at a time.")
    if not path.is_file():
        raise ValueError(f"Python source file does not exist: {path}")
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Python source exceeds the 2 MB MVP analysis limit.")
    return path


def _literal(node: ast.AST | None) -> Any:
    if node is None:
        return None
    try:
        value = ast.literal_eval(node)
    except Exception:
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return None


def _annotation(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


def _import_roots(tree: ast.AST) -> list[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return sorted(roots)


def _return_candidates(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for node in ast.walk(function):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        value = node.value
        if isinstance(value, ast.Dict):
            for key in value.keys:
                label = _literal(key)
                if isinstance(label, str):
                    results.append({"name": label, "kind": "auto"})
            if results:
                return _dedupe_outputs(results)
        if isinstance(value, (ast.Tuple, ast.List)):
            for idx, element in enumerate(value.elts):
                name = element.id if isinstance(element, ast.Name) else f"output_{idx + 1}"
                results.append({"name": name, "kind": "auto"})
            if results:
                return _dedupe_outputs(results)
        if isinstance(value, ast.Name):
            results.append({"name": value.id, "kind": "auto"})
        else:
            results.append({"name": "result", "kind": "auto"})
    return _dedupe_outputs(results) or [{"name": "result", "kind": "auto"}]


def _dedupe_outputs(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in outputs:
        name = str(row.get("name") or "result")
        if name in seen:
            continue
        seen.add(name)
        deduped.append({"name": name, "label": name.replace("_", " ").title(), "kind": row.get("kind", "auto")})
    return deduped


def _function_record(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, Any]:
    positional = list(node.args.posonlyargs) + list(node.args.args)
    defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
    parameters: list[dict[str, Any]] = []
    for arg, default_node in zip(positional, defaults):
        if arg.arg in {"self", "cls"}:
            continue
        default = _literal(default_node)
        annotation = _annotation(arg.annotation)
        inferred_type = "number" if isinstance(default, (int, float)) and not isinstance(default, bool) else "boolean" if isinstance(default, bool) else "text" if isinstance(default, str) else "auto"
        parameters.append({
            "name": arg.arg,
            "label": arg.arg.replace("_", " ").title(),
            "annotation": annotation,
            "default": default,
            "required": default_node is None,
            "type": inferred_type,
            "unit": None,
            "control": "toggle" if inferred_type == "boolean" else "number" if inferred_type == "number" else "text",
            "min": None,
            "max": None,
        })
    if node.args.vararg:
        parameters.append({"name": f"*{node.args.vararg.arg}", "unsupported": True})
    if node.args.kwarg:
        parameters.append({"name": f"**{node.args.kwarg.arg}", "unsupported": True})
    return {
        "name": node.name,
        "async": isinstance(node, ast.AsyncFunctionDef),
        "line": getattr(node, "lineno", None),
        "docstring": ast.get_docstring(node),
        "parameters": parameters,
        "outputs": _return_candidates(node),
    }


def _choose_entry(functions: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_name = {f["name"]: f for f in functions}
    for name in PREFERRED_ENTRY_NAMES:
        if name in by_name:
            return by_name[name]
    for function in functions:
        if not str(function["name"]).startswith("_"):
            return function
    return functions[0] if functions else None


def analyze_source(source: str) -> dict[str, Any]:
    path = _source_path(source)
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        raise ValueError(f"Python syntax error at line {exc.lineno}: {exc.msg}") from exc
    functions = [_function_record(node) for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    imports = _import_roots(tree)
    entry = _choose_entry(functions)
    warnings: list[dict[str, str]] = []
    for root in imports:
        if root in RISK_IMPORTS:
            warnings.append({"kind": "execution-risk", "message": f"Import '{root}' can provide {RISK_IMPORTS[root]}. Static analysis is safe, but local execution should only be enabled for trusted code."})
    if not entry:
        warnings.append({"kind": "entrypoint", "message": "No top-level function was found. Add a callable such as simulate(parameters) or choose Advanced Mode later."})
    elif entry.get("async"):
        warnings.append({"kind": "entrypoint", "message": "The candidate entry function is async; MVP execution supports synchronous functions only."})
    if any(p.get("unsupported") for p in (entry or {}).get("parameters", [])):
        warnings.append({"kind": "signature", "message": "*args/**kwargs were detected. Automatic adapter generation requires explicit named parameters in MVP."})
    candidate_spec = None
    if entry:
        parameters = [p for p in entry["parameters"] if not p.get("unsupported")]
        mapping_convention = len(parameters) == 1 and parameters[0]["name"] in {"params", "parameters", "config"}
        candidate_spec = {
            "schema": MODEL_SPEC_SCHEMA,
            "version": 1,
            "metadata": {
                "name": path.stem.replace("_", " ").title(),
                "description": "",
                "source_file": path.name,
                "source_sha256": _sha256(path),
            },
            "compute": {
                "entry_function": entry["name"],
                "calling_convention": "mapping" if mapping_convention else "keyword-arguments",
            },
            "parameters": parameters,
            "outputs": entry["outputs"],
            "visualizations": [],
            "assumptions": [],
            "validation": {"reference_tests": [], "sanity_tests": []},
            "documentation": {"notes": "Generated as a candidate ModelSpec. Units, ranges, scientific meaning and validation require human confirmation."},
        }
    return {
        "schema": "physical-lab-model-analysis-v1",
        "source": str(path),
        "source_sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "imports": imports,
        "functions": functions,
        "candidate_entry": entry["name"] if entry else None,
        "candidate_model_spec": candidate_spec,
        "warnings": warnings,
        "execution_boundary": "Analysis is static AST inspection only. The source file was not imported or executed.",
    }


def validate_model_spec(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("schema") != MODEL_SPEC_SCHEMA:
        raise ValueError(f"ModelSpec schema must be {MODEL_SPEC_SCHEMA}")
    compute = spec.get("compute") or {}
    if not isinstance(compute.get("entry_function"), str) or not compute["entry_function"].strip():
        raise ValueError("ModelSpec.compute.entry_function is required")
    if compute.get("calling_convention") not in {"keyword-arguments", "mapping"}:
        raise ValueError("ModelSpec.compute.calling_convention must be keyword-arguments or mapping")
    params = spec.get("parameters")
    if not isinstance(params, list):
        raise ValueError("ModelSpec.parameters must be a list")
    names: set[str] = set()
    for row in params:
        if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"]:
            raise ValueError("Every parameter needs a non-empty name")
        if row["name"] in names:
            raise ValueError(f"Duplicate parameter: {row['name']}")
        names.add(row["name"])
        if row.get("control") not in {"slider", "number", "toggle", "dropdown", "text"}:
            raise ValueError(f"Unsupported control for {row['name']}")
        if row.get("control") == "slider" and (row.get("min") is None or row.get("max") is None):
            raise ValueError(f"Slider {row['name']} requires explicit min and max")
    outputs = spec.get("outputs")
    if not isinstance(outputs, list) or not outputs:
        raise ValueError("ModelSpec.outputs must contain at least one output")
    return spec


def _slug(value: str) -> str:
    out = []
    for ch in value.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "_", "-", "."} and (not out or out[-1] != "-"):
            out.append("-")
    slug = "".join(out).strip("-._")
    return slug or "research-model"


def _ui_spec(model_spec: dict[str, Any]) -> dict[str, Any]:
    visualizations = list(model_spec.get("visualizations") or [])
    if not visualizations:
        outputs = model_spec.get("outputs") or []
        if len(outputs) >= 2:
            visualizations.append({"kind": "auto", "outputs": [o.get("name") for o in outputs[:2]], "title": "Primary outputs"})
        elif outputs:
            visualizations.append({"kind": "auto", "outputs": [outputs[0].get("name")], "title": outputs[0].get("label") or outputs[0].get("name")})
    return {
        "schema": "physical-lab-ui-spec-v1",
        "parameters": model_spec.get("parameters") or [],
        "outputs": model_spec.get("outputs") or [],
        "visualizations": visualizations,
        "renderer": "physical-lab-deterministic-generic-v1",
    }


def _adapter_source(entry_function: str, convention: str) -> str:
    return f'''"""Generated Physical Lab adapter. The original model snapshot remains separate."""\nfrom __future__ import annotations\nimport importlib.util\nfrom pathlib import Path\n\n_SOURCE = Path(__file__).with_name("original_model.py")\n_spec = importlib.util.spec_from_file_location("physical_lab_student_model", _SOURCE)\nif _spec is None or _spec.loader is None:\n    raise RuntimeError("Could not load original model snapshot")\n_model = importlib.util.module_from_spec(_spec)\n_spec.loader.exec_module(_model)\n_entry = getattr(_model, {entry_function!r})\n\ndef physical_lab_run(parameters):\n    if not isinstance(parameters, dict):\n        raise TypeError("Physical Lab adapter parameters must be a mapping")\n    if {convention!r} == "mapping":\n        return _entry(parameters)\n    return _entry(**parameters)\n'''


def generate_bundle(source: str, spec: dict[str, Any], output_root: str) -> dict[str, Any]:
    path = _source_path(source)
    spec = validate_model_spec(spec)
    if spec.get("metadata", {}).get("source_sha256") not in {None, _sha256(path)}:
        raise ValueError("ModelSpec source_sha256 does not match the selected source file")
    name = str(spec.get("metadata", {}).get("name") or path.stem)
    bundle_id = f"model-{_slug(name)}-{_sha256(path)[:12]}"
    root = Path(output_root).expanduser().resolve() / bundle_id
    root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, root / "original_model.py")
    entry = spec["compute"]["entry_function"]
    convention = spec["compute"]["calling_convention"]
    (root / "adapter.py").write_text(_adapter_source(entry, convention), encoding="utf-8")
    (root / "model.json").write_text(json.dumps(spec, indent=2, sort_keys=True), encoding="utf-8")
    (root / "ui.json").write_text(json.dumps(_ui_spec(spec), indent=2, sort_keys=True), encoding="utf-8")
    tests = {
        "schema": "physical-lab-model-tests-v1",
        "adapter_equivalence": {"enabled": True, "rtol": 1e-9, "atol": 1e-12},
        "scientific_reference_tests": spec.get("validation", {}).get("reference_tests", []),
        "scientific_sanity_tests": spec.get("validation", {}).get("sanity_tests", []),
        "boundary": "Generated adapter-equivalence tests establish interface consistency only; they do not establish scientific validity.",
    }
    (root / "tests.json").write_text(json.dumps(tests, indent=2, sort_keys=True), encoding="utf-8")
    provenance = {
        "schema": BUNDLE_SCHEMA,
        "bundle_id": bundle_id,
        "source_snapshot": "original_model.py",
        "source_sha256": _sha256(path),
        "adapter_sha256": _sha256(root / "adapter.py"),
        "model_spec_sha256": _sha256(root / "model.json"),
        "generation_policy": "wrapper-not-rewrite",
        "original_source_modified": False,
        "execution_policy": "No execution occurs during generation. Preview/validation is explicit local execution of trusted code.",
    }
    (root / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True), encoding="utf-8")
    return {**provenance, "bundle_path": str(root), "model_spec": spec, "ui_spec": _ui_spec(spec)}


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if hasattr(value, "tolist"):
        return _jsonable(value.tolist())
    if hasattr(value, "item"):
        try:
            return _jsonable(value.item())
        except Exception:
            pass
    return repr(value)


def _normalize_outputs(raw: Any, spec: dict[str, Any]) -> dict[str, Any]:
    names = [str(row.get("name") or f"output_{idx + 1}") for idx, row in enumerate(spec.get("outputs") or [])]
    if isinstance(raw, dict):
        return {str(k): _jsonable(v) for k, v in raw.items()}
    if isinstance(raw, (tuple, list)) and len(names) == len(raw):
        return {name: _jsonable(value) for name, value in zip(names, raw)}
    return {(names[0] if names else "result"): _jsonable(raw)}


def _load_bundle(bundle: str) -> tuple[Path, dict[str, Any]]:
    root = Path(bundle).expanduser().resolve()
    for filename in ("original_model.py", "adapter.py", "model.json", "provenance.json"):
        if not (root / filename).is_file():
            raise ValueError(f"Invalid model bundle: missing {filename}")
    spec = validate_model_spec(json.loads((root / "model.json").read_text(encoding="utf-8")))
    return root, spec


def run_bundle(bundle: str, parameters: dict[str, Any]) -> dict[str, Any]:
    root, spec = _load_bundle(bundle)
    adapter = _load_module(root / "adapter.py", "physical_lab_generated_adapter")
    raw = adapter.physical_lab_run(parameters)
    return {
        "schema": "physical-lab-model-preview-v1",
        "bundle_path": str(root),
        "parameters": parameters,
        "outputs": _normalize_outputs(raw, spec),
        "boundary": "Outputs come from explicit local execution of the bundled source snapshot through the generated adapter.",
    }


def _shape_signature(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _shape_signature(child) for key, child in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return {"type": "list", "length": len(value), "items": [_shape_signature(child) for child in value]}
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def _flatten_numeric(value: Any, prefix: str = "") -> dict[str, float]:
    out: dict[str, float] = {}
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        out[prefix or "value"] = float(value)
    elif isinstance(value, dict):
        for key, child in value.items():
            out.update(_flatten_numeric(child, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            out.update(_flatten_numeric(child, f"{prefix}[{idx}]" if prefix else f"[{idx}]"))
    return out


def validate_adapter(bundle: str, parameters: dict[str, Any], rtol: float = 1e-9, atol: float = 1e-12) -> dict[str, Any]:
    root, spec = _load_bundle(bundle)
    original = _load_module(root / "original_model.py", "physical_lab_original_model")
    adapter = _load_module(root / "adapter.py", "physical_lab_generated_adapter_validation")
    entry = getattr(original, spec["compute"]["entry_function"])
    if spec["compute"]["calling_convention"] == "mapping":
        original_raw = entry(parameters)
    else:
        original_raw = entry(**parameters)
    adapter_raw = adapter.physical_lab_run(parameters)
    original_outputs = _normalize_outputs(original_raw, spec)
    adapter_outputs = _normalize_outputs(adapter_raw, spec)
    original_numeric = _flatten_numeric(original_outputs)
    adapter_numeric = _flatten_numeric(adapter_outputs)
    common = sorted(set(original_numeric) & set(adapter_numeric))
    diffs = [abs(original_numeric[k] - adapter_numeric[k]) for k in common]
    max_abs_diff = max(diffs) if diffs else 0.0
    numeric_equivalent = all(math.isclose(original_numeric[k], adapter_numeric[k], rel_tol=rtol, abs_tol=atol) for k in common)
    same_structure = _shape_signature(original_outputs) == _shape_signature(adapter_outputs)
    numeric_paths_match = set(original_numeric) == set(adapter_numeric)
    equivalent = bool(numeric_equivalent and same_structure and numeric_paths_match)
    return {
        "schema": VALIDATION_SCHEMA,
        "equivalent": equivalent,
        "same_structure": same_structure,
        "numeric_paths_match": numeric_paths_match,
        "numeric_values_compared": len(common),
        "max_abs_diff": max_abs_diff,
        "rtol": rtol,
        "atol": atol,
        "original_outputs": original_outputs,
        "adapter_outputs": adapter_outputs,
        "boundary": "Adapter equivalence checks the generated interface against the same source snapshot. It is not scientific validation of equations, assumptions, parameters or reference truth.",
    }


def _read_json_arg(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze")
    analyze.add_argument("--source", required=True)
    generate = sub.add_parser("generate")
    generate.add_argument("--source", required=True)
    generate.add_argument("--spec-json", required=True)
    generate.add_argument("--output-root", required=True)
    run = sub.add_parser("run")
    run.add_argument("--bundle", required=True)
    run.add_argument("--parameters-json", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--bundle", required=True)
    validate.add_argument("--parameters-json", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "analyze":
            _emit(analyze_source(args.source))
        elif args.command == "generate":
            _emit(generate_bundle(args.source, _read_json_arg(args.spec_json), args.output_root))
        elif args.command == "run":
            _emit(run_bundle(args.bundle, _read_json_arg(args.parameters_json)))
        elif args.command == "validate":
            _emit(validate_adapter(args.bundle, _read_json_arg(args.parameters_json)))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "type": exc.__class__.__name__}, separators=(",", ":")), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
