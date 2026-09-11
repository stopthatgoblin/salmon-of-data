import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {chartRows,monthNumber,monthDate,interpolate} from '../lib/chart-data.ts';
const data=JSON.parse(fs.readFileSync(new URL('../data/dashboard.json',import.meta.url)));
test('frozen anchors and ordered paths are internally consistent',()=>{
 for(const m of data.metrics){
  const dates=m.history.map(p=>p.date);assert.deepEqual(dates,[...new Set(dates)].sort());
  for(const key of ['high','medium','low']){assert.deepEqual(m.paths[key][0],m.anchor);assert.ok(m.paths[key].every(p=>Number.isFinite(p.value)));const ds=m.paths[key].map(p=>p.date);assert.deepEqual(ds,[...new Set(ds)].sort());}
  const start=monthNumber(m.anchor.date),end=monthNumber(m.paths.low.at(-1).date);
  for(let n=start;n<=end;n++){
   const lo=interpolate(m.paths.low,n),md=interpolate(m.paths.medium,n),hi=interpolate(m.paths.high,n);
   if(m.annual)assert.ok(lo>=md&&md>=hi,`${m.id} ${n}`);else assert.ok(hi+1e-9>=md&&md+1e-9>=lo,`${m.id} ${n}`);
  }
 }
});
test('future observations do not move frozen scenario lines',()=>{
 const m=data.metrics[0],start=monthNumber('2026-01'),end=monthNumber('2027-12');
 const original=chartRows(m.history,m.paths,start,end);
 const updated=chartRows([...m.history,{date:'2026-10',value:142}],m.paths,start,end);
 assert.deepEqual(original.map(({high,medium,low})=>({high,medium,low})),updated.map(({high,medium,low})=>({high,medium,low})));
 assert.equal(updated.find(p=>p.date==='2026-10').actual,142);
 assert.equal(updated.find(p=>p.date==='2026-09').actual,null);
});
test('published data gaps remain gaps, and scenarios stop at their horizon',()=>{
 const m=data.metrics.find(m=>m.id==='enso');
 const rows=chartRows(m.history,m.paths,monthNumber('2026-01'),monthNumber('2027-12'));
 assert.equal(rows.find(p=>p.date==='2027-08').high,null);
 assert.equal(rows.find(p=>p.date==='2027-01').actual,null);
 assert.equal(interpolate(m.paths.high,monthNumber('2026-01')),null);
});
test('annual harvests are never turned into monthly observations',()=>{
 const m=data.metrics.find(m=>m.id==='harvest');
 const rows=chartRows(m.history,m.paths,monthNumber('2022-01'),monthNumber('2028-01'),true);
 assert.equal(rows.length,7);assert.equal(rows.find(r=>r.date==='2026-01').actual,null);
 assert.equal(m.paths.medium[1].value,m.officialForecast);
});
test('month labels round-trip across year boundaries',()=>{
 for(const d of ['2025-12','2026-01','2026-09','2029-08'])assert.equal(monthDate(monthNumber(d)),d);
});

test('El Niño anchors and paths still equal the original frozen file',()=>{
 const frozen=JSON.parse(fs.readFileSync(new URL('../public/data/scenarios-v1.json',import.meta.url)));
 for(const m of data.metrics){assert.deepEqual(m.anchor,frozen.metrics[m.id].anchor);assert.deepEqual(m.paths,frozen.metrics[m.id].paths);}
});
