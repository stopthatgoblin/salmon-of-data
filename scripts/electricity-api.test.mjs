import assert from 'node:assert/strict';
import { test } from 'node:test';
import worker from '../workers/electricity.mjs';

const current = 'a'.repeat(24), previous = 'b'.repeat(24);
function store() {
  const values = new Map([
    ['public/snapshot/current', { records: [{ version: current }, { version: previous }], ok: true }],
    ['public/history/current', { records: [{ version: previous }], ok: true }],
    [`public/snapshot/${previous}`, '{"time":"2026-11-01T12:00:00Z"}'],
    [`public/history/${previous}`, '{"days":[]}'],
  ]);
  const reads = [];
  return { reads, async get(key, options) {
    reads.push(key);
    const value = values.get(key);
    return value == null ? null : options?.type === 'json' ? value : new Blob([value]).stream();
  } };
}
const request = (path, options) => new Request('https://salmonofdata.com/api/electricity/' + path, options);

test('electricity API keeps last accepted data readable during KV propagation', async () => {
  const kv = store();
  const env = { ELECTRICITY_DATA: kv };
  const latest = await worker.fetch(request('snapshot.json'), env);
  assert.equal(latest.status, 200);
  assert.equal(latest.headers.get('X-Electricity-Version'), previous);
  assert.equal((await latest.json()).time, '2026-11-01T12:00:00Z');
  const pinned = await worker.fetch(request('snapshot.json?v=' + current), env);
  assert.equal(pinned.status, 503);
  assert.equal(pinned.headers.get('Cache-Control'), 'no-store');
  const manifest = await (await worker.fetch(request('manifest.json'), env)).json();
  assert.equal(manifest.snapshot.version, current);
  assert.equal(manifest.mode, 'live');
  const preview = await (await worker.fetch(request('manifest.json'), { ...env, ELECTRICITY_PREVIEW: 'true' })).json();
  assert.equal(preview.mode, 'preview');
});

test('electricity API exposes only public datasets and handles HEAD/conditional reads', async () => {
  const kv = store(), env = { ELECTRICITY_DATA: kv };
  assert.equal((await worker.fetch(request('../electricity/private/history/state-0'), env)).status, 404);
  assert.equal((await worker.fetch(request('snapshot.json', { method: 'POST' }), env)).status, 405);
  assert.equal((await worker.fetch(request('history.json?v=../../private'), env)).status, 400);
  const head = await worker.fetch(request('snapshot.json', { method: 'HEAD' }), env);
  assert.equal(head.status, 200);
  assert.equal(await head.text(), '');
  assert.equal((await worker.fetch(request('snapshot.json?v=' + previous, { headers: { 'If-None-Match': `"${previous}"` } }), env)).status, 304);
  assert.ok(kv.reads.every(key => key.startsWith('public/') || /^private\/(snapshot|history)\/current$/.test(key)));
});

test('ROI API isolates regional keys and serves overview without historical data', async () => {
  const reads = [];
  const env = { ELECTRICITY_MODE: 'local', ELECTRICITY_DATA: { async get(key, options) {
    reads.push(key);
    if (key === 'public/roi/snapshot/current') return { records: [{ version: current }], ok: true };
    if (key === `public/roi/snapshot/${current}`) return new Blob(['{"region":"ROI"}']).stream();
    return null;
  } } };
  const manifest = await (await worker.fetch(request('roi/manifest.json'), env)).json();
  assert.equal(manifest.mode, 'local');
  assert.equal(manifest.snapshot.version, current);
  assert.equal(manifest.history, null);
  const history = await worker.fetch(request('roi/history.json'), env);
  assert.equal(history.status, 200);
  assert.equal((await history.json()).dataBasis, 'unavailable');
  const response = await worker.fetch(request('roi/snapshot.json?v=' + current), env);
  assert.equal(response.headers.get('X-Electricity-Version'), current);
  assert.equal((await response.json()).region, 'ROI');
  for (const route of ['roi/private/snapshot/current', 'roi/roi/snapshot.json', 'roi/current', 'roi/state-0']) {
    assert.equal((await worker.fetch(request(route), env)).status, 404);
  }
  assert.ok(reads.every(key => key.startsWith('public/roi/') || /^private\/roi\/(snapshot|history)\/current$/.test(key)));
});

