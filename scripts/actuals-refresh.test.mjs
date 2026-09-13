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
 assert.ok(calendar.entries.some(e=>e.date==='2026-09-15'));
 assert.ok(calendar.entries.some(e=>e.date==='2026-09-16'));
 assert.deepEqual(calendar,read('public/data/release-calendar.json'));
});
