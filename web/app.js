const tauri = window.__TAURI__ || null;
const invoke = tauri?.core?.invoke;
const listen = tauri?.event?.listen;

let modules = [];
let statuses = {};
let runtime = {};
let dependencies = [];
let dependencyStatuses = {};
let logDir = "";
let dataDir = "";
let tasks = new Map();
let activeCategory = 'All';
let activeModule = null;
let activeMode = null;
let selectedModes = {};
let workspaces = [];
let activeWorkspaceId = localStorage.getItem('physicalLab.activeWorkspace') || null;
let datasets = [];
let pipelineTemplates = [];
let adapterStatuses = [];
let compatibilityRows = [];
let smokeResults = [];
let runSnapshots = [];
let campaignData = [];
let modelBuilderAnalysis = null;
let modelBuilderBundle = null;
let modelBuilderPreviewData = null;
let modelBuilderValidationData = null;

const DEFAULT_UI_SETTINGS = {enginePreference:'auto', density:'comfortable', showFeatured:true, taskCompletionToasts:true};
let uiSettings = {...DEFAULT_UI_SETTINGS};
try{uiSettings={...DEFAULT_UI_SETTINGS,...JSON.parse(localStorage.getItem('physicalLab.uiSettings')||'{}')}}catch(_){uiSettings={...DEFAULT_UI_SETTINGS}}

const icons = {
  'numerical-methods':'∑','ising-monte-carlo':'▦','random-walk-monte-carlo':'⌁','nonlinear-chaos':'∿',
  'oscillation-integration':'≈','radia-magnet-studio':'⊞','radiation-platform':'↯','radia-runtime':'R','chrono-modal-runtime':'C','vampire-runtime':'V'
};

const el = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

function toast(message, error=false){
  const node=document.createElement('div'); node.className='toast'+(error?' error':''); node.textContent=message;
  el('toastHost').appendChild(node); setTimeout(()=>node.remove(),4200);
}

function showView(name){
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active-view'));
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active', n.dataset.view===name));
  const map={home:['homeView','Physical Lab','One local home for your computational physics tools.'],labs:['labsView','Physics Labs','Install, open and switch between computational models.'],modelbuilder:['modelBuilderView','Research Model Builder','Preserve the science. Standardize the interface. Automate the bridge.'],runtime:['runtimeView','Runtime Center','Scientific runtimes, builders and dependency health.'],dependencies:['dependenciesView','Dependency Center','Everything Physical Lab needs, and exactly how it is delivered.'],workspaces:['workspacesView','Projects','Reproducible experimental workspaces.'],data:['dataView','Data Bridge','Measurements, Arduino serial capture and dataset provenance.'],integrity:['integrityView','Integrity Center','Per-Lab compatibility and scientific smoke tests.'],pipelines:['pipelinesView','Physics Pipelines','Explicit cross-Lab handoffs and native adapter boundaries.'],campaigns:['campaignsView','Campaigns','Persistent parameter-scan planning and run queues.'],results:['resultsView','Results Center','Statistics, model validation and reproducibility exports.'],tasks:['tasksView','Task Center','Live work performed by Physical Lab.'],settings:['settingsView','Settings','Desktop-shell defaults and visualization policy.'],lab:['labView','Lab Session','Running locally inside Physical Lab.']};
  const item=map[name]||map.home; el(item[0]).classList.add('active-view'); el('viewTitle').textContent=item[1]; el('viewSubtitle').textContent=item[2];
}

function mockModules(){
  return [
    ['numerical-methods','Numerical Error Analysis','Numerical Physics','lab'],['ising-monte-carlo','Ising Monte Carlo Lab','Statistical Physics','lab'],['random-walk-monte-carlo','Random Walk & Monte Carlo','Stochastic Physics','lab'],['nonlinear-chaos','Nonlinear Dynamics & Chaos','Dynamics','lab'],['oscillation-integration','Oscillation & Integration','Dynamics','lab'],['radia-magnet-studio','RADIA Magnet Studio','Accelerator Physics','lab'],['radiation-platform','Radiation Platform','Accelerator Physics','lab'],['radia-runtime','RADIA Universal2 Runtime','Runtime & Builders','runtime'],['chrono-modal-runtime','Chrono::Modal Universal2 Builder','Runtime & Builders','runtime'],['vampire-runtime','VAMPIRE Apple Silicon Builder','Runtime & Builders','runtime']
  ].map(x=>({id:x[0],name:x[1],category:x[2],kind:x[3],description:'Physical Lab module preview.',tags:[],runtimeRequires:[],fragileDependencies:(x[0]==='radia-magnet-studio'||x[0]==='radiation-platform')?['radia']:(x[0]==='oscillation-integration'?['pychrono']:[]),safeBackend:(x[0]==='radia-magnet-studio'?'radia-analytic':(x[0]==='radiation-platform'?'radiation-analytic':'standard')),safeModeNote:'Safe mode avoids fragile native physics engines.',fullModeNote:'Full mode enables fragile external engines when available.'}));
}

function mockDependencies(){
  return [
    {id:'python-runtime',name:'Python Runtime',category:'Core Runtime',delivery:'detect-or-official',required:true,sourceName:'Python.org',sourceUrl:'https://www.python.org/downloads/macos/',description:'Base interpreter for isolated Lab environments.',usedBy:['All Python Labs'],notes:'ABI-aware runtime selection.'},
    {id:'python-scientific-stack',name:'Per-Lab Scientific Python Stack',category:'Managed Packages',delivery:'module-managed',required:true,sourceName:'PyPI / module requirements',sourceUrl:'https://pypi.org/',description:'Module-specific Python packages are installed automatically.',usedBy:['All Python Labs'],notes:'pip check + import smoke tests.'},
    {id:'xcode-clt',name:'Xcode Command Line Tools',category:'System Prerequisite',delivery:'system-dialog',required:false,sourceName:'Apple',sourceUrl:'https://developer.apple.com/xcode/resources/',description:'Native compiler toolchain for scientific builders.',usedBy:['RADIA','Chrono::Modal','VAMPIRE'],notes:'Only needed for native builds.'},
    {id:'cmake',name:'CMake',category:'Build Tool',delivery:'official-link',required:false,sourceName:'CMake',sourceUrl:'https://cmake.org/download/',description:'Needed only to build Chrono::Modal.',usedBy:['Chrono::Modal'],notes:'Existing installs are detected first.'},
    {id:'radia',name:'RADIA + FFTW Runtime',category:'Physics Engine',delivery:'integrated-builder',required:false,sourceName:'Physical Lab RADIA Builder',sourceUrl:'',description:'Magnetic-field engine for RADIA Labs.',usedBy:['RADIA Magnet Studio','Radiation Platform'],notes:'Existing ABI-compatible builds are reused.'},
    {id:'pychrono',name:'PyChrono',category:'Physics Engine',delivery:'detect-or-official',required:false,sourceName:'Project Chrono',sourceUrl:'https://api.projectchrono.org/pychrono_installation.html',description:'Project Chrono Python runtime.',usedBy:['Future Chrono integrations'],notes:'Tracked separately from Chrono::Modal SDK.'},
    {id:'chrono-modal',name:'Chrono::Modal Universal2 SDK',category:'Physics Engine',delivery:'integrated-builder',required:false,sourceName:'Physical Lab Chrono Builder',sourceUrl:'',description:'Optional modal-analysis SDK.',usedBy:['Future modal integrations'],notes:'Built only when requested.'},
    {id:'vampire',name:'VAMPIRE Atomistic Runtime',category:'Physics Engine',delivery:'integrated-builder',required:false,sourceName:'Physical Lab VAMPIRE Builder',sourceUrl:'',description:'Optional atomistic magnetism engine.',usedBy:['Future atomistic integrations'],notes:'Apple Silicon builder.'}
  ];
}

