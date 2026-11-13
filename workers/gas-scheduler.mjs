export const gasCron = '0,20,40 18-22 * * *';
export const gasCatchupCron = '0 6,7,9,10,12,13,15,16 * * *';
const localHour = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Dublin',hour:'2-digit',hourCycle:'h23'});
const localDate = new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Dublin',year:'numeric',month:'2-digit',day:'2-digit'});
const workflowURL = 'https://api.github.com/repos/stopthatgoblin/salmon-of-data/actions/workflows/ireland-gas.yml/dispatches';

export function gasDue(cron, scheduledTime, state) {
  const today = localDate.format(new Date(scheduledTime));
  const hour = Number(localHour.format(new Date(scheduledTime)));
  if (cron === gasCatchupCron) {
    // Only a known missing report gets daytime retries, at 07/10/13/16 local.
    // Retry its original gas day rather than moving the target at midnight.
    if (![7,10,13,16].includes(hour) || state?.waitingForSource?.source !== 'SEMO meter data'
        || !/^\d{4}-\d{2}-\d{2}$/.test(state?.targetGasDay || '') || state.targetGasDay >= today) return false;
  } else {
    if (cron !== gasCron || hour < 19 || hour > 22) return false;
    const target = new Date(today + 'T12:00:00Z');
    target.setUTCDate(target.getUTCDate() - 1);
    if (state?.successfulDate === today && (!state.targetGasDay || state.targetGasDay === target.toISOString().slice(0,10))) return false;
  }
  const attempt = Date.parse(state?.lastAttempt);
  return !Number.isFinite(attempt) || scheduledTime - attempt >= 18*60000;
}

export async function collectGasOnSchedule(controller, env, request=fetch) {
  if (!env.GAS_DATA) return {action:'skip',dataset:'gas',reason:'gas binding not enabled'};
  const state = await env.GAS_DATA.get('private/gas/status',{type:'json',cacheTtl:60});
  if (!gasDue(controller.cron,controller.scheduledTime,state)) return {action:'skip',dataset:'gas',reason:'outside collection window or already completed'};
  if (!env.GITHUB_ACTIONS_TOKEN) throw new Error('Missing encrypted scheduler credential');
  const response = await request(workflowURL,{
    method:'POST',redirect:'manual',signal:AbortSignal.timeout(15000),
    headers:{Authorization:`Bearer ${env.GITHUB_ACTIONS_TOKEN}`,Accept:'application/vnd.github+json',
      'Content-Type':'application/json','User-Agent':'SalmonOfDataGasScheduler','X-GitHub-Api-Version':'2022-11-28'},
    body:JSON.stringify({ref:'main',inputs:{target:'production',automatic:'true',revision_days:'7',
      gas_day:controller.cron === gasCatchupCron ? state.targetGasDay : ''}}),
  });
  if (!response.ok) throw new Error(`Gas collector dispatch failed: HTTP ${response.status}`);
  await env.GAS_DATA.put('private/gas/status',JSON.stringify({...state,schema:1,lastAttempt:new Date(controller.scheduledTime).toISOString()}));
  return {action:'dispatch',dataset:'gas',status:response.status};
}
