'use strict';

// Use the individually authorized operation for each website. Never retry a
// mutation after a lost response: it may already have changed the server.
async function runWebsiteBatch(sites,active,apply,report=()=>{}){
  if(!Array.isArray(sites)||sites.length<1||sites.length>20||typeof active!=='boolean'||
     sites.some(s=>!s||!Number.isInteger(s.id)||s.id<1||s.id>2147483647||typeof s.domain!=='string')||
     new Set(sites.map(s=>s.id)).size!==sites.length)throw new Error('Choose between 1 and 20 different websites.');
  const results=[];let stopped=false;
  for(const site of sites){
    const result={site_id:site.id,domain:site.domain,state:'skipped',message:'Not attempted because the batch stopped.'};
    if(!stopped){
      report(site,results.length,sites.length);
      try{
        await apply({site_id:site.id,active});
        result.state='completed';result.message=active?'Activated':'Suspended';
      }catch(error){
        const status=error?.status;
        if(Number.isInteger(status)&&status>=400&&status<500){
          result.state='refused';result.message=error.message||'The server refused this change.';
          if(status===401)stopped=true;
        }else{
          result.state='unconfirmed';result.message='Result unconfirmed. Refresh this website’s status before retrying.';stopped=true;
        }
      }
    }
    results.push(result);
  }
  return results;
}

if(typeof module!=='undefined')module.exports={runWebsiteBatch};