async function refreshAll(){
  try{
    if(invoke){
      modules = await invoke('list_modules');
      dependencies = await invoke('list_dependencies');
      const depArr = await invoke('dependency_statuses'); dependencyStatuses=Object.fromEntries(depArr.map(s=>[s.id,s]));
      const arr = await invoke('module_statuses'); statuses=Object.fromEntries(arr.map(s=>[s.id,s]));
      runtime = await invoke('runtime_status');
      logDir = await invoke('log_directory');
      dataDir = await invoke('data_directory');
    }else{
      modules=mockModules(); dependencies=mockDependencies(); statuses=Object.fromEntries(modules.map(m=>[m.id,{id:m.id,installed:false,ready:false,safeReady:false,fullReady:false,state:'Not installed'}]));
      runtime={pythonReady:true,pythonVersion:'Preview mode',radiaReady:false,radiaDetail:'Not checked',pychronoReady:false,pychronoDetail:'Not checked',pychronoPython:null,chronoReady:false,chronoDetail:'Not built',vampireReady:false,vampireDetail:'Not installed',cmakeReady:false,cmakeDetail:'Not checked',xcodeCltReady:true,xcodeCltDetail:'Preview mode',arch:'arm64',os:'macOS'};
      dependencyStatuses=Object.fromEntries(dependencies.map(d=>[d.id,{id:d.id,level:'yellow',label:'Preview',detail:d.notes||'',locations:[],version:null}])); logDir='~/Library/Application Support/Physical Lab/logs'; dataDir='~/Library/Application Support/Physical Lab';
    }
    await refreshResearchBasics();
    render();
  }catch(e){toast(String(e),true)}
}

function statusFor(m){return statuses[m.id]||{installed:false,ready:false,safeReady:false,fullReady:false,state:'Unknown'}};
function modeChoice(m,s){
  if(!selectedModes[m.id]){
    const pref=uiSettings.enginePreference||'auto';
    selectedModes[m.id]=pref==='safe'?'safe':(pref==='full'?(s.fullReady?'full':'safe'):(s.fullReady?'full':'safe'));
  }
  if(selectedModes[m.id]==='full'&&!s.fullReady&&s.safeReady) selectedModes[m.id]='safe';
  const current=selectedModes[m.id]||'safe';
  const fragile=(m.fragileDependencies||[]);
  const safeNote=m.safeModeNote||'Avoids fragile external physics engines.';
  const fullNote=m.fullModeNote||'Uses the full available engine set.';
  return `<div class="mode-box">
    <div class="mode-head"><span>Engine mode</span><span class="mode-readiness"><b class="${s.safeReady?'ok':''}">Safe ${s.safeReady?'✓':'○'}</b><b class="${s.fullReady?'ok':''}">Full ${s.fullReady?'✓':'○'}</b></span></div>
    <div class="mode-switch">
      <button class="mode-option ${current==='safe'?'active':''}" data-mode-id="${m.id}" data-mode="safe">Safe</button>
      <button class="mode-option ${current==='full'?'active':''}" data-mode-id="${m.id}" data-mode="full" ${!s.fullReady&&fragile.length?'title="Fragile engine not ready"':''}>Full</button>
    </div>
    <div class="mode-note">${esc(current==='safe'?safeNote:fullNote)}</div>
  </div>`;
}
function labCard(m){
  const s=statusFor(m); const fragile=(m.fragileDependencies||[]);
  const deps=(m.pythonRequires?`<span class="tag">Python ${esc(m.pythonRequires)}</span>`:'') + ((m.supportedArches||[]).length?`<span class="tag">${esc(m.supportedArches.join(' + '))}</span>`:'') + (fragile.length?fragile.map(d=>`<span class="dependency">Fragile: ${esc(d.toUpperCase())}</span>`).join(''):`<span class="tag">No fragile engine</span>`);
  const tags=(m.tags||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('');
  const stateClass=s.ready?'ready':(s.busy?'busy':'');
  const current=selectedModes[m.id]||(s.fullReady?'full':'safe');
  const canOpen=current==='full'?s.fullReady:s.safeReady;
  const deleteBtn=s.installed?`<button class="danger" data-uninstall="${m.id}">Delete</button>`:'';
  const action=canOpen?`<button class="primary" data-open="${m.id}">Open ${current==='full'?'Full':'Safe'}</button><button class="secondary" data-install="${m.id}">Update</button>${deleteBtn}`:`<button class="primary" data-install="${m.id}">${s.installed?'Repair':'Install'}</button>${deleteBtn}`;
  return `<article class="module-card" data-search="${esc((m.name+' '+m.category+' '+(m.tags||[]).join(' ')).toLowerCase())}">
    <div class="card-top"><div class="module-icon">${icons[m.id]||'◌'}</div><span class="status-pill ${stateClass}">${esc(s.state||'Not installed')}</span></div>
    <div class="category">${esc(m.category)}</div><h4>${esc(m.name)}</h4><p class="desc">${esc(m.description)}</p>
    <div class="tags">${tags}${deps}</div>${modeChoice(m,s)}<div class="card-actions">${action}</div></article>`;
}

function runtimeCard(m){
  const s=statusFor(m); const stateClass=s.ready?'ready':(s.busy?'busy':'');
  const remove=s.installed?`<button class="danger" data-uninstall="${m.id}">Remove builder</button>`:'';
  return `<article class="module-card"><div class="card-top"><div class="module-icon">${icons[m.id]||'⬡'}</div><span class="status-pill ${stateClass}">${esc(s.state||'Available')}</span></div><div class="category">${esc(m.category)}</div><h4>${esc(m.name)}</h4><p class="desc">${esc(m.description)}</p><div class="tags">${(m.tags||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join('')}${(m.systemRequires||[]).length?`<span class="dependency">Tools: ${esc(m.systemRequires.join(', '))}</span>`:''}</div><div class="card-actions"><button class="primary" data-install="${m.id}">${s.ready?'Repair / Rebuild':'Install / Build'}</button>${remove}</div></article>`;
}

function renderRuntimeSummary(){
  const cards=[
    ['Python',runtime.pythonReady,runtime.pythonVersion||'Not found',runtime.pythonPath||'System runtime'],
    ['RADIA',runtime.radiaReady,runtime.radiaReady?'Ready':'Not ready',runtime.radiaDetail||'Universal2 runtime'],
    ['PyChrono',runtime.pychronoReady,runtime.pychronoReady?'Environment found':'Not found',(runtime.pychronoPython?runtime.pychronoPython+' · ':'')+(runtime.pychronoDetail||'Conda runtime')],
    ['Chrono::Modal SDK',runtime.chronoReady,runtime.chronoReady?'SDK found':'Not built',runtime.chronoDetail||'C++ builder output'],
    ['VAMPIRE',runtime.vampireReady,runtime.vampireReady?'Installed':'Not installed',runtime.vampireDetail||runtime.arch||'System']
  ];
  el('runtimeSummary').innerHTML=cards.map(c=>`<div class="runtime-card"><div class="name">${c[0]}</div><div class="value">${c[1]?'● ': '○ '}${esc(c[2])}</div><div class="detail">${esc(c[3])}</div></div>`).join('');
  el('pythonDot').className='dot '+(runtime.pythonReady?'good':'warn'); el('pythonMini').textContent=runtime.pythonReady?(runtime.pythonVersion||'Python ready'):'Python missing';
  el('radiaDot').className='dot '+(runtime.radiaReady?'good':'warn'); el('radiaMini').textContent=runtime.radiaReady?'RADIA ready':'RADIA not installed';
}

function dependencyState(d){
  return dependencyStatuses[d.id]||{id:d.id,level:'yellow',label:'Checking',detail:d.notes||'',locations:[],version:null};
}
function deliveryLabel(mode){return ({'module-managed':'Auto-managed','integrated-builder':'Integrated builder','detect-or-official':'Detect / official source','official-link':'Official source','system-dialog':'macOS system installer'})[mode]||mode}
function dependencyAction(d,state){
  const ready=state.level==='green';
  if(d.id==='radia'||d.id==='fftw') return `<button class="${ready?'secondary':'primary'}" data-install="radia-runtime">${ready?'Repair / rebuild RADIA':'Install with Physical Lab'}</button>`;
  if(d.id==='chrono-modal') return `<button class="${ready?'secondary':'primary'}" data-install="chrono-modal-runtime">${ready?'Repair / rebuild':'Build with Physical Lab'}</button>`;
  if(d.id==='vampire') return `<button class="${ready?'secondary':'primary'}" data-install="vampire-runtime">${ready?'Repair / rebuild':'Build with Physical Lab'}</button>`;
  if(d.delivery==='module-managed') return `<button class="secondary" data-dependency-action="${esc(d.id)}">Open PyPI</button>`;
  return `<button class="${ready?'secondary':'primary'}" data-dependency-action="${esc(d.id)}">${d.id==='xcode-clt'&&state.level==='red'?'Open macOS installer':'Open official source'}</button>`;
}

function dependencyPriority(d,st){
  if(st.level==='red') return {rank:0,label:'Fix now',detail:st.detail||d.notes||''};
  if(st.level==='green') return {rank:3,label:'Ready',detail:st.detail||''};
  if(d.id==='cmake') return {rank:2,label:'Optional — needed for Chrono::Modal build',detail:st.detail||d.notes||''};
  if(d.id==='chrono-modal') return {rank:2,label:'Optional runtime',detail:'Build only when you want Chrono::Modal experiments.'};
  if(d.id==='vampire') return {rank:2,label:'Optional runtime',detail:'Build only when you want atomistic-magnetism experiments.'};
  if(d.id==='pychrono') return {rank:2,label:'Optional runtime',detail:'Current core Labs do not require PyChrono unless a PyChrono adapter is enabled.'};
  if(d.delivery==='module-managed') return {rank:1,label:'Auto-managed',detail:'Physical Lab installs or repairs this package inside each Lab venv.'};
  return {rank:2,label:'Optional / on demand',detail:st.detail||d.notes||''};
}
function exportDependencyDoctorReport(){
  const report={
    schema:'physical-lab-dependency-doctor-v1',
    created:new Date().toISOString(),
    runtime:runtime||{},
    dependencies:(dependencies||[]).map(d=>{const st=dependencyState(d),priority=dependencyPriority(d,st);return {id:d.id,name:d.name,category:d.category,delivery:d.delivery,required:d.required,usedBy:d.usedBy||[],health:st.level,label:st.label,version:st.version||null,detail:st.detail||'',locations:st.locations||[],priority:priority.label,recommendation:priority.detail};}),
    modules:(modules||[]).map(m=>({id:m.id,name:m.name,kind:m.kind,status:statusFor(m)}))
  };
  const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const a=document.createElement('a');a.href=url;a.download='Physical-Lab-Dependency-Doctor.json';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),500);
  toast('Dependency Doctor report exported.');
}

