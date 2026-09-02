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
  const map={home:['homeView','Physical Lab','One local home for your computational physics tools.'],labs:['labsView','Physics Labs','Install, open and switch between computational models.'],runtime:['runtimeView','Runtime Center','Scientific runtimes, builders and dependency health.'],dependencies:['dependenciesView','Dependency Center','Everything Physical Lab needs, and exactly how it is delivered.'],tasks:['tasksView','Task Center','Live work performed by Physical Lab.'],lab:['labView','Lab Session','Running locally inside Physical Lab.']};
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
    render();
  }catch(e){toast(String(e),true)}
}

function statusFor(m){return statuses[m.id]||{installed:false,ready:false,safeReady:false,fullReady:false,state:'Unknown'}};
function modeChoice(m,s){
  if(!selectedModes[m.id]) selectedModes[m.id]=s.fullReady?'full':'safe';
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
  el('stats').innerHTML=[['10','Integrated modules'],[String(labs.length),'Physics labs'],[String(runtimes.length),'Runtime builders'],[String(installed),'Ready to open']].map(s=>`<div class="stat"><strong>${s[0]}</strong><span>${s[1]}</span></div>`).join('');
  el('featuredGrid').innerHTML=labs.slice(-3).map(labCard).join('');
  const cats=['All',...new Set(labs.map(m=>m.category))];
  el('labFilters').innerHTML=cats.map(c=>`<button class="filter ${c===activeCategory?'active':''}" data-cat="${esc(c)}">${esc(c)}</button>`).join('');
  const visible=activeCategory==='All'?labs:labs.filter(m=>m.category===activeCategory);
  el('labGrid').innerHTML=visible.map(labCard).join('');
  el('runtimeGrid').innerHTML=runtimes.map(runtimeCard).join('');
  renderRuntimeSummary(); renderDependencies(); bindDynamic(); renderTasks(); applySearch();
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

function renderTasks(){
  const list=[...tasks.values()].sort((a,b)=>(b.updatedAt||0)-(a.updatedAt||0));
  const running=list.filter(t=>!t.done).length; el('taskBadge').textContent=String(running); el('taskBadge').classList.toggle('hidden',running===0);
  if(!list.length){el('taskList').innerHTML='<div class="empty-state">No tasks yet.</div>';return}
  el('taskList').innerHTML=list.map(t=>`<div class="task"><div class="task-head"><div><div class="task-title">${esc(t.title)}</div><div class="task-meta">${esc(t.stage||'Working')} · ${esc(t.moduleId||'Physical Lab')}</div></div><div class="task-controls"><div class="task-state">${esc(t.status||'Running')}</div>${t.done?`<button class="task-delete" data-task-delete="${esc(t.taskId)}" title="Delete task entry">×</button>`:''}</div></div><div class="progress"><div style="width:${Math.max(2,Math.min(100,t.percent??18))}%"></div></div><div class="task-message">${esc(t.message||'')}</div></div>`).join('');
  document.querySelectorAll('[data-task-delete]').forEach(b=>b.onclick=()=>{tasks.delete(b.dataset.taskDelete);renderTasks()});
}

function onTask(ev){const t=ev.payload||ev;t.updatedAt=Date.now();tasks.set(t.taskId,t);renderTasks();}
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

initEvents().then(refreshAll);
