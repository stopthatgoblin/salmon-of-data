import assert from 'node:assert/strict';
import fs from 'node:fs';
import {test} from 'node:test';
import {replaySnapshot,validateReplayManifest,mountReplay} from '../components/electricity/replay.js';
import {applicableOutages} from '../components/electricity/asset-status.js';
const read=path=>JSON.parse(fs.readFileSync(path));
const live=region=>read(`public/data/${region}-electricity/snapshot.json`);
const day=(region,date)=>read(`public/data/electricity-replay/${region}/${date}.json`);

test('historical NI clears current availability, forecasts and dispatch provenance',()=>{
  const source=day('ni','2026-09-01'),data=replaySnapshot(source,source.rows[0],live('ni'),'ni');
  assert.equal(data.moyleAvailable,null);
  assert.equal(data.stations[0].available,null);
  assert.equal(data.stations[0].maximum,null);
  assert.equal(data.expectedPeaks,null);
  assert.equal(data.dispatchPublished,null);
  assert.equal(data.technicalSource,null);
  assert.equal(data.stations[0].units[0].availabilitySource,null);
  assert.equal(data.demand,data.generation+data.moyle+data.northSouth);
  assert.equal(data.stations[0].units[0].status,'Metered half-hour average');
});

test('historical ROI retains pumping and reconciles domestic components without changing reported generation',()=>{
  const source=day('roi','2026-09-09'),data=replaySnapshot(source,source.rows[0],live('roi'),'roi');
  assert.ok(data.stations.find(s=>s.id==='turlough-hill').output<0);
  assert.equal(data.generation,source.rows[0].grid[source.gridKeys.indexOf('generation')]);
  const domestic=data.stations.reduce((n,s)=>n+s.output,0)+data.wind+data.solar+data.other;
  assert.ok(Math.abs(domestic-data.generation-data.reconciliation)<1e-6);
  assert.ok(Math.abs(domestic+data.imports-data.demand)<1e-6);
  assert.equal(data.stations.length,17);
  const partial=structuredClone(source.rows[0]);partial.outputs.pop();
  assert.throws(()=>replaySnapshot(source,partial,live('roi'),'roi'),/Incomplete/);
});

test('archive supports a different station display order and rejects external file URLs',()=>{
  const manifest=read('public/data/electricity-replay/ni/manifest.json');
  validateReplayManifest({...manifest,stationIds:[...manifest.stationIds].reverse()},'ni',live('ni'));
  const changed=structuredClone(manifest);changed.days[0].url='https://other.example/history.json';
  assert.throws(()=>validateReplayManifest(changed,'ni',live('ni')),/Invalid archive/);
});

test('clock-change readings remain distinct and captured proxies are labelled separately from meters',()=>{
  const source=day('ni','2026-10-25');
  assert.equal(source.rows.length,100);
  const repeat=source.rows.filter(r=>r.time.slice(11,16)==='01:00');
  assert.equal(repeat.length,2);assert.notEqual(Date.parse(repeat[0].time),Date.parse(repeat[1].time));
  const data=replaySnapshot(source,{...source.rows[0],stationBasis:'captured-dispatch-proxy'},live('ni'),'ni');
  assert.equal(data.replayStationBasis,'dispatch');assert.equal(data.replayMeter,null);
  assert.equal(data.stations[0].units[0].status,'Archived dispatch estimate');
});

test('return expectations apply only to their published event window and unit scope',()=>{
  assert.equal(applicableOutages('moyle',{time:'2026-10-25T12:00:00Z'}).length,0);
  assert.match(applicableOutages('moyle',{time:'2026-11-08T12:00:00Z'})[0].display,/13 Dec/);
  assert.equal(applicableOutages('moyle',{time:'2026-12-14T12:00:00Z'}).length,0);
  const pumping=applicableOutages('turlough-hill',{time:'2026-11-08T12:00:00Z'});
  assert.equal(pumping[0].scope,'TH4 pumping only');
  assert.equal(applicableOutages('moneypoint',{time:'2026-11-08T12:00:00Z'}).some(n=>n.unitIds.length===3),false);
});

test('live polling cannot overwrite the selected historical reading, and Return to live uses the newest data',async t=>{
  class Node extends EventTarget {dataset={};disabled=false;value='';textContent='';open=false;setAttribute(){}replaceChildren(...children){this.children=children;}}
  const nodes=new Map();const get=selector=>{if(!nodes.has(selector))nodes.set(selector,new Node());return nodes.get(selector);};
  const controls=get('.replay-controls');controls.querySelector=get;
  const root={dataset:{},querySelector:get};
  const source=day('ni','2026-09-01'),manifest=read('public/data/electricity-replay/ni/manifest.json');
  const index={...manifest,days:[{...manifest.days[0]}],last:manifest.days[0].last};
  t.mock.method(globalThis,'fetch',async url=>Response.json(url.endsWith('manifest.json')?index:source));
  const saved=globalThis.document;globalThis.document={createElement:()=>new Node()};
  const events=new EventTarget(),updates=[],controller=new AbortController();
  events.addEventListener('dashboard:snapshot',e=>updates.push(e.detail));
  try {
    const initial=live('ni'),bridge=mountReplay(root,'ni',initial,events,controller.signal);
    controls.open=true;controls.dispatchEvent(new Event('toggle'));
    for(let i=0;i<10;i++)await new Promise(resolve=>setImmediate(resolve));
    assert.equal(root.dataset.replayMode,'historical');assert.equal(updates.length,1);
    const newer={...initial,time:'2026-11-08T15:00:00Z'};
    bridge.dispatchEvent(new CustomEvent('dashboard:snapshot',{detail:newer}));
    assert.equal(updates.length,1);
    get('[data-replay-live]').dispatchEvent(new Event('click'));
    assert.equal(root.dataset.replayMode,'live');assert.equal(updates.at(-1),newer);
    assert.equal(controls.getAttribute?.('aria-busy')??null,null);
    controller.abort();
  } finally {controller.abort();globalThis.document=saved;}
});
