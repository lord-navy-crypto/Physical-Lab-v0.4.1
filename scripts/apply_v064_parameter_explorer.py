#!/usr/bin/env python3
"""One-time patch: add a read-only Parameter Explorer to the Local AI Tutor."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI = ROOT / "src-tauri/resources/ui/physical_lab_local_ai.py"
VALIDATION = ROOT / "scripts/local_ai_reference_validation.py"
DOC = ROOT / "docs/LOCAL_AI_TUTOR.md"

text = AI.read_text(encoding="utf-8")
helper = r'''


def _current_parameter_rows(profile: str, session_state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return documented parameters that are actually present in this UI session."""
    guide = _parameter_guide(profile, session_state)
    rows: list[dict[str, Any]] = []
    advanced = ADVANCED_PARAMETER_GUIDES.get(profile, {})
    for key in sorted(guide):
        if key not in session_state:
            continue
        meta = guide[key]
        rows.append({
            "parameter": key,
            "value": _plain(session_state.get(key)),
            "unit": str(meta.get("unit") or ""),
            "meaning": str(meta.get("meaning") or ""),
            "source": "Physical Lab advanced" if key in advanced else "Lab/core",
        })
    return rows
'''
anchor = "\ndef render_local_ai_assistant(st: Any, profile: str, namespace: Mapping[str, Any]) -> None:\n"
if "def _current_parameter_rows(" not in text:
    if text.count(anchor) != 1:
        raise SystemExit("render_local_ai_assistant anchor missing or ambiguous")
    text = text.replace(anchor, helper + anchor, 1)

ui = r'''

        parameter_rows = _current_parameter_rows(profile, st.session_state)
        if parameter_rows:
            with st.expander("Parameter Explorer · current documented controls", expanded=False):
                st.caption(
                    "Read-only view of parameters that are both documented by Physical Lab and present in the current UI session. "
                    "Selecting a parameter can prepare a focused Tutor question; it does not change the control."
                )
                st.dataframe(parameter_rows, width="stretch", hide_index=True)
                parameter_keys = [row["parameter"] for row in parameter_rows]
                selected_parameter = st.selectbox(
                    "Parameter to inspect",
                    parameter_keys,
                    key=f"pl_local_ai_parameter_{profile}",
                )
                selected_row = next(row for row in parameter_rows if row["parameter"] == selected_parameter)
                p1, p2, p3 = st.columns([1.3, 1, 2.7])
                p1.metric("Current value", str(selected_row["value"]))
                p2.metric("Unit / convention", selected_row["unit"] or "documented meaning only")
                p3.info(selected_row["meaning"])
                a1, a2 = st.columns(2)
                if a1.button("Explain selected parameter", key=f"pl_ai_explain_parameter_{profile}", width="stretch"):
                    st.session_state[question_key] = (
                        f"Explain the current parameter `{selected_parameter}`. Its documented unit/convention is `{selected_row['unit']}` and its current value is `{selected_row['value']}`. "
                        "Explain its physical or numerical role, what increasing and decreasing it would usually change in this specific Lab, which observable/result should respond, and which assumptions limit that expectation. Do not change the parameter."
                    )
                if a2.button("Plan a controlled scan of it", key=f"pl_ai_scan_parameter_{profile}", width="stretch"):
                    st.session_state[question_key] = (
                        f"Plan one conservative controlled scan of `{selected_parameter}` from its current value `{selected_row['value']}` using the supplied Physical Lab context. "
                        "Give a bounded range or direction only when supported, say what must be held fixed, name the observable to monitor, and state what result would contradict the expected trend. Do not claim the scan has been run and do not modify the UI."
                    )
'''
insert_after = '''        else:\n            st.caption("The local runtime did not report model capabilities; vision input remains disabled rather than guessed.")\n\n        st.markdown("#### Physics Tutor shortcuts")\n        q1, q2, q3, q4 = st.columns(4)\n        question_key = f"pl_local_ai_question_{profile}"\n'''
replacement = '''        else:\n            st.caption("The local runtime did not report model capabilities; vision input remains disabled rather than guessed.")\n\n        question_key = f"pl_local_ai_question_{profile}"\n''' + ui + '''\n        st.markdown("#### Physics Tutor shortcuts")\n        q1, q2, q3, q4 = st.columns(4)\n'''
if "Parameter Explorer · current documented controls" not in text:
    if text.count(insert_after) != 1:
        raise SystemExit("Parameter Explorer UI anchor missing or ambiguous")
    text = text.replace(insert_after, replacement, 1)
AI.write_text(text, encoding="utf-8")

validation = VALIDATION.read_text(encoding="utf-8")
block = r'''

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
'''
if "Read-only Parameter Explorer: PASS" not in validation:
    validation += block
VALIDATION.write_text(validation, encoding="utf-8")

doc = DOC.read_text(encoding="utf-8")
section = r'''

## Parameter Explorer

The Tutor includes a read-only **Parameter Explorer** for documented controls that are actually present in the current Streamlit session. It displays the current value, unit/convention, meaning, and whether the control belongs to the upstream/core Lab or the Physical Lab advanced research suite. From the selected row, the user can prepare either a focused explanation question or a controlled-scan planning question. These actions only populate the Tutor question; they do not modify the parameter or launch a solver.
'''
if "## Parameter Explorer" not in doc:
    doc += section
DOC.write_text(doc, encoding="utf-8")
print("v0.64 Parameter Explorer patch: APPLIED")
