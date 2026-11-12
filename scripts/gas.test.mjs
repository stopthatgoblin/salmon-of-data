import test from 'node:test';
import assert from 'node:assert/strict';
import gas from '../workers/gas-api.mjs';
import { gasCron,gasDue,collectGasOnSchedule } from '../workers/gas-scheduler.mjs';

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
