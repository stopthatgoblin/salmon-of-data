import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildChartData } from '../lib/ai-chart-data.ts';
test('future actuals overlay continuous scenarios without rebasing', () => {
  const m = {
    period: 'month',
    anchor: { date: '2026-09-01', value: 100 },
    endpoints: [110, 90, 70],
    data: [
      { date: '2026-09-01', value: 100 },
      { date: '2026-10-01', value: 98 },
      { date: '2026-11-01', value: 97 },
    ],
  };
  const before = JSON.stringify(m);
  const rows = buildChartData(m, '2029-12-31');
  assert.equal(rows.length, 4);
  assert.equal(rows[1].observed, 98);
  for (const r of rows)
    for (const k of ['s0', 's1', 's2']) assert.ok(Number.isFinite(r[k]));
  assert.ok(rows[1].s2 > 98);
  assert.equal(rows.at(-1).s2, 70);
  assert.equal(JSON.stringify(m), before);
});
test('missing source intervals remain explicit actual gaps', () => {
  const rows = buildChartData(
    {
      period: 'quarter',
      anchor: { date: '2026-03-31', value: 100 },
      endpoints: [110, 90, 70],
      data: [
        { date: '2025-06-30', value: 90 },
        { date: '2026-03-31', value: 100 },
      ],
    },
    '2029-12-31',
  );
  assert.equal(rows.filter((r) => r.observed === null).length, 1);
});

test('imported AI history and predictions match the original frozen definitions', async()=>{
 const fs=await import('node:fs');
 const actual=JSON.parse(fs.readFileSync(new URL('../data/ai/dashboard.json',import.meta.url)));
 const frozen=JSON.parse(fs.readFileSync(new URL('../public/data/ai/frozen-metrics-v1.json',import.meta.url)));
 assert.equal(actual.metrics.length,8);
 for(const m of actual.metrics){const f=frozen.metrics.find(f=>f.id===m.id);assert.deepEqual(m.anchor,f.anchor);assert.deepEqual(m.endpoints,f.endpoints);}
});
