import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'node:test';
import { setImmediate } from 'node:timers/promises';
import {assetStatusMarkup,celtic} from '../components/electricity/asset-status.js';
import { reconcileSnapshot } from '../components/roi-electricity/balance.js';
import { validateUpdate, mountLive, readInitialDataset } from '../components/roi-electricity/live.js';
const snapshot = JSON.parse(fs.readFileSync('public/data/roi-electricity/snapshot.json'));
const history = JSON.parse(fs.readFileSync('public/data/roi-electricity/history.json'));

test('ROI falls back to the complete station edition while the API still has the old station set', async t => {
  const legacy = structuredClone(snapshot);
  legacy.stations = legacy.stations.filter(station => !['north-wall-teg','shannonbridge-teg','ringsend-flexgen','corduff-flexgen'].includes(station.id));
  Object.assign(legacy, reconcileSnapshot(legacy));
  const version = 'e'.repeat(24), requests = [];
  t.mock.method(globalThis, 'fetch', async url => {
    requests.push(url);
    if (url.endsWith('manifest.json')) return Response.json({schema:1,enabled:true,snapshot:{version}});
    if (url.startsWith('/api/')) return Response.json(legacy,{headers:{'X-Electricity-Version':version}});
    return Response.json(snapshot);
  });
  const result = await readInitialDataset('snapshot', new AbortController().signal);
  assert.equal(result.version, null);
  assert.equal(result.data.stations.length, 17);
  assert.ok(result.data.stations.some(station => station.id === 'aughinish'));
  assert.ok(requests.includes('/data/roi-electricity/snapshot.json'));
});

test('ROI preserves signed reconciliation, unknown output and aligned NI inputs', () => {
  validateUpdate('snapshot', snapshot, snapshot);
  const balanced = reconcileSnapshot(snapshot);
  assert.ok(Math.abs(balanced.other - snapshot.other) < .001);
  const unknown = structuredClone(snapshot), station = unknown.stations.find(station => station.output > 0);
  const output = station.output;
  station.output = null;
  assert.ok(Math.abs(reconcileSnapshot(unknown).other - balanced.other - output) < .001);
  assert.throws(() => reconcileSnapshot({ ...snapshot, ni: { ...snapshot.ni, time: '2026-11-03T00:00:00Z' } }), /common timestamp/);
  assert.throws(() => validateUpdate('snapshot', { ...snapshot, reconciliation: snapshot.reconciliation + 1 }, snapshot), /balance/);
  assert.throws(() => validateUpdate('snapshot', { ...snapshot, time: '2026-01-01T00:00:00Z' }, snapshot), /backwards/);
  if (history.days.length) {
    validateUpdate('history', history, history);
    assert.equal(history.dataBasis,'public-source-history');
  }
});

test('ROI polling updates overview without history, retries failures and cancels on unmount', async t => {
  const nodes = new Map();
  const root = { querySelector(selector) {
    if (!nodes.has(selector)) nodes.set(selector, { dataset: {}, hidden: true, addEventListener() {} });
    return nodes.get(selector);
  } };
  let interval, cleared = false, mode = 'missing';
  const window = Object.assign(new EventTarget(), {
    matchMedia: () => ({ matches: true }), setInterval(callback) { interval = callback; return 1; }, clearInterval() { cleared = true; },
  });
  const document = Object.assign(new EventTarget(), { hidden: false });
  const version = 'd'.repeat(24), updates = [];
  t.mock.method(globalThis, 'fetch', async url => {
    assert.ok(url.startsWith('/api/electricity/roi/'));
    if (url.endsWith('manifest.json')) return Response.json({ schema: 1, enabled: true, mode: 'local', snapshot: { version, ok: true }, history: null });
    assert.ok(url.includes('snapshot.json'));
    if (mode === 'missing') return new Response(null, { status: 503 });
    return Response.json({ ...snapshot, retrievedAt: new Date().toISOString() }, { headers: { 'X-Electricity-Version': version } });
  });
  const saved = { window: globalThis.window, document: globalThis.document };
  globalThis.window = window; globalThis.document = document;
  const controller = new AbortController();
  try {
    const events = new EventTarget();
    events.addEventListener('dashboard:snapshot', event => updates.push(event.detail));
    mountLive(root, snapshot, history, events, controller.signal);
    for (let i = 0; i < 5; i++) await setImmediate();
    assert.equal(updates.length, 0);
    mode = 'valid';
    await interval();
    assert.equal(updates.length, 1);
    assert.match(nodes.get('#refresh-health').textContent, /Local overview collection runs every 15 minutes/);
    await interval();
    assert.equal(updates.length, 1);
    controller.abort();
    assert.equal(cleared, true);
  } finally {
    controller.abort(); globalThis.window = saved.window; globalThis.document = saved.document;
  }
});