function renderDependencies(){
  const grid=el('dependencyGrid'); if(!grid)return;
  const states=(dependencies||[]).map(d=>[d,dependencyState(d)]);
  const red=states.filter(([,s])=>s.level==='red');
  const yellow=states.filter(([,s])=>s.level==='yellow');
  const green=states.filter(([,s])=>s.level==='green');
  const optional=yellow.filter(([d])=>['Physics Engine','Build Tool','Native Library'].includes(d.category));
  const summary=el('dependencySummary');
  if(summary){
    const blockerText=red.length?red.map(([d])=>d.name).join(' · '):'No blocking dependency failures detected';
    const optionalText=optional.length?optional.map(([d])=>d.name).join(' · '):'No optional native gaps detected';
    summary.innerHTML=`<div class="dep-summary-card ${red.length?'danger':'good'}"><span>Action needed</span><strong>${red.length}</strong><small>${esc(blockerText)}</small></div><div class="dep-summary-card"><span>Optional / build later</span><strong>${optional.length}</strong><small>${esc(optionalText)}</small></div><div class="dep-summary-card"><span>Verified / found</span><strong>${green.length}</strong><small>${green.length} dependency checks currently green</small></div><div class="dep-summary-card"><span>Managed automatically</span><strong>${states.filter(([d])=>d.delivery==='module-managed').length}</strong><small>Ordinary Python packages are repaired per Lab</small></div>`;
  }
  grid.innerHTML=states.map(([d,st])=>{const locs=(st.locations||[]);const priority=dependencyPriority(d,st);const locHtml=locs.length?`<details class="dependency-locations"><summary>${locs.length} detected location${locs.length===1?'':'s'}</summary>${locs.map(x=>`<code>${esc(x)}</code>`).join('')}</details>`:'';return `<article class="dependency-card"><div class="dependency-card-head"><div><div class="category">${esc(d.category)}</div><h4>${esc(d.name)}</h4></div><span class="health-light ${esc(st.level)}"><i></i>${esc(st.label)}</span></div><div class="dependency-priority"><strong>${esc(priority.label)}</strong><span>${esc(priority.detail)}</span></div><p class="desc">${esc(d.description)}</p><div class="dependency-meta"><div><span>Delivery</span><strong>${esc(deliveryLabel(d.delivery))}</strong></div><div><span>Used by</span><strong>${esc((d.usedBy||[]).join(' · '))}</strong></div><div><span>Version</span><strong>${esc(st.version||'—')}</strong></div></div><div class="dependency-detail">${esc(st.detail||d.notes||'')}</div>${locHtml}<div class="card-actions">${dependencyAction(d,st)}</div></article>`}).join('');
  document.querySelectorAll('[data-dependency-action]').forEach(b=>b.onclick=()=>runDependencyAction(b.dataset.dependencyAction));
}
async function runDependencyAction(id){
  if(!invoke){toast('Preview mode: this action is available in the desktop build.');return}
  try{const msg=await invoke('dependency_action',{dependencyId:id});toast(msg);setTimeout(refreshAll,700)}catch(e){toast(String(e),true)}
}

function render(){
  const labs=modules.filter(m=>m.kind==='lab'), runtimes=modules.filter(m=>m.kind==='runtime');
  if(el('logPath'))el('logPath').textContent=logDir||'not available'; if(el('dataPath'))el('dataPath').textContent=dataDir||'not available';
  const installed=labs.filter(m=>statusFor(m).ready).length;
  el('stats').innerHTML=[[String(modules.length),'Integrated modules'],[String(labs.length),'Physics labs'],[String(runtimes.length),'Runtime builders'],[String(installed),'Ready to open']].map(s=>`<div class="stat"><strong>${s[0]}</strong><span>${s[1]}</span></div>`).join('');
  el('featuredGrid').innerHTML=labs.slice(-3).map(labCard).join('');
  const cats=['All',...new Set(labs.map(m=>m.category))];
  el('labFilters').innerHTML=cats.map(c=>`<button class="filter ${c===activeCategory?'active':''}" data-cat="${esc(c)}">${esc(c)}</button>`).join('');
  const visible=activeCategory==='All'?labs:labs.filter(m=>m.category===activeCategory);
  el('labGrid').innerHTML=visible.map(labCard).join('');
  el('runtimeGrid').innerHTML=runtimes.map(runtimeCard).join('');
  renderRuntimeSummary(); renderDependencies(); renderResearch(); renderModelBuilder(); renderSettings(); applyUiSettings(); bindDynamic(); renderTasks(); applySearch();
}


