import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
const read=p=>JSON.parse(fs.readFileSync(new URL('../'+p,import.meta.url)));
const report=read('public/data/ai/refresh-2026-09-13.json');
const dashboard=read('data/ai/dashboard.json');
test('September refresh actuals reproduce from complete source inputs',()=>{
 const recruitment=dashboard.metrics.find(m=>m.id==='recruitment');
 for(const [date,...inputs] of report.recruitmentInputs){
  assert.equal(inputs.length,7);assert.ok(inputs.every(Number.isFinite));
  const value=Number((inputs.slice(0,6).reduce((a,b)=>a+b,0)/6/inputs[6]*100).toFixed(6));
  assert.equal(recruitment.data.find(p=>p.date===date).value,value);
 }
 const pay=dashboard.metrics.find(m=>m.id==='real-pay');
 for(const input of report.newActuals['real-pay']){
  const value=Number((input.nominalHourlyPay/input.cpi/input.base2019MeanPayDividedByCpi*100).toFixed(6));
  assert.equal(pay.data.find(p=>p.date===input.date).value,value);
 }
 assert.deepEqual(dashboard,read('public/data/ai/dashboard-snapshot.json'));
});
test('refresh preserves frozen files and removes only the imported calendar release',()=>{
 for(const [path,hash] of Object.entries(report.frozenFileSha256))assert.equal(createHash('sha256').update(fs.readFileSync(new URL('../'+path,import.meta.url))).digest('hex'),hash);
 const calendar=read('data/release-calendar.json');
 assert.ok(!calendar.entries.some(e=>e.date==='2026-09-11'&&e.title==='US consumer prices'));
 assert.ok(calendar.completedReleases.some(e=>e.date==='2026-09-11'&&e.importedAt===report.checkedAt));
 assert.ok(calendar.completedReleases.some(e=>e.date==='2026-09-15'&&e.importedAt==='2026-09-16'));
 assert.ok(calendar.completedReleases.some(e=>e.date==='2026-09-16'&&e.importedAt==='2026-09-16'));
 assert.deepEqual(calendar,read('public/data/release-calendar.json'));
});

test('September 16 actuals retain definitions and frozen scenarios',()=>{
 const refresh=read('public/data/refresh-2026-09-16.json');
 const enso=read('data/dashboard.json');
 assert.deepEqual(enso,read('public/data/dashboard.json'));
 assert.deepEqual(enso.metrics.find(m=>m.id==='retail').latest,{date:'2026-08',value:144.6});
 for(const [id,stat] of [['canada-vacancies','Job vacancies'],['canada-pay','Average offered hourly wage']]){
  const values=occ=>refresh.canadaInputs.filter(r=>r.Statistics===stat&&r['National Occupational Classification']===occ).map(r=>Number(r.VALUE));
  const software=values('Computer, software and Web designers and developers [2123]'), all=values('Total, all occupations');
  assert.equal(software.length,4);assert.equal(all.length,4);
  const expected=Number(((software.reduce((a,b)=>a+b,0)/all.reduce((a,b)=>a+b,0)-(id==='canada-pay'?1:0))*100).toFixed(6));
  assert.deepEqual(dashboard.metrics.find(m=>m.id===id).data.at(-1),{date:'2026-06-30',value:expected});
 }
 for(const [path,hash] of Object.entries(refresh.frozenFileSha256))assert.equal(createHash('sha256').update(fs.readFileSync(new URL('../'+path,import.meta.url))).digest('hex'),hash);
});
