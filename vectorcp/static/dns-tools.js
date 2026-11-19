'use strict';
// Uses the shared workspace controls and escaping helpers from app.js.
function dnsPage(){
  const d=state.dns,zone=d?.zone,publicService=d?.mode==='public';
  const notice=publicService
    ? '<strong>Public authoritative DNS</strong>Zones stay in draft until ownership is checked and public hosting is activated. Changing records here affects public answers only for active zones. Registrar delegation and both UDP/TCP port 53 must be configured separately.'
    : '<strong>Private DNS preview</strong>This service listens inside the server. Editing here does not change public DNS. The server owner can install the optional public profile when nameservers and networking are ready.';
  let body='';
  if(d){
    const canEdit=d.can_edit&&d.enabled;
    body=`<div class="panel-body"><div class="heading-actions"><h2>${e(d.domain)}</h2><span class="spacer"></span><strong>${zone?(publicService?(zone.published?'Public hosting active':'Draft zone'):'Private preview'):'No zone'}</strong></div>`;
    if(!d.enabled)body+='<p class="note-line">The DNS service is not installed on this server.</p>';
    if(!d.can_edit)body+='<p class="note-line">DNS editing is not included in this customer’s hosting plan.</p>';
    if(publicService)body+=`<p>Owner-configured nameservers:</p><ul>${d.nameservers.map(n=>`<li class="mono">${e(n)}</li>`).join('')}</ul><p class="small muted">Each nameserver must answer independently. Names alone do not establish redundancy or registrar delegation.</p>`;
    if(zone){
      body+=`<div class="heading-actions">${canEdit?actionButton('new-dns','Add record'):''}${actionButton('export-dns','Export zone','secondary','download')}${canEdit?actionButton('verify-dns','Check ownership','secondary','check')+actionButton('dns-diagnostics','Diagnostics','secondary')+actionButton('dns-rebuild','Rebuild zone','secondary'):''}${canEdit&&publicService?actionButton(zone.published?'dns-deactivate':'dns-activate',zone.published?'Stop public hosting':'Activate public hosting',zone.published?'secondary':'primary'):''}</div>`;
      if(!zone.published)body+=`<p class="note-line">Before activating public hosting, add this TXT record at your current DNS provider:</p><p class="mono">_vectorcp.${e(d.domain)}</p><code class="dns-token">${e(zone.challenge)}</code><p class="small muted">Activation checks the exact value through two public resolvers. Keep using your current DNS provider until you are ready to delegate.</p>`;
      body+=`<p class="small muted">Zone serial ${zone.serial}. ${zone.verified?'Ownership matched at the last check.':'Ownership has not matched at the last check.'}${zone.checked?' Checked '+e(date(zone.checked))+'.':''} This is not a delegation or external reachability check.</p>`;
    }else if(canEdit)body+=actionButton('create-dns',publicService?'Create draft zone':'Create private zone');
    body+='</div>';
    if(zone)body+=`<div class="table-wrap"><table><thead><tr><th>Name</th><th>Type</th><th>Value</th><th>TTL</th><th>Actions</th></tr></thead><tbody>${d.records.map(r=>`<tr><td>${e(r.name)}</td><td>${e(r.type)}</td><td class="dns-value">${e(r.value)}</td><td>${r.ttl}</td><td>${canEdit?`<div class="table-actions"><button class="quiet" data-action="edit-dns" data-id="${r.id}">Edit</button><button class="quiet" data-action="delete-dns" data-id="${r.id}">Delete</button></div>`:''}</td></tr>`).join('')}</tbody></table></div>`;
  }
  return heading('DNS zones','Manage records, public hosting and nameserver checks.')+`<div class="callout">${notice}</div><section class="panel"><div class="file-toolbar"><label for="site-choice">Website</label><select id="site-choice">${siteOptions()}</select></div>${d?body:empty('Choose a website.','DNS zones belong to an existing website.','','sites')}</section>`;
}
function dnsFormContext(d){
  return `<input type="hidden" name="site_id" value="${Number(d.zone.site_id)}"><input type="hidden" name="serial" value="${Number(d.zone.serial)}">`;
}
async function dnsToolAction(action,button){
  if(!['create-dns','new-dns','edit-dns','delete-dns','verify-dns','export-dns','dns-activate','dns-deactivate','dns-diagnostics','dns-rebuild'].includes(action))return false;
  button.disabled=true;
  const d=state.dns,siteId=state.siteId;
  if(!d||d.domain!==state.sites.find(s=>s.id===siteId)?.domain)throw new Error('Refresh this DNS zone before continuing.');
  if(action==='create-dns'){await api('dns.create',{site_id:siteId});await loadPage();notify('DNS zone created.');return true;}
  if(action==='export-dns'){const r=await api('dns.export',{site_id:siteId});saveDownload(new Blob([r.content],{type:'text/plain'}),r.filename);notify('Zone export downloaded.');return true;}
  if(action==='new-dns'||action==='edit-dns'){
    const r=action==='edit-dns'?d.records.find(r=>r.id===Number(button.dataset.id)):null;
    if(action==='edit-dns'&&!r)throw new Error('Refresh the record list.');
    const value=r?.type==='TXT'?JSON.parse(r.value):r?.value||'';
    showModal(r?'Edit DNS record':'Add DNS record','Use @ for the root or a relative name such as www.','dns-record',dnsFormContext(d)+`<input type="hidden" name="id" value="${r?.id||''}">`+field('Name','name',{value:r?.name||'@',attrs:'maxlength="253"'})+`<label class="field">Record type<select name="type">${['A','AAAA','CNAME','MX','TXT','NS','CAA','SRV'].map(t=>`<option ${t===r?.type?'selected':''}>${t}</option>`).join('')}</select></label>`+field('Value','value',{value,attrs:'maxlength="512"',help:'MX: priority hostname · SRV: priority weight port hostname · TXT: plain text.'})+field('TTL (seconds)','ttl',{type:'number',value:r?.ttl||3600,attrs:'min="300" max="86400"'}),'Save record');return true;
  }
  if(action==='delete-dns'){
    showModal('Delete DNS record?',d.zone.published?'This changes an active public zone. Cached records may remain until their TTL expires.':'This removes the selected record from the draft or private zone.','dns-remove-record',dnsFormContext(d)+`<input type="hidden" name="id" value="${Number(button.dataset.id)}">`,'Delete record');return true;
  }
  if(action==='dns-activate'||action==='dns-deactivate'){
    const activate=action==='dns-activate';
    showModal(activate?'Activate public DNS hosting?':'Stop public DNS hosting?',activate?'Prepare all records first. This makes the server authoritative for this zone. It does not change the registrar’s nameservers.':'Move delegation to your replacement DNS service first. This server will stop answering authoritatively for this zone. Records are retained.','dns-state',dnsFormContext(d)+`<input type="hidden" name="operation" value="${activate?'activate':'deactivate'}"><p>Nameservers: ${d.nameservers.map(e).join(', ')}.</p>`+field('Type '+e(d.domain)+' to confirm','confirm_domain',{attrs:'autocomplete="off" spellcheck="false"'}),activate?'Check and activate':'Stop public hosting');return true;
  }
  if(action==='verify-dns'){const r=await api('dns.verify',{site_id:siteId});if(state.page==='dns'&&state.siteId===siteId){await loadPage();notify(r.verified?'Ownership TXT matched through both public resolvers.':'Both resolvers have not returned the matching ownership TXT record.',!r.verified);}return true;}
  if(action==='dns-rebuild'){await api('dns.rebuild',{site_id:siteId,serial:d.zone.serial});if(state.page==='dns'&&state.siteId===siteId)await loadPage();notify('DNS zone rebuilt and checked.');return true;}
  const result=await api('dns.diagnostics',{site_id:siteId});
  if(state.page!=='dns'||state.siteId!==siteId)return true;
  showModal('DNS diagnostics',e(d.domain),'close-details',`<h3>Local authoritative service</h3>${result.local.length?`<dl class="data-secret">${result.local.map(p=>`<dt>${e(p.transport)}</dt><dd>${p.error?e(p.error):e(p.status)+' · '+(p.authoritative?'Authoritative':'Not authoritative')+' · Serial '+e(p.serial??'none')+(p.serial===result.expected_serial?' (current)':'')}</dd>`).join('')}</dl>`:'<p>No native service checks are available in this local preview.</p>'}<h3>Public recursive nameserver answers</h3>${result.resolvers.map(r=>`<p><strong>${e(r.resolver)}</strong><br>${r.error?e(r.error):e(r.nameservers.join(', ')||'No nameserver answer')+' · '+(r.matches?'Matches configured names':'Does not match configured names')}</p>`).join('')}<p class="note-line">${e(result.note)}</p>`,'Close');return true;
}
async function dnsToolSubmit(kind,form,data){
  if(!['dns-record','dns-remove-record','dns-state'].includes(kind))return false;
  const siteId=Number(data.site_id),payload={...data,site_id:siteId,serial:Number(data.serial)};
  let method;
  if(kind==='dns-record'){payload.ttl=Number(data.ttl);method=data.id?'dns.update':'dns.save';if(data.id)payload.id=Number(data.id);}
  else if(kind==='dns-remove-record'){method='dns.delete';payload.id=Number(data.id);}
  else method=data.operation==='activate'?'dns.activate':'dns.deactivate';
  await api(method,payload);closeModal();
  if(state.page==='dns'&&state.siteId===siteId)await loadPage();
  notify(kind==='dns-state'?(data.operation==='activate'?'Public DNS hosting activated. Verify all nameservers before changing delegation.':'Public DNS hosting stopped; records retained.'):'DNS records saved.');return true;
}
