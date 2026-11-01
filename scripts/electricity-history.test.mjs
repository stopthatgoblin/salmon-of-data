import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as model from '../components/ni-electricity/history-model.js';
test('NI electricity history preserves gaps, signed flows, coverage, leap years and daily weighting', () => {
const series = [{key:'wind'}, {key:'moyle'}];
const history = {
  first:'2024-01-01', last:'2024-02-02', series,
  days:[
    {date:'2024-01-01',v:[10,-50],n:[96,96]},
    {date:'2024-01-02',v:[null,50],n:[95,96]},
    {date:'2024-02-01',v:[20,0],n:[96,96]},
    {date:'2024-02-02',v:[40,null],n:[96,0]},
  ]
};
const daily = model.aggregate(history,'daily',2024,2024);
assert.equal(daily[1].values[0],null);
assert.equal(daily[1].values[1],50);
const monthly = model.aggregate(history,'monthly',2024,2024);
assert.equal(monthly[0].values[0],10);
assert.equal(monthly[0].days[0],1);
assert.equal(monthly[0].expectedDays,31);
assert.equal(monthly[0].values[1],0); // Export and import cancel; no absolute-value averaging.
assert.equal(monthly[0].chartValues[0],null); // A single day must not stand in for a month.
assert.equal(monthly[1].values[0],30);
assert.equal(monthly[1].expectedDays,2);
assert.equal(monthly[1].partialPeriod,true);
assert.equal(monthly[1].chartValues[0],30); // Both elapsed days in this partial month are present.
assert.equal(monthly[1].end,'2024-02-29'); // Leap-year calendar boundary retained.
const annual = model.aggregate(history,'annual',2024,2024);
assert.equal(annual[0].values[0],70/3); // Daily weighting, not equal weighting of monthly means.
assert.equal(annual[0].expectedDays,33);
assert.deepEqual(model.aggregate(history,'daily',2025,2025),[]);
const csv = model.csv(history,daily,'daily');
assert.ok(csv.startsWith('\uFEFFperiod_start,'));
assert.ok(csv.includes('2024-01-02,2024-01-02,daily,false,1,,0,95,false,50.0000,1,96,true'));
assert.throws(()=>model.aggregate(history,'daily',2025,2024));
});