function activeWorkspace(){return workspaces.find(w=>w.id===activeWorkspaceId)||null}
async function refreshResearchBasics(){
  if(!invoke){
    workspaces=[]; datasets=[];
    pipelineTemplates=[{name:'Measured Field → RADIA → Radiation',steps:[{label:'Measured magnetic field'},{label:'Measurement vs RADIA field'},{label:'RADIA field model'},{label:'Field → trajectory'},{label:'Trajectory → radiation'}],note:'Desktop build persists explicit handoffs.'},{name:'Oscillation → Chrono::Modal Comparison',steps:[{label:'Numerical oscillator'},{label:'Mass / stiffness / damping package'},{label:'Chrono::Modal provider'},{label:'Response comparison'}],note:'Adapter boundary only until a real solver adapter is validated.'}];
    adapterStatuses=[{id:'chrono-modal',name:'Chrono::Modal',runtimeFound:false,consumedByCurrentLab:false,adapterState:'Interchange contract ready',interchange:['mass matrix','stiffness matrix','damping matrix'],note:'Preview mode.'},{id:'vampire',name:'VAMPIRE',runtimeFound:false,consumedByCurrentLab:false,adapterState:'Input/result contract ready',interchange:['material','lattice','temperature','field'],note:'Preview mode.'}];
    return;
  }
  try{workspaces=await invoke('list_workspaces')}catch(e){console.warn(e);workspaces=[]}
  if(activeWorkspaceId&&!workspaces.some(w=>w.id===activeWorkspaceId))activeWorkspaceId=null;
  if(!activeWorkspaceId&&workspaces.length)activeWorkspaceId=workspaces[0].id;
  if(activeWorkspaceId)localStorage.setItem('physicalLab.activeWorkspace',activeWorkspaceId);
  try{pipelineTemplates=await invoke('pipeline_templates')}catch(e){console.warn(e);pipelineTemplates=[]}
  try{adapterStatuses=await invoke('adapter_statuses')}catch(e){console.warn(e);adapterStatuses=[]}
  await refreshDatasetsForActive(false);
  if(invoke&&activeWorkspaceId){try{runSnapshots=await invoke('list_run_snapshots',{workspaceId:activeWorkspaceId})}catch(e){runSnapshots=[]};try{campaignData=await invoke('list_campaigns',{workspaceId:activeWorkspaceId})}catch(e){campaignData=[]}}else{runSnapshots=[];campaignData=[];}
}
async function refreshDatasetsForActive(rerender=true){
  if(!invoke||!activeWorkspaceId){datasets=[];if(rerender)renderResearch();return}
  try{datasets=await invoke('list_datasets',{workspaceId:activeWorkspaceId})}catch(e){datasets=[];if(rerender)toast(String(e),true)}
  if(rerender)renderResearch();
}
function renderResearch(){
  const ws=activeWorkspace();
  if(el('activeWorkspaceBadge'))el('activeWorkspaceBadge').textContent=ws?`Project: ${ws.name}`:'No project selected';
  if(el('workspaceGrid')){
    el('workspaceGrid').innerHTML=workspaces.length?workspaces.map(w=>`<article class="workspace-card ${w.id===activeWorkspaceId?'active':''}"><div class="category">PHYSICAL LAB PROJECT</div><h4>${esc(w.name)}</h4><div class="workspace-meta"><div><span>Datasets</span><strong>${w.datasets}</strong></div><div><span>Runs</span><strong>${w.runs}</strong></div><div><span>Campaigns</span><strong>${w.campaigns}</strong></div></div><div class="dataset-path">${esc(w.path)}</div><div class="card-actions"><button class="${w.id===activeWorkspaceId?'secondary':'primary'}" data-workspace-select="${esc(w.id)}">${w.id===activeWorkspaceId?'Active':'Use Project'}</button><button class="secondary" data-workspace-open="${esc(w.id)}">Open Folder</button></div></article>`).join(''):'<div class="empty-state">Create your first reproducible Physical Lab project.</div>';
  }
  if(el('datasetGrid')){
    el('datasetGrid').innerHTML=datasets.length?datasets.map(d=>`<article class="dataset-card"><div class="category">${esc((d.format||'data').toUpperCase())} · ${esc(d.quantity||'Measurement')}</div><h4>${esc(d.name)}</h4><div class="dataset-meta"><div><span>Unit</span><strong>${esc(d.unit||'—')}</strong></div><div><span>Sensor</span><strong>${esc(d.sensor||'—')}</strong></div><div><span>SHA</span><strong>${esc((d.sha256||'—').slice(0,10))}</strong></div></div><div class="dataset-path">${esc(d.storedFile)}</div><div class="card-actions"><button class="secondary" data-dataset-analyze="${esc(d.id)}">Analyze</button></div></article>`).join(''):'<div class="empty-state">No datasets in the active project.</div>';
  }
  const labOptions=modules.filter(m=>m.kind==='lab').map(m=>`<option value="${esc(m.id)}">${esc(m.name)}</option>`).join('');
  if(el('campaignModule'))el('campaignModule').innerHTML=labOptions;if(el('snapshotModule'))el('snapshotModule').innerHTML=labOptions;
  if(el('resultDataset'))el('resultDataset').innerHTML=datasets.length?datasets.map(d=>`<option value="${esc(d.id)}">${esc(d.name)}</option>`).join(''):'<option value="">No dataset</option>';
  const runOpts=runSnapshots.length?runSnapshots.map(r=>`<option value="${esc(r.id)}">${esc((r.moduleId||'run')+' · '+(r.createdAt||''))}</option>`).join(''):'<option value="">No saved runs</option>';if(el('compareRunA'))el('compareRunA').innerHTML=runOpts;if(el('compareRunB')){el('compareRunB').innerHTML=runOpts;if(runSnapshots.length>1)el('compareRunB').selectedIndex=1;}
  if(el('pipelineGrid'))el('pipelineGrid').innerHTML=pipelineTemplates.map((p,i)=>{const steps=p.steps||[];return `<article class="pipeline-card"><div class="category">PIPELINE TEMPLATE</div><h4>${esc(p.name||'Physics pipeline')}</h4><div class="pipeline-steps">${steps.map((st,j)=>`${j?'<span class="pipeline-arrow">→</span>':''}<span class="pipeline-step">${esc(st.label||st.id||'Step')}</span>`).join('')}</div><p class="hint">${esc(p.note||'Explicit reproducible handoff.')}</p><button class="secondary" data-pipeline-save="${i}">Save to Project</button></article>`}).join('');
  if(el('adapterGrid'))el('adapterGrid').innerHTML=adapterStatuses.map(a=>`<article class="integrity-card"><div class="category">NATIVE ADAPTER</div><h4>${esc(a.name)}</h4><div class="adapter-state"><strong>${a.runtimeFound?'Runtime found':'Runtime optional / not found'}</strong><br/>${esc(a.adapterState)}<div>${(a.interchange||[]).map(x=>`<code>${esc(x)}</code>`).join('')}</div><p class="hint">${esc(a.note||'')}</p></div></article>`).join('');
  if(el('campaignStatus'))el('campaignStatus').innerHTML=campaignData.length?campaignData.map(c=>`<article class="campaign-card"><div><div class="category">${esc(c.queueState||'ready')} · ${esc(c.moduleId||'Lab')}</div><h4>${esc(c.id)}</h4><p class="hint">${esc(c.parameter||'parameter')}: ${c.start} → ${c.stop} · ${c.points} points · max parallel ${c.maxParallel||1}</p></div><div class="card-actions"><button class="secondary small" data-campaign-action="pause" data-campaign-id="${esc(c.id)}">Pause</button><button class="secondary small" data-campaign-action="resume" data-campaign-id="${esc(c.id)}">Resume</button><button class="secondary small" data-campaign-action="retry-failed" data-campaign-id="${esc(c.id)}">Retry failed</button></div></article>`).join(''):'Select a project, then create a campaign.';
  bindResearchDynamic();
}
function bindResearchDynamic(){
  document.querySelectorAll('[data-workspace-select]').forEach(b=>b.onclick=async()=>{activeWorkspaceId=b.dataset.workspaceSelect;localStorage.setItem('physicalLab.activeWorkspace',activeWorkspaceId);await refreshResearchBasics();renderResearch();toast('Active project selected.')});
  document.querySelectorAll('[data-workspace-open]').forEach(b=>b.onclick=async()=>{if(!invoke)return;try{await invoke('open_workspace',{workspaceId:b.dataset.workspaceOpen})}catch(e){toast(String(e),true)}});
  document.querySelectorAll('[data-dataset-analyze]').forEach(b=>b.onclick=async()=>{showView('results');if(el('resultDataset'))el('resultDataset').value=b.dataset.datasetAnalyze;await analyzeSelectedDataset()});
  document.querySelectorAll('[data-pipeline-save]').forEach(b=>b.onclick=()=>savePipelineTemplate(Number(b.dataset.pipelineSave)));
  document.querySelectorAll('[data-campaign-action]').forEach(b=>b.onclick=()=>runCampaignAction(b.dataset.campaignId,b.dataset.campaignAction));
}
async function createProject(){
  const name=el('workspaceName').value.trim();if(!name){toast('Enter a project name.',true);return}if(!invoke){toast('Project creation is available in the desktop build.');return}
  try{const w=await invoke('create_workspace',{name});activeWorkspaceId=w.id;localStorage.setItem('physicalLab.activeWorkspace',w.id);el('workspaceName').value='';await refreshResearchBasics();renderResearch();toast(`Created ${w.name}.`)}catch(e){toast(String(e),true)}
}
async function importMeasurement(){
  if(!activeWorkspaceId){toast('Create or select a project first.',true);return}if(!invoke){toast('Measurement import is available in the desktop build.');return}
  const payload={workspaceId:activeWorkspaceId,sourcePath:el('datasetPath').value.trim(),name:el('datasetName').value.trim()||'Measurement',quantity:el('datasetQuantity').value.trim()||'Measured quantity',unit:el('datasetUnit').value.trim(),sensor:el('datasetSensor').value.trim(),calibration:el('datasetCalibration').value.trim()};
  try{await invoke('import_measurement_dataset',payload);await refreshResearchBasics();renderResearch();toast('Measurement imported with provenance and checksum.')}catch(e){toast(String(e),true)}
}
async function scanSerialDevices(){if(!invoke){toast('Serial scan is available in the desktop build.');return}try{const devs=await invoke('list_serial_devices');el('serialDevice').innerHTML=devs.length?devs.map(d=>`<option value="${esc(d)}">${esc(d)}</option>`).join(''):'<option value="">No serial devices found</option>';toast(`${devs.length} serial device(s) found.`)}catch(e){toast(String(e),true)}}
async function captureSerial(){
  if(!activeWorkspaceId){toast('Select a project first.',true);return}const device=el('serialDevice').value;if(!device){toast('Select a serial device.',true);return}
  try{toast('Capturing serial measurement…');await invoke('capture_serial_measurement',{workspaceId:activeWorkspaceId,device,baud:Number(el('serialBaud').value||115200),seconds:Number(el('serialSeconds').value||10),name:el('serialName').value.trim()||'Serial measurement',quantity:el('serialQuantity').value.trim()||'Sensor value',unit:el('serialUnit').value.trim(),sensor:el('serialSensor').value.trim()||'Arduino sensor'});await refreshResearchBasics();renderResearch();toast('Serial measurement saved to project.')}catch(e){toast(String(e),true)}
}
async function runIntegrityChecks(){
  if(!invoke){toast('Integrity checks are available in the desktop build.');return}el('compatibilityMatrix').innerHTML='<div class="empty-state">Checking Lab environments…</div>';el('smokeGrid').innerHTML='<div class="empty-state">Running bounded scientific smoke tests…</div>';
  try{compatibilityRows=await invoke('lab_compatibility_matrix');smokeResults=await invoke('scientific_smoke_tests');renderIntegrity();toast('Integrity check complete.')}catch(e){toast(String(e),true)}
}
function renderIntegrity(){
  if(el('compatibilityMatrix')){const rows=compatibilityRows;el('compatibilityMatrix').innerHTML=rows.length?`<table class="research-table"><thead><tr><th>Lab</th><th>Interpreter</th><th>Package</th><th>Requirement</th><th>Found</th><th>Status</th><th>Repair</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.moduleName)}</td><td class="muted-text">${esc(r.interpreter||'Not installed')}</td><td>${esc(r.package)}</td><td><code>${esc(r.requirement)}</code></td><td>${esc(r.foundVersion||'—')}</td><td class="${r.compatible===true?'ok-text':r.compatible===false?'bad-text':'muted-text'}">${r.compatible===true?'Compatible':r.compatible===false?'Incompatible':'Not checked'}</td><td>${r.installed&&r.compatible===false?`<button class="secondary repair-button" data-repair-lab="${esc(r.moduleId)}">Repair Lab venv</button>`:''}</td></tr>`).join('')}</tbody></table>`:'<div class="empty-state">No compatibility results yet.</div>';}
  if(el('smokeGrid'))el('smokeGrid').innerHTML=smokeResults.length?smokeResults.map(r=>`<article class="integrity-card"><div class="category">${r.installed?'SCIENTIFIC SMOKE':'NOT INSTALLED'}</div><h4>${esc(r.moduleName)}</h4><strong class="${r.passed?'ok-text':'bad-text'}">${r.passed?'Scientific Ready':'Not Ready / Skipped'}</strong><p class="hint">${esc(r.detail)}</p><span class="muted-text">${r.durationMs} ms</span></article>`).join(''):'<div class="empty-state">Run the integrity check to test installed Labs.</div>';
  document.querySelectorAll('[data-repair-lab]').forEach(b=>b.onclick=()=>repairLabVenv(b.dataset.repairLab));
}
async function repairLabVenv(id){if(!invoke)return;try{const msg=await invoke('repair_lab_environment',{moduleId:id});toast(msg);await runIntegrityChecks()}catch(e){toast(String(e),true)}}
async function savePipelineTemplate(index){if(!activeWorkspaceId){toast('Select a project first.',true);return}if(!invoke)return;const p=pipelineTemplates[index];const kinds=['accelerator-measurement','oscillation-modal','atomistic-magnetism','measurement-validation'];try{const id=await invoke('save_pipeline',{workspaceId:activeWorkspaceId,kind:kinds[index]||'measurement-validation'});toast(`Pipeline saved: ${id}`)}catch(e){toast(String(e),true)}}
async function createCampaignQueue(){if(!activeWorkspaceId){toast('Select a project first.',true);return}if(!invoke)return;try{const id=await invoke('create_campaign',{workspaceId:activeWorkspaceId,moduleId:el('campaignModule').value,parameter:el('campaignParameter').value.trim()||'parameter',start:Number(el('campaignStart').value),stop:Number(el('campaignStop').value),points:Number(el('campaignPoints').value),maxParallel:Number(el('campaignParallel').value)});el('campaignStatus').textContent=`Created ${id}. Queue is persisted inside the active project.`;await refreshResearchBasics();renderResearch();toast('Campaign queue created.')}catch(e){toast(String(e),true)}}
async function runCampaignAction(id,action){if(!invoke||!activeWorkspaceId)return;try{await invoke('campaign_action',{workspaceId:activeWorkspaceId,campaignId:id,action});await refreshResearchBasics();renderResearch();toast(`Campaign ${action} applied.`)}catch(e){toast(String(e),true)}}
async function analyzeSelectedDataset(){if(!activeWorkspaceId||!el('resultDataset').value){toast('Select a project dataset.',true);return}try{const stats=await invoke('analyze_dataset',{workspaceId:activeWorkspaceId,datasetId:el('resultDataset').value});el('statsTable').innerHTML=stats.length?`<table class="research-table"><thead><tr><th>Column</th><th>N</th><th>Mean</th><th>Std dev</th><th>95% CI</th><th>Min</th><th>Max</th></tr></thead><tbody>${stats.map(x=>`<tr><td>${esc(x.column)}</td><td>${x.n}</td><td>${fmt(x.mean)}</td><td>${fmt(x.stdDev)}</td><td>${fmt(x.ci95Low)} – ${fmt(x.ci95High)}</td><td>${fmt(x.min)}</td><td>${fmt(x.max)}</td></tr>`).join('')}</tbody></table>`:'<div class="empty-state">No numeric columns detected.</div>'}catch(e){toast(String(e),true)}}
function fmt(x){return Number.isFinite(Number(x))?Number(x).toPrecision(6):'—'}
async function validateSelectedDataset(){if(!activeWorkspaceId||!el('resultDataset').value){toast('Select a dataset.',true);return}try{const r=await invoke('validate_dataset_columns',{workspaceId:activeWorkspaceId,datasetId:el('resultDataset').value,observedColumn:el('observedColumn').value.trim(),referenceColumn:el('referenceColumn').value.trim()});el('validationResult').innerHTML=`<div class="metric-grid"><div class="metric-box"><span>Agreement</span><strong>${esc(r.agreement)}</strong></div><div class="metric-box"><span>RMSE</span><strong>${fmt(r.rmse)}</strong></div><div class="metric-box"><span>MAE</span><strong>${fmt(r.mae)}</strong></div><div class="metric-box"><span>Relative RMSE</span><strong>${r.relativeRmse==null?'—':(100*r.relativeRmse).toFixed(2)+'%'}</strong></div><div class="metric-box"><span>R²</span><strong>${r.r2==null?'—':fmt(r.r2)}</strong></div></div><p class="hint">${(r.notes||[]).map(esc).join(' ')}</p>`}catch(e){toast(String(e),true)}}
async function saveRunSnapshot(){if(!activeWorkspaceId){toast('Select a project.',true);return}try{const id=await invoke('record_run_snapshot',{workspaceId:activeWorkspaceId,moduleId:el('snapshotModule').value,mode:el('snapshotMode').value,parametersJson:el('snapshotParameters').value,resultsJson:el('snapshotResults').value});toast(`Run snapshot saved: ${id}`);await refreshResearchBasics();renderResearch()}catch(e){toast(String(e),true)}}
async function exportRepro(){if(!activeWorkspaceId){toast('Select a project.',true);return}try{const path=await invoke('export_reproducibility_package',{workspaceId:activeWorkspaceId});toast(`Reproducibility package created: ${path}`)}catch(e){toast(String(e),true)}}
async function compareSavedRuns(){if(!activeWorkspaceId||!el('compareRunA').value||!el('compareRunB').value){toast('Choose two saved runs.',true);return}try{const r=await invoke('compare_run_snapshots',{workspaceId:activeWorkspaceId,runA:el('compareRunA').value,runB:el('compareRunB').value});el('runComparison').innerHTML=r.differences?.length?`<table class="research-table"><thead><tr><th>Field</th><th>Run A</th><th>Run B</th></tr></thead><tbody>${r.differences.map(d=>`<tr><td><code>${esc(d.field)}</code></td><td>${esc(d.a??'—')}</td><td>${esc(d.b??'—')}</td></tr>`).join('')}</tbody></table>`:'<div class="empty-state">No differences detected.</div>'}catch(e){toast(String(e),true)}}


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

function bindDynamic(){
  document.querySelectorAll('[data-install]').forEach(b=>b.onclick=()=>installModule(b.dataset.install));
  document.querySelectorAll('[data-uninstall]').forEach(b=>b.onclick=()=>uninstallModule(b.dataset.uninstall));
  document.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>openModule(b.dataset.open,selectedModes[b.dataset.open]||'safe'));
  document.querySelectorAll('[data-mode-id]').forEach(b=>b.onclick=()=>{selectedModes[b.dataset.modeId]=b.dataset.mode;render()});
  document.querySelectorAll('[data-cat]').forEach(b=>b.onclick=()=>{activeCategory=b.dataset.cat;render()});
}

async function installModule(id){
  if(!invoke){toast('Preview mode: build the Tauri app to install modules.');return}
  const m=modules.find(x=>x.id===id); if(!m)return;
  toast(`Starting ${m.name}…`);
  try{await invoke('install_module',{moduleId:id}); await refreshAll(); toast(`${m.name} is ready.`)}catch(e){toast(`${m.name}: ${e}`,true);await refreshAll()}
}

async function uninstallModule(id){
  if(!invoke){toast('Preview mode: uninstall is available in the desktop build.');return}
  const m=modules.find(x=>x.id===id); if(!m)return;
  const wording=m.kind==='runtime'?'Remove the downloaded builder from Physical Lab? External runtimes it installed will be kept.':`Delete ${m.name} from Physical Lab? Its downloaded source and isolated environment will be removed.`;
  if(!window.confirm(wording))return;
  try{const msg=await invoke('uninstall_module',{moduleId:id});toast(msg);await refreshAll()}catch(e){toast(String(e),true)}
}

async function openModule(id,mode){
  if(!invoke){toast('Preview mode: module server launch is available in the desktop build.');return}
  const m=modules.find(x=>x.id===id); if(!m)return;
  try{
    const requested=mode||selectedModes[id]||'safe'; const info=await invoke('launch_module',{moduleId:id,mode:requested}); activeModule=id; activeMode=info.mode||requested; el('openLabTitle').textContent=`${m.name} · ${activeMode==='full'?'Full':'Safe'} Mode`; el('openLabUrl').textContent=info.url; el('labFrame').src=info.url; showView('lab');
  }catch(e){toast(String(e),true)}
}

async function closeModule(){
  if(activeModule&&invoke){try{await invoke('stop_module',{moduleId:activeModule})}catch(_){} }
  el('labFrame').src='about:blank'; activeModule=null; activeMode=null; showView('labs');
}


function currentModelBuilderSpec(){
  const raw=(el('modelBuilderSpec')?.value||'').trim();
  if(!raw)return null;
  try{return JSON.parse(raw)}catch(_){return null}
}
function nullableNumber(raw){const text=String(raw??'').trim();if(!text)return null;const value=Number(text);return Number.isFinite(value)?value:null}
function modelBuilderDefaultText(value){if(value===null||value===undefined)return '';if(typeof value==='string')return value;return JSON.stringify(value)}
function parseModelBuilderDefault(raw,type){const text=String(raw??'').trim();if(!text)return null;if(type==='number'){const n=Number(text);return Number.isFinite(n)?n:null}if(type==='boolean')return text==='true';try{return JSON.parse(text)}catch(_){return text}}
function renderModelBuilder(){
  const badge=el('modelBuilderProjectBadge');const ws=activeWorkspace();if(badge)badge.textContent=ws?`Project: ${ws.name}`:'No project selected';
  const analysisNode=el('modelBuilderAnalysis');
  if(analysisNode){
    if(!modelBuilderAnalysis)analysisNode.innerHTML='<div class="empty-state">Choose a Python model and analyze it.</div>';
    else{
      const warnings=modelBuilderAnalysis.warnings||[];const functions=modelBuilderAnalysis.functions||[];const imports=modelBuilderAnalysis.imports||[];
      analysisNode.innerHTML=`<div class="model-builder-kpis"><div><span>Entry</span><strong>${esc(modelBuilderAnalysis.candidate_entry||'Needs review')}</strong></div><div><span>Functions</span><strong>${functions.length}</strong></div><div><span>Imports</span><strong>${imports.length}</strong></div><div><span>SHA-256</span><strong>${esc((modelBuilderAnalysis.source_sha256||'').slice(0,12))}</strong></div></div><div class="builder-tags">${imports.map(x=>`<code>${esc(x)}</code>`).join('')||'<span class="hint">No imports detected.</span>'}</div>${warnings.length?`<div class="builder-warnings">${warnings.map(w=>`<div class="callout"><strong>${esc(w.kind)}</strong><br/>${esc(w.message)}</div>`).join('')}</div>`:'<div class="callout good-callout">No static execution-risk warning was detected. This is not a security guarantee.</div>'}<p class="hint">${esc(modelBuilderAnalysis.execution_boundary||'')}</p>`;
    }
  }
  const spec=currentModelBuilderSpec();const review=el('modelBuilderParameterReview');
  if(review){
    const params=spec?.parameters||[];
    review.innerHTML=params.length?params.map((p,i)=>`<article class="model-param-review" data-model-review="${i}"><div class="category">${esc(p.name)}</div><div class="form-grid"><label>Label<input data-mb-review-field="label" value="${esc(p.label||p.name)}" /></label><label>Unit<input data-mb-review-field="unit" value="${esc(p.unit||'')}" placeholder="unknown" /></label><label>Control<select data-mb-review-field="control"><option ${p.control==='number'?'selected':''}>number</option><option ${p.control==='slider'?'selected':''}>slider</option><option ${p.control==='toggle'?'selected':''}>toggle</option><option ${p.control==='dropdown'?'selected':''}>dropdown</option><option ${p.control==='text'?'selected':''}>text</option></select></label><label>Default<input data-mb-review-field="default" value="${esc(modelBuilderDefaultText(p.default))}" /></label><label>Min<input data-mb-review-field="min" type="number" step="any" value="${esc(p.min??'')}" /></label><label>Max<input data-mb-review-field="max" type="number" step="any" value="${esc(p.max??'')}" /></label></div></article>`).join(''):'<div class="empty-state">Detected parameters will appear here.</div>';
  }
  const bundleNode=el('modelBuilderBundle');
  if(bundleNode){bundleNode.innerHTML=modelBuilderBundle?`<div class="model-bundle-card"><div><div class="category">${esc(modelBuilderBundle.bundle_id||'MODEL BUNDLE')}</div><h4>${esc(modelBuilderBundle.model_spec?.metadata?.name||'Research Model')}</h4><p class="dataset-path">${esc(modelBuilderBundle.bundle_path||'')}</p></div><div class="builder-tags"><code>source ${esc((modelBuilderBundle.source_sha256||'').slice(0,12))}</code><code>adapter ${esc((modelBuilderBundle.adapter_sha256||'').slice(0,12))}</code><code>ModelSpec ${esc((modelBuilderBundle.model_spec_sha256||'').slice(0,12))}</code></div></div>`:'<div class="empty-state">Generate a model bundle first.</div>'}
  renderModelBuilderControls(modelBuilderBundle?.model_spec||spec);
  const previewNode=el('modelBuilderPreviewOutput');if(previewNode)previewNode.innerHTML=modelBuilderPreviewData?renderModelBuilderOutputs(modelBuilderPreviewData.outputs||{}):'<div class="empty-state">No preview run yet.</div>';
  const validationNode=el('modelBuilderValidationOutput');if(validationNode){validationNode.innerHTML=modelBuilderValidationData?`<div class="validation-banner ${modelBuilderValidationData.equivalent?'good-callout':'bad-callout'}"><strong>${modelBuilderValidationData.equivalent?'INTERFACE EQUIVALENT':'NEEDS REVIEW'}</strong><span>Compared ${modelBuilderValidationData.numeric_values_compared||0} numeric values · max |Δ| ${esc(modelBuilderValidationData.max_abs_diff??'—')}</span></div><p class="hint">${esc(modelBuilderValidationData.boundary||'')}</p>`:'<div class="empty-state">No adapter-equivalence check yet.</div>'}
}
function invalidateModelBuilderGeneratedArtifacts(){modelBuilderBundle=null;modelBuilderPreviewData=null;modelBuilderValidationData=null}
function syncModelSpecFromReview(){
  const spec=currentModelBuilderSpec();if(!spec){toast('ModelSpec JSON is invalid.',true);return null}
  document.querySelectorAll('[data-model-review]').forEach(card=>{const i=Number(card.dataset.modelReview);const p=spec.parameters?.[i];if(!p)return;const get=name=>card.querySelector(`[data-mb-review-field="${name}"]`)?.value??'';p.label=get('label').trim()||p.name;p.unit=get('unit').trim()||null;p.control=get('control');p.default=parseModelBuilderDefault(get('default'),p.type);p.min=nullableNumber(get('min'));p.max=nullableNumber(get('max'));});
  el('modelBuilderSpec').value=JSON.stringify(spec,null,2);invalidateModelBuilderGeneratedArtifacts();return spec;
}
function renderModelBuilderControls(spec){
  const node=el('modelBuilderRuntimeControls');if(!node)return;const params=spec?.parameters||[];
  if(!modelBuilderBundle||!params.length){node.innerHTML=modelBuilderBundle?'<div class="hint">This ModelSpec declares no interactive parameters.</div>':'<div class="empty-state">Generate a bundle to render ModelSpec controls.</div>';return}
  node.innerHTML=`<div class="model-runtime-controls">${params.map(p=>modelBuilderControlHtml(p)).join('')}</div>`;
  document.querySelectorAll('[data-model-param-range]').forEach(input=>input.oninput=()=>{const out=document.querySelector(`[data-model-param-value="${CSS.escape(input.dataset.modelParamRange)}"]`);if(out)out.textContent=input.value});
}
function modelBuilderControlHtml(p){
  const name=esc(p.name),label=esc(p.label||p.name),unit=p.unit?` <span>${esc(p.unit)}</span>`:'';const value=p.default??'';
  if(p.control==='slider'&&p.min!==null&&p.max!==null)return `<label class="model-runtime-control">${label}${unit}<div class="range-row"><input data-model-param data-model-param-range="${name}" data-param-name="${name}" type="range" min="${esc(p.min)}" max="${esc(p.max)}" step="any" value="${esc(value??p.min)}"/><output data-model-param-value="${name}">${esc(value??p.min)}</output></div></label>`;
  if(p.control==='toggle')return `<label class="model-runtime-control toggle-row"><input data-model-param data-param-name="${name}" type="checkbox" ${value?'checked':''}/>${label}${unit}</label>`;
  if(p.control==='dropdown'&&Array.isArray(p.options))return `<label class="model-runtime-control">${label}${unit}<select data-model-param data-param-name="${name}">${p.options.map(v=>`<option value="${esc(v)}" ${String(v)===String(value)?'selected':''}>${esc(v)}</option>`).join('')}</select></label>`;
  const type=p.control==='number'||p.type==='number'?'number':'text';return `<label class="model-runtime-control">${label}${unit}<input data-model-param data-param-name="${name}" type="${type}" ${type==='number'?'step="any"':''} value="${esc(value)}"/></label>`;
}
function collectModelBuilderParameters(){
  const params={};for(const input of document.querySelectorAll('[data-model-param]')){const name=input.dataset.paramName;if(!name)continue;if(input.type==='checkbox')params[name]=input.checked;else if(input.type==='number'||input.type==='range'){const n=Number(input.value);if(!Number.isFinite(n))throw new Error(`Parameter ${name} needs a finite number.`);params[name]=n}else params[name]=input.value}return params;
}
function numericArray(value){return Array.isArray(value)&&value.length>1&&value.every(v=>typeof v==='number'&&Number.isFinite(v))}
function sparkline(values){const w=280,h=90,min=Math.min(...values),max=Math.max(...values),span=Math.max(1e-12,max-min);const points=values.map((v,i)=>`${(i/(values.length-1)*w).toFixed(2)},${(h-(v-min)/span*h).toFixed(2)}`).join(' ');return `<svg class="builder-sparkline" viewBox="0 0 ${w} ${h}" role="img" aria-label="numeric output sparkline"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2"/></svg>`}
function xyPlot(x,y){const w=520,h=180,x0=Math.min(...x),x1=Math.max(...x),y0=Math.min(...y),y1=Math.max(...y),xs=Math.max(1e-12,x1-x0),ys=Math.max(1e-12,y1-y0);const points=x.map((v,i)=>`${((v-x0)/xs*w).toFixed(2)},${(h-(y[i]-y0)/ys*h).toFixed(2)}`).join(' ');return `<div class="builder-xy"><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="automatic x-y preview"><polyline points="${points}" fill="none" stroke="currentColor" stroke-width="2"/></svg><small>x ${x0.toPrecision(4)} → ${x1.toPrecision(4)} · y ${y0.toPrecision(4)} → ${y1.toPrecision(4)}</small></div>`}
function renderModelBuilderOutputs(outputs){const entries=Object.entries(outputs||{});const arrays=entries.filter(([,v])=>numericArray(v));const auto=arrays.length>=2&&arrays[0][1].length===arrays[1][1].length?`<div class="builder-auto-plot"><div class="category">AUTO X-Y · ${esc(arrays[0][0])} → ${esc(arrays[1][0])}</div>${xyPlot(arrays[0][1],arrays[1][1])}</div>`:'';return `${auto}<div class="model-output-grid">${entries.map(([k,v])=>`<article class="model-output-card"><div class="category">${esc(k)}</div>${typeof v==='number'?`<strong>${esc(v)}</strong>`:numericArray(v)?`${sparkline(v)}<small>${v.length} values · min ${Math.min(...v).toPrecision(5)} · max ${Math.max(...v).toPrecision(5)}</small>`:`<pre>${esc(JSON.stringify(v,null,2))}</pre>`}</article>`).join('')}</div>`}
async function chooseResearchModelSource(){if(!invoke){toast('File chooser is available in the desktop build.');return}try{const path=await invoke('model_builder_choose_source');el('modelBuilderSource').value=path}catch(e){if(!String(e).toLowerCase().includes('cancel'))toast(String(e),true)}}
async function analyzeResearchModel(){const sourcePath=el('modelBuilderSource').value.trim();if(!sourcePath){toast('Choose a .py source first.',true);return}if(!invoke){toast('Static model analysis is available in the desktop build.');return}try{modelBuilderAnalysis=await invoke('model_builder_analyze',{sourcePath});modelBuilderBundle=null;modelBuilderPreviewData=null;modelBuilderValidationData=null;el('modelBuilderSpec').value=JSON.stringify(modelBuilderAnalysis.candidate_model_spec||{},null,2);renderModelBuilder();toast('Static analysis complete. Source was not executed.')}catch(e){toast(String(e),true)}}
async function generateResearchModel(){if(!invoke)return;const sourcePath=el('modelBuilderSource').value.trim();const spec=syncModelSpecFromReview()||currentModelBuilderSpec();if(!sourcePath||!spec){toast('Analyze the source and review ModelSpec first.',true);return}try{modelBuilderBundle=await invoke('model_builder_generate',{sourcePath,modelSpec:spec});modelBuilderPreviewData=null;modelBuilderValidationData=null;renderModelBuilder();toast('Adapter and deterministic UI bundle generated without executing the source.')}catch(e){toast(String(e),true)}}
function modelBuilderTrusted(){return !!el('modelBuilderTrusted')?.checked}
async function runResearchModelPreview(){if(!invoke||!modelBuilderBundle){toast('Generate a model bundle first.',true);return}if(!modelBuilderTrusted()){toast('Confirm that you trust this local Python source before execution.',true);return}try{const parameters=collectModelBuilderParameters();modelBuilderPreviewData=await invoke('model_builder_run',{bundlePath:modelBuilderBundle.bundle_path,parameters,trusted:true});renderModelBuilder();toast('Local preview complete.')}catch(e){toast(String(e),true)}}
async function validateResearchModelAdapter(){if(!invoke||!modelBuilderBundle){toast('Generate a model bundle first.',true);return}if(!modelBuilderTrusted()){toast('Confirm that you trust this local Python source before execution.',true);return}try{const parameters=collectModelBuilderParameters();modelBuilderValidationData=await invoke('model_builder_validate',{bundlePath:modelBuilderBundle.bundle_path,parameters,trusted:true});renderModelBuilder();toast(modelBuilderValidationData.equivalent?'Adapter equivalence passed.':'Adapter needs review.',!modelBuilderValidationData.equivalent)}catch(e){toast(String(e),true)}}
async function saveResearchModelToProject(){if(!invoke||!modelBuilderBundle){toast('Generate a model bundle first.',true);return}if(!activeWorkspaceId){toast('Create or select a canonical Project first.',true);return}try{const record=await invoke('save_model_builder_bundle',{workspaceId:activeWorkspaceId,bundlePath:modelBuilderBundle.bundle_path});await refreshResearchBasics();render();toast(`Saved ${record.name||'research model'} to the active Project.`)}catch(e){toast(String(e),true)}}
async function openResearchModelBundle(){if(!invoke||!modelBuilderBundle)return;try{await invoke('model_builder_open_bundle',{bundlePath:modelBuilderBundle.bundle_path})}catch(e){toast(String(e),true)}}

