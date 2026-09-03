#!/usr/bin/env python3
"""One-time patch: explicit .physlab provenance saving for Local AI exchanges."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "src-tauri/resources/ui/physical_lab_local_ai.py"
VALIDATION = ROOT / "scripts/local_ai_reference_validation.py"
DOC = ROOT / "docs/LOCAL_AI_TUTOR.md"

text = AI.read_text(encoding="utf-8")
text = text.replace(
    "import base64\nimport json\nimport math\nimport os\nfrom typing import Any, Mapping\n",
    "import base64\nimport hashlib\nimport json\nimport math\nimport os\nfrom datetime import datetime, timezone\nfrom pathlib import Path\nfrom typing import Any, Mapping\n",
    1,
)
if "MAX_AI_NOTE_ANSWER_CHARS" not in text:
    text = text.replace(
        'MAX_VISION_IMAGES = 2\n_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}\n',
        'MAX_VISION_IMAGES = 2\nMAX_AI_NOTE_ANSWER_CHARS = 200_000\n_ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}\n',
        1,
    )

helpers = r'''


def _workspaces_root_from_environment() -> Path | None:
    raw = os.environ.get("PHYSICAL_LAB_DATA_DIR", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve() / "workspaces"


def list_local_workspaces() -> list[dict[str, str]]:
    """List .physlab workspaces exposed to this local Lab process by Tauri."""
    root = _workspaces_root_from_environment()
    if root is None or not root.is_dir():
        return []
    output: list[dict[str, str]] = []
    for path in sorted(root.glob("*.physlab"), key=lambda p: p.name.lower()):
        if not path.is_dir():
            continue
        name = path.stem
        workspace_id = path.stem
        project = path / "project.json"
        try:
            data = json.loads(project.read_text(encoding="utf-8"))
            if isinstance(data, Mapping):
                raw_name = data.get("name")
                raw_id = data.get("id")
                if isinstance(raw_name, str) and raw_name.strip():
                    name = raw_name.strip()
                if isinstance(raw_id, str) and raw_id.strip():
                    workspace_id = raw_id.strip()
        except Exception:
            pass
        output.append({"id": workspace_id, "name": name, "path": str(path.resolve())})
    return output


def save_ai_research_note(
    workspace_path: str,
    *,
    profile: str,
    runtime_label: str,
    runtime_base: str,
    model: str,
    question: str,
    answer: str,
    context: Mapping[str, Any],
    user_note: str = "",
) -> str:
    """Persist one explicit advisory exchange under <workspace>/provenance/ai-notes/."""
    root = _workspaces_root_from_environment()
    if root is None or not root.is_dir():
        raise RuntimeError("Physical Lab workspace root is unavailable in this Lab process")
    root = root.resolve()
    workspace = Path(workspace_path).expanduser().resolve()
    try:
        workspace.relative_to(root)
    except ValueError as exc:
        raise ValueError("AI notes can only be saved inside the managed Physical Lab workspaces directory") from exc
    if workspace.parent != root or workspace.suffix != ".physlab" or not workspace.is_dir():
        raise ValueError("Choose an existing top-level .physlab workspace")

    plain_context = _plain(context)
    canonical_context = json.dumps(plain_context, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    context_hash = hashlib.sha256(canonical_context.encode("utf-8")).hexdigest()
    answer_text = str(answer)
    truncated = len(answer_text) > MAX_AI_NOTE_ANSWER_CHARS
    if truncated:
        answer_text = answer_text[:MAX_AI_NOTE_ANSWER_CHARS]

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%S.%fZ")
    notes_dir = workspace / "provenance" / "ai-notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    destination = notes_dir / f"{stamp}-{profile}-local-ai.json"
    record = {
        "schema": "physical-lab-local-ai-note-v1",
        "createdUtc": now.isoformat(),
        "classification": "AI ADVISORY NOTE",
        "scientificAuthority": "Not a measurement, solver result, fitted quantity, or validation record. Preserve the linked structured context and verify claims against Physical Lab evidence.",
        "profile": profile,
        "runtime": {"label": runtime_label, "base": runtime_base},
        "model": model,
        "question": str(question),
        "answer": answer_text,
        "answerTruncated": truncated,
        "userNote": str(user_note).strip(),
        "contextSha256": context_hash,
        "context": plain_context,
    }
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return str(destination)
'''
anchor = "\ndef render_local_ai_assistant(st: Any, profile: str, namespace: Mapping[str, Any]) -> None:\n"
if "def save_ai_research_note(" not in text:
    if text.count(anchor) != 1:
        raise SystemExit("AI research-note helper anchor missing or ambiguous")
    text = text.replace(anchor, helpers + anchor, 1)

old_exchange = '''                st.session_state[f"pl_local_ai_answer_{profile}"] = answer\n            except Exception as exc:\n                st.error(f"Local AI request failed: {exc}")\n'''
new_exchange = '''                st.session_state[f"pl_local_ai_answer_{profile}"] = answer\n                st.session_state[f"__physical_lab_ai_exchange_{profile}"] = {\n                    "profile": profile,\n                    "runtimeLabel": engine["label"],\n                    "runtimeBase": engine["base"],\n                    "model": model,\n                    "question": question,\n                    "answer": answer,\n                    "context": _plain(context),\n                }\n            except Exception as exc:\n                st.error(f"Local AI request failed: {exc}")\n'''
if old_exchange in text:
    text = text.replace(old_exchange, new_exchange, 1)
elif "__physical_lab_ai_exchange_" not in text:
    raise SystemExit("AI exchange snapshot anchor missing")

old_tail = '''        answer = st.session_state.get(f"pl_local_ai_answer_{profile}")\n        if answer:\n            st.markdown("#### Explanation")\n            st.write(answer)\n            st.caption("AI explanation is advisory. Check units, model assumptions, measured data, uncertainty and solver validation before drawing scientific conclusions.")\n'''
new_tail = '''        answer = st.session_state.get(f"pl_local_ai_answer_{profile}")\n        if answer:\n            st.markdown("#### Explanation")\n            st.write(answer)\n            st.caption("AI explanation is advisory. Check units, model assumptions, measured data, uncertainty and solver validation before drawing scientific conclusions.")\n\n            exchange = st.session_state.get(f"__physical_lab_ai_exchange_{profile}")\n            workspaces = list_local_workspaces()\n            if isinstance(exchange, Mapping) and workspaces:\n                with st.expander("Save this exchange to .physlab provenance", expanded=False):\n                    st.caption(\n                        "Nothing is saved automatically. This writes a JSON advisory note under the selected project's provenance/ai-notes folder. "\n                        "It is explicitly labeled as AI advice and is not mixed with measured data or solver results."\n                    )\n                    workspace_labels = [f"{item['name']} · {item['id']}" for item in workspaces]\n                    workspace_label = st.selectbox(\n                        "Research workspace", workspace_labels, key=f"pl_local_ai_note_workspace_{profile}"\n                    )\n                    workspace = workspaces[workspace_labels.index(workspace_label)]\n                    research_note = st.text_input(\n                        "Optional research note",\n                        placeholder="Why is this explanation or scan idea worth preserving?",\n                        key=f"pl_local_ai_note_text_{profile}",\n                    )\n                    if st.button("Save advisory note to .physlab", key=f"pl_local_ai_save_note_{profile}", width="stretch"):\n                        try:\n                            saved = save_ai_research_note(\n                                workspace["path"],\n                                profile=str(exchange.get("profile") or profile),\n                                runtime_label=str(exchange.get("runtimeLabel") or "local runtime"),\n                                runtime_base=str(exchange.get("runtimeBase") or "loopback"),\n                                model=str(exchange.get("model") or model),\n                                question=str(exchange.get("question") or ""),\n                                answer=str(exchange.get("answer") or answer),\n                                context=exchange.get("context") if isinstance(exchange.get("context"), Mapping) else {},\n                                user_note=research_note,\n                            )\n                            st.success(f"Saved advisory provenance note: {saved}")\n                        except Exception as exc:\n                            st.error(f"Could not save AI research note: {exc}")\n'''
if "Save this exchange to .physlab provenance" not in text:
    if text.count(old_tail) != 1:
        raise SystemExit("AI explanation tail anchor missing or ambiguous")
    text = text.replace(old_tail, new_tail, 1)
AI.write_text(text, encoding="utf-8")

validation = VALIDATION.read_text(encoding="utf-8")
block = r'''

# Explicit AI provenance saving uses only the managed workspaces root, is opt-in,
# preserves a hash of the exact structured context, and labels the record as AI.
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
        (_ws / "project.json").write_text(_json.dumps({"id": "test-project", "name": "Test Project"}), encoding="utf-8")
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
                profile="numerical-methods", runtime_label="x", runtime_base="loopback", model="m",
                question="q", answer="a", context={},
            )
        except ValueError:
            pass
        else:
            raise AssertionError("AI note path traversal / unmanaged destination should be rejected")
finally:
    if _old_data_dir is None:
        _os.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
    else:
        _os.environ["PHYSICAL_LAB_DATA_DIR"] = _old_data_dir

print("Opt-in .physlab AI provenance notes: PASS")
'''
if "Opt-in .physlab AI provenance notes: PASS" not in validation:
    validation += block
VALIDATION.write_text(validation, encoding="utf-8")

doc = DOC.read_text(encoding="utf-8")
section = r'''

## Opt-in AI research provenance

After a successful Local AI response, Physical Lab may offer **Save this exchange to .physlab provenance** when managed workspaces are available. Saving is always an explicit user action. The JSON record is written to `<workspace>.physlab/provenance/ai-notes/` and includes the Lab profile, local runtime/model, question, answer, optional human research note, a bounded copy of the structured context, and a SHA-256 hash of that context. The record is classified as `AI ADVISORY NOTE` and explicitly states that it is not a measurement, solver result, fit, or validation record. Screenshot bytes are not written by this feature; only the structured context used by the Tutor is preserved.
'''
if "## Opt-in AI research provenance" not in doc:
    doc += section
DOC.write_text(doc, encoding="utf-8")
print("v0.65 AI research provenance patch: APPLIED")
