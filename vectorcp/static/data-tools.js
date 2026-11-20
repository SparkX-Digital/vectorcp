'use strict';
// Shares the existing workspace helpers; functions run after app.js initializes.
function databasePage(){
  const site=state.sites.find(s=>s.id===state.siteId),info=state.databaseInfo,users=state.databaseUsers;
  const choice=`<div class="file-toolbar"><label for="site-choice">Website</label><select id="site-choice">${siteOptions()}</select></div>`;
  if(!site?.database_name)return heading('Databases','Manage private MariaDB databases and their users.')+`<section class="panel">${choice}${empty('No database selected.','Create a database from Apps & databases for this website.','<button class="secondary" data-page="hosting">Open applications</button>','disk')}</section>`;
  if(!info)return heading('Databases','Manage private MariaDB databases and their users.')+`<section class="panel">${choice}<p class="note-line">${e(state.databaseError||'Loading database…')}</p></section>`;
  return heading('Databases','Manage tables, access and SQL files for this website.')+`<section class="panel">${choice}<div class="panel-body"><div class="heading-actions"><h2>${e(info.name)}</h2><span class="spacer"></span><button class="secondary" data-action="database-credentials">Connection details</button><button class="secondary" data-action="sql-export">Export SQL</button><button class="secondary" data-action="sql-import">Import SQL</button></div><p>${Number(info.usage.tables)} ${Number(info.usage.tables)===1?'table':'tables'} · ${bytes(info.usage.bytes)} estimated storage</p><p class="small muted">Import and export support SQL files up to 1 MB. Larger databases are included in full website backups.</p></div><div class="table-wrap"><table><thead><tr><th>Table</th><th>Engine</th><th>Estimated rows</th><th>Size</th><th></th></tr></thead><tbody>${info.tables.length?info.tables.map(t=>`<tr><td><strong>${e(t.name)}</strong><div class="small muted">${e(t.kind)}</div></td><td>${e(t.engine||'—')}</td><td>${e(t.rows??'—')}</td><td>${bytes(t.bytes)}</td><td><button class="quiet" data-action="browse-database" data-table="${e(t.name)}" data-offset="0">Browse</button></td></tr>`).join(''):'<tr><td colspan="5">No tables yet. Import an application’s SQL file to begin.</td></tr>'}</tbody></table></div>${info.more?'<p class="note-line">Showing the first 200 tables. Export SQL to inspect the complete database.</p>':''}</section><section class="panel"><div class="panel-head"><h2>Additional database users</h2><button class="secondary" data-action="new-database-user">Create user</button></div><p class="note-line">The primary application user, ${e(users?.primary)}, is managed separately. Additional passwords are shown once. Changes disconnect that user’s active database sessions.</p>${users?.users.length?`<div class="table-wrap"><table><thead><tr><th>User</th><th>Permissions</th><th></th></tr></thead><tbody>${users.users.map(u=>`<tr><td><strong>${e(u.label)}</strong><div class="small mono">${e(u.username)}</div></td><td>${e(u.privileges.join(', ')||'No database permissions')}</td><td><div class="table-actions"><button class="quiet" data-action="edit-database-user" data-user="${e(u.username)}">Permissions</button><button class="quiet" data-action="rotate-database-user" data-user="${e(u.username)}">New password</button><button class="quiet" data-action="delete-database-user" data-user="${e(u.username)}">Remove</button></div></td></tr>`).join('')}</tbody></table></div>`:empty('Create access for a tool or teammate.','Choose only the permissions that user needs.','','lock')}</section>`;
}
function backupSchedulePanel(){
  const days=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];
  return `<section class="panel"><div class="panel-head"><h2>Automatic backups</h2><button class="secondary" data-action="new-backup-schedule">Add schedule</button></div><p class="note-line">Times use UTC. Keep 1–4 scheduled copies per website within the shared customer limit of 5 copies and 512 MB. Manual copies are preserved. A new backup must succeed before older scheduled copies are removed.</p>${state.schedules?.length?`<div class="table-wrap"><table><thead><tr><th>Website</th><th>Schedule</th><th>Latest run</th><th></th></tr></thead><tbody>${state.schedules.map(s=>`<tr><td><strong>${e(s.domain)}</strong><div class="small muted">${bytes(s.stored_bytes)} · ${s.stored_copies} customer copies</div></td><td>${s.enabled?e(s.frequency==='monthly'?'Monthly, day '+s.monthday:s.frequency==='weekly'?days[s.weekday]:'Daily')+' at '+String(s.hour).padStart(2,'0')+':00 UTC':'Paused'}<div class="small muted">Keep ${s.keep} · Next: ${s.enabled?e(date(s.next_run)):'—'}</div></td><td>${e(s.last_status)}${s.last_run?`<div class="small muted">${e(date(s.last_run))}</div>`:''}${s.last_error?`<div class="small">${e(s.last_error)}</div>`:''}</td><td><div class="table-actions"><button class="quiet" data-action="edit-backup-schedule" data-site="${s.site_id}">Edit</button><button class="quiet" data-action="run-backup-schedule" data-site="${s.site_id}">Run now</button><button class="quiet" data-action="delete-backup-schedule" data-site="${s.site_id}">Remove</button></div></td></tr>`).join('')}</tbody></table></div>`:empty('Back up on a regular schedule.','Choose an isolated website and a daily, weekly or monthly time.','','clock')}</section>`;
}
function databaseGrantFields(selected=[]){
  return '<fieldset class="data-permissions"><legend>Database permissions</legend>'+state.databaseInfo.privileges.map(p=>`<label><input type="checkbox" name="privileges" value="${e(p)}" ${selected.includes(p)?'checked':''}>${e(p)}</label>`).join('')+'</fieldset>';
}
function offsitePanel(){
  return `<section class="panel"><div class="panel-head"><h2>Verified offsite copies</h2><span class="badge-counter">${state.offsiteCopies?.length||0} saved</span></div><p class="note-line">SFTP destinations are configured by the server owner. Every saved copy is downloaded again and checked against its SHA-256 hash. Fetch a copy to local storage before restoring it. Remote copies are retained until the owner removes them at the destination.</p>${state.destinations?.length?`<p class="note-line">Available destinations: ${state.destinations.map(d=>e(d.label)).join(', ')}.</p>`:'<p class="note-line">No offsite destination is configured on this server.</p>'}${state.offsiteCopies?.length?`<div class="table-wrap"><table><thead><tr><th>Website</th><th>Destination</th><th>Verified</th><th>Size</th><th></th></tr></thead><tbody>${state.offsiteCopies.map(c=>`<tr><td><strong>${e(c.domain)}</strong><div class="small mono">${e(c.sha256.slice(0,16))}…</div></td><td>${e(state.destinations?.find(d=>d.id===c.destination)?.label||c.destination)}</td><td>${e(date(c.created))}</td><td>${bytes(c.bytes)}</td><td><button class="quiet" data-action="fetch-offsite" data-id="${e(c.id)}">Fetch to server</button></td></tr>`).join('')}</tbody></table></div>`:''}<div class="panel-body heading-actions">${state.offsiteOffset?'<button class="secondary" data-action="offsite-previous">Newer copies</button>':''}${state.offsiteMore?'<button class="secondary" data-action="offsite-next">Older copies</button>':''}</div></section>`;
}
function destinationOptions(selected=''){
  return `<option value="">Local storage only</option>`+(state.destinations||[]).map(d=>`<option value="${e(d.id)}" ${d.id===selected?'selected':''}>${e(d.label)} · SFTP</option>`).join('');
}
function databaseSecret(result){
  showModal('Save these connection details','This password is shown once. Store it privately before closing.','close-details',`<dl class="data-secret"><dt>Database</dt><dd>${e(result.name)}</dd><dt>Username</dt><dd>${e(result.username)}</dd><dt>Password</dt><dd class="mono">${e(result.password)}</dd><dt>Socket</dt><dd class="mono">${e(result.socket)}</dd></dl>`,'I have saved it');
}
async function dataToolAction(action,button){
  if(action==='offsite-next'||action==='offsite-previous'){state.offsiteOffset=Math.max(0,(state.offsiteOffset||0)+(action==='offsite-next'?100:-100));await loadPage('backups');return true;}
  if(action==='send-offsite'){
    if(!state.destinations?.length)throw new Error('The server owner must configure an SFTP destination first.');
    showModal('Send this backup offsite','A successful transfer includes a downloaded copy and SHA-256 verification. Your local backup is retained.','send-offsite',`<input type="hidden" name="id" value="${e(button.dataset.id)}"><label class="field">Destination<select name="destination" required>${state.destinations.map(d=>`<option value="${e(d.id)}">${e(d.label)}</option>`).join('')}</select></label>`,'Send and verify');return true;
  }
  if(action==='fetch-offsite'){
    showModal('Fetch a verified offsite copy?','This downloads and verifies the saved archive into local backup storage. Your website is restored only when you choose Restore afterwards.','fetch-offsite',`<input type="hidden" name="id" value="${e(button.dataset.id)}">`,'Fetch copy');return true;
  }
  if(action==='browse-database'){
    const result=await api('databases.browse',{site_id:state.siteId,table:button.dataset.table,offset:Number(button.dataset.offset)});
    showModal(e(button.dataset.table),'Read-only preview: 25 rows per page, up to 512 bytes per cell. Row order can change while the application writes data.','close-details',`<div class="table-wrap database-preview"><table><thead><tr>${result.columns.map(c=>`<th>${e(c.name)}<div class="small muted">${e(c.type)}</div></th>`).join('')}</tr></thead><tbody>${result.rows.map(r=>`<tr>${r.map(v=>`<td>${v===null?'<em>NULL</em>':e(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div><div class="heading-actions">${result.offset?`<button type="button" class="secondary" data-action="browse-database" data-table="${e(button.dataset.table)}" data-offset="${Math.max(0,result.offset-25)}">Previous rows</button>`:''}${result.more&&result.offset<10000?`<button type="button" class="secondary" data-action="browse-database" data-table="${e(button.dataset.table)}" data-offset="${result.offset+25}">Next rows</button>`:''}</div>`,'Close');return true;
  }
  if(action==='new-database-user'||action==='edit-database-user'){
    const user=state.databaseUsers?.users.find(u=>u.username===button.dataset.user);
    showModal(user?'Edit database permissions':'Create database user','Access applies only to this website’s database. Up to eight additional users are supported.','database-user',`<input type="hidden" name="username" value="${e(user?.username||'')}">`+(user?`<p class="mono">${e(user.username)}</p>`:field('User label','label',{attrs:'maxlength="80"',help:'For example, Reporting tool. A unique login name and password will be generated.'}))+databaseGrantFields(user?.privileges||['SELECT']),'Save user');return true;
  }
  if(action==='rotate-database-user'||action==='delete-database-user'){
    const username=button.dataset.user;
    showModal(action==='rotate-database-user'?'Generate a new database password?':'Remove database user?',action==='rotate-database-user'?'Applications using this user must be updated with its new password.':'This permanently removes this additional user’s access.','database-user-change',`<input type="hidden" name="username" value="${e(username)}"><input type="hidden" name="operation" value="${action==='rotate-database-user'?'rotate':'delete'}">${action==='delete-database-user'?field('Type '+e(username)+' to confirm','confirm'):''}`,'Confirm');return true;
  }
  if(action==='sql-export'){
    const result=await api('databases.export',{site_id:state.siteId}),payload=Uint8Array.from(atob(result.base64),c=>c.charCodeAt(0));
    if(await sha256(payload)!==result.sha256)throw new Error('SQL download integrity check failed.');
    saveDownload(new Blob([payload],{type:'application/sql'}),result.filename);notify('SQL export verified and downloaded.');return true;
  }
  if(action==='sql-import'){
    showModal('Import SQL into this database','SQL can replace existing tables and data. PHP pauses during import. If import fails, VectorCP restores its database snapshot. Keep a full backup before importing.','sql-import',`<label class="field">SQL file<input type="file" name="sql_file" accept=".sql" required><small>Maximum 1 MB. Use SQL intended for this database. Server, user and other database commands are denied.</small></label>`+field('Type '+e(state.databaseInfo.name)+' to confirm','confirm'),'Import SQL');return true;
  }
  if(action==='new-backup-schedule'||action==='edit-backup-schedule'){
    if(!state.sites.length)throw new Error('Create an isolated website first.');
    const s=state.schedules?.find(p=>p.site_id===Number(button.dataset.site));
    showModal(s?'Edit backup schedule':'Schedule automatic backups','Choose a UTC time. Existing saved copies remain when a schedule is paused or removed.','backup-schedule',`<label class="field">Website<select name="site_id">${state.sites.map(site=>`<option value="${site.id}" ${(s?.site_id||state.siteId)===site.id?'selected':''}>${e(site.domain)}</option>`).join('')}</select></label><label class="field">Frequency<select name="frequency"><option value="daily" ${s?.frequency==='daily'?'selected':''}>Daily</option><option value="weekly" ${s?.frequency==='weekly'?'selected':''}>Weekly</option><option value="monthly" ${s?.frequency==='monthly'?'selected':''}>Monthly</option></select></label><div class="field-grid"><label class="field">UTC hour<select name="hour">${Array.from({length:24},(_,h)=>`<option value="${h}" ${h===(s?.hour??3)?'selected':''}>${String(h).padStart(2,'0')}:00 UTC</option>`).join('')}</select></label><label class="field" data-schedule-frequency="weekly" ${(s?.frequency||'daily')!=='weekly'?'hidden':''}>Weekly day<select name="weekday">${['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'].map((d,i)=>`<option value="${i}" ${i===(s?.weekday??0)?'selected':''}>${d}</option>`).join('')}</select></label><label class="field" data-schedule-frequency="monthly" ${s?.frequency!=='monthly'?'hidden':''}>Monthly day<input type="number" name="monthday" value="${s?.monthday??1}" min="1" max="31"><small>For a missing day, use the month’s last day.</small></label></div>`+`<label class="field">Offsite destination<select name="destination">${destinationOptions(s?.destination)}</select></label>`+field('Scheduled copies to retain','keep',{type:'number',value:s?.keep??2,attrs:'min="1" max="4"'})+`<label class="field">State<select name="enabled"><option value="true" ${s?.enabled!==0?'selected':''}>Enabled</option><option value="false" ${s?.enabled===0?'selected':''}>Paused</option></select></label>`,'Save schedule');return true;
  }
  if(action==='run-backup-schedule'){
    await api('backups.schedule.run',{site_id:Number(button.dataset.site)});await loadPage('backups');notify('Scheduled backup job started.');return true;
  }
  if(action==='delete-backup-schedule'){
    showModal('Remove this schedule?','Saved copies remain available. Future automatic backups for this website will stop.','delete-backup-schedule',`<input type="hidden" name="site_id" value="${Number(button.dataset.site)}">`,'Remove schedule');return true;
  }
  return false;
}
async function dataToolSubmit(kind,form,data){
  if(kind==='send-offsite'||kind==='fetch-offsite'){
    await api(kind==='send-offsite'?'backups.offsite.send':'backups.offsite.fetch',data);closeModal();await loadPage('backups');notify('Offsite job started. Check Background jobs for its result.');return true;
  }
  if(kind==='database-user'){
    const result=await api(data.username?'databases.users.grants':'databases.users.create',{...data,site_id:state.siteId,privileges:new FormData(form).getAll('privileges')});
    closeModal();await loadPage('databases');if(result.password)databaseSecret(result);else notify('Database permissions saved.');return true;
  }
  if(kind==='database-user-change'){
    const result=await api('databases.users.'+data.operation,{...data,site_id:state.siteId});closeModal();await loadPage('databases');if(result.password)databaseSecret(result);else notify('Database user removed.');return true;
  }
  if(kind==='sql-import'){
    const file=form.elements.sql_file.files[0];if(!file||!file.size||file.size>1048576)throw new Error('Choose a nonempty SQL file up to 1 MB.');
    await api('databases.import',{site_id:state.siteId,confirm:data.confirm,base64:base64Bytes(new Uint8Array(await file.arrayBuffer()))});closeModal();await loadPage('hosting');notify('SQL import job started. Check its result before continuing.');return true;
  }
  if(kind==='backup-schedule'){
    await api('backups.schedule.save',{site_id:Number(data.site_id),frequency:data.frequency,hour:Number(data.hour),weekday:Number(data.weekday),monthday:Number(data.monthday),keep:Number(data.keep),enabled:data.enabled==='true',destination:data.destination});closeModal();await loadPage('backups');notify('Automatic backup schedule saved.');return true;
  }
  if(kind==='delete-backup-schedule'){
    await api('backups.schedule.delete',{site_id:Number(data.site_id)});closeModal();await loadPage('backups');notify('Schedule removed. Saved copies remain available.');return true;
  }
  return false;
}

// Frequency-specific inputs keep the schedule dialog focused.
document.addEventListener('change',event=>{
  if(event.target.matches('select[name="frequency"]')){
    for(const field of event.target.form.querySelectorAll('[data-schedule-frequency]')){
      field.hidden=field.dataset.scheduleFrequency!==event.target.value;
    }
  }
});