function renderTasks(){
  const list=[...tasks.values()].sort((a,b)=>(b.updatedAt||0)-(a.updatedAt||0));
  const running=list.filter(t=>!t.done).length; el('taskBadge').textContent=String(running); el('taskBadge').classList.toggle('hidden',running===0);
  if(!list.length){el('taskList').innerHTML='<div class="empty-state">No tasks yet.</div>';return}
  el('taskList').innerHTML=list.map(t=>`<div class="task"><div class="task-head"><div><div class="task-title">${esc(t.title)}</div><div class="task-meta">${esc(t.stage||'Working')} · ${esc(t.moduleId||'Physical Lab')}</div></div><div class="task-controls"><div class="task-state">${esc(t.status||'Running')}</div>${t.done?`<button class="task-delete" data-task-delete="${esc(t.taskId)}" title="Delete task entry">×</button>`:`<button class="secondary small" data-task-cancel="${esc(t.taskId)}">Cancel</button>`}</div></div><div class="progress"><div style="width:${Math.max(2,Math.min(100,t.percent??18))}%"></div></div><div class="task-message">${esc(t.message||'')}</div></div>`).join('');
  document.querySelectorAll('[data-task-delete]').forEach(b=>b.onclick=()=>{tasks.delete(b.dataset.taskDelete);renderTasks()});
  document.querySelectorAll('[data-task-cancel]').forEach(b=>b.onclick=()=>cancelTaskById(b.dataset.taskCancel));
}

