'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const {runWebsiteBatch}=require('../vectorcp/static/site-batch.js');
const sites=[{id:7,domain:'one.example'},{id:9,domain:'two.example'},{id:11,domain:'three.example'}];

test('applies one authorized request at a time, in selection order',async()=>{
  const calls=[],progress=[];let inFlight=false;
  const results=await runWebsiteBatch(sites,false,async data=>{
    assert.equal(inFlight,false);inFlight=true;await Promise.resolve();calls.push(data);inFlight=false;
  },(site,done,total)=>progress.push([site.id,done,total]));
  assert.deepEqual(calls,sites.map(s=>({site_id:s.id,active:false})));
  assert.deepEqual(progress,[[7,0,3],[9,1,3],[11,2,3]]);
  assert.deepEqual(results.map(r=>r.state),['completed','completed','completed']);
  assert.ok(results.every(r=>r.message==='Suspended'));
});
test('activation sends true and reports activation',async()=>{
  const r=await runWebsiteBatch([sites[0]],true,async data=>assert.equal(data.active,true));
  assert.equal(r[0].message,'Activated');
});
for(const status of [403,404,409])test('reports a '+status+' refusal and continues other websites',async()=>{
  const calls=[];const r=await runWebsiteBatch(sites,true,async data=>{
    calls.push(data.site_id);if(data.site_id===9)throw Object.assign(new Error('Owner hold or unavailable website'),{status});
  });
  assert.deepEqual(calls,[7,9,11]);assert.deepEqual(r.map(x=>x.state),['completed','refused','completed']);
  assert.equal(r[1].message,'Owner hold or unavailable website');
});
test('session expiry stops remaining changes without retrying',async()=>{
  const calls=[];const r=await runWebsiteBatch(sites,false,async data=>{
    calls.push(data.site_id);throw Object.assign(new Error('Sign in again.'),{status:401});
  });
  assert.deepEqual(calls,[7]);assert.deepEqual(r.map(x=>x.state),['refused','skipped','skipped']);
});
for(const status of [undefined,500,503])test('stops on an uncertain response '+status,async()=>{
  const calls=[];const r=await runWebsiteBatch(sites,false,async data=>{
    calls.push(data.site_id);if(data.site_id===9)throw Object.assign(new Error('Lost or failed response'),{status});
  });
  assert.deepEqual(calls,[7,9]);assert.deepEqual(r.map(x=>x.state),['completed','unconfirmed','skipped']);
  assert.match(r[1].message,/before retrying/);
});
test('rejects invalid selections before sending a mutation',async()=>{
  let calls=0;
  for(const selection of [null,[],[sites[0],sites[0]],[{id:true,domain:'x'}],[{id:1,domain:1}],Array.from({length:21},(_,i)=>({id:i+1,domain:'x'}))]){
    await assert.rejects(runWebsiteBatch(selection,false,async()=>calls++));
  }
  await assert.rejects(runWebsiteBatch(sites,'false',async()=>calls++));assert.equal(calls,0);
});
