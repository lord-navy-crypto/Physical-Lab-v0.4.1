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
