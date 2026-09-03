#!/usr/bin/env python3
"""One-time integration patch for the Physical Lab Visualization Studio and shell settings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADV = ROOT / "src-tauri" / "resources" / "ui" / "physical_lab_advanced.py"
INDEX = ROOT / "web" / "index.html"
APP = ROOT / "web" / "app.js"
CSS = ROOT / "web" / "styles.css"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} anchor count={count}, expected 1")
    return text.replace(old, new, 1)


advanced = ADV.read_text(encoding="utf-8")
old_dispatch = '''    if profile == "numerical-methods":
        _numerical_suite(st, namespace)
    elif profile == "ising-monte-carlo":
        _ising_suite(st, namespace)
    elif profile == "random-walk-monte-carlo":
        _random_walk_suite(st, namespace)
    elif profile == "nonlinear-chaos":
        _chaos_suite(st, namespace)
    elif profile == "oscillation-integration":
        _oscillation_suite(st, namespace)
    elif profile == "radia-magnet-studio":
        _radia_magnet_suite(st, namespace)
    elif profile == "radiation-platform":
        _radiation_suite(st, namespace)
'''
new_dispatch = '''    def _render_profile_suite() -> None:
        if profile == "numerical-methods":
            _numerical_suite(st, namespace)
        elif profile == "ising-monte-carlo":
            _ising_suite(st, namespace)
        elif profile == "random-walk-monte-carlo":
            _random_walk_suite(st, namespace)
        elif profile == "nonlinear-chaos":
            _chaos_suite(st, namespace)
        elif profile == "oscillation-integration":
            _oscillation_suite(st, namespace)
        elif profile == "radia-magnet-studio":
            _radia_magnet_suite(st, namespace)
        elif profile == "radiation-platform":
            _radiation_suite(st, namespace)

    try:
        from physical_lab_visualization import visualization_context
        with visualization_context(st, profile):
            _render_profile_suite()
    except Exception as _pl_visualization_error:
        st.warning(f"Physical Lab Visualization Studio could not load: {_pl_visualization_error}")
        _render_profile_suite()
'''
advanced = replace_once(advanced, old_dispatch, new_dispatch, "advanced profile dispatch")
ADV.write_text(advanced, encoding="utf-8")

index = INDEX.read_text(encoding="utf-8")
old_nav = '        <button class="nav-item" data-view="tasks"><span>≡</span>Task Center <b id="taskBadge" class="badge hidden">0</b></button>\n'
new_nav = old_nav + '        <button class="nav-item" data-view="settings"><span>⚙</span>Settings</button>\n'
index = replace_once(index, old_nav, new_nav, "settings nav")
settings_section = '''
      <section id="settingsView" class="view">
        <div class="research-hero"><div><div class="eyebrow">WORKBENCH PREFERENCES</div><h2>Physical Lab Settings</h2><p>Choose desktop-shell defaults without changing scientific solver inputs. Per-Lab Visualization Studio settings live inside each model and are captured separately in Run Vault.</p></div><div class="research-badge">Display & workflow only</div></div>
        <div class="two-col">
          <div class="tool-panel"><h3>Lab launch defaults</h3><label>Preferred engine mode<select id="settingsEnginePreference"><option value="auto">Auto — Full when ready, otherwise Safe</option><option value="safe">Prefer Safe</option><option value="full">Prefer Full when available</option></select></label><p class="hint">This only chooses the initial Safe/Full button state. Readiness checks still decide whether a mode can actually launch.</p></div>
          <div class="tool-panel"><h3>Desktop density</h3><label>Interface density<select id="settingsDensity"><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label><label class="settings-check"><input id="settingsShowFeatured" type="checkbox" checked /> Show Featured Labs on Home</label><label class="settings-check"><input id="settingsTaskToasts" type="checkbox" checked /> Toast when a background task completes</label></div>
        </div>
        <div class="tool-panel"><h3>Visualization policy</h3><p class="hint">Plot transforms are explicitly display-only. Normalization, z-score, percent-change, heatmap log-magnitude, axis overrides, trace hiding and display decimation never rewrite solver arrays, measurements or saved scientific results.</p><div class="settings-policy-grid"><div><span>Shared controls</span><strong>axes · legend · grid · hover · height · line/marker size · export · display point budget</strong></div><div><span>Analysis views</span><strong>raw · normalized · z-score · percent change · heatmap transforms</strong></div><div><span>Model-aware behavior</span><strong>theory/reference visibility · chaos equal phase scale · profile-specific defaults</strong></div></div></div>
        <div class="card-actions"><button id="saveSettings" class="primary">Save Settings</button><button id="resetSettings" class="secondary">Reset Defaults</button></div>
      </section>

'''
lab_anchor = '      <section id="labView" class="view lab-frame-view">\n'
index = replace_once(index, lab_anchor, settings_section + lab_anchor, "settings section")
INDEX.write_text(index, encoding="utf-8")

app = APP.read_text(encoding="utf-8")
state_anchor = 'let campaignData = [];\n'
settings_state = '''let campaignData = [];

const DEFAULT_UI_SETTINGS = {enginePreference:'auto', density:'comfortable', showFeatured:true, taskCompletionToasts:true};
let uiSettings = {...DEFAULT_UI_SETTINGS};
try{uiSettings={...DEFAULT_UI_SETTINGS,...JSON.parse(localStorage.getItem('physicalLab.uiSettings')||'{}')}}catch(_){uiSettings={...DEFAULT_UI_SETTINGS}}
'''
app = replace_once(app, state_anchor, settings_state, "ui settings state")
old_map = "tasks:['tasksView','Task Center','Live work performed by Physical Lab.'],lab:['labView','Lab Session','Running locally inside Physical Lab.']}"
new_map = "tasks:['tasksView','Task Center','Live work performed by Physical Lab.'],settings:['settingsView','Settings','Desktop-shell defaults and visualization policy.'],lab:['labView','Lab Session','Running locally inside Physical Lab.']}"
app = replace_once(app, old_map, new_map, "showView settings map")
old_mode = "  if(!selectedModes[m.id]) selectedModes[m.id]=s.fullReady?'full':'safe';\n"
new_mode = '''  if(!selectedModes[m.id]){
    const pref=uiSettings.enginePreference||'auto';
    selectedModes[m.id]=pref==='safe'?'safe':(pref==='full'?(s.fullReady?'full':'safe'):(s.fullReady?'full':'safe'));
  }
'''
app = replace_once(app, old_mode, new_mode, "mode preference")
old_render_tail = "  renderRuntimeSummary(); renderDependencies(); renderResearch(); bindDynamic(); renderTasks(); applySearch();\n"
new_render_tail = "  renderRuntimeSummary(); renderDependencies(); renderResearch(); renderSettings(); applyUiSettings(); bindDynamic(); renderTasks(); applySearch();\n"
app = replace_once(app, old_render_tail, new_render_tail, "render settings call")
settings_functions = r'''
function applyUiSettings(){
  document.body.classList.toggle('ui-compact',uiSettings.density==='compact');
  if(el('featuredGrid'))el('featuredGrid').style.display=uiSettings.showFeatured?'':'none';
}
function renderSettings(){
  if(el('settingsEnginePreference'))el('settingsEnginePreference').value=uiSettings.enginePreference||'auto';
  if(el('settingsDensity'))el('settingsDensity').value=uiSettings.density||'comfortable';
  if(el('settingsShowFeatured'))el('settingsShowFeatured').checked=uiSettings.showFeatured!==false;
  if(el('settingsTaskToasts'))el('settingsTaskToasts').checked=uiSettings.taskCompletionToasts!==false;
}
function saveUiSettings(){
  uiSettings={
    enginePreference:el('settingsEnginePreference')?.value||'auto',
    density:el('settingsDensity')?.value||'comfortable',
    showFeatured:Boolean(el('settingsShowFeatured')?.checked),
    taskCompletionToasts:Boolean(el('settingsTaskToasts')?.checked),
  };
  localStorage.setItem('physicalLab.uiSettings',JSON.stringify(uiSettings));
  selectedModes={};
  applyUiSettings();render();toast('Physical Lab settings saved.');
}
function resetUiSettings(){
  uiSettings={...DEFAULT_UI_SETTINGS};localStorage.setItem('physicalLab.uiSettings',JSON.stringify(uiSettings));selectedModes={};render();toast('Physical Lab settings reset.');
}

'''
bind_anchor = 'function bindDynamic(){\n'
app = replace_once(app, bind_anchor, settings_functions + bind_anchor, "settings functions")
old_task = "function onTask(ev){const t=ev.payload||ev;t.updatedAt=Date.now();tasks.set(t.taskId,t);renderTasks();}\n"
new_task = "function onTask(ev){const t=ev.payload||ev;const previous=tasks.get(t.taskId);t.updatedAt=Date.now();tasks.set(t.taskId,t);renderTasks();if(uiSettings.taskCompletionToasts&&t.done&&!previous?.done)toast(`${t.title||'Physical Lab task'} completed.`);}\n"
app = replace_once(app, old_task, new_task, "task completion preference")
handlers_anchor = "if(el('compareRuns'))el('compareRuns').onclick=compareSavedRuns;\n"
handlers_new = handlers_anchor + "if(el('saveSettings'))el('saveSettings').onclick=saveUiSettings;\nif(el('resetSettings'))el('resetSettings').onclick=resetUiSettings;\n"
app = replace_once(app, handlers_anchor, handlers_new, "settings handlers")
APP.write_text(app, encoding="utf-8")

css = CSS.read_text(encoding="utf-8")
css_add = r'''

/* v0.67 desktop settings */
.settings-check{display:flex;align-items:center;gap:10px;margin-top:14px;font-size:14px;color:var(--text)}
.settings-check input{width:18px;height:18px}
.settings-policy-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:14px}
.settings-policy-grid>div{border:1px solid var(--border);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:7px;background:rgba(255,255,255,.02)}
.settings-policy-grid span{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted)}
.settings-policy-grid strong{font-size:13px;line-height:1.45}
body.ui-compact .module-card{padding:15px}
body.ui-compact .card-grid,body.ui-compact .dependency-grid,body.ui-compact .workspace-grid{gap:12px}
body.ui-compact .module-card .desc{margin:7px 0 10px}
@media(max-width:820px){.settings-policy-grid{grid-template-columns:1fr}}
'''
if "/* v0.67 desktop settings */" in css:
    raise SystemExit("settings CSS already present")
CSS.write_text(css.rstrip() + css_add + "\n", encoding="utf-8")

print("v0.67 visualization + shell settings patch applied")
