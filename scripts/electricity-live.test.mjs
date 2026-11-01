import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'node:test';
import { setImmediate } from 'node:timers/promises';
import { mountLive } from '../components/ni-electricity/live.js';

const data = name => JSON.parse(fs.readFileSync(`public/data/ni-electricity/${name}.json`));
const flush = async () => { for (let i = 0; i < 5; i++) await setImmediate(); };

test('live polling retries missing versions independently and retains valid readings', async t => {
  const nodes = new Map();
  const root = { querySelector(selector) {
    if (!nodes.has(selector)) nodes.set(selector, { dataset: {}, hidden: true });
    return nodes.get(selector);
  } };
  const page = Object.assign(new EventTarget(), { hidden: false });
  let interval, cleared = false;
  const window = Object.assign(new EventTarget(), {
    matchMedia: () => ({ matches: true }),
    setInterval(callback) { interval = callback; return 1; },
    clearInterval() { cleared = true; },
  });
  const snapshot = data('snapshot'), history = data('history');
  const version = 'c'.repeat(24);
  let snapshotMode = 'missing';
  let requests = 0;
  t.mock.method(globalThis, 'fetch', async url => {
    requests++;
    if (url.endsWith('manifest.json')) return Response.json({ schema: 1, enabled: true,
      snapshot: { version, ok: true }, history: { version, ok: true } });
    if (url.includes('snapshot.json')) {
      if (snapshotMode === 'missing') return new Response(null, { status: 503 });
      return Response.json({ ...snapshot, time: snapshotMode === 'backwards' ? '2026-01-01T00:00:00Z' : snapshot.time,
        retrievedAt: '2026-11-01T12:00:00Z' }, { headers: { 'X-Electricity-Version': version } });
    }
    return Response.json({ ...history, generatedAt: new Date(Date.parse(history.generatedAt) + 60000).toISOString() }, { headers: { 'X-Electricity-Version': version } });
  });
  const saved = { window: globalThis.window, document: globalThis.document };
  globalThis.window = window; globalThis.document = page;
  try {
    const events = new EventTarget(), updates = [];
    for (const name of ['snapshot', 'history']) events.addEventListener(`dashboard:${name}`, () => updates.push(name));
    const controller = new AbortController();
    mountLive(root, snapshot, history, events, controller.signal);
    await flush();
    assert.deepEqual(updates, ['history']);
    snapshotMode = 'backwards';
    await interval();
    assert.deepEqual(updates, ['history']);
    snapshotMode = 'valid';
    window.dispatchEvent(new Event('focus'));
    await flush();
    assert.deepEqual(updates, ['history', 'snapshot']);
    await interval();
    assert.deepEqual(updates, ['history', 'snapshot']);
    const before = requests;
    page.hidden = true;
    await interval();
    assert.equal(requests, before);
    controller.abort();
    assert.equal(cleared, true);
    assert.match(nodes.get('#refresh-health').textContent, /07:00 Europe\/London/);
  } finally {
    globalThis.window = saved.window; globalThis.document = saved.document;
  }
});

test('initial connection checks and one transient failure do not announce an outage', async t => {
  const nodes = new Map();
  const root = { querySelector(selector) {
    if (!nodes.has(selector)) nodes.set(selector, { dataset: {}, hidden: true });
    return nodes.get(selector);
  } };
  const page = Object.assign(new EventTarget(), { hidden: false });
  let interval;
  const window = Object.assign(new EventTarget(), {
    matchMedia: () => ({ matches: true }), setInterval(callback) { interval = callback; return 1; }, clearInterval() {},
  });
  const version = 'e'.repeat(24);
  let mode = 'failed';
  t.mock.method(globalThis, 'fetch', async () => mode === 'failed' ? new Response(null, { status: 503 }) : Response.json({ schema: 1, enabled: true, mode: 'preview', snapshot: { version }, history: { version } }));
  const saved = { window: globalThis.window, document: globalThis.document };
  globalThis.window = window; globalThis.document = page;
  const controller = new AbortController();
  try {
    const snapshot = { ...data('snapshot'), time: new Date().toISOString() };
    mountLive(root, snapshot, data('history'), new EventTarget(), controller.signal, { snapshot: version, history: version });
    assert.match(nodes.get('.snapshot-label').innerHTML, /Checking for updates/);
    await flush();
    assert.match(nodes.get('.snapshot-label').innerHTML, /Checking for updates/);
    await interval();
    assert.match(nodes.get('.snapshot-label').innerHTML, /Connection unavailable/);
    mode = 'healthy';
    await interval();
    assert.match(nodes.get('.snapshot-label').innerHTML, /Preview readings/);
    assert.match(nodes.get('#refresh-health').textContent, /Preview collectors run on demand/);
  } finally {
    controller.abort();
    globalThis.window = saved.window; globalThis.document = saved.document;
  }
});