async function cancelTaskById(id){if(!invoke)return;try{const msg=await invoke('cancel_task',{taskId:id});toast(msg)}catch(e){toast(String(e),true)}}
function onTask(ev){const t=ev.payload||ev;const previous=tasks.get(t.taskId);t.updatedAt=Date.now();tasks.set(t.taskId,t);renderTasks();if(uiSettings.taskCompletionToasts&&t.done&&!previous?.done)toast(`${t.title||'Physical Lab task'} completed.`);}
function applySearch(){const q=el('searchInput').value.trim().toLowerCase();document.querySelectorAll('.module-card[data-search]').forEach(c=>c.style.display=(!q||c.dataset.search.includes(q))?'':'none')}

async function initEvents(){if(listen){await listen('physical-lab://task-progress',onTask)}}

document.querySelectorAll('.nav-item').forEach(b=>b.onclick=()=>showView(b.dataset.view));
document.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>showView(b.dataset.go));
el('refreshBtn').onclick=refreshAll;
  if(el('exportDependencyReport'))el('exportDependencyReport').onclick=exportDependencyDoctorReport;
  if(el('refreshDependencies'))el('refreshDependencies').onclick=refreshAll; el('searchInput').oninput=applySearch; el('backFromLab').onclick=closeModule; el('reloadLab').onclick=()=>{const f=el('labFrame');f.src=f.src};
