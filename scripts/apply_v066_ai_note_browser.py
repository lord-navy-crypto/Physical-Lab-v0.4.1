#!/usr/bin/env python3
"""One-time patch: read-only browser for saved Local AI advisory provenance."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "src-tauri/resources/ui/physical_lab_local_ai.py"
VALIDATION = ROOT / "scripts/local_ai_reference_validation.py"
DOC = ROOT / "docs/LOCAL_AI_TUTOR.md"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}; expected 1")
    return text.replace(old, new, 1)


text = AI.read_text(encoding="utf-8")
if "def list_ai_research_notes(" not in text:
    helper = r'''


def list_ai_research_notes(workspace_path: str, *, limit: int = 100) -> list[dict[str, Any]]:
    """Read bounded Local AI advisory notes and verify each saved context hash."""
    root = _workspaces_root_from_environment()
    if root is None or not root.is_dir():
        return []
    root = root.resolve()
    workspace = Path(workspace_path).expanduser().resolve()
    try:
        workspace.relative_to(root)
    except ValueError as exc:
        raise ValueError("AI notes can only be read from managed Physical Lab workspaces") from exc
    if workspace.parent != root or workspace.suffix != ".physlab" or not workspace.is_dir():
        raise ValueError("Choose an existing top-level .physlab workspace")

    notes_dir = workspace / "provenance" / "ai-notes"
    if not notes_dir.is_dir():
        return []
    bounded_limit = max(1, min(int(limit), 250))
    output: list[dict[str, Any]] = []
    for path in sorted(notes_dir.glob("*.json"), key=lambda item: item.name, reverse=True):
        if len(output) >= bounded_limit:
            break
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(record, Mapping):
            continue
        if record.get("schema") != "physical-lab-local-ai-note-v1":
            continue
        if record.get("classification") != "AI ADVISORY NOTE":
            continue
        context = record.get("context") if isinstance(record.get("context"), Mapping) else {}
        canonical_context = json.dumps(
            _plain(context),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        calculated_hash = hashlib.sha256(canonical_context.encode("utf-8")).hexdigest()
        saved_hash = str(record.get("contextSha256") or "")
        runtime = record.get("runtime") if isinstance(record.get("runtime"), Mapping) else {}
        output.append({
            "filename": path.name,
            "path": str(path.resolve()),
            "createdUtc": str(record.get("createdUtc") or ""),
            "profile": str(record.get("profile") or ""),
            "model": str(record.get("model") or ""),
            "runtimeLabel": str(runtime.get("label") or ""),
            "question": str(record.get("question") or ""),
            "answer": str(record.get("answer") or ""),
            "answerTruncated": bool(record.get("answerTruncated")),
            "userNote": str(record.get("userNote") or ""),
            "contextSha256": saved_hash,
            "contextHashValid": bool(saved_hash) and saved_hash == calculated_hash,
            "context": _plain(context),
            "classification": "AI ADVISORY NOTE",
        })
    return output
'''
    anchor = "\ndef render_local_ai_assistant(st: Any, profile: str, namespace: Mapping[str, Any]) -> None:"
    text = replace_once(text, anchor, helper + anchor, "AI note browser helper")

if "AI Research Notes Browser" not in text:
    anchor = '        question_key = f"pl_local_ai_question_{profile}"'
    ui = anchor + r'''

        workspace_catalog = list_local_workspaces()
        if workspace_catalog:
            with st.expander("AI Research Notes Browser · .physlab", expanded=False):
                st.caption(
                    "Read-only browser for previously saved AI ADVISORY NOTE records. Context hashes are recomputed on read so a changed/corrupted context is visible. "
                    "Reusing a question only copies text back into the Tutor; it does not run a model or alter experiment parameters."
                )
                browser_labels = [f"{item['name']} · {item['id']}" for item in workspace_catalog]
                browser_label = st.selectbox(
                    "Workspace notes",
                    browser_labels,
                    key=f"pl_local_ai_browser_workspace_{profile}",
                )
                browser_workspace = workspace_catalog[browser_labels.index(browser_label)]
                saved_notes = list_ai_research_notes(browser_workspace["path"])
                if not saved_notes:
                    st.info("No saved Local AI advisory notes in this workspace yet.")
                else:
                    st.caption(f"{len(saved_notes)} saved advisory note(s), newest first.")
                    note_labels = [
                        f"{note['createdUtc'] or note['filename']} · {note['model'] or 'local model'} · {note['profile'] or 'Lab'}"
                        for note in saved_notes
                    ]
                    note_label = st.selectbox(
                        "Saved advisory note",
                        note_labels,
                        key=f"pl_local_ai_browser_note_{profile}",
                    )
                    saved_note = saved_notes[note_labels.index(note_label)]
                    n1, n2, n3 = st.columns([1.3, 1.5, 1.2])
                    n1.metric("Classification", saved_note["classification"])
                    n2.metric("Model", saved_note["model"] or "unknown local model")
                    n3.metric("Context hash", "verified" if saved_note["contextHashValid"] else "MISMATCH")
                    if saved_note["contextHashValid"]:
                        st.success(f"Structured-context SHA-256 verified: {saved_note['contextSha256']}")
                    else:
                        st.warning(
                            "The stored context hash does not match the context currently inside this note. Treat this record as modified/corrupted until reviewed."
                        )
                    if saved_note["userNote"]:
                        st.info(f"Human research note: {saved_note['userNote']}")
                    st.markdown("**Saved question**")
                    st.write(saved_note["question"] or "(empty)")
                    st.markdown("**Saved Local AI answer**")
                    st.write(saved_note["answer"] or "(empty)")
                    if saved_note["answerTruncated"]:
                        st.caption("The saved answer was truncated by the provenance size bound.")
                    with st.expander("Saved structured context", expanded=False):
                        st.json(saved_note["context"])
                    if st.button(
                        "Reuse saved question in Tutor",
                        key=f"pl_local_ai_browser_reuse_{profile}",
                        width="stretch",
                    ):
                        st.session_state[question_key] = saved_note["question"]
'''
    text = replace_once(text, anchor, ui, "AI note browser UI")

AI.write_text(text, encoding="utf-8")

validation = VALIDATION.read_text(encoding="utf-8")
if "Read-only AI provenance browser: PASS" not in validation:
    validation += r'''

# Read-only provenance browser verifies saved context hashes and ignores unrelated
# or malformed JSON records without changing workspace state.
import os as _os2
import json as _json2
import tempfile as _tempfile2
from pathlib import Path as _Path2

_old_data_dir2 = _os2.environ.get("PHYSICAL_LAB_DATA_DIR")
try:
    with _tempfile2.TemporaryDirectory() as _td2:
        _os2.environ["PHYSICAL_LAB_DATA_DIR"] = _td2
        _root2 = _Path2(_td2) / "workspaces"
        _ws2 = _root2 / "browser-test.physlab"
        _ws2.mkdir(parents=True)
        (_ws2 / "project.json").write_text(_json2.dumps({"id": "browser-test", "name": "Browser Test"}), encoding="utf-8")
        _saved2 = mod.save_ai_research_note(
            str(_ws2),
            profile="oscillation-integration",
            runtime_label="External Ollama",
            runtime_base="http://127.0.0.1:11434",
            model="browser-test-model",
            question="What does damping change?",
            answer="Advisory only.",
            context={"schema": "physical-lab-local-ai-context-v3", "gamma": 0.2},
            user_note="browser validation",
        )
        _before2 = _Path2(_saved2).read_text(encoding="utf-8")
        _notes2 = mod.list_ai_research_notes(str(_ws2))
        _after2 = _Path2(_saved2).read_text(encoding="utf-8")
        assert _before2 == _after2
        assert len(_notes2) == 1
        assert _notes2[0]["contextHashValid"] is True
        assert _notes2[0]["classification"] == "AI ADVISORY NOTE"
        assert _notes2[0]["question"] == "What does damping change?"

        # Malformed/unrelated JSON is ignored rather than displayed as provenance.
        _notes_dir2 = _ws2 / "provenance" / "ai-notes"
        (_notes_dir2 / "junk.json").write_text("not json", encoding="utf-8")
        (_notes_dir2 / "other.json").write_text(_json2.dumps({"schema": "other"}), encoding="utf-8")
        assert len(mod.list_ai_research_notes(str(_ws2))) == 1

        # Changing structured context makes the verification status fail visibly.
        _record2 = _json2.loads(_Path2(_saved2).read_text(encoding="utf-8"))
        _record2["context"]["gamma"] = 0.4
        _Path2(_saved2).write_text(_json2.dumps(_record2), encoding="utf-8")
        _tampered2 = mod.list_ai_research_notes(str(_ws2))
        assert len(_tampered2) == 1
        assert _tampered2[0]["contextHashValid"] is False
finally:
    if _old_data_dir2 is None:
        _os2.environ.pop("PHYSICAL_LAB_DATA_DIR", None)
    else:
        _os2.environ["PHYSICAL_LAB_DATA_DIR"] = _old_data_dir2

print("Read-only AI provenance browser: PASS")
'''
VALIDATION.write_text(validation, encoding="utf-8")

doc = DOC.read_text(encoding="utf-8")
if "## AI Research Notes Browser" not in doc:
    doc += r'''

## AI Research Notes Browser

When one or more managed `.physlab` workspaces exist, the Tutor can browse previously saved `AI ADVISORY NOTE` records in read-only mode. Notes are shown newest first with their timestamp, Lab profile, local model, human research note, saved question/answer, and structured context. Physical Lab recomputes the saved context SHA-256 when the note is opened; a mismatch is displayed prominently rather than silently trusted. The **Reuse saved question in Tutor** action only copies the question text into the current Tutor input and does not call the model, change parameters, or launch a solver.
'''
DOC.write_text(doc, encoding="utf-8")
print("v0.66 AI Research Notes Browser patch: APPLIED")
