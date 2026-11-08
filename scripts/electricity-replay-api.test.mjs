import {test} from 'node:test';
import assert from 'node:assert/strict';
import worker from '../workers/electricity.mjs';
const version='a'.repeat(24);

test('historical API exposes only allowlisted public manifest and pinned day files',async()=>{
  const accesses=[];
  const env={ELECTRICITY_MODE:'local',ELECTRICITY_DATA:{async get(key){accesses.push(key);if(key==='public/replay/roi/manifest')return JSON.stringify({schema:1,region:'roi'});if(key===`public/replay/roi/2026-09-09/${version}`)return JSON.stringify({schema:1,rows:[]});return null;}}};
  const fetch=(path,options)=>worker.fetch(new Request('https://example.test/api/electricity/replay/'+path,options),env);
  const manifest=await fetch('roi/manifest.json');assert.equal(manifest.status,200);assert.equal((await manifest.json()).region,'roi');
  const day=await fetch(`roi/2026-09-09.json?v=${version}`);assert.equal(day.status,200);assert.equal(day.headers.get('ETag'),`"${version}"`);assert.match(day.headers.get('Cache-Control'),/immutable/);
  const head=await fetch(`roi/2026-09-09.json?v=${version}`,{method:'HEAD'});assert.equal(head.status,200);assert.equal(await head.text(),'');
  const conditional=await fetch(`roi/2026-09-09.json?v=${version}`,{headers:{'If-None-Match':`"${version}"`}});assert.equal(conditional.status,304);
  assert.equal((await fetch('roi/2026-09-09.json')).status,400);
  assert.equal((await fetch('roi/2026-09-09.json?v=private')).status,400);
  assert.equal((await fetch('roi/private.json?v='+version)).status,404);
  assert.equal((await fetch('roi/manifest.json',{method:'POST'})).status,405);
  assert.equal((await fetch('ni/2026-09-09.json?v='+version)).status,404);
  assert.ok(accesses.every(key=>key.startsWith('public/replay/')));
});

test('historical reads share the successful edge cache and never cache missing data',async t=>{
  const old=globalThis.caches,entries=new Map();let reads=0,puts=0;
  globalThis.caches={default:{async match(request){return entries.get(request.url)?.clone();},async put(request,response){puts++;entries.set(request.url,response);}}};
  const env={ELECTRICITY_DATA:{async get(){reads++;return JSON.stringify({rows:[]});}}};
  try {
    const url=`https://example.test/api/electricity/replay/ni/2026-09-01.json?v=${version}`;
    await worker.fetch(new Request(url),env);
    const hit=await worker.fetch(new Request(url,{method:'HEAD'}),env);
    assert.equal(hit.headers.get('X-Electricity-Cache'),'HIT');assert.equal(reads,1);assert.equal(puts,1);
    env.ELECTRICITY_DATA.get=async()=>null;
    const missing=await worker.fetch(new Request(url.replace('09-01','09-02')),env);
    assert.equal(missing.status,404);assert.equal(puts,1);
    assert.match(missing.headers.get('Cache-Control'),/no-store/);
  } finally {globalThis.caches=old;}
});
