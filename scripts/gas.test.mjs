import test from 'node:test';
import assert from 'node:assert/strict';
import gas from '../workers/gas-api.mjs';
import { gasCron,gasCatchupCron,gasDue,collectGasOnSchedule } from '../workers/gas-scheduler.mjs';
import { collectOnSchedule } from '../workers/electricity-scheduler.mjs';
import { readFileSync } from 'node:fs';
import { validSnapshot } from '../components/ireland-gas/data.ts';

test('gas client accepts unavailable demand only as a paired schema 2 value',()=>{
  const snapshot=JSON.parse(readFileSync(new URL('../public/data/ireland-gas/2026-11-08.json',import.meta.url)));
  snapshot.version='a'.repeat(24);
  assert.equal(validSnapshot(snapshot,snapshot.gasDay,snapshot.version),true);
  snapshot.regions.ni.demand=null;snapshot.regions.ni.demandShare=null;
  assert.equal(validSnapshot(snapshot,snapshot.gasDay,snapshot.version),false);
  snapshot.schema=2;
  assert.equal(validSnapshot(snapshot,snapshot.gasDay,snapshot.version),true);
  snapshot.regions.ni.demandShare=0;
  assert.equal(validSnapshot(snapshot,snapshot.gasDay,snapshot.version),false);
  snapshot.regions.ni.demandShare=null;snapshot.regions.ni.totalGas=null;
  assert.equal(validSnapshot(snapshot,snapshot.gasDay,snapshot.version),false);
});

test('partial publication keeps daytime and evening retries on the original target',async()=>{
  let state={pending:true,targetGasDay:'2026-11-16',successfulDate:'2026-11-17',
    lastSuccess:'2026-11-17T07:01:00Z',lastAttempt:'2026-11-17T07:01:00Z',lastError:null};
  assert.equal(gasDue(gasCatchupCron,Date.parse('2026-11-17T10:00:00Z'),state),true);
  assert.equal(gasDue(gasCron,Date.parse('2026-11-17T19:00:00Z'),state),true);
  let inputs;
  await collectGasOnSchedule({cron:gasCatchupCron,scheduledTime:Date.parse('2026-11-17T10:00:00Z')},
    {GITHUB_ACTIONS_TOKEN:'test-only',GAS_DATA:{get:async()=>state,put:async(_key,value)=>{state=JSON.parse(value);}}},
    async(_url,options)=>{inputs=JSON.parse(options.body).inputs;return new Response(null,{status:204});});
  assert.equal(inputs.gas_day,'2026-11-16');
  assert.equal(gasDue(gasCatchupCron,Date.parse('2026-11-17T10:10:00Z'),state),false);
  state={...state,pending:false};
  assert.equal(gasDue(gasCatchupCron,Date.parse('2026-11-17T13:00:00Z'),state),false);
  assert.equal(gasDue(gasCron,Date.parse('2026-11-17T19:00:00Z'),state),false);
});

test('gas timer starts at 19:00 Ireland time in both seasons and suppresses success',()=>{
  for(const time of ['2026-11-12T19:00:00Z','2026-07-12T18:00:00Z'])assert.equal(gasDue(gasCron,Date.parse(time),null),true);
  for(const time of ['2026-11-12T18:00:00Z','2026-07-12T22:00:00Z'])assert.equal(gasDue(gasCron,Date.parse(time),null),false);
  assert.equal(gasDue(gasCron,Date.parse('2026-11-12T19:20:00Z'),{successfulDate:'2026-11-12'}),false);
  assert.equal(gasDue(gasCron,Date.parse('2026-11-12T19:20:00Z'),{lastAttempt:'2026-11-12T19:10:00Z'}),false);
});

test('gas dispatch targets only its workflow and preserves the encrypted-token boundary',async()=>{
  let saved;
  const result=await collectGasOnSchedule({cron:gasCron,scheduledTime:Date.parse('2026-11-12T19:00:00Z')},
    {GITHUB_ACTIONS_TOKEN:'test-secret',GAS_DATA:{get:async()=>null,put:async(key,value)=>{saved={key,value};}}},async(url,options)=>{
      assert.equal(url,'https://api.github.com/repos/stopthatgoblin/salmon-of-data/actions/workflows/ireland-gas.yml/dispatches');
      assert.equal(options.redirect,'manual');
      assert.equal(JSON.parse(options.body).inputs.target,'production');
      return new Response(null,{status:204});
    });
  assert.equal(result.action,'dispatch');assert.equal(saved.key,'private/gas/status');assert.equal(saved.value.includes('test-secret'),false);
});

