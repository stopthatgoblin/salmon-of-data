import assert from 'node:assert/strict';
import { test } from 'node:test';
import { scheduledDataset, collectionDue, collectOnSchedule, overviewCron, historyCron, catchupCron } from '../workers/electricity-scheduler.mjs';

test('Cloudflare history clock follows 07:00 UK time across GMT, BST and clock changes', () => {
  for (const day of ['2026-01-15', '2026-03-28', '2026-10-25', '2026-11-01']) {
    assert.equal(scheduledDataset(historyCron, Date.parse(day + 'T06:00:00Z')), null);
    assert.equal(scheduledDataset(historyCron, Date.parse(day + 'T07:00:00Z')), 'history');
  }
  for (const day of ['2026-03-29', '2026-07-15', '2026-10-24']) {
    assert.equal(scheduledDataset(historyCron, Date.parse(day + 'T06:00:00Z')), 'history');
    assert.equal(scheduledDataset(historyCron, Date.parse(day + 'T07:00:00Z')), null);
  }
  assert.equal(scheduledDataset(catchupCron, Date.parse('2026-07-15T12:05:00Z')), null);
  assert.equal(scheduledDataset(catchupCron, Date.parse('2026-11-01T07:05:00Z')), null);
  assert.equal(scheduledDataset(catchupCron, Date.parse('2026-11-01T12:05:00Z')), 'history');
  assert.equal(scheduledDataset(overviewCron, Date.parse('2026-07-15T23:02:00Z')), 'snapshot');
});

test('external timer suppresses duplicate collections and daily successes without hiding failed retries', () => {
  const now = Date.parse('2026-11-01T07:05:00Z');
  const pointer = { records: [{}], lastSuccess: '2026-11-01T07:00:00Z', successfulDate: '2026-11-01' };
  assert.equal(collectionDue('snapshot', pointer, now), false);
  assert.equal(collectionDue('snapshot', pointer, now + 10 * 60000), true);
  assert.equal(collectionDue('history', pointer, now), false);
  assert.equal(collectionDue('history', { ...pointer, successfulDate: '2026-10-31', lastAttempt: '2026-11-01T07:00:00Z', ok: false }, now), false);
  assert.equal(collectionDue('history', { ...pointer, successfulDate: '2026-10-31', lastAttempt: '2026-11-01T06:00:00Z', ok: false }, now), true);
  // UK calendar date has already rolled over during BST.
  assert.equal(collectionDue('history', { records: [{}], successfulDate: '2026-07-16' }, Date.parse('2026-07-15T23:05:00Z')), false);
  assert.throws(() => collectionDue('snapshot', null, now), /not been seeded/);
});

test('timer dispatch is pinned to production main, protects credentials and preserves collector guards', async () => {
  const now = Date.parse('2026-11-01T16:17:00Z');
  const controller = { cron: overviewCron, scheduledTime: now };
  const env = { GITHUB_ACTIONS_TOKEN: 'test-only-placeholder', ELECTRICITY_DATA: {
    async get(key) {
      assert.equal(key, 'public/snapshot/current');
      return { records: [{}], lastSuccess: '2026-11-01T15:57:00Z' };
    },
  } };
  let calls = 0;
  const request = async (url, options) => {
    calls++;
    assert.equal(url, 'https://api.github.com/repos/stopthatgoblin/salmon-of-data/actions/workflows/ni-electricity.yml/dispatches');
    assert.equal(options.redirect, 'error');
    assert.deepEqual(JSON.parse(options.body), { ref: 'main', inputs: { dataset: 'snapshot', target: 'production', automatic: 'true', preview_watch: 'false' } });
    return new Response(null, { status: 204 });
  };
  assert.deepEqual(await collectOnSchedule(controller, env, request, now), { action: 'dispatch', dataset: 'snapshot', status: 204 });
  assert.equal(calls, 1);
  await assert.rejects(collectOnSchedule(controller, env, async () => new Response('sensitive upstream response', { status: 403 }), now), error => error.message === 'GitHub collector dispatch failed: HTTP 403');
  await assert.rejects(collectOnSchedule(controller, { ...env, GITHUB_ACTIONS_TOKEN: '' }, request, now), /Missing encrypted/);
});
