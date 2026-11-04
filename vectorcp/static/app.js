'use strict';
const app = document.querySelector('#app');
const modal = document.querySelector('#modal');
const names = {security:'Account & security',overview:'Tools',sites:'Websites & domains',hosting:'Apps & databases',files:'File manager',accounts:'Accounts',plans:'Hosting plans',dns:'DNS zones',backups:'Backups',audit:'Activity log',status:'Release status'};
const paths = {overview:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',sites:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z"/>',files:'<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z"/>',accounts:'<circle cx="9" cy="7" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3M16 4a3 3 0 0 1 0 6M18 14a5 5 0 0 1 3 4v3"/>',backups:'<path d="M5 8H3v13h18V8h-2M3 3h18v5H3ZM12 12v5m-3-3 3 3 3-3"/>',audit:'<path d="M5 3h10l4 4v14H5ZM9 11h6M9 15h6M15 3v5h4"/>',status:'<path d="m12 3 8 4v6c0 4-8 8-8 8s-8-4-8-8V7Z"/><path d="m8 12 3 3 5-6"/>',plus:'<path d="M12 5v14M5 12h14"/>',arrow:'<path d="M4 12h15m-5-5 5 5-5 5"/>',refresh:'<path d="M20 5v5h-5M4 19v-5h5M19 9a8 8 0 0 0-13-4M5 15a8 8 0 0 0 13 4"/>',logout:'<path d="M9 4H4v16h5m5-4 4-4-4-4m-6 4h14"/>',check:'<path d="m5 12 4 4L20 5"/>',close:'<path d="m6 6 12 12M6 18 18 6"/>',server:'<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6.5h.1M7 17.5h.1"/>',cpu:'<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 1v5m6-5v5M9 18v5m6-5v5M1 9h5m-5 6h5m12-6h5m-5 6h5"/>',disk:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',file:'<path d="M5 3h9l5 5v13H5ZM14 3v6h5"/>',download:'<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',up:'<path d="M12 20V4m-6 6 6-6 6 6"/>',lock:'<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>'};
paths.security=paths.lock;
paths.hosting=paths.server;
paths.plans=paths.disk;
paths.dns='<circle cx="12" cy="5" r="2"/><circle cx="5" cy="19" r="2"/><circle cx="19" cy="19" r="2"/><path d="M12 7v5M5 17v-5h14v5"/>';
const icon = name => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${paths[name]||paths.status}</svg>`;
const e = value => String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bytes = n => n==null?'Unavailable':n<1024?`${n} B`:n<1048576?`${(n/1024).toFixed(1)} KB`:n<1073741824?`${(n/1048576).toFixed(1)} MB`:`${(n/1073741824).toFixed(1)} GB`;
const date = n => new Date(n*1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
const managesCustomers=()=>['admin','reseller'].includes(state.overview?.user.role);
const featureNames={php:'PHP',wordpress:'WordPress',databases:'Databases',tls:'HTTPS',dns:'DNS preview',mail:'Email (planned)'};
let state = {security:null,sessions:[],profile:null,accountFilters:{query:'',role:'all',status:'all',offset:0},accountTotal:0,plans:[],pool:null,dns:null,page:'overview', overview:null, sites:[], accounts:[], events:[], backups:[], jobs:[], databases:[], csrf:'', siteId:null, folder:'', file:null, revision:null};
let setupToken = new URLSearchParams(location.hash.slice(1)).get('setup') || '';
if(location.hash) history.replaceState(null,'',location.pathname);
let toastTimer, toolQuery='', navigationBusy=false, pageRequest=0, transferBusy=false;
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
    ['files','File manager','Transfer, find and manage website files.','editor directory upload copy move rename search storage'],
    ['backups','Backup & restore','Create, download and restore local recovery points.','recovery export download']]},
  {title:'Applications & databases',icon:'server',tools:[
    ['hosting','WordPress installer','Install WordPress on a fresh isolated website.','wordpress cms install'],
    ['hosting','PHP hosting','Enable isolated PHP for a website.','php fpm runtime'],
    ['hosting','Databases','Create a private database and view connection details.','mariadb mysql sql credentials']]},
  {title:'Account & security',icon:'lock',tools:[['security','Account & security','Update your details, password, authenticator and active sessions.','password two factor mfa recovery sessions contact']]},
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
  if(method.startsWith('files.'))data={...data,show_hidden:Boolean(state.showHidden)};
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
  pageRequest++;navigationBusy=false;toolQuery='';document.body.classList.remove('navigation-open');if(modal.open)closeModal();
  state.overview=null;state.csrf='';
  app.innerHTML=`<main class="auth"><section class="auth-story">${brand()}<div class="story"><div class="eyebrow">Open-source hosting control.</div><h1>Your hosting.<br><span>Your control.</span></h1><p>A focused workspace for your websites, files and the people behind them.</p></div><footer>OPEN-SOURCE HOSTING CONTROL · VECTORCP</footer></section><section class="auth-form"><div class="eyebrow muted">${setup?'FIRST-TIME SETUP':({'/admin':'SERVER OWNER SIGN-IN','/reseller':'RESELLER SIGN-IN','/customer':'CUSTOMER SIGN-IN'}[location.pathname]||'YOUR HOSTING WORKSPACE')}</div><h2>${setup?'Make it yours.':'Welcome back.'}</h2><p class="intro">${setup?'Create the first administrator using the one-time token from your server.':'Sign in to manage your hosting workspace.'}</p><form data-form="${setup?'bootstrap':'login'}">${setup?`<label class="field">Setup token<input name="setup_token" type="password" required autocomplete="off" value="${e(setupToken)}"></label><label class="field">Your name<input name="name" required maxlength="80" autocomplete="name"></label>`:''}<label class="field">Username<input name="username" required minlength="3" maxlength="32" autocomplete="username" autocapitalize="none" spellcheck="false"></label><label class="field">Password<input name="password" type="password" required ${setup?'minlength="15"':''} maxlength="256" autocomplete="${setup?'new-password':'current-password'}"></label><label class="field" id="login-factor" hidden>Authenticator or recovery code<input name="code" autocomplete="one-time-code" maxlength="35" spellcheck="false" autocapitalize="none"><small>Use a new six-digit code, or one of your saved recovery codes.</small></label><p class="form-error" role="alert"></p><button class="primary" type="submit">${setup?'Create administrator':'Sign in'} ${icon('arrow')}</button></form><p class="auth-bottom">${setup?'Already configured?':'Setting up a new server?'} <button class="quiet" data-action="auth-toggle" data-setup="${setup?'false':'true'}">${setup?'Sign in':'First-time setup'}</button></p></section></main>`;
}
function shell(){
  const o=state.overview,u=o.user;
  const groups=u.password_change_required?[['Account',['security']]]:[['Workspace',['overview','sites','hosting','files','dns']],...(managesCustomers()?[['Account management',['accounts','plans']]]:[]),['Operations',['security','backups','audit','status']]];
  document.body.classList.remove('navigation-open');
  app.innerHTML=`<a class="skip-link" href="#page">Skip to main content</a><div class="shell"><aside class="sidebar" id="workspace-navigation" aria-label="Workspace navigation"><div class="sidebar-heading">${brand()}<button class="icon-button close-navigation" data-action="close-navigation" aria-label="Close navigation">${icon('close')}</button></div><div class="workspace-label">${workspaceName()}</div><nav aria-label="Main navigation">${groups.map(([label,pages])=>`<div class="nav-section"><div class="nav-label">${label}</div>${pages.map(p=>`<button class="nav-item ${state.page===p?'current':''}" ${state.page===p?'aria-current="page"':''} data-page="${p}">${icon(p)}<span>${names[p]}</span></button>`).join('')}</div>`).join('')}</nav><div class="sidebar-bottom"><span class="version-label">Development · ${e(o.version)}</span><div class="person"><span class="avatar">${e(u.name.slice(0,1).toUpperCase())}</span><div class="person-copy"><div class="person-name">${e(u.name)}</div><div class="person-role">${e(u.role==='admin'?'Server owner':u.role)}</div></div></div></div></aside><button class="navigation-shade" data-action="close-navigation" aria-label="Close navigation" tabindex="-1"></button><main class="main"><header class="topbar"><button class="icon-button open-navigation" data-action="open-navigation" aria-label="Open navigation" aria-controls="workspace-navigation" aria-expanded="false">${icon('overview')}</button><div class="breadcrumb">${workspaceName()}<span>/ ${names[state.page]}</span></div><form class="tool-search" data-form="tool-search" role="search"><label class="sr-only" for="tool-search">Search tools</label><input id="tool-search" type="search" name="query" placeholder="Search tools…" value="${e(toolQuery)}" autocomplete="off"><button type="submit" class="icon-button" aria-label="Search tools">${icon('arrow')}</button></form><div class="top-actions"><button class="icon-button" data-action="refresh" aria-label="Refresh current page">${icon('refresh')}</button><button class="icon-button" data-action="logout" aria-label="Sign out">${icon('logout')}</button></div></header>${o.development?`<div class="development-banner">${icon('status')}Local validation instance. Websites are not published to the Internet.</div>`:''}<div class="page-loading" id="page-loading" role="status" hidden></div><div class="content" id="page" tabindex="-1"></div></main></div>`;
  render();
}
function heading(title,sub,action=''){return `<div class="page-heading"><div><h1 tabindex="-1">${title}</h1><p>${sub}</p></div>${action?`<div class="heading-actions">${action}</div>`:''}</div>`;}
function actionButton(action,label,kind='primary',ico='plus'){return `<button class="${kind}" data-action="${action}">${icon(ico)}${label}</button>`;}
function empty(title,body,action='',ico='sites'){return `<div class="empty">${icon(ico)}<strong>${title}</strong>${body}${action}</div>`;}
function statusPill(status){return `<span class="pill ${status==='active'?'':'gray'}">${status==='active'?'Active':e(status)}</span>`;}
function tableFilter(name){return `<div class="table-filter"><label for="filter-${name}">Filter ${name}</label><input id="filter-${name}" type="search" data-filter-table placeholder="Search visible ${name}…" autocomplete="off"><span class="filter-result" role="status"></span></div>`;}
function siteRows(rows,compact=false){return `<div class="table-wrap"><table><thead><tr><th>Website</th>${compact?'':'<th>Owner</th>'}<th>Status</th><th></th></tr></thead><tbody>${rows.map(s=>`<tr><td><div class="domain-cell"><span class="site-icon">${icon('sites')}</span>${e(s.domain)}</div></td>${compact?'':`<td class="muted">${e(s.username)}</td>`}<td>${statusPill(s.status)}</td><td><div class="table-actions"><button class="quiet" data-action="open-hosting" data-id="${s.id}">Hosting</button><button class="quiet" data-action="open-files" data-id="${s.id}">Files ${icon('arrow')}</button>${compact || !managesCustomers()?'':`<button class="quiet" data-action="toggle-site" data-id="${s.id}" data-active="${s.status!=='active'}">${s.status==='active'?'Suspend':'Activate'}</button>`}</div></td></tr>`).join('')}</tbody></table></div>`;}
const actionName = a => ({'copy':'File copied','move':'Item moved','remove':'Item removed','folder.copied':'Folder copied','file.uploaded':'File uploaded','file.trashed':'Item moved to trash','file.restored':'Item restored','file.trash_purged':'Trash item permanently removed','file.permissions_changed':'File permissions changed','archive.created':'ZIP created','archive.extracted':'ZIP extracted','account.updated':'Account details changed','profile.updated':'Contact details changed','session.revoked':'Session access revoked','password.changed':'Password changed','password.reset_required':'Temporary password set','two_factor.enrollment_started':'Authenticator setup started','two_factor.enabled':'Authenticator enabled','two_factor.disabled':'Authenticator disabled','two_factor.recovery_replaced':'Recovery codes replaced','accounts.bulk_lock':'Selected accounts locked','accounts.bulk_enable':'Selected accounts enabled','accounts.bulk_plan':'Selected account plans changed','site.created':'Website created','site.active':'Website activated','site.suspended':'Website suspended','file.saved':'File saved','folder.created':'Folder created','account.created':'Customer created','account.access_enabled':'Panel access enabled','account.access_locked':'Panel access locked','session.created':'Signed in','session.closed':'Signed out','administrator.created':'Administrator created','backup.created':'Site export created','backup.downloaded':'Site export downloaded'}[a]||a);
const jobLabel=a=>({'hosting.enable':'Enable customer hosting','hosting.php':'Enable PHP','hosting.wordpress':'Install WordPress','hosting.tls':'Enable HTTPS','databases.create':'Create database','backups.full':'Create full backup','backups.restore':'Restore website'}[a]||a);
function activity(rows){return rows.length?rows.map(a=>`<div class="activity-item"><span class="activity-dot"></span><div><strong>${e(actionName(a.action))}</strong><small>${e(a.target)} · ${e(a.actor)}</small></div><time>${e(date(a.created))}</time></div>`).join(''):empty('A fresh start','Your workspace activity will appear here.','','audit');}

function contactField(value=''){return `<div class="field"><label for="contact-email">Contact email (optional)</label><input id="contact-email" name="contact_email" type="email" maxlength="160" value="${e(value)}" autocomplete="email"></div>`;}
function newPasswordField(label='New password'){return field(label,'new_password',{type:'password',attrs:'minlength="15" maxlength="256" autocomplete="new-password"',help:'15–256 characters. Use a unique password or passphrase; predictable passwords are refused.'});}
function credentialFields(status){return field('Your current password','password',{type:'password',attrs:'maxlength="256" autocomplete="current-password"'})+(status.enabled?field('Authenticator or recovery code','code',{attrs:'maxlength="35" autocomplete="one-time-code" autocapitalize="none" spellcheck="false"',help:'Each code works once. Wait for the next authenticator code if you just used one.'}):'');}
function showRecovery(codes){showModal('Save your recovery codes','Store these somewhere private, separate from your server. Each code works once. These codes will not be shown again.','close-details',`<div class="recovery-codes">${codes.map(code=>`<code data-recovery-code>${e(code)}</code>`).join('')}</div><button type="button" class="secondary" data-action="download-recovery">Download codes</button>`,'I have saved my codes');}
const permissionName=mode=>({'600':'Owner reads and writes','640':'Owner writes; group reads','644':'Owner writes; everyone reads','700':'Owner only, with execute','750':'Owner controls; group reads and executes','755':'Owner controls; everyone reads and executes'}[mode]||mode);
function securityPage(){
  const status=state.security,profile=state.profile,forced=state.overview.user.password_change_required;
  let html=heading('Account & security','Manage your sign-in, contact details and active devices.');
  if(forced)return html+`<section class="panel"><div class="panel-body"><h2>Choose your own password</h2><p>Your account has a temporary password. Change it before opening your hosting tools.</p>${actionButton('change-password','Change temporary password','primary','lock')}</div></section>`;
  html+=`<div class="columns"><section class="panel"><div class="panel-head"><h2>Your details</h2></div><div class="panel-body"><dl class="account-details"><dt>Username</dt><dd>${e(profile.username)}</dd><dt>Name</dt><dd>${e(profile.name)}</dd><dt>Contact email</dt><dd>${e(profile.contact_email||'Not set')}</dd></dl>${actionButton('edit-profile','Edit details','secondary','accounts')}</div></section><section class="panel"><div class="panel-head"><h2>Password & authenticator</h2></div><div class="panel-body"><p>Two-factor authentication: <strong>${status.enabled?'Enabled':'Not enabled'}</strong></p>${status.enabled?`<p>${status.recovery_remaining} unused recovery codes remain.</p>`:'<p>Add a time-based authenticator app to protect your sign-in.</p>'}<div class="heading-actions">${actionButton('change-password','Change password','secondary','lock')}${status.enabled?actionButton('replace-recovery','Replace recovery codes','secondary','refresh')+actionButton('disable-factor','Disable authenticator','secondary','lock'):actionButton('enroll-factor','Enable authenticator','primary','lock')}</div></div></section></div>`;
  return html+`<section class="panel"><div class="panel-head"><h2>Active sessions</h2><button class="secondary" data-action="revoke-session" data-id="others">Sign out other sessions</button></div><div class="table-wrap"><table><thead><tr><th>Device / browser</th><th>Signed in</th><th>Last active</th><th>Expires</th><th>Action</th></tr></thead><tbody>${state.sessions.map(session=>`<tr><td class="session-client">${e(session.client||'Device details unavailable')}${session.current?' <span class="pill">This session</span>':''}</td><td>${e(date(session.created))}</td><td>${e(date(session.last_seen))}</td><td>${e(date(session.expires))}</td><td><button class="quiet" data-action="revoke-session" data-id="${e(session.id)}">Sign out${session.current?' this session':''}</button></td></tr>`).join('')}</tbody></table></div><p class="note-line">Sessions expire after eight hours. Up to 20 devices can stay signed in. Device descriptions come from the browser and may be inaccurate.</p></section>`;
}
function accountSearch(){const f=state.accountFilters;return `<form class="account-search" data-form="account-search"><div class="field"><label for="account-query">Search accounts</label><input id="account-query" name="query" type="search" maxlength="100" value="${e(f.query)}" placeholder="Name, username or contact"></div><div class="field"><label for="account-type">Type</label><select id="account-type" name="role">${['all','admin','reseller','customer'].map(x=>`<option value="${x}" ${x===f.role?'selected':''}>${x==='all'?'All types':x}</option>`).join('')}</select></div><div class="field"><label for="account-status">Access</label><select id="account-status" name="status">${['all','active','locked'].map(x=>`<option value="${x}" ${x===f.status?'selected':''}>${x==='all'?'All access states':x}</option>`).join('')}</select></div><button class="secondary" type="submit">Search</button><button class="secondary" type="button" data-action="bulk-accounts">Change selected…</button></form>`;}
function accountPagination(){const offset=state.accountFilters.offset;return `<div class="account-pagination"><span>${state.accountTotal?offset+1:0}–${Math.min(offset+state.accounts.length,state.accountTotal)} of ${state.accountTotal} accounts</span><button class="secondary" data-action="account-previous" ${offset===0?'disabled':''}>Previous</button><button class="secondary" data-action="account-next" ${offset+50>=state.accountTotal?'disabled':''}>Next</button></div>`;}

function render(){
  const page=document.querySelector('#page'); if(!page)return;
  const o=state.overview;let html='';
  if(state.page==='overview'){
    const disk=o.host.disk,percent=Math.round(disk.used/disk.total*100),memory=o.host.memory;
    html=heading('Tools',managesCustomers()?'Manage hosting accounts, websites and server operations.':'Manage your websites, files, applications and backups.');
    html+=`<div class="tools-layout"><div class="tools-main"><div class="directory-caption"><h2 id="tool-results" aria-live="polite">Available tools</h2><button class="quiet" data-action="clear-search">Show all tools</button></div>${toolDirectory()}<p class="note-line">This development workspace contains implemented tools. <a href="https://vectorcp.net/docs/capabilities/" target="_blank" rel="noopener noreferrer">View the full capability catalog ↗</a> for partial and planned systems, including email and public DNS.</p><section class="panel"><div class="panel-head"><h2>Recent activity</h2><button class="quiet" data-page="audit">View all ${icon('arrow')}</button></div>${activity(state.events.slice(0,3))}</section></div><aside class="workspace-information" aria-label="Workspace information"><section class="panel"><div class="panel-head"><h2>${managesCustomers()?'Server information':'General information'}</h2></div><dl class="information-list"><div><dt>Current user</dt><dd>${e(o.user.username)}</dd></div><div><dt>Access level</dt><dd>${e(o.user.role==='admin'?'Server owner':o.user.role)}</dd></div><div><dt>${managesCustomers()?'Hostname':'Primary website'}</dt><dd>${e(managesCustomers()?o.host.hostname:(state.sites[0]?.domain||'No websites yet'))}</dd></div>${managesCustomers()?`<div><dt>Operating system</dt><dd>${e(o.host.os)}</dd></div>`:''}<div><dt>Server address</dt><dd class="mono">${e(o.public_ipv4||'Not configured')}</dd></div><div><dt>Release</dt><dd>${e(o.version)} <span class="muted">· Development</span></dd></div></dl></section><section class="panel"><div class="panel-head"><h2>${managesCustomers()?'Server statistics':'Account statistics'}</h2></div><div class="panel-body"><div class="health-row"><span>Websites</span><strong>${o.counts.sites}${!managesCustomers()?' / '+o.user.site_limit:''}</strong></div><div class="health-row"><span>Active websites</span><strong>${o.counts.active}</strong></div>${managesCustomers()?`<div class="health-row"><span>Customers</span><strong>${o.counts.accounts}</strong></div>`:''}<div class="resource-line"><span>Website files</span><strong>${bytes(o.usage_bytes)}</strong></div>${managesCustomers()?`<hr><div class="resource-line"><span>Host disk used</span><strong>${percent}%</strong></div><progress class="progress" max="100" value="${percent}" aria-label="Host disk used"></progress><p class="small muted">${bytes(disk.used)} / ${bytes(disk.total)}</p><div class="resource-line"><span>Host memory used</span><strong>${memory?.total?Math.round((1-memory.available/memory.total)*100)+'%':'Unavailable'}</strong></div><progress class="progress" max="100" value="${memory?.total?Math.round((1-memory.available/memory.total)*100):0}" aria-label="Host memory used"></progress><div class="health-row"><span>1-minute load</span><strong>${o.host.load[0].toFixed(2)} / ${o.host.cpus} cores</strong></div><p class="small muted">Observed host measurements.</p>`:''}</div></section></aside></div>`;
  }else if(state.page==='sites'){
    html=heading('Websites & domains','Domains, website status and the people who own them.',actionButton('new-site','Add website'))+`<section class="panel"><div class="panel-head"><h2>All websites</h2><span class="badge-counter">${state.sites.length} total</span></div>${state.sites.length?tableFilter('websites')+siteRows(state.sites):empty('Your first website starts here.','Create a website, then point its domain to your server.',actionButton('new-site','Add website','secondary'))}</section><p class="note-line">Point each domain’s A record to ${e(o.public_ipv4||'the configured server IP')}. Apps & databases provides PHP, WordPress and HTTPS for isolated customers. Suspending a website returns HTTP 503.</p>`;
  }else if(state.page==='security'){
    html=securityPage();
  }else if(state.page==='accounts'){
    html=heading('Accounts','Customers, resellers and the plans that give them room.',actionButton('new-account','Add account'))+`<section class="panel"><div class="panel-head"><h2>Workspace accounts</h2><span class="badge-counter">${state.accounts.length} visible</span></div>${accountSearch()}<div class="table-wrap"><table><thead><tr><th>Select</th><th>Name</th><th>Username</th><th>Plan & allowance</th><th>Panel access</th><th></th></tr></thead><tbody>${state.accounts.map(a=>`<tr><td>${a.role!=='admin'?`<label class="selection"><input type="checkbox" data-account-selection value="${a.id}" aria-label="Select ${e(a.username)}"></label>`:''}</td><td><strong>${e(a.name)}</strong><div class="small muted">${e(a.role)}${a.parent_id?' · delegated customer':''}</div></td><td>${e(a.username)}</td><td>${e(a.plan_name||'Custom allowance')}<div class="small muted">${a.site_limit} sites · ${a.storage_mb} MB</div></td><td>${statusPill(a.active?'active':'locked')}${a.admin_lock?' <span class="small muted">Owner lock</span>':''}</td><td><div class="table-actions">${a.role!=='admin'?`<button class="quiet" data-action="inspect-account" data-id="${a.id}">Details</button><button class="quiet" data-action="edit-account" data-id="${a.id}">Edit</button><button class="quiet" data-action="reset-password" data-id="${a.id}">Reset password</button><button class="quiet" data-action="toggle-account" data-id="${a.id}" data-active="${!a.active}">${a.active?'Lock panel':'Enable panel'}</button>${!a.parent_id||a.parent_id===o.user.id?`<button class="quiet" data-action="assign-plan" data-id="${a.id}">Change plan</button>`:''}${a.role==='customer'?(a.hosting_slot?' <span class="pill">Isolated</span>':` <button class="quiet" data-action="enable-hosting" data-id="${a.id}">Enable hosting</button>`):''}`:''}</div></td></tr>`).join('')}</tbody></table></div>${accountPagination()}</section><p class="note-line">A reseller manages only its own customers. Locking a reseller also signs out its customers; hosted websites keep their current state. The server owner’s locks and website holds cannot be reversed by resellers. Hosting volumes have fixed sizes.</p>`;
  }else if(state.page==='plans'){
    const pool=state.pool;
    html=heading('Hosting plans','Reusable packages for customers and resellers.',actionButton('new-plan','Create plan'))+`<div class="callout"><strong>${o.user.role==='reseller'?'Your reserved customer pool':'Server hosting reservations'}</strong>${pool?.customers!=null?`${pool.customers} / ${pool.customer_limit} customers · ${pool.sites} / ${pool.site_limit} websites · ${pool.storage_mb} / ${pool.storage_limit_mb} MB reserved`:`${pool?.reserved_mb||0} / ${pool?.storage_limit_mb||16384} MB reserved`}<p>Locked accounts still reserve their allowance. Plans stay unchanged after creation; create another plan and assign it explicitly when a customer needs a change. Retiring a plan stops new assignments.</p></div><section class="panel"><div class="panel-head"><h2>Hosting packages</h2><span class="badge-counter">${state.plans.length} plans</span></div>${state.plans.length?`<div class="table-wrap"><table><thead><tr><th>Plan</th><th>Allowance</th><th>Included features</th><th>Assigned</th><th></th></tr></thead><tbody>${state.plans.map(p=>`<tr><td><strong>${e(p.name)}</strong><div class="small muted">${e(p.kind)} · ${e(p.owner)}</div></td><td>${p.site_limit} sites · ${p.storage_mb} MB${p.kind==='reseller'?`<div class="small muted">${p.customer_limit} customers</div>`:''}</td><td>${Object.entries(featureNames).filter(([k])=>p['allow_'+k]).map(([,v])=>v).join(', ')||'Static websites'}</td><td>${p.assigned}</td><td>${p.owner_id===o.user.id?`<button class="quiet" data-action="toggle-plan" data-id="${p.id}" data-active="${!p.active}">${p.active?'Retire':'Enable'}</button>`:''}${statusPill(p.active?'active':'retired')}</td></tr>`).join('')}</tbody></table></div>`:empty('Your first hosting package.','Create a customer plan before adding accounts.','','accounts')}</section><p class="note-line">Email and public DNS activation are still being built. Including those features in a package reserves permission to use them when configured; it does not start a public mail or DNS service.</p>`;
  }else if(state.page==='dns'){
    const d=state.dns;
    html=heading('DNS zones','Create, validate and export the records for a website.')+`<div class="callout"><strong>Private DNS preview</strong>These zones are validated by the server’s authoritative DNS service. This service currently listens only inside the VPS. Editing here does not change public DNS. Continue using your current DNS provider until public nameservers are configured.</div><section class="panel"><div class="file-toolbar"><label for="site-choice">Website</label><select id="site-choice">${siteOptions()}</select></div>${d?`<div class="panel-body"><h2>${e(d.domain)}</h2>${!d.can_edit?'<p class="note-line">DNS editing is not included in this customer’s hosting plan.</p>':''}${d.zone?`<div class="heading-actions">${d.can_edit?actionButton('new-dns','Add record'):''}${actionButton('export-dns','Export zone','secondary','download')}${d.can_edit?actionButton('verify-dns','Check ownership','secondary','check'):''}</div><p class="note-line">To verify ownership, add a TXT record named <strong>_vectorcp.${e(d.domain)}</strong> at your current public DNS provider with this value:</p><code class="dns-token">${e(d.zone.challenge)}</code><p>${d.zone.verified?'Ownership verified at the last check.':'Public ownership has not been verified.'}${d.zone.checked?' Checked '+e(date(d.zone.checked))+'.':''}</p><p class="small muted">Private zone serial ${d.zone.serial}. Exported SOA and nameserver records describe this preview; use your provider’s required nameservers when importing.</p>`:d.can_edit?actionButton('create-dns','Create private zone'):''}</div>${d.zone?`<div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Value</th><th>TTL</th><th></th></tr></thead><tbody>${d.records.map(r=>`<tr><td>${e(r.name)}</td><td>${e(r.type)}</td><td class="dns-value">${e(r.value)}</td><td>${r.ttl}</td><td>${d.can_edit?`<button class="quiet" data-action="delete-dns" data-id="${r.id}">Delete</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:''}`:empty('Choose a website.','DNS zones belong to an existing website.','','sites')}</section>`;
  }else if(state.page==='files'){
    html=heading('File manager','Manage website files. Transfers and file copies support up to 32 MB; the text editor supports 256 KB.')+`<section class="panel"><div class="file-toolbar"><label for="site-choice" class="small muted">Website</label><select id="site-choice" aria-label="Website">${state.sites.map(s=>`<option value="${s.id}" ${s.id===state.siteId?'selected':''}>${e(s.domain)}</option>`).join('')}</select><span class="file-path">/public/${e(state.folder)}</span><span class="spacer"></span>${actionButton('new-folder','Folder','secondary','files')}${actionButton('new-file','File','secondary','plus')}${actionButton('upload-file','Upload','primary','up')}${actionButton('batch-files','Selected…','secondary','files')}${actionButton('view-trash','Trash','secondary','backups')}<label class="hidden-preference"><input type="checkbox" id="show-hidden" ${state.showHidden?'checked':''}> Show hidden files</label></div><form class="file-search" data-form="file-search"><label for="file-query">Find by name</label><input id="file-query" name="query" value="${e(state.fileSearch||'')}" maxlength="100" placeholder="Search this website"><button class="secondary" type="submit">Search</button><button class="quiet" type="button" data-action="clear-file-search">Clear</button><p class="form-error" role="alert"></p></form><div class="file-grid"><div class="file-list" id="file-list"><p class="note-line" role="status">Loading files…</p></div><div class="editor" id="editor">${empty('Pick a file to begin.','Your changes are checked against the version you opened.','','file')}</div></div></section>`;
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
function pageLoading(loading,page){
  const content=document.querySelector('#page'),message=document.querySelector('#page-loading');
  if(content){content.inert=loading;content.setAttribute('aria-busy',String(loading));}
  if(message){message.textContent=loading?`Opening ${names[page]||'workspace'}…`:'';message.hidden=!loading;}
  document.querySelectorAll('.nav-item,#tool-search,[data-action="refresh"]').forEach(control=>control.disabled=loading);
}
async function loadPage(page=state.page){
  const request=++pageRequest;pageLoading(true,page);
  try{
    const o=await api('overview');if(request!==pageRequest)return;state.csrf=o.csrf;
    const forced=Boolean(o.user.password_change_required);if(forced)page='security';
    const manages=!forced&&['admin','reseller'].includes(o.user.role);
    const [sites,events,accounts,plans,jobs,backups]=await Promise.all([
      forced?Promise.resolve({sites:[]}):api('sites.list'),forced?Promise.resolve({events:[]}):api('audit'),manages?api('accounts.list',page==='accounts'?{...state.accountFilters,limit:50}:{}):Promise.resolve({accounts:[],total:0}),
      manages?api('plans.list'):Promise.resolve({plans:[],pool:null}),forced?Promise.resolve({jobs:[]}):api('jobs.list'),
      page==='backups'?api('backups.list'):Promise.resolve(null)
    ]);
    if(request!==pageRequest)return;
    const siteId=sites.sites.some(s=>s.id===state.siteId)?state.siteId:sites.sites[0]?.id||null;
    const dns=page==='dns'&&siteId?await api('dns.list',{site_id:siteId}):null;
    if(request!==pageRequest)return;
    if(siteId!==state.siteId){state.folder='';state.file=null;state.fileSearch='';}
    Object.assign(state,{page,overview:o,sites:sites.sites,events:events.events,accounts:accounts.accounts,plans:plans.plans,pool:plans.pool,jobs:jobs.jobs,dns,siteId});
    state.accountTotal=accounts.total;
    if(page==='security'){state.security=await api('security.status');const [profile,sessions]=forced?[null,{sessions:[]}]:await Promise.all([api('profile.get'),api('security.sessions')]);state.profile=profile;state.sessions=sessions.sessions;}
    if(request!==pageRequest)return;
    if(backups)state.backups=backups.backups;
    history.replaceState(null,'','/'+o.user.role);
    shell();
  }finally{if(request===pageRequest)pageLoading(false,page);}
}
async function loadFiles(){
  const list=document.querySelector('#file-list');if(!list)return;
  if(!state.siteId){list.innerHTML=empty('No websites yet.','Add a website before editing files.','','files');return;}
  const siteId=state.siteId,folder=state.folder,query=state.fileSearch||'';list.setAttribute('aria-busy','true');
  try{
    const result=await api(query?'files.search':'files.list',query?{site_id:siteId,query}:{site_id:siteId,path:folder});
    if(!list.isConnected||siteId!==state.siteId||folder!==state.folder||query!==(state.fileSearch||''))return;
    list.innerHTML=(folder&&!query?`<button class="file-row" data-action="folder-up">${icon('up')}Parent folder</button>`:'')+result.files.map(f=>{const path=f.path||[folder,f.name].filter(Boolean).join('/');return `<div class="file-entry"><label class="selection"><input type="checkbox" data-file-selection data-path="${e(path)}" data-revision="${e(f.revision)}" aria-label="Select ${e(f.path||f.name)}"></label><button class="file-row" data-action="${f.directory?'open-folder':'open-file'}" data-path="${e(path)}">${icon(f.directory?'files':'file')}<span>${e(f.path||f.name)}</span><small>${f.directory?'Folder':bytes(f.bytes)}</small></button><button class="quiet file-actions" data-action="file-actions" data-path="${e(path)}" data-revision="${e(f.revision)}" data-directory="${f.directory}" aria-label="Actions for ${e(f.path||f.name)}">Actions</button></div>`;}).join('')+(result.limited?'<p class="note-line">Showing the first 200 matches or 12,000 scanned entries. Narrow your search.</p>':'');
    if(!result.files.length)list.innerHTML+=empty(query?'No matching files.':'Nothing here yet.',query?'Try another name'+(state.showHidden?'.':', or enable hidden files.'):'Upload a file or add a folder.','','files');
  }catch(err){if(list.isConnected)list.innerHTML=empty('Files could not be loaded.',e(err.message),actionButton('refresh','Try again','secondary','refresh'),'files');throw err;}
  finally{list.removeAttribute('aria-busy');}
}
function closeModal(){if(modal.querySelector('form')?.dataset.form==='confirm-factor')api('security.cancel').catch(()=>{});modal.close();document.querySelector('#modal-content').replaceChildren();}
function showModal(title,sub,form,body,submit){
  document.querySelector('#modal-content').innerHTML=`<div class="modal-head"><div><h2 id="modal-title">${title}</h2><p id="modal-description">${sub}</p></div><button class="quiet" data-action="close-modal" aria-label="Close dialog">${icon('close')}</button></div><form data-form="${form}" class="modal-body">${body}<p class="form-error" role="alert"></p><div class="modal-foot"><button type="button" class="secondary" data-action="close-modal">Cancel</button><button class="${form.startsWith('delete-')?'danger':'primary'}" type="submit">${submit}</button></div></form>`;
  modal.showModal();
  modal.querySelector('input:not([type="hidden"]):enabled,select:enabled,textarea:enabled')?.focus();
}
function field(label,name,options={}){const id='field-'+name;return `<div class="field"><label for="${id}">${label}</label><input id="${id}" name="${name}" type="${options.type||'text'}" ${options.attrs||''} required ${options.help?`aria-describedby="${id}-help"`:''} ${options.value!=null?`value="${e(options.value)}"`:''}>${options.help?`<small id="${id}-help">${options.help}</small>`:''}</div>`;}
function planOptions(kind){return state.plans.filter(p=>p.active&&p.kind===kind&&p.owner_id===state.overview.user.id).map(p=>`<option value="${p.id}">${e(p.name)} · ${p.storage_mb} MB · ${p.site_limit} sites</option>`).join('')||`<option value="" disabled selected>No active ${e(kind)} plans</option>`;}
function siteOptions(){return state.sites.map(s=>`<option value="${s.id}" ${s.id===state.siteId?'selected':''}>${e(s.domain)}</option>`).join('');}
function clearEditor(){state.file=null;state.revision=null;const editor=document.querySelector('#editor');if(editor)editor.innerHTML=empty('Pick a file to begin.','Select a file from the current folder.','','file');}
function editFile(name,content,revision){
  state.file=name;state.revision=revision;
  const el=document.querySelector('#editor');
  el.innerHTML=`<div class="editor-heading"><span class="mono">${e(name)}</span><button class="primary" data-action="save-file">Save changes ${icon('check')}</button></div><textarea id="file-content" aria-label="File contents" spellcheck="false"></textarea><span class="small muted">Text editor · UTF-8 · maximum 256 KB. File changes are written atomically.</span>`;
  document.querySelector('#file-content').value=content;
}
const sha256=async data=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',data))].map(n=>n.toString(16).padStart(2,'0')).join('');
function base64Bytes(data){let value='';for(let i=0;i<data.length;i+=8192)value+=String.fromCharCode(...data.subarray(i,i+8192));return btoa(value);}
function saveDownload(blob,name){const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function downloadFile(siteId,path){
  if(!crypto.subtle)throw new Error('File verification requires HTTPS or a local SSH tunnel.');
  const info=await api('files.describe',{site_id:siteId,path}),parts=[];let offset=0;
  while(offset<info.bytes){
    const chunk=await api('files.chunk',{site_id:siteId,path,revision:info.revision,offset});
    if(chunk.next<=offset)throw new Error('The download stopped before it finished. Please retry.');
    const value=atob(chunk.base64);parts.push(Uint8Array.from(value,c=>c.charCodeAt(0)));offset=chunk.next;
    notify(`Downloading ${path.split('/').pop()}: ${Math.round(offset/Math.max(info.bytes,1)*100)}%`);
  }
  const blob=new Blob(parts,{type:'application/octet-stream'});
  if(await sha256(await blob.arrayBuffer())!==info.sha256)throw new Error('Download verification failed. Please retry.');
  saveDownload(blob,path.split('/').pop());notify('File downloaded and checksum verified.');
}
modal.addEventListener('cancel',event=>{if(transferBusy){event.preventDefault();return;}const form=modal.querySelector('form');if(form?.dataset.uploadId)api('files.upload.cancel',{site_id:Number(form.dataset.siteId),id:form.dataset.uploadId}).catch(()=>{});event.preventDefault();closeModal();});
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
    if(action==='close-modal'){if(transferBusy){notify('Wait for the current transfer request to finish.');return;}const form=modal.querySelector('form');if(form?.dataset.uploadId)api('files.upload.cancel',{site_id:Number(form.dataset.siteId),id:form.dataset.uploadId}).catch(()=>{});closeModal();return;}
    if(action==='refresh'){await loadPage();notify('Workspace refreshed.');return;}
    if(action==='logout'){await api('logout');auth();return;}
    if(action==='account-previous'||action==='account-next'){state.accountFilters.offset=Math.max(0,state.accountFilters.offset+(action==='account-next'?50:-50));await loadPage('accounts');return;}
    if(action==='bulk-accounts'){
      const ids=[...document.querySelectorAll('[data-account-selection]:checked')].map(x=>Number(x.value));
      if(!ids.length){notify('Select at least one account.',true);return;}
      showModal('Change selected accounts',`${ids.length} account${ids.length===1?'':'s'} selected. The entire request is refused if any account is outside your permissions or cannot accept the change.`,'bulk-accounts',`<input type="hidden" name="ids" value="${e(JSON.stringify(ids))}"><label class="field">Change<select name="operation" id="bulk-operation"><option value="lock">Lock panel access</option><option value="enable">Enable panel access</option><option value="plan">Assign hosting plan</option></select></label><label class="field" id="bulk-plan-field" hidden>Hosting plan<select name="plan_id">${state.plans.filter(p=>p.owner_id===state.overview.user.id&&p.active).map(p=>`<option value="${p.id}">${e(p.name)} · ${e(p.kind)}</option>`).join('')}</select></label><p>Access changes sign out the selected accounts and their delegated customers. Hosted websites keep their current state.</p>`,'Apply changes');return;
    }
    if(action==='inspect-account'){
      const r=await api('accounts.inspect',{id:Number(button.dataset.id)}),a=r.account;
      showModal('Account details',e(a.username),'close-details',`<dl class="account-details"><dt>Name</dt><dd>${e(a.name)}</dd><dt>Contact</dt><dd>${e(a.contact_email||'Not set')}</dd><dt>Account type</dt><dd>${e(a.role)}</dd><dt>Created</dt><dd>${e(date(a.created))}</dd><dt>Plan</dt><dd>${e(a.plan_name||'Custom allowance')}</dd><dt>Website files</dt><dd>${bytes(r.file_bytes)} / ${a.storage_mb} MB</dd><dt>Websites</dt><dd>${r.websites.length} / ${a.site_limit}</dd><dt>Active sessions</dt><dd>${r.active_sessions}</dd>${a.role==='reseller'?`<dt>Delegated customers</dt><dd>${r.customers}</dd>`:''}<dt>Password change</dt><dd>${a.password_change_required?'Required at next sign-in':'Not required'}</dd></dl><h3>Websites</h3>${r.websites.length?r.websites.map(x=>`<p>${e(x.domain)} · ${e(x.status)} · ${e(x.runtime)}</p>`).join(''):'<p>No websites.</p>'}`,'Close');return;
    }
    if(action==='edit-account'){
      const a=state.accounts.find(a=>a.id===Number(button.dataset.id));
      showModal('Edit account',e(a.username),'edit-account',`<input type="hidden" name="id" value="${a.id}">`+field('Name','name',{value:a.name,attrs:'maxlength="80"'})+contactField(a.contact_email),'Save details');return;
    }
    if(action==='reset-password'){
      const a=state.accounts.find(a=>a.id===Number(button.dataset.id));
      const status=await api('security.status');
      showModal('Reset account password',`Set a temporary password for ${e(a.username)}. Existing sessions are revoked and the account must choose its own password at next sign-in. Its authenticator remains enabled.`,'reset-password',`<input type="hidden" name="id" value="${a.id}">`+newPasswordField('Temporary password')+credentialFields(status),'Reset password');return;
    }
    if(action==='edit-profile'){showModal('Your contact details','Your contact address is stored for account administration. Email delivery is not configured.','edit-profile',field('Name','name',{value:state.profile.name,attrs:'maxlength="80"'})+contactField(state.profile.contact_email)+credentialFields(state.security),'Save details');return;}
    if(action==='change-password'){showModal('Change password','All sessions, including this one, will be signed out after the change.','change-password',newPasswordField()+credentialFields(state.security),'Change password');return;}
    if(['enroll-factor','disable-factor','replace-recovery'].includes(action)){
      const kind={'enroll-factor':'enroll-factor','disable-factor':'disable-factor','replace-recovery':'replace-recovery'}[action];
      showModal(action==='enroll-factor'?'Enable two-factor authentication':action==='disable-factor'?'Disable two-factor authentication':'Replace recovery codes',action==='enroll-factor'?'Verify your password, then add the setup key to your authenticator app.':'This signs out your other sessions. Replacing recovery codes invalidates all previously saved codes.',kind,credentialFields(state.security),action==='enroll-factor'?'Continue':action==='disable-factor'?'Disable authenticator':'Replace codes');return;
    }
    if(action==='revoke-session'){
      showModal('Sign out this session?',button.dataset.id==='others'?'Your current session will stay signed in.':'The selected device must sign in again.','revoke-session',`<input type="hidden" name="id" value="${e(button.dataset.id)}">`,'Sign out');return;
    }
    if(action==='download-recovery'){
      const codes=[...modal.querySelectorAll('[data-recovery-code]')].map(x=>x.textContent);
      saveDownload(new Blob(['VectorCP recovery codes for '+state.overview.user.username+'\nKeep these private. Each code works once.\n\n'+codes.join('\n')+'\n'],{type:'text/plain'}),'VectorCP-recovery-codes.txt');return;
    }
    if(action==='new-site'){
      showModal('Create website','Create under an isolated customer to use PHP or WordPress.','site',field('Domain name','domain',{attrs:'placeholder="example.com" autocapitalize="none" maxlength="253"'})+(managesCustomers()?`<label class="field">Owner<select name="user_id">${state.accounts.filter(a=>a.active&&a.role==='customer').map(a=>`<option value="${a.id}">${e(a.name)} (${e(a.username)})</option>`).join('')}</select></label>`:''),'Create website');return;
    }
    if(action==='new-account'){
      if(!state.plans.some(p=>p.owner_id===state.overview.user.id&&p.active)){notify('Create a hosting plan first.',true);await loadPage('plans');return;}
      showModal('Create account','Each account receives a hosting plan and its reserved allowance.','account',field('Name','name',{attrs:'maxlength="80"'})+field('Username','username',{attrs:'minlength="3" maxlength="32" pattern="[a-z][a-z0-9_-]{2,31}" autocapitalize="none"'})+field('Password','password',{type:'password',attrs:'minlength="15" maxlength="256" autocomplete="new-password"',help:'Share this through a private channel.'})+(state.overview.user.role==='admin'?'<label class="field">Account type<select name="role" id="account-role"><option value="customer">Customer</option><option value="reseller">Reseller</option></select></label>':'<input type="hidden" name="role" value="customer">')+'<label class="field">Hosting plan<select required name="plan_id" id="account-plan">'+planOptions('customer')+'</select></label>','Create account');return;
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
      showModal('Install WordPress','Installs the current official release into this website. Only its welcome page may exist.','wordpress',field('Site title','title',{attrs:'maxlength="120"'})+field('WordPress administrator','admin',{attrs:'minlength="3" maxlength="40" autocomplete="off"'})+field('Administrator email','email',{type:'email',attrs:'maxlength="160"'})+field('WordPress password','password',{type:'password',attrs:'minlength="15" maxlength="128" autocomplete="new-password"',help:'Keep this password. It is separate from your VectorCP sign-in.'}),'Install WordPress');return;
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
    if(action==='open-files'){state.siteId=Number(button.dataset.id);state.folder='';state.file=null;state.fileSearch='';await loadPage('files');return;}
    if(action==='go-files'){await loadPage('files');return;}
    if(action==='go-backups'){await loadPage('backups');return;}
    if(action==='open-folder'){state.folder=button.dataset.path;state.file=null;state.fileSearch='';render();return;}
    if(action==='folder-up'){state.folder=state.folder.split('/').slice(0,-1).join('/');state.file=null;state.fileSearch='';render();return;}
    if(action==='open-file'){const name=button.dataset.path,siteId=state.siteId;const result=await api('files.read',{site_id:siteId,path:name});if(state.page==='files'&&state.siteId===siteId)editFile(name,result.content,result.revision);return;}
    if(action==='clear-file-search'){state.fileSearch='';document.querySelector('#file-query').value='';await loadFiles();return;}
    if(action==='upload-file'){
      if(!state.siteId){notify('Add a website first.',true);return;}
      showModal('Upload a file','Maximum 32 MB. Existing files are preserved; use a new name to upload another version.','upload-file',`<input type="hidden" name="site_id" value="${state.siteId}"><input type="hidden" name="folder" value="${e(state.folder)}"><div class="field"><label for="upload-file-input">File</label><input id="upload-file-input" type="file" name="upload_file" required></div><p id="upload-progress" role="status" aria-live="polite"></p>`,'Upload');return;
    }
    if(action==='file-actions'){
      const path=button.dataset.path,directory=button.dataset.directory==='true';
      const attributes=`data-path="${e(path)}" data-revision="${e(button.dataset.revision)}" data-site-id="${state.siteId}"`;
      showModal('File actions',e('/public/'+path),'close-details',`<p>${directory?'Folder: copies and moves include hidden contents. Copies support up to 32 MB and 1,000 entries. Removal requires an empty folder.':'Regular file: copies and downloads support up to 32 MB.'}</p><div class="file-operation-list">${directory?'':`<button type="button" class="secondary" data-action="file-edit" ${attributes}>Edit text</button><button type="button" class="secondary" data-action="file-download" ${attributes}>Download</button>`}<button type="button" class="secondary" data-action="file-copy" ${attributes}>Copy</button><button type="button" class="secondary" data-action="archive-create" ${attributes}>Create ZIP</button>${!directory&&path.toLowerCase().endsWith('.zip')?`<button type="button" class="secondary" data-action="archive-extract" ${attributes}>Extract ZIP</button>`:''}<button type="button" class="secondary" data-action="file-permissions" ${attributes}>Permissions</button><button type="button" class="secondary" data-action="file-move" ${attributes}>Move / rename</button><button type="button" class="secondary" data-action="file-trash" ${attributes}>Move to trash</button><button type="button" class="danger" data-action="file-remove" ${attributes}>Remove permanently</button></div>`,'Close');return;
    }
    if(action==='view-trash'){
      const siteId=state.siteId;if(!siteId){notify('Choose a website first.',true);return;}const result=await api('files.trash.list',{site_id:siteId});
      showModal('Website trash','Trash stays on this customer’s storage and counts against its file allowance. Items are kept until restored or permanently removed.','close-details',result.entries.length?result.entries.map(item=>`<div class="batch-result"><strong>${e(item.path)}</strong><span>${bytes(item.bytes)} · ${e(date(item.created))}</span><div class="heading-actions"><button type="button" class="secondary" data-action="restore-trash" data-id="${e(item.id)}" data-site-id="${siteId}" data-path="${e(item.path)}">Restore</button><button type="button" class="danger" data-action="purge-trash" data-id="${e(item.id)}" data-site-id="${siteId}" data-path="${e(item.path)}">Remove permanently</button></div></div>`).join(''):'<p>Trash is empty.</p>','Close');return;
    }
    if(action==='file-trash'){
      const path=button.dataset.path;closeModal();showModal('Move item to trash?',`Remove /public/${e(path)} from the live website? You can restore it from this website’s Trash.`,'trash-item',`<input type="hidden" name="site_id" value="${Number(button.dataset.siteId)}"><input type="hidden" name="path" value="${e(path)}"><input type="hidden" name="revision" value="${e(button.dataset.revision)}">`,'Move to trash');return;
    }
    if(action==='restore-trash'||action==='purge-trash'){
      const purge=action==='purge-trash',id=button.dataset.id,site=Number(button.dataset.siteId),path=button.dataset.path;closeModal();
      showModal(purge?'Permanently remove this trash item?':'Restore from trash',purge?`Permanently remove ${e(path)} and its contents? This cannot be undone.`:'Restore to the original path or choose another website-relative path. Existing destinations are preserved.',purge?'purge-trash':'restore-trash',`<input type="hidden" name="id" value="${e(id)}"><input type="hidden" name="site_id" value="${site}">`+(purge?field('Type REMOVE to confirm','confirm',{attrs:'pattern="REMOVE" autocomplete="off"'}):field('Restore path','destination',{value:path,attrs:'maxlength="512"'})),purge?'Remove permanently':'Restore');if(purge)modal.querySelector('button[type="submit"]').className='danger';return;
    }
    if(action==='batch-files'){
      const items=[...document.querySelectorAll('[data-file-selection]:checked')].map(x=>({path:x.dataset.path,revision:x.dataset.revision}));
      if(!items.length||items.length>20){notify('Select between 1 and 20 items.',true);return;}
      showModal('Selected file actions',`${items.length} items selected. Each item reports its own result; a failed item does not undo completed items.`,'batch-files',`<input type="hidden" name="items" value="${e(JSON.stringify(items))}"><input type="hidden" name="site_id" value="${state.siteId}"><label class="field">Operation<select name="operation" id="file-batch-operation"><option value="copy">Copy</option><option value="move">Move</option><option value="remove">Permanently remove</option></select></label><div class="field" id="file-batch-destination"><label for="batch-destination">Destination folder</label><input id="batch-destination" name="destination" value="${e(state.folder)}" maxlength="512"><small>Existing website folder, or leave empty for /public. Existing destinations are preserved.</small></div><div class="field" id="file-batch-confirm" hidden><label for="batch-remove-confirm">Type REMOVE to confirm</label><input id="batch-remove-confirm" name="confirm" autocomplete="off"><small>Removal cannot be undone and requires folders to be empty.</small></div>`,'Run selected actions');return;
    }
    if(action==='archive-create'||action==='archive-extract'){
      const extract=action==='archive-extract',path=button.dataset.path,siteId=Number(button.dataset.siteId),rev=button.dataset.revision;closeModal();
      showModal(extract?'Extract ZIP':'Create ZIP',extract?'Extract into a new folder. Existing files and folders are preserved.':'Create a ZIP containing this item, including hidden contents. Source files stay unchanged.','archive-operation',`<input type="hidden" name="site_id" value="${siteId}"><input type="hidden" name="path" value="${e(path)}"><input type="hidden" name="revision" value="${e(rev)}"><input type="hidden" name="operation" value="${extract?'extract':'create'}">`+field(extract?'New folder path':'ZIP destination path','destination',{value:extract?path.slice(0,-4)+'-unpacked':path+'.zip',attrs:'maxlength="512"',help:'Website-relative path; the parent folder must exist. Maximum 32 MB of file content and 1,000 entries. Unencrypted standard ZIP only.'}),extract?'Extract ZIP':'Create ZIP');return;
    }
    if(action==='file-permissions'){
      const siteId=Number(button.dataset.siteId),path=button.dataset.path,r=await api('files.permissions',{site_id:siteId,path});closeModal();
      showModal('File permissions',e('/public/'+path),'file-permissions',`<input type="hidden" name="site_id" value="${siteId}"><input type="hidden" name="path" value="${e(path)}"><input type="hidden" name="revision" value="${e(r.revision)}"><p>Current permissions: <strong>${e(r.mode)}</strong></p><label class="field">Permissions<select name="mode">${r.choices.map(mode=>`<option value="${mode}" ${mode===r.mode?'selected':''}>${mode} · ${permissionName(mode)}</option>`).join('')}</select></label><p>${r.isolated?'Ownership is restored to '+e(r.owner)+' when saving.':'Static preview files keep their existing ownership.'} Shared write permissions and special privilege bits are refused. Restrictive modes can stop your website from reading a file.</p>`,'Save permissions');return;
    }
    if(action==='file-edit'){
      const path=button.dataset.path,siteId=Number(button.dataset.siteId),result=await api('files.read',{site_id:siteId,path});closeModal();if(state.page==='files'&&state.siteId===siteId)editFile(path,result.content,result.revision);return;
    }
    if(action==='file-download'){button.disabled=true;await downloadFile(Number(button.dataset.siteId),button.dataset.path);return;}
    if(['file-copy','file-move','file-remove'].includes(action)){
      const path=button.dataset.path,kind=action.slice(5);closeModal();
      showModal(kind==='remove'?'Permanently remove this item?':kind==='copy'?'Copy item':'Move / rename',kind==='remove'?`Remove /public/${e(path)}? This cannot be undone. Keep a backup first.`:'Destinations are relative to this website’s public folder. Existing items are never overwritten.','file-operation',`<input type="hidden" name="site_id" value="${Number(button.dataset.siteId)}"><input type="hidden" name="path" value="${e(path)}"><input type="hidden" name="revision" value="${e(button.dataset.revision)}"><input type="hidden" name="operation" value="${kind}">${kind==='remove'?field('Type REMOVE to confirm','confirm',{attrs:'pattern="REMOVE" autocomplete="off"'}):field('Destination path','destination',{value:path,attrs:'maxlength="512"',help:'For example, assets/logo.png. The destination folder must already exist.'})}`,kind==='remove'?'Remove permanently':kind==='copy'?'Copy item':'Move item');
      if(kind==='remove')modal.querySelector('button[type="submit"]').className='danger';return;
    }
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
  if(event.target.id==='file-batch-operation'){const remove=event.target.value==='remove';document.querySelector('#file-batch-destination').hidden=remove;document.querySelector('#file-batch-confirm').hidden=!remove;modal.querySelector('button[type="submit"]').className=remove?'danger':'primary';}
  if(event.target.id==='show-hidden'){state.showHidden=event.target.checked;if(!state.showHidden&&state.folder.split('/').some(x=>x.startsWith('.'))){state.folder='';state.file=null;}render();return;}
  if(event.target.id==='bulk-operation')document.querySelector('#bulk-plan-field').hidden=event.target.value!=='plan';
  if(event.target.id==='account-role')document.querySelector('#account-plan').innerHTML=planOptions(event.target.value);
  if(event.target.id==='plan-kind'){const reseller=event.target.value==='reseller';document.querySelector('#reseller-count').hidden=!reseller;document.querySelector('[name="site_limit"]').max=reseller?1000:100;document.querySelector('[name="storage_mb"]').max=reseller?16384:4096;}
  if(event.target.id==='site-choice'){state.siteId=Number(event.target.value);state.folder='';state.file=null;state.fileSearch='';if(state.page==='dns')loadPage().catch(err=>notify(err.message,true));else render();}
});
document.addEventListener('submit',async event=>{
  const form=event.target.closest('form[data-form]');if(!form)return;event.preventDefault();
  if(form.dataset.form==='tool-search'){try{toolQuery=form.elements.query.value;if(state.page!=='overview'){await loadPage('overview');focusPage();}else filterTools();}catch(err){notify(err.message,true);}return;}
  if(form.dataset.form==='account-search'){const data=Object.fromEntries(new FormData(form));state.accountFilters={...data,offset:0};try{await loadPage('accounts');}catch(err){notify(err.message,true);}return;}
  if(form.dataset.form==='file-search'){state.fileSearch=form.elements.query.value.trim();form.querySelector('.form-error').textContent='';try{await loadFiles();}catch(err){form.querySelector('.form-error').textContent=err.message;}return;}
  const button=form.querySelector('button[type="submit"]');button.disabled=true;form.querySelector('.form-error').textContent='';
  try{
    const data=Object.fromEntries(new FormData(form));const kind=form.dataset.form;
    if(kind==='login'||kind==='bootstrap'){if(kind==='login'&&['/admin','/reseller','/customer'].includes(location.pathname))data.entry=location.pathname.slice(1);const result=await api(kind,data);if(result.mfa_required){const field=form.querySelector('#login-factor');field.hidden=false;field.querySelector('input').required=true;field.querySelector('input').focus();return;}form.reset();state.csrf=result.csrf;setupToken='';await loadPage('overview');return;}
    if(kind==='close-details'){closeModal();return;}
    if(kind==='edit-account'){await api('accounts.update',{id:Number(data.id),name:data.name,contact_email:data.contact_email});closeModal();await loadPage();notify('Account details saved.');return;}
    if(kind==='bulk-accounts'){await api('accounts.bulk',{ids:JSON.parse(data.ids),operation:data.operation,plan_id:data.plan_id?Number(data.plan_id):null});closeModal();await loadPage();notify('Selected accounts updated.');return;}
    if(kind==='reset-password'){await api('accounts.password',{...data,id:Number(data.id)});closeModal();await loadPage();notify('Temporary password set. Share it privately with the account owner.');return;}
    if(kind==='edit-profile'){await api('profile.update',data);closeModal();await loadPage();notify('Contact details saved.');return;}
    if(kind==='change-password'){await api('security.password',data);closeModal();auth();notify('Password changed. Sign in with your new password.');return;}
    if(kind==='enroll-factor'){
      const result=await api('security.enroll',data);closeModal();
      showModal('Add your authenticator','In your authenticator app, add an account using the setup key below. Choose time-based codes, six digits and a 30-second interval.','confirm-factor',`<p>Issuer: <strong>VectorCP</strong><br>Account: <strong>${e(result.account)}</strong></p><p class="secret-key mono">${e(result.secret)}</p><p>This key is shown only for this enrollment. Enrollment expires in 10 minutes.</p>`+field('Authenticator code','verification_code',{attrs:'inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code"'})+credentialFields({enabled:false}),'Enable authenticator');return;
    }
    if(['confirm-factor','disable-factor','replace-recovery'].includes(kind)){
      const result=await api({'confirm-factor':'security.confirm','disable-factor':'security.disable','replace-recovery':'security.recovery'}[kind],data);closeModal();await loadPage('security');
      if(result.recovery_codes)showRecovery(result.recovery_codes);else notify('Two-factor authentication disabled.');return;
    }
    if(kind==='revoke-session'){const result=await api('security.revoke',data);closeModal();if(result.signed_out)auth();else await loadPage('security');notify('Session access revoked.');return;}
    if(['trash-item','restore-trash','purge-trash'].includes(kind)){
      if(kind==='purge-trash'&&data.confirm!=='REMOVE')throw new Error('Type REMOVE to confirm permanent removal.');
      const method={'trash-item':'files.trash','restore-trash':'files.trash.restore','purge-trash':'files.trash.purge'}[kind];await api(method,{...data,site_id:Number(data.site_id)});closeModal();clearEditor();await loadFiles();notify(kind==='trash-item'?'Moved to trash. You can restore it from Trash.':kind==='restore-trash'?'Item restored.':'Trash item permanently removed.');return;
    }
    if(kind==='batch-files'){
      if(data.operation==='remove'&&data.confirm!=='REMOVE')throw new Error('Type REMOVE to confirm permanent removal.');
      const result=await api('files.batch',{items:JSON.parse(data.items),site_id:Number(data.site_id),operation:data.operation,destination:data.destination});closeModal();clearEditor();await loadFiles();
      showModal('Selected action results','Completed items stay completed. Review failed items before retrying.','close-details',result.results.map(r=>`<div class="batch-result"><strong>${e(r.path)}</strong><span>${r.ok?'Completed':e(r.error)}</span></div>`).join(''),'Close');return;
    }
    if(kind==='archive-operation'){await api('files.archive.'+data.operation,{...data,site_id:Number(data.site_id)});closeModal();clearEditor();await loadFiles();notify(data.operation==='create'?'ZIP created.':'ZIP verified and extracted.');return;}
    if(kind==='file-permissions'){await api('files.chmod',{...data,site_id:Number(data.site_id)});closeModal();await loadFiles();notify('Permissions saved.');return;}
    if(kind==='file-operation'){
      if(data.operation==='remove'&&data.confirm!=='REMOVE')throw new Error('Type REMOVE to confirm.');
      data.site_id=Number(data.site_id);await api('files.'+data.operation,data);closeModal();state.file=null;if(state.siteId===data.site_id){document.querySelector('#editor').innerHTML=empty('Pick a file to begin.','File operation completed.','','file');await loadFiles();}notify('File operation completed.');return;
    }
    if(kind==='upload-file'){
      const file=form.elements.upload_file.files[0],siteId=Number(data.site_id),progress=form.querySelector('#upload-progress');
      if(!file||file.size>33554432)throw new Error('Choose a file up to 32 MB.');
      if(!crypto.subtle)throw new Error('File verification requires HTTPS or a local SSH tunnel.');
      transferBusy=true;form.querySelector('input[type="file"]').disabled=true;
      try{
        progress.textContent='Checking file…';const buffer=new Uint8Array(await file.arrayBuffer()),checksum=await sha256(buffer);
        const path=[data.folder,file.name].filter(Boolean).join('/');form.dataset.siteId=String(siteId);
        if(form.dataset.uploadId&&form.dataset.checksum!==checksum){await api('files.upload.cancel',{site_id:siteId,id:form.dataset.uploadId});delete form.dataset.uploadId;}
        let ticket;
        if(form.dataset.uploadId){try{ticket=await api('files.upload.status',{site_id:siteId,id:form.dataset.uploadId});}catch(err){if(err.status!==404)throw err;delete form.dataset.uploadId;}}
        if(!ticket){ticket=await api('files.upload.start',{site_id:siteId,path,bytes:file.size,sha256:checksum});form.dataset.uploadId=ticket.id;form.dataset.checksum=checksum;}
        let offset=ticket.received;
        while(offset<file.size){const chunk=buffer.subarray(offset,offset+ticket.chunk_bytes);const result=await api('files.upload.chunk',{site_id:siteId,id:ticket.id,offset,base64:base64Bytes(chunk)});if(result.received<=offset)throw new Error('The upload did not advance. Please retry.');offset=result.received;progress.textContent=`Uploading: ${Math.round(offset/Math.max(file.size,1)*100)}%`;}
        progress.textContent='Verifying and publishing…';await api('files.upload.finish',{site_id:siteId,id:ticket.id});delete form.dataset.uploadId;closeModal();if(state.page==='files'&&state.siteId===siteId)await loadFiles();notify('File uploaded and checksum verified.');
      }finally{transferBusy=false;form.querySelector('input[type="file"]').disabled=false;}
      return;
    }
    if(['hosting-enable','wordpress','full-backup','restore','delete-backup'].includes(kind)){
      const method={'hosting-enable':'hosting.enable','wordpress':'hosting.wordpress','full-backup':'backups.full','restore':'backups.restore','delete-backup':'backups.delete'}[kind];
      if(kind==='hosting-enable'){data.id=Number(data.id);data.storage_mb=Number(data.storage_mb);}
      if(kind==='wordpress')data.site_id=state.siteId;
      if(kind==='full-backup')data.site_id=Number(data.site_id);
      await api(method,data);closeModal();await loadPage(kind==='delete-backup'?'backups':'hosting');notify(kind==='delete-backup'?'Backup deleted.':'Server job started.');return;
    }
    if(kind==='plan'){data.site_limit=Number(data.site_limit);data.storage_mb=Number(data.storage_mb);data.customer_limit=data.kind==='reseller'?Number(data.customer_limit):0;for(const k of Object.keys(featureNames))data['allow_'+k]=form.elements['allow_'+k].checked;await api('plans.create',data);closeModal();await loadPage('plans');notify('Hosting plan created.');return;}
    if(kind==='assign-plan'){await api('plans.assign',{id:Number(data.id),plan_id:Number(data.plan_id)});closeModal();await loadPage();notify('Hosting plan assigned.');return;}
    if(kind==='dns'||kind==='delete-dns'){data.site_id=state.siteId;if(kind==='dns')data.ttl=Number(data.ttl);else data.id=Number(data.id);await api(kind==='dns'?'dns.save':'dns.delete',data);closeModal();await loadPage();notify('Private DNS zone updated.');return;}
    if(kind==='site'){if(data.user_id)data.user_id=Number(data.user_id);await api('sites.create',data);}
    if(kind==='account'){data.plan_id=Number(data.plan_id);await api('accounts.create',data);}
    if(kind==='folder'){await api('files.mkdir',{site_id:state.siteId,path:[state.folder,data.name].filter(Boolean).join('/')});closeModal();await loadFiles();notify('Folder created.');return;}
    if(kind==='file'){const path=[state.folder,data.name].filter(Boolean).join('/');await api('files.write',{site_id:state.siteId,path,content:'',revision:'new'});closeModal();const saved=await api('files.read',{site_id:state.siteId,path});await loadFiles();editFile(path,saved.content,saved.revision);notify('File created.');return;}
    if(kind==='backup'){await api('backups.create',{site_id:Number(data.site_id)});}
    closeModal();await loadPage();notify(kind==='site'?'Website created. Configure its DNS before visiting.':kind==='account'?'Customer account created.':'Site export created.');
  }catch(err){const box=form.querySelector('.form-error');if(box)box.textContent=err.message;}finally{if(button.isConnected)button.disabled=false;}
});
async function start(){try{await loadPage();}catch(err){if(err.status===401)auth(Boolean(setupToken));else{auth(Boolean(setupToken));notify(err.message,true);}}}
setInterval(()=>{if(state.overview && ['hosting','backups','status'].includes(state.page) && state.jobs.some(j=>['queued','running'].includes(j.status)) && !modal.open)loadPage().catch(err=>notify(err.message,true));},5000);
start();