test('ROI API announces and serves a separately versioned historical dataset', async () => {
  const env={ELECTRICITY_DATA:{async get(key,options) {
    if(key==='public/roi/snapshot/current') return {records:[{version:current}],ok:true};
    if(key==='public/roi/history/current') return {records:[{version:previous}],ok:true};
    if(key===`public/roi/history/${previous}`) return new Blob(['{"dataBasis":"public-source-history","days":[{"date":"2026-11-03"}]}']).stream();
    return null;
  }}};
  const manifest=await(await worker.fetch(request('roi/manifest.json'),env)).json();
  assert.equal(manifest.history.version,previous);
  const response=await worker.fetch(request('roi/history.json?v='+previous),env);
  assert.equal(response.headers.get('X-Electricity-Version'),previous);
  assert.equal((await response.json()).dataBasis,'public-source-history');
});

test('API uses the accepted commit pointer and never exposes private archive metadata', async () => {
  const env={ELECTRICITY_DATA:{async get(key,options) {
    if (key.startsWith('public/')) throw new Error('A duplicate public pointer must not be needed');
    return {schema:1,ok:true,lastSuccess:'2026-11-05T07:00:00Z',secretMarker:'internal',records:[
      {version:current,key:`public/snapshot/${current}`,stateKey:'private/snapshot/state-0',stateSha256:'internal',slot:0,time:'2026-11-05T06:45:00Z'}]};
  }}};
  const response=await worker.fetch(request('manifest.json'),env);
  assert.equal(response.status,200);
  const text=await response.text();
  assert.doesNotMatch(text,/stateKey|stateSha256|slot|secretMarker|private\//);
  assert.equal(JSON.parse(text).snapshot.version,current);
});

test('edge cache shares public GET, HEAD and conditional reads without repeated KV operations', async t => {
  const saved=globalThis.caches, values=new Map(), reads=[];
  globalThis.caches={default:{
    async match(key){return values.get(key.url)?.clone();},
    async put(key,response){values.set(key.url,response.clone());}
  }};
  t.after(()=>{if(saved===undefined)delete globalThis.caches;else globalThis.caches=saved;});
  const env={ELECTRICITY_DATA:{async get(key,options){
    reads.push(key);
    if(options.type==='json')return {ok:true,records:[{version:current}]};
    return new Blob(['{"accepted":true}']).stream();
  }}};
  await worker.fetch(request('manifest.json'),env);
  await worker.fetch(request('manifest.json?ignored=tracking'),env);
  assert.equal(reads.length,2);
  const head=await worker.fetch(request('snapshot.json?v='+current,{method:'HEAD'}),env);
  assert.equal(await head.text(),'');
  const get=await worker.fetch(request('snapshot.json?v='+current),env);
  assert.equal(get.headers.get('X-Electricity-Cache'),'HIT');
  assert.deepEqual(await get.json(),{accepted:true});
  const conditional=await worker.fetch(request('snapshot.json?v='+current,{headers:{'If-None-Match':`"${current}"`}}),env);
  assert.equal(conditional.status,304);
  assert.equal(conditional.headers.get('X-Content-Type-Options'),'nosniff');
  assert.equal(reads.length,3);
  values.clear();
  await worker.fetch(request('manifest.json'),env);
  assert.equal(reads.length,5); // An expired/evicted cache re-reads current health.
  assert.equal((await worker.fetch(request('snapshot.json?v=invalid'),env)).status,400);
  assert.equal(values.size,1);
});

test('edge cache never stores unavailable data and cache failures do not break the API', async t => {
  const saved=globalThis.caches, stored=[];
  globalThis.caches={default:{async match(){throw new Error('cache unavailable');},async put(key){stored.push(key.url);throw new Error('cache full');}}};
  t.after(()=>{if(saved===undefined)delete globalThis.caches;else globalThis.caches=saved;});
  const missing={ELECTRICITY_DATA:{async get(){return null;}}};
  assert.equal((await worker.fetch(request('manifest.json'),missing)).status,503);
  assert.equal((await worker.fetch(request('roi/history.json'),missing)).status,200);
  assert.equal(stored.length,0);
  assert.equal((await worker.fetch(request('manifest.json'),{ELECTRICITY_DATA:store()})).status,200);
  assert.equal(stored.length,1);
});
