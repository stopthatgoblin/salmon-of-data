// Private, timer-only Worker. The GitHub credential is an encrypted Worker
// secret, never an asset, a URL parameter, a log message or an HTTP endpoint.
import { readElectricityPointer } from './electricity-state.mjs';
const workflowURL = 'https://api.github.com/repos/stopthatgoblin/salmon-of-data/actions/workflows/ni-electricity.yml/dispatches';
export const overviewCron = '2,17,32,47 * * * *';
export const historyCron = '0 6,7 * * *';
export const catchupCron = '5 7-12 * * *';
// Initialise ICU formatters once per isolate, keeping timer CPU work small.
const ukHour = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Europe/London', hour: '2-digit', hourCycle: 'h23',
});
const ukDate = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit',
});

export function scheduledDataset(cron, scheduledTime) {
  if (cron === overviewCron) return 'snapshot';
  const hour = Number(ukHour.format(new Date(scheduledTime)));
  // Run 07:00 UK time in both GMT and BST; the other UTC invocation is a no-op.
  if (cron === historyCron && hour === 7) return 'history';
  if (cron === catchupCron && hour >= 8 && hour <= 12) return 'history';
  return null;
}

export function collectionDue(dataset, pointer, now = Date.now()) {
  if (!pointer?.records?.length) throw new Error('Electricity state has not been seeded');
  if (dataset === 'snapshot') {
    const last = Date.parse(pointer.lastSuccess);
    return !Number.isFinite(last) || Math.floor(now / 900000) > Math.floor(last / 900000);
  }
  const today = ukDate.format(new Date(now));
  if (pointer.successfulDate === today) return false;
  const last = Date.parse(pointer.lastAttempt);
  return !Number.isFinite(last) || now - last >= 55 * 60000;
}

export async function collectOnSchedule(controller, env, request = fetch, now = Date.now()) {
  const dataset = scheduledDataset(controller.cron, controller.scheduledTime);
  if (!dataset) return { action: 'skip', reason: 'outside UK collection hours' };
  if (!env.GITHUB_ACTIONS_TOKEN) throw new Error('Missing encrypted GITHUB_ACTIONS_TOKEN secret');
  const pointer = await readElectricityPointer(env.ELECTRICITY_DATA, dataset);
  const roiPointer = env.ELECTRICITY_ROI_ENABLED === 'true'
    ? await readElectricityPointer(env.ELECTRICITY_DATA, dataset, 'roi/') : null;
  if (env.ELECTRICITY_ROI_ENABLED === 'true' && !roiPointer?.records?.length) throw new Error('ROI state has not been initialized; run both datasets with include_roi first');
  const roiDue = roiPointer ? collectionDue(dataset, roiPointer, now) : false;
  if (!collectionDue(dataset, pointer, now) && !roiDue) return { action: 'skip', dataset, reason: 'recent successful collection or retry guard' };
  const response = await request(workflowURL, {
    // Workers supports manual/follow, not Fetch's redirect:error. Reject every
    // 3xx below without forwarding the Authorization header to another host.
    method: 'POST', redirect: 'manual', signal: AbortSignal.timeout(15000),
    headers: {
      Authorization: `Bearer ${env.GITHUB_ACTIONS_TOKEN}`,
      Accept: 'application/vnd.github+json', 'Content-Type': 'application/json',
      'User-Agent': 'SalmonOfDataElectricityScheduler', 'X-GitHub-Api-Version': '2022-11-28',
    },
    body: JSON.stringify({ ref: 'main', inputs: {
      dataset, target: 'production', automatic: 'true', preview_watch: 'false',
    } }),
  });
  // Never print GitHub's response body or request headers, including on errors.
  if (!response.ok) throw new Error(`GitHub collector dispatch failed: HTTP ${response.status}`);
  return { action: 'dispatch', dataset, status: response.status };
}

export default {
  async scheduled(controller, env) {
    const result = await collectOnSchedule(controller, env);
    console.log(JSON.stringify(result));
  },
};