test('late meter data gets bounded daytime retries in GMT and BST without suppressing the next evening',async()=>{
  for(const [date,hour] of [['2026-11-14','07'],['2026-07-14','06']]){
    const previousDay=date.slice(0,8)+'12';
    let state={targetGasDay:previousDay,waitingForSource:{source:'SEMO meter data',gasDay:previousDay},lastAttempt:date.slice(0,8)+'13T22:40:00Z'};
    const controller={cron:gasCatchupCron,scheduledTime:Date.parse(`${date}T${hour}:00:00Z`)};
    assert.equal(gasDue(controller.cron,controller.scheduledTime,state),true);
    assert.equal(gasDue(controller.cron,controller.scheduledTime,null),false);
    let dispatched;
    const env={GITHUB_ACTIONS_TOKEN:'test-only',GAS_DATA:{get:async()=>state,put:async(_key,value)=>{state=JSON.parse(value);}}};
    await collectOnSchedule(controller,env,async(_url,options)=>{dispatched=JSON.parse(options.body);return new Response(null,{status:204});});
    assert.equal(dispatched.inputs.gas_day,previousDay);
    assert.equal(gasDue(gasCatchupCron,controller.scheduledTime+10*60000,state),false);
    state={...state,successfulDate:date,waitingForSource:null,lastAttempt:new Date(controller.scheduledTime).toISOString()};
    assert.equal(gasDue(gasCatchupCron,Date.parse(`${date}T${String(Number(hour)+3).padStart(2,'0')}:00:00Z`),state),false);
    // A successful catch-up for an older gas day cannot suppress yesterday's run.
    assert.equal(gasDue(gasCron,Date.parse(`${date}T${hour==='07'?'19':'18'}:00:00Z`),state),true);
  }
});

test('a transient failure after a source wait cannot disable the remaining daytime retries',async()=>{
  let state={schema:1,targetGasDay:'2026-11-14',lastAttempt:'2026-11-16T07:02:41Z',
    lastSuccess:'2026-11-12T22:51:03Z',successfulDate:'2026-11-12',waitingForSource:null,
    lastError:'Daily update failed; retaining the last accepted data.'};
  const controller={cron:gasCatchupCron,scheduledTime:Date.parse('2026-11-16T10:00:00Z')};
  assert.equal(gasDue(controller.cron,controller.scheduledTime,state),true);
  assert.equal(gasDue(gasCatchupCron,Date.parse('2026-11-16T11:00:00Z'),state),false);
  let dispatched;
  await collectOnSchedule(controller,{GITHUB_ACTIONS_TOKEN:'test-only',GAS_DATA:{
    get:async()=>state,put:async(_key,value)=>{state=JSON.parse(value);},
  }},async(_url,options)=>{dispatched=JSON.parse(options.body);return new Response(null,{status:204});});
  assert.equal(dispatched.inputs.gas_day,'2026-11-14');
  assert.equal(gasDue(gasCatchupCron,controller.scheduledTime+10*60000,state),false);
  assert.equal(gasDue(gasCatchupCron,Date.parse('2026-11-16T13:00:00Z'),state),true);
  state={...state,lastError:null,waitingForSource:null,successfulDate:'2026-11-16'};
  assert.equal(gasDue(gasCatchupCron,Date.parse('2026-11-16T16:00:00Z'),state),false);
  assert.equal(gasDue(gasCron,Date.parse('2026-11-16T19:00:00Z'),state),true);
});

test('gas failures do not prevent the shared scheduler dispatching electricity',async()=>{
  const time=Date.parse('2026-11-16T17:17:00Z');
  let dispatch;
  const result=await collectOnSchedule({cron:'2,17,32,47 * * * *',scheduledTime:time},{
    GITHUB_ACTIONS_TOKEN:'test-only',ELECTRICITY_ROI_ENABLED:'true',
    ELECTRICITY_DATA:{get:async()=>({records:[{}],lastSuccess:'2026-11-16T17:00:00Z'})},
    GAS_DATA:{get:async()=>{throw new Error('Gas state must not be read during an electricity tick');}},
  },async(url,options)=>{dispatch={url,inputs:JSON.parse(options.body).inputs};return new Response(null,{status:204});},time);
  assert.equal(result.action,'dispatch');
  assert.match(dispatch.url,/ni-electricity\.yml\/dispatches$/);
  assert.equal(dispatch.inputs.dataset,'snapshot');
});

test('gas API exposes only dated public objects and tolerates propagation misses',async()=>{
  const calls=[];const version='a'.repeat(24);
  const env={GAS_MODE:'local',GAS_DATA:{get:async(key)=>{calls.push(key);return key==='public/gas/manifest'?{schema:1,latest:'2026-11-11',days:[{date:'2026-11-11',version}]}:null;}}};
  for(const path of ['/api/gas/private/status','/api/gas/day/2026-02-31.json'])assert.equal((await gas.fetch(new Request('https://example.com'+path),env)).status,404);
  assert.equal(calls.length,0);
  const manifest=await gas.fetch(new Request('https://example.com/api/gas/manifest.json'),env);
  assert.equal(manifest.status,200);
  const missing=await gas.fetch(new Request('https://example.com/api/gas/day/2026-11-11.json?v='+version),env);
  assert.equal(missing.status,503);assert.equal(missing.headers.get('Cache-Control'),'no-store');
  assert.deepEqual(calls,['public/gas/manifest','public/gas/day/2026-11-11/'+version]);
});

test('immutable gas responses support conditional reads and HEAD without leaking a body',async()=>{
  const version='b'.repeat(24);
  const env={GAS_MODE:'local',GAS_DATA:{get:async()=>JSON.stringify({gasDay:'2026-11-11'})}};
  const url='https://example.com/api/gas/day/2026-11-11.json?v='+version;
  const head=await gas.fetch(new Request(url,{method:'HEAD'}),env);assert.equal(await head.text(),'');assert.equal(head.status,200);
  const hit=await gas.fetch(new Request(url,{headers:{'If-None-Match':`"${version}"`}}),env);assert.equal(hit.status,304);assert.equal(await hit.text(),'');
  assert.ok(head.headers.get('X-Content-Type-Options'));
});
