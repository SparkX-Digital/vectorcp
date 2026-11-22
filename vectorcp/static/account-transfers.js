'use strict';

function transferCustomers(emptyOnly=false){
  return state.accounts.filter(a=>a.role==='customer'&&!a.is_reseller&&a.hosting_slot&&
    (!emptyOnly||!state.sites.some(s=>s.user_id===a.id)));
}
function transferCustomerField(emptyOnly=false){
  const customers=transferCustomers(emptyOnly);
  return `<div class="field"><label for="transfer-customer">${emptyOnly?'Empty destination customer':'Source customer'}</label><select id="transfer-customer" name="user_id" required><option value="" disabled selected>Choose an isolated customer</option>${customers.map(a=>`<option value="${a.id}">${e(a.username)} · ${e(a.name)}</option>`).join('')}</select><small>${emptyOnly?'Create an account and enable its isolated hosting first. Existing websites cannot be merged or overwritten.':'The account’s PHP service pauses briefly while its files and database are copied.'}</small></div>`;
}
function accountTransferPanel(){
  const rows=state.accountTransfers||[],busy=['queued','checking','exporting','importing','rolling_back'];
  return heading('Account transfers','Move websites into an empty, isolated customer account.',
    actionButton('account-transfer-upload','Upload archive','primary','up'))+
    `<div class="callout"><strong>Review before activation.</strong>Portable VectorCP account v1 includes website files, the primary database, routing, DNS recovery copies and paused backup schedules. Imported websites stay suspended. Mail, additional SQL users, access credentials and certificates require separate setup.</div>
    <section class="panel"><div class="panel-head"><h2>Private transfer archives</h2><button class="secondary" data-action="account-transfer-export">Export customer</button></div>
    ${rows.length?`<div class="table-wrap"><table><thead><tr><th>Transfer</th><th>Status</th><th>Size</th><th>Updated</th><th>Actions</th></tr></thead><tbody>${rows.map(r=>`<tr><td><strong>${r.direction==='export'?'Export':'Import'}</strong><div class="small mono">${e(r.id)}</div></td><td><span class="pill ${r.status==='complete'?'':'gray'}">${e(r.status.replaceAll('_',' '))}</span><p class="small">${e(r.message||'Ready for the next step.')}</p></td><td class="account-transfer-size">${bytes(r.direction==='import'&&r.status==='uploading'?r.received:r.bytes)}</td><td>${e(date(r.updated))}</td><td><div class="table-actions"><button class="quiet" data-action="account-transfer-details" data-id="${e(r.id)}">Review</button>${r.direction==='export'&&r.status==='complete'?`<button class="quiet" data-action="account-transfer-download" data-id="${e(r.id)}">Download</button>`:''}${r.direction==='import'&&['uploaded','ready','blocked','failed','rolled_back'].includes(r.status)?`<button class="quiet" data-action="account-transfer-inspect" data-id="${e(r.id)}">Inspect</button>`:''}${r.status==='uploading'?`<button class="quiet" data-action="account-transfer-resume" data-id="${e(r.id)}">Resume upload</button>`:''}${r.status==='ready'?`<button class="quiet" data-action="account-transfer-import" data-id="${e(r.id)}">Import</button>`:''}${r.status==='needs_inspection'&&state.overview.user.role==='admin'?`<button class="quiet" data-action="account-transfer-rollback" data-id="${e(r.id)}">Recover</button>`:''}${!busy.includes(r.status)&&r.status!=='needs_inspection'?`<button class="quiet" data-action="account-transfer-delete" data-id="${e(r.id)}">Remove archive</button>`:''}</div></td></tr>`).join('')}</tbody></table></div>`:empty('No account transfers yet.','Export a customer on the source server, then upload and inspect that archive on the destination.','','backups')}</section>
    <p class="note-line">Keep archives private: they contain website secrets and SQL data. Maximum 350 MB per archive; retain at most two per operator. Refresh this page to follow background jobs.</p>`;
}
function transferReport(row){
  const report=row.report||{};
  return `<p><strong>${e(row.status.replaceAll('_',' '))}</strong> · ${e(row.message)}</p>${report.source?`<p>Source: ${e(report.source.username)} · Destination: ${e(report.target_username)}</p>`:''}${report.sites?.length?`<ul>${report.sites.map(s=>`<li>${e(s.domain)} · ${e(s.runtime)}${s.files!=null?` · ${s.files} file${s.files===1?'':'s'} · ${bytes(s.file_bytes)} files / ${bytes(s.sql_bytes)} SQL`:''}</li>`).join('')}</ul>`:''}${report.conflicts?.length?`<div role="alert"><strong>Resolve before importing</strong><ul>${report.conflicts.map(c=>`<li>${e(c)}</li>`).join('')}</ul></div>`:''}${report.warnings?.length?`<ul>${report.warnings.map(w=>`<li>${e(w)}</li>`).join('')}</ul>`:''}${row.sha256?`<div class="field"><label>Archive SHA-256</label><textarea readonly rows="3" aria-label="Archive SHA-256">${e(row.sha256)}</textarea></div>`:''}`;
}
async function accountTransferAction(action,button){
  if(!action.startsWith('account-transfer-'))return false;
  if(!managesCustomers())throw new Error('Account transfers require an owner or authorized reseller.');
  const id=button.dataset.id,hidden=id?`<input type="hidden" name="id" value="${e(id)}">`:'';
  if(action==='account-transfer-export')showModal('Export customer','Download the archive privately, then remove it when the move is verified.','account-transfer-export',transferCustomerField()+field('Type the source username','confirm_username'),'Create export');
  else if(['account-transfer-upload','account-transfer-resume'].includes(action))showModal(id?'Resume archive upload':'Upload account archive','Choose a portable VectorCP account v1 .tar.gz file up to 350 MB. Files are verified before import.','account-transfer-upload',hidden+`<div class="field"><label for="transfer-archive">Private account archive</label><input id="transfer-archive" name="archive" type="file" accept=".tar.gz,application/gzip" required></div><p id="transfer-progress" role="status">Keep this dialog open during upload. If interrupted, choose Resume upload and select the same file.</p>`,'Upload and verify');
  else if(action==='account-transfer-inspect')showModal('Inspect account archive','This checks conflicts and space without importing website data.','account-transfer-inspect',hidden+transferCustomerField(true),'Inspect archive');
  else if(['account-transfer-import','account-transfer-details','account-transfer-rollback'].includes(action)){
    const row=await api('transfers.get',{id});
    if(action==='account-transfer-details')showModal('Transfer details','Review every conflict and the scope of this transfer.','close-details',transferReport(row),'Close');
    else if(action==='account-transfer-import')showModal('Import into empty customer','Fresh database credentials are generated. Websites remain suspended until reviewed.','account-transfer-import',hidden+`<input type="hidden" name="user_id" value="${row.user_id}"><input type="hidden" name="sha256" value="${e(row.sha256)}">`+transferReport(row)+field('Type destination username: '+e(row.report.target_username),'confirm_username'),'Import suspended websites');
    else showModal('Recover interrupted transfer','After inspecting the server, remove only recorded new allocations and restore a recorded PHP maintenance stop. Existing accounts and unrelated data are preserved.','account-transfer-rollback',hidden+transferReport(row)+field('Type the affected customer username','confirm_username'),'Recover transfer');
  }else if(action==='account-transfer-delete')showModal('Remove private archive','This removes only the transfer archive and its record. Existing websites stay on the server. Download a private copy first if needed.','account-transfer-delete',hidden+field('Type REMOVE','confirm'),'Remove archive');
  else if(action==='account-transfer-download'){
    button.disabled=true;
    try{const info=await api('transfers.describe',{id});const blob=await downloadBackup(id,'transfers');saveDownload(blob,info.filename);notify('Account archive downloaded and checksum verified.');}finally{button.disabled=false;}
  }
  return true;
}
async function accountTransferSubmit(kind,form,data){
  if(!kind.startsWith('account-transfer-'))return false;
  const operation=kind.slice('account-transfer-'.length);
  if(operation==='upload'){
    const file=form.elements.archive.files[0],progress=form.querySelector('#transfer-progress');
    if(!file||!file.size||file.size>350*1024**2)throw new Error('Choose a nonempty account archive up to 350 MB.');
    if(!crypto.subtle)throw new Error('Archive verification requires HTTPS or localhost.');
    transferBusy=true;form.querySelectorAll('input,button').forEach(c=>c.disabled=true);
    try{
      progress.textContent='Checking archive SHA-256…';
      const hash=await sha256(await file.arrayBuffer());
      let upload;
      if(data.id){
        const row=await api('transfers.get',{id:data.id});
        if(row.sha256!==hash||row.bytes!==file.size)throw new Error('Select the same archive to resume this upload.');
        upload=await api('transfers.upload.status',{id:data.id});
      }else upload=await api('transfers.upload.start',{bytes:file.size,sha256:hash});
      form.dataset.transferId=upload.id;
      let offset=upload.received;
      while(offset<file.size){
        const block=new Uint8Array(await file.slice(offset,offset+upload.chunk_bytes).arrayBuffer());
        let binary='';for(let i=0;i<block.length;i+=8192)binary+=String.fromCharCode(...block.subarray(i,i+8192));
        const payload={id:upload.id,offset,base64:btoa(binary)};let result;
        for(let retry=0;retry<3;retry++){try{result=await api('transfers.upload.chunk',payload);break;}catch(err){if(retry===2||[401,403,404,409].includes(err.status))throw err;}}
        if(result.received<=offset||result.received>file.size)throw new Error('The upload stopped before it finished. Resume with the same file.');
        offset=result.received;progress.textContent=`Uploading and verifying… ${Math.round(offset/file.size*100)}%`;
      }
      await api('transfers.upload.finish',{id:upload.id});closeModal();await loadPage('transfers');notify('Archive verified. Inspect it for an empty destination customer next.');
    }catch(err){if(form.dataset.transferId)err.message+=' Use Resume upload from Account transfers with the same archive.';throw err;}
    finally{transferBusy=false;form.querySelectorAll('input,button').forEach(c=>c.disabled=false);}
  }else{
    if(operation==='delete'&&data.confirm!=='REMOVE')throw new Error('Type REMOVE to confirm.');
    await api('transfers.'+operation,{...data,...(data.user_id?{user_id:Number(data.user_id)}:{})});
    closeModal();await loadPage('transfers');notify(operation==='delete'?'Private archive removed.':'Transfer job queued. Refresh to follow progress.');
  }
  return true;
}
