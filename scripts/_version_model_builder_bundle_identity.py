#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def patch_once(path,old,new):
    text=path.read_text(encoding='utf-8')
    count=text.count(old)
    if count!=1: raise SystemExit(f'guard failed {path}: {count} matches')
    path.write_text(text.replace(old,new,1),encoding='utf-8')

core=ROOT/'src-tauri/resources/ui/physical_lab_model_builder.py'
patch_once(core,'''def _sha256(path: Path) -> str:\n    h = hashlib.sha256()\n    with path.open("rb") as fh:\n        for chunk in iter(lambda: fh.read(1024 * 1024), b""):\n            h.update(chunk)\n    return h.hexdigest()\n\n\n''','''def _sha256(path: Path) -> str:\n    h = hashlib.sha256()\n    with path.open("rb") as fh:\n        for chunk in iter(lambda: fh.read(1024 * 1024), b""):\n            h.update(chunk)\n    return h.hexdigest()\n\n\ndef _sha256_json(value: Any) -> str:\n    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")\n    return hashlib.sha256(payload).hexdigest()\n\n\n''')
old='''    name = str(spec.get("metadata", {}).get("name") or path.stem)\n    bundle_id = f"model-{_slug(name)}-{_sha256(path)[:12]}"\n    root = Path(output_root).expanduser().resolve() / bundle_id\n'''
new='''    name = str(spec.get("metadata", {}).get("name") or path.stem)\n    source_digest = _sha256(path)\n    reviewed_spec_digest = _sha256_json(spec)\n    bundle_id = f"model-{_slug(name)}-{source_digest[:10]}-{reviewed_spec_digest[:10]}"\n    root = Path(output_root).expanduser().resolve() / bundle_id\n'''
patch_once(core,old,new)
patch_once(core,'''        "source_sha256": _sha256(path),\n        "adapter_sha256": _sha256(root / "adapter.py"),\n''','''        "source_sha256": source_digest,\n        "reviewed_model_spec_sha256": reviewed_spec_digest,\n        "adapter_sha256": _sha256(root / "adapter.py"),\n''')

val=ROOT/'scripts/model_builder_validation.py'
anchor='''        provenance = json.loads((bundle_path / "provenance.json").read_text())\n        assert provenance["generation_policy"] == "wrapper-not-rewrite"\n        assert provenance["original_source_modified"] is False\n\n'''
addition=anchor+'''        revised_spec = json.loads(json.dumps(spec))\n        revised_spec["parameters"][0]["max"] = 12.0\n        revised_bundle = core.generate_bundle(str(static_source), revised_spec, str(root / "bundles"))\n        assert revised_bundle["bundle_id"] != bundle["bundle_id"], "reviewed ModelSpec change reused a bundle identity"\n        assert revised_bundle["source_sha256"] == bundle["source_sha256"]\n        assert revised_bundle["reviewed_model_spec_sha256"] != bundle["reviewed_model_spec_sha256"]\n\n'''
patch_once(val,anchor,addition)
patch_once(val,'''    print("- sliders require explicit human-confirmed ranges")\n''','''    print("- sliders require explicit human-confirmed ranges")\n    print("- bundle identity changes when reviewed ModelSpec changes, even with identical source")\n''')

doc=ROOT/'docs/RESEARCH_MODEL_BUILDER_MVP.md'
patch_once(doc,'''- `provenance.json` — source, adapter and ModelSpec fingerprints plus generation policy.\n''','''- `provenance.json` — source, reviewed-ModelSpec, adapter and stored-ModelSpec fingerprints plus generation policy.\n\nBundle identity includes both the source fingerprint and the reviewed ModelSpec fingerprint. Editing units, ranges, controls or other reviewed interface metadata therefore creates a new bundle identity instead of silently overwriting a prior interface version built from the same scientific source.\n''')

readme=ROOT/'README.md'
patch_once(readme,'''Generation never overwrites the selected source file. A generated bundle contains an `original_model.py` snapshot plus separate `adapter.py`, `model.json`, `ui.json`, `tests.json` and `provenance.json`, each with source/model fingerprints where applicable. Slider bounds are never invented automatically: ranges and scientific units remain human-confirmed metadata.\n''','''Generation never overwrites the selected source file. A generated bundle contains an `original_model.py` snapshot plus separate `adapter.py`, `model.json`, `ui.json`, `tests.json` and `provenance.json`, each with source/model fingerprints where applicable. Bundle identity includes both source and reviewed-ModelSpec fingerprints, so a changed interface review cannot silently overwrite an earlier bundle made from the same scientific source. Slider bounds are never invented automatically: ranges and scientific units remain human-confirmed metadata.\n''')

changelog=ROOT/'CHANGELOG.md'
patch_once(changelog,'''- Added wrapper-not-rewrite generation of `original_model.py`, `adapter.py`, `model.json`, `ui.json`, `tests.json` and `provenance.json` with deterministic fingerprints.\n''','''- Added wrapper-not-rewrite generation of `original_model.py`, `adapter.py`, `model.json`, `ui.json`, `tests.json` and `provenance.json` with deterministic fingerprints; bundle identity includes both source and reviewed-ModelSpec fingerprints so interface revisions do not silently overwrite prior bundles.\n''')

print('Model Builder bundle identity versioning applied')
