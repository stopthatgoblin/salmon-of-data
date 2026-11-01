import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import vm from 'node:vm';
import { test } from 'node:test';

const dataset = name => JSON.parse(fs.readFileSync(`public/data/ni-electricity/${name}.json`, 'utf8'));

test('electricity snapshot retains signed balance, station totals and recorded provenance', () => {
  const data = dataset('snapshot');
  const stationOutput = data.stations.reduce((sum, station) => sum + station.output, 0);
  assert.equal(data.demand - data.generation - data.moyle, data.northSouth);
  assert.ok(Math.abs(data.generation - data.wind - data.solar - stationOutput - data.other) < 0.0001);
  assert.equal(data.stations.reduce((sum, station) => sum + station.units.length, 0), 13);
  for (const station of data.stations) {
    assert.ok(Math.abs(station.output - station.units.reduce((sum, unit) => sum + unit.output, 0)) < 0.0001);
  }
  assert.ok(Date.parse(data.retrievedAt) >= Date.parse(data.time));
  assert.ok(data.dispatchPublished && data.dispatchCoverageThrough && data.availabilityPublished);
  const edition = dataset('edition');
  assert.equal(edition.automaticUpdates, false);
  for (const [name, entry] of Object.entries(edition.datasets)) {
    const bytes = fs.readFileSync(`public/data/ni-electricity/${name}`);
    assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), entry.sha256);
  }
});

test('electricity overview labels imports, exports and zero consistently', () => {
  const source = fs.readFileSync('components/ni-electricity/overview.js', 'utf8').replace('export function', 'function');
  for (const [northSouth, label, value, shareHidden, moyle] of [
    [-145, 'Net imports', '100', false, 245],
    [-345, 'Net exports', '100', true, 245],
    [-245, 'Net flow', '0', true, 245],
    [215, 'Net imports', '198', false, -17],
    [0, 'Net flow', '0', true, 0],
  ]) {
    const nodes = new Map();
    const node = key => {
      if (!nodes.has(key)) nodes.set(key, { dataset: {}, style: {}, attributes: {}, children: [], classList: { toggle() {} }, setAttribute(name,value) { this.attributes[name]=value; }, removeAttribute(name) { delete this.attributes[name]; }, append(child) { this.children.push(child); }, replaceChildren() { this.children=[]; }, addEventListener() {} });
      return nodes.get(key);
    };
    const reading = node('reading'); reading.dataset.reading = 'imports';
    const share = node('share'); share.dataset.share = 'imports';
    const signedNumber = node('signed'); signedNumber.dataset.number = 'imports';
    const selectors = { '[data-reading]': [reading], '[data-share]': [share], '[data-number]': [signedNumber] };
    const root = { dataset: {}, querySelector: node, querySelectorAll: selector => selectors[selector] || [], addEventListener() {} };
    const data = { time: '2026-10-31T21:00:00Z', demand: 1000, generation: 1000 - moyle - northSouth, wind: 300, solar: 0, other: 0, moyle, northSouth, moyleAvailable: 250, northSouthReferenceCapacity: 300, stations: [] };
    const context = { root, data, map: {}, events: { dispatchEvent() {}, addEventListener() {} }, signal: {}, document: { createElement: () => node(Symbol()), createElementNS: () => node(Symbol()) }, window: { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} }, history: { replaceState() {} }, location: { hash: '#overview' }, CustomEvent: class {} };
    vm.runInNewContext(`${source}\nmountOverview(root, data, map, events, signal);`, context);
    assert.equal(node('#net-flow-label').textContent, label);
    assert.equal(reading.innerHTML, `${value} <small>MW</small>`);
    assert.equal(node('#net-flow-share').hidden, shareHidden);
    assert.equal(signedNumber.textContent, String(data.moyle + northSouth));
    assert.match(node('[data-interconnector="northSouth"]').innerHTML, northSouth < 0 ? /Exporting/ : northSouth > 0 ? /Importing/ : /No net flow/);
    assert.equal(node('.moyle-flow').dataset.direction, moyle < 0 ? 'export' : moyle > 0 ? 'import' : 'balanced');
  }
});
