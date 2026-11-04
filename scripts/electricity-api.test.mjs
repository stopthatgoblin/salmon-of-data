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
  assert.ok(kv.reads.every(key => key.startsWith('public/')));
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
  assert.ok(reads.every(key => key.startsWith('public/roi/')));
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
