'use strict';
const app = document.querySelector('#app');
const modal = document.querySelector('#modal');
const names = {overview:'Tools',sites:'Websites & domains',hosting:'Apps & databases',files:'File manager',accounts:'Accounts',plans:'Hosting plans',dns:'DNS zones',backups:'Backups',audit:'Activity log',status:'Release status'};
const paths = {overview:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',sites:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z"/>',files:'<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>',accounts:'<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3"/>',backups:'<path d="M5 8H3v13h18V8h-2M3 3h18v5H3ZM12 12v5m-3-3 3 3 3-3"/>',audit:'<path d="M5 3h10l4 4v14H5ZM9 11h6M9 15h6M15 3v5h4"/>',status:'<path d="m12 3 8 4v6c0 4-8 8-8 8s-8-4-8-8V7Z"/><path d="m8 12 3 3 5-6"/>',plus:'<path d="M12 5v14M5 12h14"/>',arrow:'<path d="M4 12h15m-5-5 5 5-5 5"/>',refresh:'<path d="M20 5v5h-5M4 19v-5h5M19 9a8 8 0 0 0-13-4M5 15a8 8 0 0 0 13 4"/>',logout:'<path d="M9 4H4v16h5m5-4 4-4-4-4m-6 4h14"/>',check:'<path d="m5 12 4 4L20 5"/>',close:'<path d="m6 6 12 12M6 18 18 6"/>',server:'<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.1M7 17.5h.1"/>',cpu:'<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 1v5m6-5v5M9 18v5m6-5v5M1 9h5m-5 6h5m12-6h5m-5 6h5"/>',disk:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',file:'<path d="M5 3h9l5 5v13H5ZM14 3v6h5"/>',download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',up:'<path d="M12 20V4m-6 6 6-6 6 6"/>',lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>'};
paths.hosting=paths.server;
paths.plans=paths.disk;
paths.dns='<circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 7v5M5 17v-5h14v5"/>';
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name]||paths.status}</svg>`;
const e = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bytes = n => n==null?'Unavailable':n<1024?`${n} B`:n<1048576?`${(n/1024).toFixed(1)} KB`:n<1073741824?`${(n/1048576).toFixed(1)} MB`:`${(n/1073741824).toFixed(1)} GB`;
const date = n => new Date(n*1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
const managesCustomers=()=>['admin','reseller'].includes(state.overview?.user.role);
const featureNames={php:'PHP',wordpress:'WordPress',databases:'Databases',tls:'HTTPS',dns:'DNS preview',mail:'Email (planned)'};
let state = {plans:[],pool:null,dns:null,page:'overview', overview:null, sites:[], accounts:[], events:[], backups:[], jobs:[], databases:[], csrf:'', siteId:null, folder:'', file:null, revision:null};
let setupToken = new URLSearchParams(location.hash.slice(1)).get('setup') || '';
if(location.hash) history.replaceState(null,'',location.pathname);
let toastTimer, toolQuery='', navigationBusy=false;
const workspaceName=()=>({admin:'Server administration',reseller:'Reseller management',customer:'Hosting workspace'}[state.overview?.user.role]||'Hosting workspace');
function toolGroups(){
  const groups=[];
  if(managesCustomers())groups.push({title:'Accounts & packages',icon:'accounts',tools:[
    ['accounts','List accounts','Manage customers, access and hosting allowances.','customers resellers users suspend'],
    ['new-account','Create account','Add a customer'+(state.overview.user.role==='admin'?' or reseller':'')+' with a hosting plan.','new user reseller','action'],
    ['plans','Hosting plans','Review packages, reservations and included features.','packages quotas limits'],
    ['new-plan','Create hosting plan','Define a package for new or existing accounts.','add package quota','action']]});
  groups.push({title:'Websites & domains',icon:'sites',tools:[
    ['sites','Websites & domains','View domains, owners and website status.','domain suspend activate'],
    ['new-site','Create website','Add a domain to your hosting workspace.','add domain site','action'],
    ['dns','DNS zone editor','Validate and export a private DNS preview.','records nameserver zone ttl txt'],
    ['hosting','HTTPS certificates','Issue a domain certificate for an isolated website.','ssl tls acme certificate']]},
  {title:'Files & backups',icon:'files',tools:[
    ['files','File manager','Browse folders and edit website text files.','editor directory storage'],
    ['backups','Backup & restore','Create, download and restore local recovery points.','recovery export download']]},
  {title:'Applications & databases',icon:'server',tools:[
    ['hosting','WordPress installer','Install WordPress on a fresh isolated website.','wordpress cms install'],
    ['hosting','PHP hosting','Enable isolated PHP for a website.','php fpm runtime'],
    ['hosting','Databases','Create a private database and view connection details.','mariadb mysql sql credentials']]},
  {title:'Monitoring & information',icon:'audit',tools:[
    ['audit','Activity log','Review the actions visible to your account.','events history audit'],
    ['hosting','Background jobs','View installation, certificate and recovery jobs.','queue tasks progress'],
    ['status','Release & service status','See implemented capabilities and observed services.','version server health planned']]});
  return groups;
}
function toolDirectory(){return `<div id="tool-directory">${toolGroups().map((g,i)=>`<section class="panel tool-group" data-tool-group><h2 class="tool-group-heading"><button class="group-toggle" data-action="toggle-group" aria-expanded="true" aria-controls="tool-group-${i}">${icon(g.icon)}<span>${g.title}</span><span class="chevron" aria-hidden="true">⌃</span></button></h2><div class="tool-grid" id="tool-group-${i}">${g.tools.map(t=>`<button class="tool-link" ${t[4]==='action'?`data-action="${t[0]}"`:`data-page="${t[0]}"`} data-tool-search="${e([g.title,...t.slice(1,4)].join(' ').toLowerCase())}"><span class="tool-icon">${icon(t[0] in paths?t[0]:g.icon)}</span><span class="tool-copy"><strong>${t[1]}</strong><small>${t[2]}</small></span></button>`).join('')}</div></section>`).join('')}<p id="tool-no-results" class="empty" hidden>No tools match your search. Try a tool name such as files, DNS or backups.</p></div>`;}
function filterTools(){
  const terms=toolQuery.trim().toLowerCase().split(/\s+/).filter(Boolean);let count=0;
  document.querySelectorAll('[data-tool-group]').forEach(group=>{
    let visible=0;group.querySelectorAll('[data-tool-search]').forEach(tool=>{tool.hidden=!terms.every(t=>tool.dataset.toolSearch.includes(t));if(!tool.hidden)visible++;});
    group.hidden=visible===0;count+=visible;
    if(terms.length&&visible){group.querySelector('.tool-grid').hidden=false;group.querySelector('.group-toggle').setAttribute('aria-expanded','true');}
  });
  const empty=document.querySelector('#tool-no-results');if(empty)empty.hidden=count>0;
  const result=document.querySelector('#tool-results');if(result)result.textContent=toolQuery.trim()?`${count} matching tool${count===1?'':'s'}`:'Available tools';
}
function setNavigation(open){
  const shell=document.querySelector('.shell');if(!shell)return;
  const mobile=matchMedia('(max-width: 760px)').matches,sidebar=document.querySelector('.sidebar'),main=document.querySelector('.main');
  open=Boolean(open&&mobile);shell.classList.toggle('menu-open',open);document.body.classList.toggle('navigation-open',open);main.inert=open;
  document.querySelector('[data-action="open-navigation"]').setAttribute('aria-expanded',String(open));
  if(open){sidebar.setAttribute('role','dialog');sidebar.setAttribute('aria-modal','true');document.querySelector('[data-action="close-navigation"]').focus();}
  else{sidebar.removeAttribute('role');sidebar.removeAttribute('aria-modal');}
}
function focusPage(){document.querySelector('#page h1')?.focus();}
function notify(message,error=false){const el=document.querySelector('#toast');el.textContent=message;el.className=error?'error':'';el.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.hidden=true,6000);}
async function api(method,data={},download=false){
  const response=await fetch('/api',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},body:JSON.stringify({method,data})});
  if(!response.ok){const body=await response.json().catch(()=>({error:'The server could not complete the request.'}));const err=new Error(body.error);err.status=response.status;throw err;}
  return download?response.blob():response.json();
}
async function downloadBackup(id){
  const info=await api('backups.describe',{id});
  const size=262144,parts=new Array(Math.ceil(info.bytes/size));
  let cursor=0,done=0,lastNotice=0;
  async function worker(){
    while(cursor<parts.length){
      const index=cursor++,offset=index*size;
      let result;
      for(let retry=0;retry<3;retry++){
        try{result=await api('backups.chunk',{id,offset});break;}catch(err){if(retry===2||err.status===401||err.status===404)throw err;}
      }
      const raw=atob(result.base64),part=Uint8Array.from(raw,c=>c.charCodeAt(0));
      if(part.length!==Math.min(size,info.bytes-offset))throw new Error('The backup download was incomplete. Please retry.');
      parts[index]=part;done+=part.length;
      if(Date.now()-lastNotice>3000){notify(`Downloading backup… ${Math.round(done/info.bytes*100)}%`);lastNotice=Date.now();}
    }
  }
  await Promise.all([worker(),worker(),worker()]);
  const blob=new Blob(parts,{type:'application/gzip'});
  const digest=await crypto.subtle.digest('SHA-256',await blob.arrayBuffer());
  const hash=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
  if(hash!==info.sha256)throw new Error('Backup download integrity verification failed. Please retry.');
  return blob;
}
function brand(){return '<div class="brand"><img class="brand-wordmark" src="/brand-light.svg" alt="VectorCP"></div>';}
function auth(setup=false){
  state.overview=null;state.csrf='';
  app.innerHTML=`<main class="auth"><section class="auth-story">${brand()}<div class="story"><div class="eyebrow">Open-source hosting control.</div><h1>Your hosting.<br><span>Your control.</span></h1><p>A focused workspace for your websites, files and the people behind them.</p></div><footer>OPEN-SOURCE HOSTING CONTROL · VECTORCP</footer></section><section class="auth-form"><div class="eyebrow muted">${setup?'FIRST-TIME SETUP':({'/admin':'SERVER OWNER SIGN-IN','/reseller':'RESELLER SIGN-IN','/customer':'CUSTOMER SIGN-IN'}[location.pathname]||'YOUR HOSTING WORKSPACE')}</div><h2>${setup?'Make it yours.':'Welcome back.'}</h2><p class="intro">${setup?'Create the first administrator using the one-time token from your server.':'Sign in to manage your hosting workspace.'}</p><form data-form="${setup?'bootstrap':'login'}">${setup?`<label class="field">Setup token<input name="setup_token" type="password" required autocomplete="off" value="${e(setupToken)}"></label><label class="field">Your name<input name="name" required maxlength="80" autocomplete="name"></label>`:''}<label class="field">Username<input name="username" required minlength="3" maxlength="32" autocomplete="username" autocapitalize="none" spellcheck="false"></label><label class="field">Password<input name="password" type="password" required ${setup?'minlength="12"':''} maxlength="256" autocomplete="${setup?'new-password':'current-password'}"></label><p class="form-error" role="alert"></p><button class="primary" type="submit">${setup?'Create administrator':'Sign in'} ${icon('arrow')}</button></form><p class="auth-bottom">${setup?'Already configured?':'Setting up a new server?'} <button class="quiet" data-action="auth-toggle" data-setup="${setup?'false':'true'}">${setup?'Sign in':'First-time setup'}</button></p></section></main>`;
}
function shell(){
  const o=state.overview,u=o.user;
  const groups=[['Workspace',['overview','sites','hosting','files','dns']],...(managesCustomers()?[['Account management',['accounts','plans']]]:[]),['Operations',['backups','audit','status']]];
  document.body.classList.remove('navigation-open');
  app.innerHTML=`<a class="skip-link" href="#page">Skip to main content</a><div class="shell"><aside class="sidebar" id="workspace-navigation" aria-label="Workspace navigation"><div class="sidebar-heading">${brand()}<button class="icon-button close-navigation" data-action="close-navigation" aria-label="Close navigation">${icon('close')}</button></div><div class="workspace-label">${workspaceName()}</div><nav aria-label="Main navigation">${groups.map(([label,pages])=>`<div class="nav-section"><div class="nav-label">${label}</div>${pages.map(p=>`<button class="nav-item ${state.page===p?'current':''}" ${state.page===p?'aria-current="page"':''} data-page="${p}">${icon(p)}<span>${names[p]}</span></button>`).join('')}</div>`).join('')}</nav><div class="sidebar-bottom"><span class="version-label">Development · ${e(o.version)}</span><div class="person"><span class="avatar">${e(u.name.slice(0,1).toUpperCase())}</span><div class="person-copy"><div class="person-name">${e(u.name)}</div><div class="person-role">${e(u.role==='admin'?'Server owner':u.role)}</div></div></div></div></aside><button class="navigation-shade" data-action="close-navigation" aria-label="Close navigation" tabindex="-1"></button><main class="main"><header class="topbar"><button class="icon-button open-navigation" data-action="open-navigation" aria-label="Open navigation" aria-controls="workspace-navigation" aria-expanded="false">${icon('overview')}</button><div class="breadcrumb">${workspaceName()}<span>/ ${names[state.page]}</span></div><form class="tool-search" data-form="tool-search" role="search"><label class="sr-only" for="tool-search">Search tools</label><input id="tool-search" type="search" name="query" placeholder="Search tools…" value="${e(toolQuery)}" autocomplete="off"><button type="submit" class="icon-button" aria-label="Search tools">${icon('arrow')}</button></form><div class="top-actions"><button class="icon-button" data-action="refresh" aria-label="Refresh current page">${icon('refresh')}</button><button class="icon-button" data-action="logout" aria-label="Sign out">${icon('logout')}</button></div></header>${o.development?`<div class="development-banner">${icon('status')}Local validation instance. Websites are not published to the Internet.</div>`:''}<div class="content" id="page" tabindex="-1"></div></main></div>`;
  render();
}
function heading(title,sub,action=''){return `<div class="page-heading"><div><h1 tabindex="-1">${title}</h1><p>${sub}</p></div>${action?`<div class="heading-actions">${action}</div>`:''}</div>`;}
function actionButton(action,label,kind='primary',ico='plus'){return `<button class="${kind}" data-action="${action}">${icon(ico)}${label}</button>`;}
function empty(title,body,action='',ico='sites'){return `<div class="empty">${icon(ico)}<strong>${title}</strong>${body}${action}</div>`;}
function statusPill(status){return `<span class="pill ${status==='active'?'':'gray'}">${status==='active'?'Active':e(status)}</span>`;}
function tableFilter(name){return `<div class="table-filter"><label for="filter-${name}">Filter ${name}</label><input id="filter-${name}" type="search" data-filter-table placeholder="Search visible ${name}…" autocomplete="off"><span class="filter-result" role="status"></span></div>`;}
function siteRows(rows,compact=false){return `<div class="table-wrap"><table><thead><tr><th>Website</th>${compact?'':'<th>Owner</th>'}<th>Status</th><th></th></tr></thead><tbody>${rows.map(s=>`<tr><td><div class="domain-cell"><span class="site-icon">${icon('sites')}</span>${e(s.domain)}</div></td>${compact?'':`<td class="muted">${e(s.username)}</td>`}<td>${statusPill(s.status)}</td><td><div class="table-actions"><button class="quiet" data-action="open-hosting" data-id="${s.id}">Hosting</button><button class="quiet" data-action="open-files" data-id="${s.id}">Files ${icon('arrow')}</button>${compact || !managesCustomers()?'':`<button class="quiet" data-action="toggle-site" data-id="${s.id}" data-active="${s.status!=='active'}">${s.status==='active'?'Suspend':'Activate'}</button>`}</div></td></tr>`).join('')}</tbody></table></div>`;}
const actionName = a => ({'site.created':'Website created','site.active':'Website activated','site.suspended':'Website suspended','file.saved':'File saved','folder.created':'Folder created','account.created':'Customer created','account.access_enabled':'Panel access enabled','account.access_locked':'Panel access locked','session.created':'Signed in','session.closed':'Signed out','administrator.created':'Administrator created','backup.created':'Site export created','backup.downloaded':'Site export downloaded'}[a]||a);
const jobLabel=a=>({'hosting.enable':'Enable customer hosting','hosting.php':'Enable PHP','hosting.wordpress':'Install WordPress','hosting.tls':'Enable HTTPS','databases.create':'Create database','backups.full':'Create full backup','backups.restore':'Restore website'}[a]||a);
function activity(rows){return rows.length?rows.map(a=>`<div class="activity-item"><span class="activity-dot"></span><div><strong>${e(actionName(a.action))}</strong><small>${e(a.target)} · ${e(a.actor)}</small></div><time>${e(date(a.created))}</time></div>`).join(''):empty('A fresh start','Your workspace activity will appear here.','','audit');}
function render(){
  const page=document.querySelector('#page'); if(!page)return;
  const o=state.overview;let html='';
  if(state.page==='overview'){
    const disk=o.host.disk,percent=Math.round(disk.used/disk.total*100),memory=o.host.memory;
    html=heading('Tools',managesCustomers()?'Manage hosting accounts, websites and server operations.':'Manage your websites, files, applications and backups.');
    html+=`<div class="tools-layout"><div class="tools-main"><div class="directory-caption"><h2 id="tool-results" aria-live="polite">Available tools</h2><button class="quiet" data-action="clear-search">Show all tools</button></div>${toolDirectory()}<p class="note-line">This development workspace contains implemented tools. <a href="https://vectorcp.net/docs/capabilities/" target="_blank" rel="noopener noreferrer">View the full capability catalog ↗</a> for partial and planned systems, including email and public DNS.</p><section class="panel"><div class="panel-head"><h2>Recent activity</h2><button class="quiet" data-page="audit">View all ${icon('arrow')}</button></div>${activity(state.events.slice(0,3))}</section></div><aside class="workspace-information" aria-label="Workspace information"><section class="panel"><div class="panel-head"><h2>${managesCustomers()?'Server information':'General information'}</h2></div><dl class="information-list"><div><dt>Current user</dt><dd>${e(o.user.username)}</dd></div><div><dt>Access level</dt><dd>${e(o.user.role==='admin'?'Server owner':o.user.role)}</dd></div><div><dt>${managesCustomers()?'Hostname':'Primary website'}</dt><dd>${e(managesCustomers()?o.host.hostname:(state.sites[0]?.domain||'No websites yet'))}</dd></div>${managesCustomers()?`<div><dt>Operating system</dt><dd>${e(o.host.os)}</dd></div>`:''}<div><dt>Server address</dt><dd class="mono">${e(o.public_ipv4||'Not configured')}</dd></div><div><dt>Release</dt><dd>${e(o.version)} <span class="muted">· Development</span></dd></div></dl></section><section class="panel"><div class="panel-head"><h2>${managesCustomers()?'Server statistics':'Account statistics'}</h2></div><div class="panel-body"><div class="health-row"><span>Websites</span><strong>${o.counts.sites}${!managesCustomers()?' / '+o.user.site_limit:''}</strong></div><div class="health-row"><span>Active websites</span><strong>${o.counts.active}</strong></div>${managesCustomers()?`<div class="health-row"><span>Customers</span><strong>${o.counts.accounts}</strong></div>`:''}<div class="resource-line"><span>Website files</span><strong>${bytes(o.usage_bytes)}</strong></div>${managesCustomers()?`<hr><div class="resource-line"><span>Host disk used</span><strong>${percent}%</strong></div><progress class="progress" max="100" value="${percent}" aria-label="Host disk used"></progress><p class="small muted">${bytes(disk.used)} / ${bytes(disk.total)}</p><div class="resource-line"><span>Host memory used</span><strong>${memory?.total?Math.round((1-memory.available/memory.total)*100)+'%':'Unavailable'}</strong></div><progress class="progress" max="100" value="${memory?.total?Math.round((1-memory.available/memory.total)*100):0}" aria-label="Host memory used"></progress><div class="health-row"><span>1-minute load</span><strong>${o.host.load[0].toFixed(2)} / ${o.host.cpus} cores</strong></div><p class="small muted">Observed host measurements.</p>`:''}</div></section></aside></div>`;
  }else if(state.page==='sites'){
    html=heading('Websites & domains','Domains, website status and the people who own them.',actionButton('new-site','Add website'))+`<section class="panel"><div class="panel-head"><h2>All websites</h2><span class="badge-counter">${state.sites.length} total</span></div>${state.sites.length?tableFilter('websites')+siteRows(state.sites):empty('Your first website starts here.','Create a website, then point its domain to your server.',actionButton('new-site','Add website','secondary'))}</section><p class="note-line">Point each domain’s A record to ${e(o.public_ipv4||'the configured server IP')}. Apps & hosting provides PHP, WordPress and HTTPS for isolated customers. Suspending a website returns HTTP 503.</p>`;
  }else if(state.page==='accounts'){
    html=heading('Accounts','Customers, resellers and the plans that give them room.',actionButton('new-account','Add account'))+`<section class="panel"><div class="panel-head"><h2>Workspace accounts</h2><span class="badge-counter">${state.accounts.length} visible</span></div>${tableFilter('accounts')}<div class="table-wrap"><table><thead><tr><th>Name</th><th>Username</th><th>Plan & allowance</th><th>Panel access</th><th></th></tr></thead><tbody>${state.accounts.map(a=>`<tr><td><strong>${e(a.name)}</strong><div class="small muted">${e(a.role)}${a.parent_id?' · delegated customer':''}</div></td><td>${e(a.username)}</td><td>${e(a.plan_name||'Custom allowance')}<div class="small muted">${a.site_limit} sites · ${a.storage_mb} MB</div></td><td>${statusPill(a.active?'active':'locked')}${a.admin_lock?' <span class="small muted">Owner lock</span>':''}</td><td><div class="table-actions">${a.role!=='admin'?`<button class="quiet" data-action="toggle-account" data-id="${a.id}" data-active="${!a.active}">${a.active?'Lock panel':'Enable panel'}</button>${!a.parent_id||a.parent_id===o.user.id?`<button class="quiet" data-action="assign-plan" data-id="${a.id}">Change plan</button>`:''}${a.role==='customer'?(a.hosting_slot?' <span class="pill">Isolated</span>':` <button class="quiet" data-action="enable-hosting" data-id="${a.id}">Enable hosting</button>`):''}`:''}</div></td></tr>`).join('')}</tbody></table></div></section><p class="note-line">A reseller manages only its own customers. Locking a reseller also signs out its customers; hosted websites keep their current state. The server owner’s locks and website holds cannot be reversed by resellers. Hosting volumes have fixed sizes.</p>`;
  }else if(state.page==='plans'){
    const pool=state.pool;
    html=heading('Hosting plans','Reusable packages for customers and resellers.',actionButton('new-plan','Create plan'))+`<div class="callout"><strong>${o.user.role==='reseller'?'Your reserved customer pool':'Server hosting reservations'}</strong>${pool?.customers!=null?`${pool.customers} / ${pool.customer_limit} customers · ${pool.sites} / ${pool.site_limit} websites · ${pool.storage_mb} / ${pool.storage_limit_mb} MB reserved`:`${pool?.reserved_mb||0} / ${pool?.storage_limit_mb||16384} MB reserved`}<p>Locked accounts still reserve their allowance. Plans stay unchanged after creation; create another plan and assign it explicitly when a customer needs a change. Retiring a plan stops new assignments.</p></div><section class="panel"><div class="panel-head"><h2>Hosting packages</h2><span class="badge-counter">${state.plans.length} plans</span></div>${state.plans.length?`<div class="table-wrap"><table><thead><tr><th>Plan</th><th>Allowance</th><th>Included features</th><th>Assigned</th><th></th></tr></thead><tbody>${state.plans.map(p=>`<tr><td><strong>${e(p.name)}</strong><div class="small muted">${e(p.kind)} · ${e(p.owner)}</div></td><td>${p.site_limit} sites · ${p.storage_mb} MB${p.kind==='reseller'?`<div class="small muted">${p.customer_limit} customers</div>`:''}</td><td>${Object.entries(featureNames).filter(([k])=>p['allow_'+k]).map(([,v])=>v).join(', ')||'Static websites'}</td><td>${p.assigned}</td><td>${p.owner_id===o.user.id?`<button class="quiet" data-action="toggle-plan" data-id="${p.id}" data-active="${!p.active}">${p.active?'Retire':'Enable'}</button>`:''}${statusPill(p.active?'active':'retired')}</td></tr>`).join('')}</tbody></table></div>`:empty('Your first hosting package.','Create a customer plan before adding accounts.','','accounts')}</section><p class="note-line">Email and public DNS activation are still being built. Including those features in a package reserves permission to use them when configured; it does not start a public mail or DNS service.</p>`;
  }else if(state.page==='dns'){
    const d=state.dns;
    html=heading('DNS zones','Create, validate and export the records for a website.')+`<div class="callout"><strong>Private DNS preview</strong>These zones are validated by the server’s authoritative DNS service. This service currently listens only inside the VPS. Editing here does not change public DNS. Continue using your current DNS provider until public nameservers are configured.</div><section class="panel"><div class="file-toolbar"><label for="site-choice">Website</label><select id="site-choice">${siteOptions()}</select></div>${d?`<div class="panel-body"><h2>${e(d.domain)}</h2>${!d.can_edit?'<p class="note-line">DNS editing is not included in this customer’s hosting plan.</p>':''}${d.zone?`<div class="heading-actions">${d.can_edit?actionButton('new-dns','Add record'):''}${actionButton('export-dns','Export zone','secondary','download')}${d.can_edit?actionButton('verify-dns','Check ownership','secondary','check'):''}</div><p class="note-line">To verify ownership, add a TXT record named <strong>_vectorcp.${e(d.domain)}</strong> at your current public DNS provider with this value:</p><code class="dns-token">${e(d.zone.challenge)}</code><p>${d.zone.verified?'Ownership verified at the last check.':'Public ownership has not been verified.'}${d.zone.checked?' Checked '+e(date(d.zone.checked))+'.':''}</p><p class="small muted">Private zone serial ${d.zone.serial}. Exported SOA and nameserver records describe this preview; use your provider’s required nameservers when importing.</p>`:d.can_edit?actionButton('create-dns','Create private zone'):''}</div>${d.zone?`<div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Value</th><th>TTL</th><th></th></tr></thead><tbody>${d.records.map(r=>`<tr><td>${e(r.name)}</td><td>${e(r.type)}</td><td class="dns-value">${e(r.value)}</td><td>${r.ttl}</td><td>${d.can_edit?`<button class="quiet" data-action="delete-dns" data-id="${r.id}">Delete</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:''}`:empty('Choose a website.','DNS zones belong to an existing website.','','sites')}</section>`;
  }else if(state.page==='files'){
    html=heading('File manager','Browse folders and edit UTF-8 text files, up to 256 KB each.')+`<section class="panel"><div class="file-toolbar"><label for="site-choice" class="small muted">Website</label><select id="site-choice" aria-label="Website">${state.sites.map(s=>`<option value="${s.id}" ${s.id===state.siteId?'selected':''}>${e(s.domain)}</option>`).join('')}</select><span class="file-path">/public/${e(state.folder)}</span><span class="spacer"></span>${actionButton('new-folder','Folder','secondary','files')}${actionButton('new-file','File','secondary','plus')}</div><div class="file-grid"><div class="file-list" id="file-list"></div><div class="editor" id="editor">${empty('Pick a file to begin.','Your changes are checked against the version you opened.','','file')}</div></div></section>`;
  }else if(state.page==='hosting'){
    const site=state.sites.find(s=>s.id===state.siteId);
    const included=state.accounts.find(a=>a.id===site?.user_id)?.features||o.features;
    const isolated=site && (state.accounts.find(a=>a.id===site.user_id)?.hosting_slot || (o.user.id===site.user_id && o.user.hosting_slot));
    html=heading('Applications & databases','Install WordPress, run PHP and protect your domain.')+`<section class="panel"><div class="file-toolbar"><label for="site-choice">Website</label><select id="site-choice">${siteOptions()}</select></div><div class="panel-body">${site?`<h2>${e(site.domain)}</h2><p>${e(site.runtime)} · ${site.tls?'HTTPS enabled':'HTTP · HTTPS not yet enabled'}</p>${isolated?`<div class="heading-actions">${site.runtime==='static'?(included.wordpress?actionButton('install-wordpress','Install WordPress'):'')+(included.php?actionButton('enable-php','Enable PHP','secondary'):''):''}${!site.database_name&&included.databases?actionButton('create-database','Create database','secondary','disk'):''}${!site.tls&&included.tls?actionButton('enable-tls','Enable HTTPS','secondary','lock'):''}</div><p class="note-line">PHP runs as this customer with its own storage and resource limits. Point the domain A record to ${e(o.public_ipv4||'the configured server IP')} before enabling HTTPS. Remove conflicting A and AAAA records.</p>${site.database_name?`<p><strong>Database:</strong> ${e(site.database_name)} <button class="quiet" data-action="database-credentials">View connection details</button></p>`:''}${site.runtime==='wordpress'?`<p>WordPress ${e(site.wordpress_version)} · <a href="${site.tls?'https':'http'}://${e(site.domain)}/wp-admin/" target="_blank" rel="noopener noreferrer">Open WordPress admin ↗</a></p>`:''}`:`<div class="callout">${managesCustomers()?'Enable isolated hosting for this customer from Accounts before installing applications. Create application websites under a customer account.':'Ask your administrator to enable isolated hosting before creating application websites.'}</div>`}`:empty('Choose a website to begin.','Create a website under an isolated customer account.','','sites')}</div></section><section class="panel"><div class="panel-head"><h2>Server jobs</h2><span class="badge-counter">${state.jobs.length} recent</span></div>${state.jobs.length?`<div class="table-wrap"><table><thead><tr><th>Operation</th><th>Status</th><th>Details</th></tr></thead><tbody>${state.jobs.map(j=>`<tr><td>${e(jobLabel(j.action))}<div class="small muted">${e(date(j.created))}</div></td><td>${statusPill(j.status)}</td><td>${e(j.message)}</td></tr>`).join('')}</tbody></table></div>`:empty('All quiet.','Installations and backup jobs will appear here.','','clock')}</section>`;
  }else if(state.page==='backups'){
    html=heading('Backup & restore','Local backups of website files and databases.',actionButton('new-full-backup','Create backup','primary','backups'))+`<div class="callout"><strong>Files and database together.</strong>Isolated websites support local backups and restore, up to 200 MB of files and 64 MB of database data. PHP pauses briefly during the copy. Keep up to 5 backups and 512 MB per customer. Download a copy to keep it away from this server.</div><section class="panel"><div class="panel-head"><h2>Saved copies</h2><button class="quiet" data-action="new-backup">Small static export</button></div>${state.backups.length?`<div class="table-wrap"><table><thead><tr><th>Website</th><th>Created</th><th>Size</th><th>Type</th><th></th></tr></thead><tbody>${state.backups.map(b=>`<tr><td><strong>${e(b.domain)}</strong></td><td>${e(date(b.created))}</td><td>${bytes(b.bytes)}</td><td>${e(b.kind)}</td><td><div class="table-actions"><button class="quiet" data-action="download" data-id="${e(b.id)}">${icon('download')} Download</button>${b.kind==='full'?`<button class="quiet" data-action="restore-backup" data-id="${e(b.id)}">Restore</button>`:''}<button class="quiet" data-action="delete-backup" data-id="${e(b.id)}">Delete</button></div></td></tr>`).join('')}</tbody></table></div>`:empty('Your first recovery point.','Create a backup when your website is ready.','','backups')}</section><p class="note-line">Restore requires space for a temporary second copy. The server keeps the previous files and a database snapshot during restore so a failed operation can roll back. Scheduling and off-server destinations are still planned.</p>`;
  }else if(state.page==='audit'){
    html=heading('Activity log','The latest 100 actions visible to your account.')+`<section class="panel"><div class="panel-head"><h2>Activity history</h2><span class="badge-counter">${state.events.length} events</span></div>${activity(state.events)}</section>`;
  }else{
    html=heading('Release & service status','VectorCP · an open-source hosting control panel.')+`<div class="callout"><strong>Development release: review the available tools and limits.</strong>The implemented capabilities below are available in this release. Availability also depends on server configuration and account permissions. The remaining systems are still planned; the public capability catalog records the wider scope.</div><div class="columns"><section class="panel"><div class="panel-head"><h2>Available in this release</h2><span class="pill">Implemented</span></div><div class="panel-body feature-list">${o.capabilities.map(x=>`<div>${icon('check')}${e(x)}</div>`).join('')}</div></section><section class="panel"><div class="panel-head"><h2>Further work</h2><span class="pill gray">Planned</span></div><div class="panel-body feature-list">${o.planned.map(x=>`<div>${icon('clock')}${e(x)}</div>`).join('')}</div></section></div><section class="panel"><div class="panel-head"><h2>Observed services</h2></div>${o.services.length?`<div class="panel-body feature-list">${o.services.map(s=>`<div>${icon('server')}<strong>${e(s.name)}</strong><span class="pill ${s.status==='active'?'':'gray'}">${e(s.status)}</span></div>`).join('')}</div>`:empty('Service status is unavailable locally.','Linux service checks run on the deployed server.','','server')}</section>`;
  }
  page.innerHTML=html+`<footer class="workspace-footer"><span>VectorCP · Your hosting. Your control.</span><span>Release ${e(o.version)} · ${o.development?'Local validation':'Server workspace'}</span></footer>`;
  document.querySelectorAll('.table-wrap').forEach(wrap=>{wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',(wrap.closest('.panel')?.querySelector('h2')?.textContent||names[state.page])+' table; scroll horizontally for more columns');});
  document.querySelectorAll('th').forEach(th=>{th.scope='col';if(!th.textContent.trim()){th.textContent='Actions';}});
  if(state.page==='overview')filterTools();
  if(state.page==='files') loadFiles().catch(err=>notify(err.message,true));
}
async function loadPage(page=state.page){
  state.page=page;
  const o=await api('overview');state.overview=o;state.csrf=o.csrf;
  history.replaceState(null,'','/'+o.user.role);
  const calls=[api('sites.list'),api('audit')];if(managesCustomers())calls.push(api('accounts.list'));
  const results=await Promise.all(calls);state.sites=results[0].sites;state.events=results[1].events;state.accounts=results[2]?.accounts||[];
  if(!state.sites.some(s=>s.id===state.siteId)){state.siteId=state.sites[0]?.id||null;state.folder='';state.file=null;}
  if(page==='backups') state.backups=(await api('backups.list')).backups;
  if(managesCustomers()){const p=await api('plans.list');state.plans=p.plans;state.pool=p.pool;}else{state.plans=[];state.pool=null;}
  state.dns=page==='dns'&&state.siteId?await api('dns.list',{site_id:state.siteId}):null;
  state.jobs=(await api('jobs.list')).jobs;
  shell();
}
async function loadFiles(){
  const list=document.querySelector('#file-list');if(!list)return;
  if(!state.siteId){list.innerHTML=empty('No websites yet.','Add a website before editing files.','','files');return;}
  const result=await api('files.list',{site_id:state.siteId,path:state.folder});
  list.innerHTML=(state.folder?`<button class="file-row" data-action="folder-up">${icon('up')}Parent folder</button>`:'')+result.files.map(f=>`<button class="file-row" data-action="${f.directory?'open-folder':'open-file'}" data-name="${e(f.name)}">${icon(f.directory?'files':'file')}${e(f.name)}<small>${f.directory?'':bytes(f.bytes)}</small></button>`).join('');
  if(!result.files.length)list.innerHTML+=empty('Nothing here yet.','Add a text file or folder.','','files');
}
function showModal(title,sub,form,body,submit){
  document.querySelector('#modal-content').innerHTML=`<div class="modal-head"><div><h2 id="modal-title">${title}</h2><p id="modal-description">${sub}</p></div><button class="quiet" data-action="close-modal" aria-label="Close dialog">${icon('close')}</button></div><form data-form="${form}" class="modal-body">${body}<p class="form-error" role="alert"></p><div class="modal-foot"><button type="button" class="secondary" data-action="close-modal">Cancel</button><button class="${form.startsWith('delete-')?'danger':'primary'}" type="submit">${submit}</button></div></form>`;
  modal.showModal();
  modal.querySelector('input:not([type="hidden"]):enabled,select:enabled,textarea:enabled')?.focus();
}
function field(label,name,options={}){const id='field-'+name;return `<div class="field"><label for="${id}">${label}</label><input id="${id}" name="${name}" type="${options.type||'text'}" ${options.attrs||''} required ${options.help?`aria-describedby="${id}-help"`:''} ${options.value!=null?`value="${e(options.value)}"`:''}>${options.help?`<small id="${id}-help">${options.help}</small>`:''}</div>`;}
function planOptions(kind){return state.plans.filter(p=>p.active&&p.kind===kind&&p.owner_id===state.overview.user.id).map(p=>`<option value="${p.id}">${e(p.name)} · ${p.storage_mb} MB · ${p.site_limit} sites</option>`).join('')||`<option value="" disabled selected>No active ${e(kind)} plans</option>`;}
function siteOptions(){return state.sites.map(s=>`<option value="${s.id}" ${s.id===state.siteId?'selected':''}>${e(s.domain)}</option>`).join('');}
function editFile(name,content,revision){
  state.file=name;state.revision=revision;
  const el=document.querySelector('#editor');
  el.innerHTML=`<div class="editor-heading"><span class="mono">${e(name)}</span><button class="primary" data-action="save-file">Save changes ${icon('check')}</button></div><textarea id="file-content" aria-label="File contents" spellcheck="false"></textarea><span class="small muted">Text editor · UTF-8 · maximum 256 KB. File changes are written atomically.</span>`;
  document.querySelector('#file-content').value=content;
}
document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  try{
    if(button.dataset.page){if(navigationBusy)return;navigationBusy=true;try{setNavigation(false);await loadPage(button.dataset.page);focusPage();}finally{navigationBusy=false;}return;}
    const action=button.dataset.action;if(!action)return;
    if(action==='open-navigation'){setNavigation(true);return;}
    if(action==='close-navigation'){setNavigation(false);document.querySelector('[data-action="open-navigation"]').focus();return;}
    if(action==='toggle-group'){const body=document.getElementById(button.getAttribute('aria-controls'));body.hidden=!body.hidden;button.setAttribute('aria-expanded',String(!body.hidden));return;}
    if(action==='clear-search'){toolQuery='';document.querySelector('#tool-search').value='';document.querySelectorAll('.tool-grid').forEach(g=>g.hidden=false);document.querySelectorAll('.group-toggle').forEach(b=>b.setAttribute('aria-expanded','true'));filterTools();return;}
    if(action==='auth-toggle'){auth(button.dataset.setup==='true');return;}
    if(action==='close-modal'){modal.close();return;}
    if(action==='refresh'){await loadPage();notify('Workspace refreshed.');return;}
    if(action==='logout'){await api('logout');auth();return;}
    if(action==='new-site'){
      showModal('Create website','Create under an isolated customer to use PHP or WordPress.','site',field('Domain name','domain',{attrs:'placeholder="example.com" autocapitalize="none" maxlength="253"'})+(managesCustomers()?`<label class="field">Owner<select name="user_id">${state.accounts.filter(a=>a.active&&a.role==='customer').map(a=>`<option value="${a.id}">${e(a.name)} (${e(a.username)})</option>`).join('')}</select></label>`:''),'Create website');return;
    }
    if(action==='new-account'){
      if(!state.plans.some(p=>p.owner_id===state.overview.user.id&&p.active)){notify('Create a hosting plan first.',true);await loadPage('plans');return;}
      showModal('Create account','Each account receives a hosting plan and its reserved allowance.','account',field('Name','name',{attrs:'maxlength="80"'})+field('Username','username',{attrs:'minlength="3" maxlength="32" pattern="[a-z][a-z0-9_-]{2,31}" autocapitalize="none"'})+field('Password','password',{type:'password',attrs:'minlength="12" maxlength="256" autocomplete="new-password"',help:'Share this through a private channel.'})+(state.overview.user.role==='admin'?'<label class="field">Account type<select name="role" id="account-role"><option value="customer">Customer</option><option value="reseller">Reseller</option></select></label>':'<input type="hidden" name="role" value="customer">')+'<label class="field">Hosting plan<select required name="plan_id" id="account-plan">'+planOptions('customer')+'</select></label>','Create account');return;
    }
    if(action==='new-plan'){
      showModal('Create hosting plan','Allowances reserve space when accounts are created.','plan',field('Plan name','name',{attrs:'maxlength="80"'})+(state.overview.user.role==='admin'?'<label class="field">Package type<select name="kind" id="plan-kind"><option value="customer">Customer</option><option value="reseller">Reseller</option></select></label>':'<input type="hidden" name="kind" value="customer">')+`<div class="field-grid">${field('Website allowance','site_limit',{type:'number',value:3,attrs:'min="1" max="100"'})}${field('Storage (MB)','storage_mb',{type:'number',value:1024,attrs:'min="512" max="4096"'})}</div><label class="field" id="reseller-count" hidden>Customer allowance<input name="customer_limit" type="number" value="4" min="1" max="16"></label><div class="plan-features">${Object.entries(featureNames).map(([k,v])=>`<label><input name="allow_${k}" type="checkbox" ${state.overview.features[k]?'checked':'disabled'}> ${v}</label>`).join('')}</div>`,'Create plan');return;
    }
    if(action==='assign-plan'){
      const a=state.accounts.find(a=>a.id===Number(button.dataset.id));
      showModal('Choose a hosting plan.','An existing hosting volume must keep its current storage size. Current usage must fit the new plan.','assign-plan',`<input type="hidden" name="id" value="${a.id}"><label class="field">Plan<select required name="plan_id">${planOptions(a.role)}</select></label>`,'Assign plan');return;
    }
    if(action==='toggle-plan'){await api('plans.active',{id:Number(button.dataset.id),active:button.dataset.active==='true'});await loadPage();notify('Plan availability updated.');return;}
    if(action==='create-dns'){await api('dns.create',{site_id:state.siteId});await loadPage();notify('Private DNS zone created.');return;}
    if(action==='new-dns'){
      showModal('Add a DNS record.','Use @ for the root or a relative name such as www.','dns',field('Name','name',{value:'@',attrs:'maxlength="253"'})+`<label class="field">Record type<select name="type">${['A','AAAA','CNAME','MX','TXT','NS','CAA','SRV'].map(t=>`<option>${t}</option>`).join('')}</select></label>`+field('Value','value',{attrs:'maxlength="512"',help:'MX: priority hostname · SRV: priority weight port hostname · TXT: enter plain text.'})+field('TTL (seconds)','ttl',{type:'number',value:3600,attrs:'min="300" max="86400"'}),'Add record');return;
    }
    if(action==='delete-dns'){
      showModal('Delete this DNS record?','This removes the selected record from the private zone.','delete-dns',`<input type="hidden" name="id" value="${Number(button.dataset.id)}">`,'Delete record');return;
    }
    if(action==='verify-dns'){const r=await api('dns.verify',{site_id:state.siteId});await loadPage();notify(r.verified?'Public domain ownership verified.':'The matching TXT record was not found at your public DNS provider.',!r.verified);return;}
    if(action==='export-dns'){const r=await api('dns.export',{site_id:state.siteId});const u=URL.createObjectURL(new Blob([r.content],{type:'text/plain'}));const a=document.createElement('a');a.href=u;a.download=r.filename;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);notify('Zone export downloaded.');return;}
    if(action==='open-hosting'){state.siteId=Number(button.dataset.id);await loadPage('hosting');document.querySelector('#site-choice').value=state.siteId;return;}
    if(action==='enable-hosting'){
      const a=state.accounts.find(a=>a.id===Number(button.dataset.id));
      showModal('Enable customer hosting','Provision a fixed storage volume and isolated application services.','hosting-enable',`<input type="hidden" name="id" value="${Number(button.dataset.id)}">`+field('Hosting storage (MB)','storage_mb',{type:'number',value:a.plan_id?a.storage_mb:1024,attrs:'min="512" max="4096" '+(a.plan_id?'readonly':''),help:'Includes website files, the database and temporary application data. The volume size is fixed in this release.'}),'Enable hosting');return;
    }
    if(action==='install-wordpress'){
      showModal('Install WordPress','Installs the current official release into this website. Only its welcome page may exist.','wordpress',field('Site title','title',{attrs:'maxlength="120"'})+field('WordPress administrator','admin',{attrs:'minlength="3" maxlength="40" autocomplete="off"'})+field('Administrator email','email',{type:'email',attrs:'maxlength="160"'})+field('WordPress password','password',{type:'password',attrs:'minlength="12" maxlength="128" autocomplete="new-password"',help:'Keep this password. It is separate from your VectorCP sign-in.'}),'Install WordPress');return;
    }
    if(['enable-php','create-database','enable-tls'].includes(action)){
      const method={'enable-php':'hosting.php','create-database':'databases.create','enable-tls':'hosting.tls'}[action];
      await api(method,{site_id:state.siteId});await loadPage('hosting');notify('Server job started. Its progress appears below.');return;
    }
    if(action==='database-credentials'){
      const c=await api('databases.credentials',{site_id:state.siteId});
      showModal('Database connection details.','Private to this website owner. Use a local socket connection.','close-details',`<dl><dt>Database</dt><dd>${e(c.name)}</dd><dt>Username</dt><dd>${e(c.username)}</dd><dt>Password</dt><dd class="mono">${e(c.password)}</dd><dt>Socket</dt><dd class="mono">${e(c.socket)}</dd></dl>`,'Close');return;
    }
    if(action==='new-full-backup'){
      if(!state.sites.length){notify('Create a website first.',true);return;}
      showModal('Create website backup','PHP briefly pauses while the backup is made.','full-backup',`<label class="field">Website<select name="site_id">${siteOptions()}</select></label>`,'Create backup');return;
    }
    if(action==='restore-backup'||action==='delete-backup'){
      const b=state.backups.find(x=>x.id===button.dataset.id);
      showModal(action==='restore-backup'?'Restore this recovery point?':'Delete this saved copy?',action==='restore-backup'?`Replace ${e(b.domain)} with its files and database from ${e(date(b.created))}. PHP will pause during restore.`:'This permanently removes the selected backup from this server.',action==='restore-backup'?'restore':'delete-backup',`<input type="hidden" name="id" value="${e(b.id)}">`,action==='restore-backup'?'Restore website':'Delete backup');return;
    }
    if(action==='toggle-site'){button.disabled=true;await api('sites.active',{site_id:Number(button.dataset.id),active:button.dataset.active==='true'});await loadPage();notify('Website state updated.');return;}
    if(action==='toggle-account'){button.disabled=true;await api('accounts.active',{id:Number(button.dataset.id),active:button.dataset.active==='true'});await loadPage();notify('Customer panel access updated.');return;}
    if(action==='open-files'){state.siteId=Number(button.dataset.id);state.folder='';state.file=null;await loadPage('files');return;}
    if(action==='go-files'){await loadPage('files');return;}
    if(action==='go-backups'){await loadPage('backups');return;}
    if(action==='open-folder'){state.folder=[state.folder,button.dataset.name].filter(Boolean).join('/');state.file=null;render();return;}
    if(action==='folder-up'){state.folder=state.folder.split('/').slice(0,-1).join('/');state.file=null;render();return;}
    if(action==='open-file'){const name=[state.folder,button.dataset.name].filter(Boolean).join('/');const result=await api('files.read',{site_id:state.siteId,path:name});editFile(name,result.content,result.revision);return;}
    if(action==='new-file'||action==='new-folder'){
      if(!state.siteId){notify('Add a website first.',true);return;}
      showModal(action==='new-file'?'Create file':'Create folder','Created inside the current website folder.',action==='new-file'?'file':'folder',field('Name','name',{attrs:'maxlength="200"',help:action==='new-file'?'For example, about.html or style.css.':'For example, assets.'}),'Create');return;
    }
    if(action==='save-file'){
      button.disabled=true;const result=await api('files.write',{site_id:state.siteId,path:state.file,content:document.querySelector('#file-content').value,revision:state.revision});state.revision=result.revision;notify('Changes saved.');await loadFiles();return;
    }
    if(action==='new-backup'){
      if(!state.sites.length){notify('Add a website first.',true);return;}
      showModal('Create static export','Exports contain website files only, up to 5 MB.','backup',`<label class="field">Website<select name="site_id">${siteOptions()}</select></label>`,'Create export');return;
    }
    if(action==='download'){
      button.disabled=true;const blob=await downloadBackup(button.dataset.id);const b=state.backups.find(b=>b.id===button.dataset.id);const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`${b.domain}-${b.id}.tar.gz`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notify('Export download started.');return;
    }
  }catch(err){if(err.status===401&&state.overview)auth();notify(err.message,true);}finally{if(button.isConnected)button.disabled=false;}
});
document.addEventListener('input',event=>{
  if(event.target.matches('[data-filter-table]')){const panel=event.target.closest('.panel'),rows=[...panel.querySelectorAll('tbody tr')],query=event.target.value.trim().toLowerCase();let visible=0;rows.forEach(row=>{row.hidden=!row.textContent.toLowerCase().includes(query);if(!row.hidden)visible++;});panel.querySelector('.filter-result').textContent=`${visible} of ${rows.length} shown`;return;}
  if(event.target.id==='tool-search'){toolQuery=event.target.value;if(state.page==='overview')filterTools();}
});
document.addEventListener('keydown',event=>{
  if(!document.querySelector('.shell.menu-open'))return;
  if(event.key==='Escape'){event.preventDefault();setNavigation(false);document.querySelector('[data-action="open-navigation"]').focus();}
  if(event.key==='Tab'){
    const items=[...document.querySelectorAll('.sidebar button')].filter(b=>b.getClientRects().length&&!b.disabled),first=items[0],last=items[items.length-1];
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  }
});
matchMedia('(max-width: 760px)').addEventListener('change',()=>setNavigation(false));
document.addEventListener('change',event=>{
  if(event.target.id==='account-role')document.querySelector('#account-plan').innerHTML=planOptions(event.target.value);
  if(event.target.id==='plan-kind'){const reseller=event.target.value==='reseller';document.querySelector('#reseller-count').hidden=!reseller;document.querySelector('[name="site_limit"]').max=reseller?1000:100;document.querySelector('[name="storage_mb"]').max=reseller?16384:4096;}
  if(event.target.id==='site-choice'){state.siteId=Number(event.target.value);state.folder='';state.file=null;if(state.page==='dns')loadPage().catch(err=>notify(err.message,true));else render();}
});
document.addEventListener('submit',async event=>{
  const form=event.target.closest('form[data-form]');if(!form)return;event.preventDefault();
  if(form.dataset.form==='tool-search'){try{toolQuery=form.elements.query.value;if(state.page!=='overview'){await loadPage('overview');focusPage();}else filterTools();}catch(err){notify(err.message,true);}return;}
  const button=form.querySelector('button[type="submit"]');button.disabled=true;form.querySelector('.form-error').textContent='';
  try{
    const data=Object.fromEntries(new FormData(form));const kind=form.dataset.form;
    if(kind==='login'||kind==='bootstrap'){if(kind==='login'&&['/admin','/reseller','/customer'].includes(location.pathname))data.entry=location.pathname.slice(1);const result=await api(kind,data);state.csrf=result.csrf;setupToken='';await loadPage('overview');return;}
    if(kind==='close-details'){modal.close();return;}
    if(['hosting-enable','wordpress','full-backup','restore','delete-backup'].includes(kind)){
      const method={'hosting-enable':'hosting.enable','wordpress':'hosting.wordpress','full-backup':'backups.full','restore':'backups.restore','delete-backup':'backups.delete'}[kind];
      if(kind==='hosting-enable'){data.id=Number(data.id);data.storage_mb=Number(data.storage_mb);}
      if(kind==='wordpress')data.site_id=state.siteId;
      if(kind==='full-backup')data.site_id=Number(data.site_id);
      await api(method,data);modal.close();await loadPage(kind==='delete-backup'?'backups':'hosting');notify(kind==='delete-backup'?'Backup deleted.':'Server job started.');return;
    }
    if(kind==='plan'){data.site_limit=Number(data.site_limit);data.storage_mb=Number(data.storage_mb);data.customer_limit=data.kind==='reseller'?Number(data.customer_limit):0;for(const k of Object.keys(featureNames))data['allow_'+k]=form.elements['allow_'+k].checked;await api('plans.create',data);modal.close();await loadPage('plans');notify('Hosting plan created.');return;}
    if(kind==='assign-plan'){await api('plans.assign',{id:Number(data.id),plan_id:Number(data.plan_id)});modal.close();await loadPage();notify('Hosting plan assigned.');return;}
    if(kind==='dns'||kind==='delete-dns'){data.site_id=state.siteId;if(kind==='dns')data.ttl=Number(data.ttl);else data.id=Number(data.id);await api(kind==='dns'?'dns.save':'dns.delete',data);modal.close();await loadPage();notify('Private DNS zone updated.');return;}
    if(kind==='site'){if(data.user_id)data.user_id=Number(data.user_id);await api('sites.create',data);}
    if(kind==='account'){data.plan_id=Number(data.plan_id);await api('accounts.create',data);}
    if(kind==='folder'){await api('files.mkdir',{site_id:state.siteId,path:[state.folder,data.name].filter(Boolean).join('/')});modal.close();await loadFiles();notify('Folder created.');return;}
    if(kind==='file'){const path=[state.folder,data.name].filter(Boolean).join('/');await api('files.write',{site_id:state.siteId,path,content:'',revision:'new'});modal.close();const saved=await api('files.read',{site_id:state.siteId,path});await loadFiles();editFile(path,saved.content,saved.revision);notify('File created.');return;}
    if(kind==='backup'){await api('backups.create',{site_id:Number(data.site_id)});}
    modal.close();await loadPage();notify(kind==='site'?'Website created. Configure its DNS before visiting.':kind==='account'?'Customer account created.':'Site export created.');
  }catch(err){const box=form.querySelector('.form-error');if(box)box.textContent=err.message;}finally{if(button.isConnected)button.disabled=false;}
});
async function start(){try{await loadPage();}catch(err){if(err.status===401)auth(Boolean(setupToken));else{auth(Boolean(setupToken));notify(err.message,true);}}}
setInterval(()=>{if(state.overview && ['hosting','backups','status'].includes(state.page) && state.jobs.some(j=>['queued','running'].includes(j.status)) && !modal.open)loadPage().catch(err=>notify(err.message,true));},5000);
start();