test('ROI overview updates cards, arrow direction and the open drawer in place', async () => {
  const { default: vm } = await import('node:vm');
  const { project, flowGeometry } = await import('../components/roi-electricity/flow-geometry.js');
  const { generationIcon, interconnectorIcon } = await import('../components/roi-electricity/generation-icons.js');
  const source = fs.readFileSync('components/roi-electricity/overview.js', 'utf8').replace(/^import .*;\n/gm, '').replace('export function', 'function');
  const nodes = new Map();
  const node = key => {
    if (!nodes.has(key)) nodes.set(key, {
      dataset: {}, hidden: false, open: false, viewBox: { baseVal: { width: 1240, height: 1180 } }, firstChild: {},
      style: { setProperty() {} }, classList: { toggle() {}, add() {}, remove() {} },
      setAttribute() {}, removeAttribute() {}, append() {}, addEventListener() {}, getScreenCTM() { return null; },
    });
    return nodes.get(key);
  };
  const demand = node('demand'); demand.dataset.reading = 'demand';
  const generation = node('generation');generation.dataset.reading='generation';
  const peak = node('peak'); peak.dataset.expectedPeak = 'demand';
  const root = { dataset: {}, querySelector: node, querySelectorAll: selector => selector === '[data-reading]' ? [demand,generation] : selector === '[data-expected-peak]' ? [peak] : [], addEventListener() {} };
  const dialog = node('#station-dialog');
  const events = new EventTarget(), controller = new AbortController();
  const initial = {...snapshot,expectedPeaks:{date:new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Dublin'}).format(new Date()),demand:5517,demandTime:'17:30'}};
  const context = { root, data: initial, map: {}, events, signal: controller.signal, reconcileSnapshot, assetStatusMarkup, celtic, project, flowGeometry, generationIcon, interconnectorIcon,
    document: { createElement: () => node(Symbol()), createElementNS: () => node(Symbol()) },
    window: { matchMedia: () => ({ matches: true, addEventListener() {} }), addEventListener() {} },
    history: { replaceState() {} }, location: { hash: '#overview' }, CustomEvent, requestAnimationFrame() {} };
  vm.runInNewContext(`${source}\nmountOverview(root,data,map,events,signal);`, context);
  const card = node(`[data-interconnector="eastWest"]`);
  assert.equal(peak.textContent,"Today's expected peak: 5,517 MW at 17:30");
  assert.equal(node('.preview-note').hidden,true);
  dialog.open = true; dialog.dataset.activeStation = snapshot.stations[0].id;
  const next = structuredClone(initial);
  next.expectedPeaks.demand = 5520;
  next.expectedPeaks.demandTime = '18:00';
  next.demand += 1;
  next.interconnectors.find(flow => flow.id === 'eastWest').value = -100;
  next.stations[0].units[0].output += 1; next.stations[0].output += 1;
  // Pumped storage uses technical capacity even when declared availability changes.
  const storage = next.stations.find(station => station.id === 'turlough-hill');
  storage.available = 0; storage.maximum = 292; storage.output = 146;
  events.dispatchEvent(new CustomEvent('dashboard:snapshot', { detail: next }));
  assert.equal(dialog.open, true);
  assert.equal(node(`[data-interconnector="eastWest"]`), card);
  assert.match(card.innerHTML, /Exporting/);
  assert.match(card.innerHTML,/East-West Interconnector/);
  assert.equal(node('[data-flow="eastWest"]').dataset.direction, 'export');
  assert.match(node('#station-detail').innerHTML, new RegExp(String(Math.round(next.stations[0].units[0].output))));
  assert.equal(demand.innerHTML, `${new Intl.NumberFormat('en-IE').format(next.demand)} <small>MW</small>`);
  assert.equal(peak.textContent,"Today's expected peak: 5,520 MW at 18:00");
  const balanced=reconcileSnapshot(next);
  assert.equal(generation.innerHTML,`${new Intl.NumberFormat('en-IE').format(balanced.generation+balanced.reconciliation)} <small>MW</small>`);
  assert.equal(balanced.generation+balanced.reconciliation+balanced.imports,balanced.demand);
  const storageCard = node('.plant-callout[data-station="turlough-hill"]').innerHTML;
  assert.match(storageCard, /292 MW<\/b> capacity/);
  assert.match(storageCard, /capacity-percent">50%/);
  assert.equal(node('.preview-note').hidden,true);
  events.dispatchEvent(new CustomEvent('dashboard:snapshot',{detail:{...next,expectedPeaks:{...next.expectedPeaks,date:'2000-01-01'}}}));
  assert.equal(peak.textContent,"Today's expected peak: unavailable");
  controller.abort();
});

test('East–West schematic endpoint stays near Holyhead for both flow directions and old snapshots', async () => {
  const {project,flowGeometry} = await import('../components/roi-electricity/flow-geometry.js');
  const flow = snapshot.interconnectors.find(flow => flow.id === 'eastWest');
  const expected = project([-4.64,53.32]);
  for (const value of [-100,100]) {
    const geometry = flowGeometry({...flow,remoteLocation:[-3.4,53.343],value});
    assert.deepEqual(geometry.remote,expected);
    assert.deepEqual(value > 0 ? geometry.start : geometry.end,expected);
  }
  const greenlink = snapshot.interconnectors.find(flow => flow.id === 'greenlink');
  assert.deepEqual(flowGeometry(greenlink).remote,project(greenlink.remoteLocation));
});

test('ROI history validator accepts observed history and rejects shrinking or unverified editions', () => {
  const fixture={dataBasis:'public-source-history',first:'2026-01-01',last:'2026-11-03',generatedAt:'2026-11-04T07:00:00Z',
    days:[{date:'2026-01-01'}],series:['wind','solar','otherROI','generation','demand','eastWest','greenlink','northSouth'].map(key=>({key}))};
  validateUpdate('history',fixture,{dataBasis:'unavailable',days:[]});
  assert.throws(()=>validateUpdate('history',{...fixture,last:'2026-11-02'},fixture),/backwards/);
  assert.throws(()=>validateUpdate('history',{...fixture,dataBasis:'illustrative-design-fixture'},fixture),/Unverified/);
});
