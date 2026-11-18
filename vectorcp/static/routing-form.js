'use strict';
var VectorCPRoutingForm = (() => {
  function rule(index, value, escape) {
    const select=(key,label,choices)=>`<label class="field">${label}<select data-key="${key}">${choices.map(([v,t])=>`<option value="${v}" ${String(value[key])===String(v)?'selected':''}>${t}</option>`).join('')}</select></label>`;
    const input=(key,label,type='text',maximum=256)=>`<label class="field">${label}<input data-key="${key}" type="${type}" value="${escape(value[key])}" maxlength="${maximum}" required></label>`;
    return `<fieldset class="routing-rule" data-routing-rule><legend>Redirect ${index+1}</legend><div class="field-grid">${input('path','Website path')}${select('match','Match',[['exact','Exact path'],['prefix','Folder prefix · ends with /']])}</div>${input('target','Destination URL','url',2048)}${select('code','Redirect status',[[301,'301 · Permanent'],[302,'302 · Temporary'],[307,'307 · Temporary, preserve method'],[308,'308 · Permanent, preserve method']])}<div class="routing-options"><label><input data-key="keep_query" type="checkbox" ${value.keep_query?'checked':''}> Keep query parameters</label><label><input data-key="append_path" type="checkbox" ${value.append_path?'checked':''}> Keep the remaining folder path</label></div><button type="button" class="quiet" data-action="remove-routing-rule">Remove redirect</button></fieldset>`;
  }
  function body(config, escape) {
    return `<input type="hidden" name="site_id" value="${config.site_id}"><input type="hidden" name="revision" value="${config.revision}"><fieldset class="routing-settings" ${config.editable?'':'disabled'}><legend class="sr-only">Website routing settings</legend><label class="routing-toggle"><input name="force_https" type="checkbox" ${config.force_https?'checked':''}> Redirect HTTP visitors to HTTPS</label><p class="note-line">${config.tls?'Your certificate stays installed when this is switched off. Applications may still redirect visitors themselves.':'This preference takes effect after a trusted HTTPS certificate is installed.'}</p><h3>Redirects</h3><p class="note-line">Up to 20 rules. Exact paths take priority, then the longest matching folder prefix. Folder destinations must end with / when keeping the remaining path.</p><div id="routing-rules">${config.redirects.map((r,i)=>rule(i,r,escape)).join('')}</div><button type="button" class="secondary" data-action="add-routing-rule">Add redirect</button><details class="routing-errors"><summary>Custom error pages</summary><p class="note-line">Create a nonempty HTML file up to 256 KB in this website’s file manager first. Enter its path relative to /public, such as errors/404.html. Leave a field empty to use the server default. These pages are served as static HTML.</p><div class="field-grid">${config.error_codes.map(code=>`<label class="field">HTTP ${code}<input data-error-code="${code}" value="${escape(config.error_pages[String(code)]||'')}" maxlength="256" placeholder="errors/${code}.html"></label>`).join('')}</div></details></fieldset>${config.editable?'':'<p class="note-line">Activate this website before changing its routing.</p>'}`;
  }
  function read(form) {
    const redirects=[...form.querySelectorAll('[data-routing-rule]')].map(row=>{
      const values={};for(const input of row.querySelectorAll('[data-key]'))values[input.dataset.key]=input.type==='checkbox'?input.checked:input.value;
      values.code=Number(values.code);return values;
    });
    const error_pages={};for(const input of form.querySelectorAll('[data-error-code]'))if(input.value.trim())error_pages[input.dataset.errorCode]=input.value.trim();
    return {site_id:Number(form.elements.site_id.value),revision:Number(form.elements.revision.value),
      force_https:form.elements.force_https.checked,redirects,error_pages};
  }
  return {rule,body,read};
})();
if(typeof module==='object'&&module.exports)module.exports=VectorCPRoutingForm;
