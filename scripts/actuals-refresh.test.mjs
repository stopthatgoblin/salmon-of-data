import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
const read=p=>JSON.parse(fs.readFileSync(new URL('../'+p,import.meta.url)));
const report=read('public/data/ai/refresh-2026-09-13.json');
const dashboard=read('data/ai/dashboard.json');
test('September refresh vintage reproduces from its complete source inputs',()=>{
 // Current observations include later provider revisions. Replay the saved
 // September vintage against its own report, rather than today's revised data.
 const recruitment=report.newActuals.recruitment;
 for(const [date,...inputs] of report.recruitmentInputs){
  assert.equal(inputs.length,7);assert.ok(inputs.every(Number.isFinite));
  const value=Number((inputs.slice(0,6).reduce((a,b)=>a+b,0)/6/inputs[6]*100).toFixed(6));
  assert.equal(recruitment.find(p=>p.date===date).value,value);
 }
 for(const input of report.newActuals['real-pay']){
  const value=Number((input.nominalHourlyPay/input.cpi/input.base2019MeanPayDividedByCpi*100).toFixed(6));
  assert.equal(input.value,value);
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
 assert.deepEqual(refresh.newActuals.retail,[{date:'2026-08',value:144.6}]);
 assert.ok(enso.metrics.find(m=>m.id==='retail').latest.date>='2026-08');
 for(const [id,stat] of [['canada-vacancies','Job vacancies'],['canada-pay','Average offered hourly wage']]){
  const values=occ=>refresh.canadaInputs.filter(r=>r.Statistics===stat&&r['National Occupational Classification']===occ).map(r=>Number(r.VALUE));
  const software=values('Computer, software and Web designers and developers [2123]'), all=values('Total, all occupations');
  assert.equal(software.length,4);assert.equal(all.length,4);
  const expected=Number(((software.reduce((a,b)=>a+b,0)/all.reduce((a,b)=>a+b,0)-(id==='canada-pay'?1:0))*100).toFixed(6));
  assert.deepEqual(dashboard.metrics.find(m=>m.id===id).data.at(-1),{date:'2026-06-30',value:expected});
 }
 for(const [path,hash] of Object.entries(refresh.frozenFileSha256))assert.equal(createHash('sha256').update(fs.readFileSync(new URL('../'+path,import.meta.url))).digest('hex'),hash);
});


test('current recruitment observations reproduce from their seven downloaded input series',()=>{
 const lines=fs.readFileSync(new URL('../public/data/ai/recruitment-excel-inputs.csv',import.meta.url),'utf8').trim().split(/\r?\n/).slice(1);
 const actuals=new Map(dashboard.metrics.find(m=>m.id==='recruitment').data.map(p=>[p.date,p.value]));
 for(const line of lines){
  const [date,...raw]=line.split(',');const input=raw.map(Number);
  assert.equal(input.length,7);assert.ok(input.every(Number.isFinite));
  const expected=Number((input.slice(0,6).reduce((sum,value)=>sum+value,0)/6/input[6]*100).toFixed(6));
  assert.equal(actuals.get(date),expected,`Recruitment calculation ${date}`);
 }
});

test('November release review imports UK prices and excludes daily electricity and retired metrics',()=>{
 const calendar=read('data/release-calendar.json');
 assert.ok(calendar.completedReleases.some(e=>e.title==='UK consumer prices'&&e.date==='2026-10-21'&&e.importedAt==='2026-11-01'));
 assert.ok(calendar.entries.every(e=>['ai','el-nino'].includes(e.tracker)&&!['daily','weekly'].includes(e.frequency)));
 assert.ok(!calendar.entries.some(e=>e.metrics.includes('Maize harvest')));
 assert.ok(calendar.entries.every(e=>!e.date||e.date>=calendar.lastReleaseReviewAt));
 const refresh=read('public/data/refresh-2026-11-01.json');
 assert.deepEqual(refresh.newActuals.retail,[{date:'2026-09',value:144.3}]);
 for(const [path,hash] of Object.entries(refresh.frozenFileSha256))assert.equal(createHash('sha256').update(fs.readFileSync(new URL('../'+path,import.meta.url))).digest('hex'),hash);
});