el('clearTasks').onclick=()=>{for(const [k,v] of tasks)if(v.done)tasks.delete(k);renderTasks()};
el('openLogs').onclick=async()=>{if(!invoke){toast(logDir||'Log folder is available in the desktop build.');return}try{const p=await invoke('open_log_directory');toast(`Opened logs: ${p}`)}catch(e){toast(String(e),true)}};
el('openData').onclick=async()=>{if(!invoke){toast(dataDir||'Data folder is available in the desktop build.');return}try{const p=await invoke('open_data_directory');toast(`Opened Physical Lab data: ${p}`)}catch(e){toast(String(e),true)}};


if(el('modelBuilderChooseSource'))el('modelBuilderChooseSource').onclick=chooseResearchModelSource;
if(el('modelBuilderAnalyze'))el('modelBuilderAnalyze').onclick=analyzeResearchModel;
if(el('modelBuilderApplyReview'))el('modelBuilderApplyReview').onclick=()=>{if(syncModelSpecFromReview())renderModelBuilder()};
if(el('modelBuilderGenerate'))el('modelBuilderGenerate').onclick=generateResearchModel;
if(el('modelBuilderPreview'))el('modelBuilderPreview').onclick=runResearchModelPreview;
if(el('modelBuilderValidate'))el('modelBuilderValidate').onclick=validateResearchModelAdapter;
if(el('modelBuilderSave'))el('modelBuilderSave').onclick=saveResearchModelToProject;
if(el('modelBuilderOpenBundle'))el('modelBuilderOpenBundle').onclick=openResearchModelBundle;
if(el('modelBuilderSpec'))el('modelBuilderSpec').onchange=()=>{invalidateModelBuilderGeneratedArtifacts();renderModelBuilder()};

