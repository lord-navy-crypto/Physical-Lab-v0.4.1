#!/usr/bin/env python3
"""Acceptance checks for canonical-native Rust campaign metadata writes."""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src-tauri/src/research.rs"
LEGACY = ROOT / "src-tauri/src/research_legacy_impl.rs"

def compact(value: str) -> str:
    return "".join(value.split())

def function_block(text: str, name: str) -> str:
    marker = f"fn {name}("
    start = text.index(marker)
    brace = text.index("{", start)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{": depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0: return text[start:index + 1]
    raise AssertionError(name)

def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    legacy = LEGACY.read_text(encoding="utf-8")

    for helper in ("create_campaign_to_dir", "campaign_action_in_dir"):
        assert f"fn {helper}(" in source

    for command, helper in (
        ("create_campaign", "create_campaign_to_dir"),
        ("campaign_action", "campaign_action_in_dir"),
    ):
        block = compact(function_block(source, command))
        assert "resolve_project_dir" in block
        assert helper in block
        assert "ensure_alias_for_id" not in block
        assert "legacy::" not in block

    new_create = compact(function_block(source, "create_campaign_to_dir"))
    old_create = compact(function_block(legacy, "create_campaign"))
    for token in (
        'points<2||points>10_000',
        '"Campaignpointsmustbebetween2and10000."',
        '"physical-lab-campaign-v1"',
        '"run-{:04}"',
        '"status":"queued"',
        'max_parallel.clamp(1,8)',
        '"queueState":"ready"',
        '"execution":"queue-and-handoff"',
        'CurrentLabUIsremainsolverownersuntilmodule-specificparameteradaptersareadded.',
    ):
        assert token in new_create, token
    for token in (
        'points<2||points>10000',
        '"Campaignpointsmustbebetween2and10000."',
        '"physical-lab-campaign-v1"',
        '"run-{:04}"',
        '"status":"queued"',
        'max_parallel.clamp(1,8)',
        '"queueState":"ready"',
        '"execution":"queue-and-handoff"',
    ):
        assert token in old_create, token

    new_action = compact(function_block(source, "campaign_action_in_dir"))
    old_action = compact(function_block(legacy, "campaign_action"))
    for token in (
        '"pause"', '"paused"', '"resume"', '"ready"',
        '"retry-failed"', '"failed"', '"reset"', '"queued"',
        '"Supportedcampaignactions:pause,resume,retry-failed,reset"',
        'value["updatedAt"]',
    ):
        assert token in new_action, token
    for token in (
        '"pause"', '"paused"', '"resume"', '"ready"',
        '"retry-failed"', '"failed"', '"reset"', '"queued"',
        '"Supportedcampaignactions:pause,resume,retry-failed,reset"',
    ):
        assert token in old_action, token

    assert "touch_project_after_direct_write" in new_create
    assert "ifcanonical" in new_action
    assert "touch_project_after_direct_write" in new_action

    print("Physical Lab Rust canonical campaign writes: PASS")
    print("- campaign creation: direct canonical/legacy resolver, no alias")
    print("- campaign action state machine preserved")
    print("- point bounds / spacing / maxParallel contracts preserved")
    print("- canonical project updated_at write-through preserved")
    print("Boundary: campaign metadata remains queue/provenance state; it does not mean a solver ran or a scientific result was validated.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
