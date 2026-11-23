'use strict';

function mailPanel(){
  const info=state.mail,owner=state.overview.user.role==='admin';
  const enabled=info.domains.filter(d=>d.enabled);
  return heading('Email accounts','Manage private mailboxes and connect your email client.',
    info.installed&&enabled.length&&!info.recovery_required?actionButton('mail-create','Create mailbox'):'' )+
    (!info.installed?`<div class="callout"><strong>Mail service is not installed.</strong>The server administrator can install the optional mail profile using the <a href="https://vectorcp.net/docs/mail_hosting/" target="_blank" rel="noopener noreferrer">mail hosting guide ↗</a>. Existing external email routing stays unchanged.</div>`:
    `<div class="callout"><strong>${e(info.hostname)}</strong>Use your complete email address as the username. IMAP: port 993 with TLS. SMTP: port 587 with STARTTLS and authentication. DNS, trusted certificates and reverse DNS need server-owner setup.${info.recovery_required?`<p role="alert"><strong>Mail publication is paused for recovery.</strong>Inspect the service journal before restoring the committed configuration.</p>${owner?actionButton('mail-recover','Recover mail services','secondary','refresh'):''}`:''}</div>`)+
    `<section class="panel"><div class="panel-head"><h2>Mail domains</h2><span class="badge-counter">${enabled.length} enabled</span></div>${info.domains.length?`<div class="table-wrap"><table><thead><tr><th>Domain</th><th>Status</th><th>Mailboxes</th><th>Actions</th></tr></thead><tbody>${info.domains.map(d=>`<tr><td><strong>${e(d.domain)}</strong></td><td>${statusPill(d.effective?'active':d.enabled?'paused':'not enabled')}</td><td>${d.mailboxes.length} · ${d.mailboxes.reduce((n,b)=>n+b.quota_mb,0)} MB reserved</td><td>${owner&&info.installed&&!info.recovery_required?`<button class="quiet" data-action="mail-domain" data-site="${d.site_id}">${d.enabled?'Disable mail':'Enable mail'}</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:empty('No domains yet.','Create a website in an isolated customer account before setting up mail.','','mail')}</section>`+
    `<section class="panel"><div class="panel-head"><h2>Mailboxes</h2></div>${info.domains.some(d=>d.mailboxes.length)?`<div class="table-wrap"><table><thead><tr><th>Email address</th><th>Status</th><th>Quota</th><th>Actions</th></tr></thead><tbody>${info.domains.flatMap(d=>d.mailboxes.map(b=>`<tr><td><strong>${e(b.address)}</strong></td><td>${statusPill(b.effective?'active':'paused')}</td><td>${b.quota_mb} MB</td><td><div class="table-actions">${!info.recovery_required?`<button class="quiet" data-action="mail-password" data-id="${e(b.id)}">Password</button><button class="quiet" data-action="mail-quota" data-id="${e(b.id)}">Quota</button><button class="quiet" data-action="mail-active" data-id="${e(b.id)}">${b.active?'Suspend':'Enable'}</button>`:''}</div></td></tr>`)).join('')}</tbody></table></div>`:empty('No mailboxes yet.','The server owner enables a domain before its customer can create mailboxes.','','mail')}</section>`+
    `<p class="note-line">Mailbox and access changes briefly restart mail services and disconnect existing clients. Suspended mailboxes retain their messages and storage reservation. Aliases, webmail, forwarding, filtering and mail backup are still planned.</p>`;
}
function mailBox(id){return state.mail.domains.flatMap(d=>d.mailboxes).find(b=>b.id===id);}
async function mailAction(action,button){
  if(!action.startsWith('mail-'))return false;
  const id=button.dataset.id,box=id?mailBox(id):null,hidden=id?`<input type="hidden" name="id" value="${e(id)}">`:'';
  if(action==='mail-create')showModal('Create mailbox','Use a separate password for this mailbox. Keep it privately; it cannot be retrieved later.','mail-create',
    `<div class="field"><label for="mail-domain">Domain</label><select id="mail-domain" name="site_id" required>${state.mail.domains.filter(d=>d.enabled).map(d=>`<option value="${d.site_id}">${e(d.domain)}</option>`).join('')}</select></div>`+field('Address before @','local',{attrs:'minlength="1" maxlength="64" autocomplete="off" autocapitalize="none" spellcheck="false"'})+field('Mailbox password','password',{type:'password',attrs:'minlength="15" maxlength="72" autocomplete="new-password"'})+field('Quota in MB','quota_mb',{type:'number',value:64,attrs:'min="1" max="4096" step="1"'}),'Create mailbox');
  else if(action==='mail-domain'){
    const d=state.mail.domains.find(d=>d.site_id===Number(button.dataset.site));
    showModal(d.enabled?'Disable mail domain':'Enable mail domain','Review domain ownership and mail routing first. This does not change DNS. Disabling retains mail but rejects new delivery.','mail-domain',`<input type="hidden" name="site_id" value="${d.site_id}"><input type="hidden" name="enabled" value="${!d.enabled}">`+field('Type domain: '+e(d.domain),'confirm_domain'),d.enabled?'Disable mail':'Enable mail');
  }else if(action==='mail-password')showModal('Change mailbox password',e(box.address)+'. Existing email clients will be disconnected.','mail-password',hidden+field('New mailbox password','password',{type:'password',attrs:'minlength="15" maxlength="72" autocomplete="new-password"'}),'Change password');
  else if(action==='mail-quota')showModal('Change mailbox quota',e(box.address)+'. Reducing below current usage keeps messages; new delivery waits until space is available.','mail-quota',hidden+field('Quota in MB','quota_mb',{type:'number',value:box.quota_mb,attrs:'min="1" max="4096" step="1"'}),'Save quota');
  else if(action==='mail-active')showModal(box.active?'Suspend mailbox':'Enable mailbox',e(box.address)+'. Messages are preserved.','mail-active',hidden+`<input type="hidden" name="active" value="${!box.active}"><p>${box.active?'Existing clients are disconnected and new mail is rejected.':'The account, website, package and mail domain must also allow access.'}</p>`,box.active?'Suspend mailbox':'Enable mailbox');
  else if(action==='mail-recover')showModal('Recover mail publication','After inspecting the service journal, publish the committed configuration and restart both mail services.','mail-recover',field('Type RECOVER MAIL','confirm'),'Recover services');
  return true;
}
async function mailSubmit(kind,form,data){
  if(!kind.startsWith('mail-'))return false;
  const payload={...data};
  for(const key of ['site_id','quota_mb'])if(key in payload)payload[key]=Number(payload[key]);
  for(const key of ['enabled','active'])if(key in payload)payload[key]=payload[key]==='true';
  await api('mail.'+kind.slice(5),payload);closeModal();await loadPage('mail');notify('Mail configuration saved.');
  return true;
}
