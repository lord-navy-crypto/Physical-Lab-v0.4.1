#!/usr/bin/env python3
"""Deterministic validation for Physical Lab's local-only AI bridge.

No model runtime, network access, or model download is required. The checks
exercise capability gating, structured provenance, image bounds, and the exact
Ollama-compatible message shape using an in-process fake transport.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "src-tauri/resources/ui/physical_lab_local_ai.py"

spec = importlib.util.spec_from_file_location("physical_lab_local_ai", MODULE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit("Could not load physical_lab_local_ai.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeUpload:
    def __init__(self, name: str, mime: str, data: bytes):
        self.name = name
        self.type = mime
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


# Structured physics context keeps provenance explicit and does not infer units
# for controls that are absent from the guide.
context = mod.build_physics_context(
    "radia-magnet-studio",
    {
        "current_params": {"gap_mm": 12.0, "br_t": 1.2},
        "metrics": {"K_peak": 1.1, "Bperp_peak_T": 0.24},
        "classification": "undulator-like",
    },
    {"cfg_gap_mm": 12.0, "cfg_br_t": 1.2},
)
assert context["schema"] == "physical-lab-local-ai-context-v3"
assert "VISUAL OBSERVATIONS" in context["provenanceRules"]
assert context["parameterGuide"]["cfg_gap_mm"]["unit"] == "mm"
assert "latestResultSummary" in context

# Capability gate is based on /api/show metadata, not model-name guessing.
original_request = mod._request_json
try:
    mod._request_json = lambda base, path, payload=None, timeout=8.0: {
        "capabilities": ["completion", "vision"]
    }
    info = mod.inspect_local_model("http://127.0.0.1:11434", "local-vision-model")
    assert info["vision"] is True
    assert info["reported"] is True

    mod._request_json = lambda base, path, payload=None, timeout=8.0: {
        "capabilities": ["completion"]
    }
    info = mod.inspect_local_model("http://127.0.0.1:11434", "local-text-model")
    assert info["vision"] is False
    assert info["reported"] is True
finally:
    mod._request_json = original_request

# Vision uploads are bounded and their metadata is kept separate from base64 data.
images, metadata = mod._prepare_vision_images([
    FakeUpload("plot.png", "image/png", b"tiny-local-test-image"),
])
assert len(images) == 1 and isinstance(images[0], str)
assert metadata[0]["name"] == "plot.png"
assert metadata[0]["provenance"] == "USER-SUPPLIED VISUAL CONTEXT"

try:
    mod._prepare_vision_images([FakeUpload("notes.txt", "text/plain", b"not an image")])
except ValueError:
    pass
else:
    raise AssertionError("Non-image upload should be rejected")

# Request-shape check: images are attached only when the caller explicitly supplies
# them after the UI capability gate. Text-only calls do not gain an images field.
captured = []
try:
    def fake_request(base, path, payload=None, timeout=8.0):
        captured.append((base, path, payload))
        return {"message": {"content": "validated"}}

    mod._request_json = fake_request
    answer = mod.ask_local_model(
        "http://127.0.0.1:11434",
        "local-vision-model",
        "Explain this plot.",
        context,
        images=[images[0]],
    )
    assert answer == "validated"
    user_message = captured[-1][2]["messages"][-1]
    assert user_message["images"] == [images[0]]

    captured.clear()
    mod.ask_local_model(
        "http://127.0.0.1:11434",
        "local-text-model",
        "Explain the parameters.",
        context,
    )
    user_message = captured[-1][2]["messages"][-1]
    assert "images" not in user_message
finally:
    mod._request_json = original_request

print("Local AI bridge reference validation: PASS")
print("Context schema: physical-lab-local-ai-context-v3")
print("Capability-gated local vision: configured")
print("Structured solver context remains authoritative over visual estimates")


# Every supported research Lab now has an explicit advanced-control guide. This
# protects the Tutor from falling back to variable-name guessing for Physical
# Lab's own experiment controls.
expected_profiles = {
    "numerical-methods", "ising-monte-carlo", "random-walk-monte-carlo",
    "nonlinear-chaos", "oscillation-integration", "radia-magnet-studio",
    "radiation-platform",
}
assert expected_profiles <= set(mod.ADVANCED_PARAMETER_GUIDES)
for profile in expected_profiles:
    entries = mod.ADVANCED_PARAMETER_GUIDES[profile]
    assert len(entries) >= 3, (profile, len(entries))
    for key, meta in entries.items():
        assert key.startswith("pl_"), (profile, key)
        assert isinstance(meta.get("unit"), str) and meta["unit"].strip(), (profile, key, "unit")
        assert isinstance(meta.get("meaning"), str) and meta["meaning"].strip(), (profile, key, "meaning")

merged = mod._parameter_guide(
    "numerical-methods",
    {"pl_n_xmax": 100.0, "pl_n_micro_n": 50},
)
assert merged["pl_n_xmax"]["unit"] == "rad"
assert merged["pl_n_micro_n"]["unit"] == "Taylor terms"
assert merged["pl_n_micro_n"]["meaning"].strip()

merged_rad = mod._parameter_guide(
    "radia-magnet-studio",
    {"cfg_gap_mm": 12.0, "pl_m_seeds": 4},
)
assert merged_rad["cfg_gap_mm"]["unit"] == "mm"
assert merged_rad["pl_m_seeds"]["unit"] == "independent RNG seeds"

print("Seven-Lab advanced parameter guide coverage: PASS")


# Parameter Explorer exposes only documented controls that actually exist in the
# current session and preserves their source/units without mutating state.
explorer_state = {"pl_o_force": 0.6, "pl_o_e_dt": 0.01, "unrelated": 123}
explorer_before = dict(explorer_state)
rows = mod._current_parameter_rows("oscillation-integration", explorer_state)
assert explorer_state == explorer_before
by_key = {row["parameter"]: row for row in rows}
assert set(by_key) == {"pl_o_force", "pl_o_e_dt"}
assert by_key["pl_o_force"]["unit"] == "N"
assert by_key["pl_o_force"]["source"] == "Physical Lab advanced"
assert by_key["pl_o_e_dt"]["unit"] == "s/step"
assert all(row["meaning"].strip() for row in rows)
print("Read-only Parameter Explorer: PASS")


# Explicit AI provenance saving is opt-in, constrained to the managed workspaces
# root, hashes the structured context, and never reclassifies advice as evidence.
import os as _os
import json as _json
import tempfile as _tempfile
from pathlib import Path as _Path

_old_data_dir = _os.environ.get("PHYSICAL_LAB_DATA_DIR")
try:
    with _tempfile.TemporaryDirectory() as _td:
        _os.environ["PHYSICAL_LAB_DATA_DIR"] = _td
        _root = _Path(_td) / "workspaces"
        _ws = _root / "test-project.physlab"
        _ws.mkdir(parents=True)
        (_ws / "project.json").write_text(
            _json.dumps({"id": "test-project", "name": "Test Project"}),
            encoding="utf-8",
        )
        _listed = mod.list_local_workspaces()
        assert len(_listed) == 1
        assert _listed[0]["id"] == "test-project"
        _note = mod.save_ai_research_note(
            _listed[0]["path"],
            profile="numerical-methods",
            runtime_label="External Ollama",
            runtime_base="http://127.0.0.1:11434",
            model="test-local-model",
            question="Explain this parameter",
            answer="Advisory explanation",
            context={"schema": "physical-lab-local-ai-context-v3", "value": 1.0},
            user_note="validation note",
        )
        _record = _json.loads(_Path(_note).read_text(encoding="utf-8"))
        assert _record["schema"] == "physical-lab-local-ai-note-v1"
        assert _record["classification"] == "AI ADVISORY NOTE"
        assert len(_record["contextSha256"]) == 64
        assert _Path(_note).parent == _ws / "provenance" / "ai-notes"
        try:
            mod.save_ai_research_note(
                _td,
                profile="numerical-methods",
                runtime_label="x",
                runtime_base="loopback",
                model="m",
                question="q",
                answer="a",
                context={},
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Unmanaged AI-note destination should be rejected")
finally:
    if _old_data_dir is None:
        _os.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
    else:
        _os.environ["PHYSICAL_LAB_DATA_DIR"] = _old_data_dir

print("Opt-in .physlab AI provenance notes: PASS")
