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
    assert.equal(options.redirect, 'manual');
    assert.deepEqual(JSON.parse(options.body), { ref: 'main', inputs: { dataset: 'snapshot', target: 'production', automatic: 'true', preview_watch: 'false' } });
    return new Response(null, { status: 204 });
  };
  assert.deepEqual(await collectOnSchedule(controller, env, request, now), { action: 'dispatch', dataset: 'snapshot', status: 204 });
  assert.equal(calls, 1);
  await assert.rejects(collectOnSchedule(controller, env, async () => new Response('sensitive upstream response', { status: 403 }), now), error => error.message === 'GitHub collector dispatch failed: HTTP 403');
  await assert.rejects(collectOnSchedule(controller, env, async (_url, options) => {
    assert.equal(options.redirect, 'manual');
    return new Response(null, { status: 302, headers: { Location: 'https://example.invalid/' } });
  }, now), error => error.message === 'GitHub collector dispatch failed: HTTP 302');
  await assert.rejects(collectOnSchedule(controller, { ...env, GITHUB_ACTIONS_TOKEN: '' }, request, now), /Missing encrypted/);
});

test('07:00 history dispatch runs once per UK date and skips the other UTC candidate', async () => {
  for (const [day, hour, otherHour] of [['2026-11-02', '07', '06'], ['2026-07-15', '06', '07']]) {
    const now = Date.parse(`${day}T${hour}:00:00Z`);
    let pointer = { records: [{}], successfulDate: '2026-07-01', lastAttempt: '2026-07-01T07:00:00Z' };
    let dispatches = 0, reads = 0;
    const env = { GITHUB_ACTIONS_TOKEN: 'test-only-placeholder', ELECTRICITY_DATA: { async get(key) {
      assert.equal(key, 'public/history/current'); reads++; return pointer;
    } } };
    const request = async (_url, options) => {
      assert.deepEqual(JSON.parse(options.body).inputs, { dataset: 'history', target: 'production', automatic: 'true', preview_watch: 'false' });
      dispatches++; return new Response(null, { status: 204 });
    };
    const controller = { cron: historyCron, scheduledTime: now };
    assert.equal((await collectOnSchedule(controller, env, request, now)).action, 'dispatch');
    pointer = { ...pointer, successfulDate: day, lastSuccess: new Date(now).toISOString() };
    assert.equal((await collectOnSchedule(controller, env, request, now)).action, 'skip');
    const before = reads;
    assert.equal((await collectOnSchedule({ cron: historyCron, scheduledTime: Date.parse(`${day}T${otherHour}:00:00Z`) }, env, request, now)).action, 'skip');
    assert.equal(reads, before); assert.equal(dispatches, 1);
  }
});

test('ROI alone can trigger the shared timer and missing enabled state fails explicitly', async () => {
  const now = Date.parse('2026-11-04T12:17:00Z');
  const controller = { cron: overviewCron, scheduledTime: now };
  let roi = { records: [{}], lastSuccess: '2026-11-04T12:00:00Z' };
  const env = { GITHUB_ACTIONS_TOKEN: 'test-only', ELECTRICITY_ROI_ENABLED: 'true', ELECTRICITY_DATA: { async get(key) {
    return key === 'public/roi/snapshot/current' ? roi : { records: [{}], lastSuccess: '2026-11-04T12:16:00Z' };
  } } };
  let calls = 0;
  const request = async () => { calls++; return new Response(null, { status: 204 }); };
  assert.equal((await collectOnSchedule(controller, env, request, now)).action, 'dispatch');
  assert.equal(calls, 1);
  roi.lastSuccess = '2026-11-04T12:16:00Z';
  assert.equal((await collectOnSchedule(controller, env, request, now)).action, 'skip');
  roi = null;
  await assert.rejects(collectOnSchedule(controller, env, request, now), /ROI state has not been initialized/);
});

test('ROI daily history retries even after NI history succeeded today', async () => {
  const now = Date.parse('2026-11-04T09:05:00Z');
  const controller = {cron:catchupCron,scheduledTime:now};
  let roi = {records:[{}],successfulDate:'2026-11-03',lastAttempt:'2026-11-04T07:00:00Z',ok:false};
  const env = {GITHUB_ACTIONS_TOKEN:'test-only',ELECTRICITY_ROI_ENABLED:'true',ELECTRICITY_DATA:{async get(key) {
    return key === 'public/roi/history/current' ? roi : {records:[{}],successfulDate:'2026-11-04'};
  }}};
  let calls=0;
  const request=async (_url,options)=>{assert.equal(JSON.parse(options.body).inputs.dataset,'history');calls++;return new Response(null,{status:204});};
  assert.equal((await collectOnSchedule(controller,env,request,now)).action,'dispatch');
  roi={...roi,successfulDate:'2026-11-04',lastAttempt:'2026-11-04T09:00:00Z',ok:true};
  assert.equal((await collectOnSchedule(controller,env,request,now)).action,'skip');
  assert.equal(calls,1);
});