if(el('createWorkspace'))el('createWorkspace').onclick=createProject;
if(el('refreshWorkspaces'))el('refreshWorkspaces').onclick=async()=>{await refreshResearchBasics();renderResearch()};
if(el('importDataset'))el('importDataset').onclick=importMeasurement;
if(el('scanSerial'))el('scanSerial').onclick=scanSerialDevices;
if(el('captureSerial'))el('captureSerial').onclick=captureSerial;
if(el('refreshDatasets'))el('refreshDatasets').onclick=()=>refreshDatasetsForActive(true);
if(el('runIntegrity'))el('runIntegrity').onclick=runIntegrityChecks;
if(el('createCampaign'))el('createCampaign').onclick=createCampaignQueue;
if(el('analyzeDataset'))el('analyzeDataset').onclick=analyzeSelectedDataset;
if(el('validateDataset'))el('validateDataset').onclick=validateSelectedDataset;
if(el('saveSnapshot'))el('saveSnapshot').onclick=saveRunSnapshot;
if(el('exportRepro'))el('exportRepro').onclick=exportRepro;
if(el('compareRuns'))el('compareRuns').onclick=compareSavedRuns;
if(el('saveSettings'))el('saveSettings').onclick=saveUiSettings;
if(el('resetSettings'))el('resetSettings').onclick=resetUiSettings;

initEvents().then(refreshAll);
