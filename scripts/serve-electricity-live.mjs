// Local-only collector loop. It reads public NI data and writes a private local
// file store; it needs no Cloudflare credentials and never publishes remotely.
import fs from 'node:fs/promises';
import path from 'node:path';
import { spawn } from 'node:child_process';
const directory = path.resolve(process.env.ELECTRICITY_LOCAL_KV_DIR || 'outputs/electricity-local');
const python = process.env.ELECTRICITY_PYTHON || 'python3';
const origin = 'https://salmonofdata.com';
const interval = 15 * 60 * 1000;
const env = { ...process.env, ELECTRICITY_LOCAL_KV_DIR: directory, ELECTRICITY_LOCAL_LIVE: 'true' };
delete env.ELECTRICITY_PREVIEW_API;
const server = spawn(process.execPath, ['scripts/serve.mjs'], { env, stdio: 'inherit' });
let collector, timer, historyCollector, historyTimer, replayCollector, replayBusy=false, historyBusy = false, stopped = false;
let replayQueue=Promise.resolve(),replayDay='',replayAttempt=0;
const stop = () => { stopped = true; clearTimeout(timer); clearInterval(historyTimer); replayCollector?.kill('SIGTERM'); historyCollector?.kill('SIGTERM'); collector?.kill('SIGTERM'); server.kill('SIGTERM'); };
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, stop);
server.on('exit', code => { stop(); process.exitCode = code || 0; });
server.on('error', error => { console.error(error.message); stop(); process.exitCode = 1; });
async function write(key, value) {
  const file = path.join(directory, key);
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file + '.tmp', value);
  await fs.rename(file + '.tmp', file);
}
async function read(url) {
  const response = await fetch(new URL(url, origin), { headers: { 'User-Agent': 'Mozilla/5.0 SalmonOfDataLocalPreview' }, signal: AbortSignal.timeout(30000), cache: 'no-store' });
  if (!response.ok) throw new Error(`NI public API: HTTP ${response.status}`);
  return response;
}
// Serialize daily meter backfills and the live journal so both retain all
// previously accepted readings. Public files never contain source archives.
function runReplay(args,module='electricity.replay') {
  replayQueue=replayQueue.then(async()=>{
    if(stopped)return;
    const code=await new Promise((resolve,reject)=>{
      replayCollector=spawn(python,['-u','-m',module,...args],{env,stdio:'inherit',timeout:20*60*1000});
      replayCollector.on('error',reject);replayCollector.on('exit',resolve);
    });
    if(code!==0)throw new Error(`Archive exporter exited ${code}`);
    return true;
  }).catch(error=>{console.error(`[electricity local] Historical archive: ${error.message}. Previous complete dates retained.`);return false;});
  return replayQueue;
}
async function captureReplay(){
  await runReplay(['--journal-local',directory]);
  await runReplay(['--seed','--local-dir',directory],'electricity.replay_cloud');
}
async function mirrorNI() {
  const manifest = await (await read('/api/electricity/manifest.json')).json();
  if (manifest.schema !== 1 || !manifest.enabled) throw new Error('Invalid NI manifest');
  for (const name of ['snapshot', 'history']) {
    try {
      const pointer = manifest[name], version = pointer?.version;
      if (!/^[a-f0-9]{24}$/.test(version)) throw new Error('Invalid NI public version');
      const key = `public/${name}/${version}`;
      try { await fs.access(path.join(directory, key)); }
      catch {
        const response = await read(`/api/electricity/${name}.json?v=${version}`);
        if (response.headers.get('X-Electricity-Version') !== version) throw new Error('NI version mismatch');
        const raw = await response.text();
        JSON.parse(raw);
        await write(key, raw);
      }
      // Never announce a version before its full data exists locally.
      await write(`public/${name}/current`, JSON.stringify(pointer));
      const files = await fs.readdir(path.join(directory, 'public', name));
      const retained = new Set(['current', ...pointer.records.map(record => record.version)]);
      for (const file of files) if (/^[a-f0-9]{24}$/.test(file) && !retained.has(file)) await fs.unlink(path.join(directory, 'public', name, file));
    } catch (error) {
      if (name === 'snapshot') throw error;
      console.error(`[electricity local] NI history mirror: ${error.message}. ROI overview collection continues.`);
    }
  }
}
async function tick() {
  if (stopped) return;
  const started = Date.now();
  console.log(`[electricity local] Collection started ${new Date().toISOString()}`);
  try {
    await mirrorNI();
    if (stopped) return;
    const code = await new Promise((resolve, reject) => {
      collector = spawn(python, ['-u', 'electricity/roi_cloud.py', 'snapshot', '--force', '--local-dir', directory], { env, stdio: 'inherit', timeout: 12 * 60 * 1000 });
      collector.on('error', reject);
      collector.on('exit', resolve);
    });
    if (code !== 0) throw new Error(`ROI collector exited ${code}`);
    console.log('[electricity local] Accepted ROI overview published to the local store.');
  } catch (error) {
    console.error(`[electricity local] ${error.message}. Previous accepted readings retained; the next interval retries.`);
    {
      const key = 'private/roi/snapshot/current';
      try {
        const current = JSON.parse(await fs.readFile(path.join(directory, key), 'utf8'));
        await write(key, JSON.stringify({ ...current, ok: false, lastAttempt: new Date().toISOString() }));
      } catch { /* A first-run failure has no accepted ROI state to replace. */ }
    }
  }
  if (!stopped) {
    await captureReplay();
    const delay = Math.max(0, interval - (Date.now() - started));
    console.log(`[electricity local] Next collection ${new Date(Date.now() + delay).toISOString()}`);
    timer = setTimeout(tick, delay);
  }
}
void tick();

async function checkHistory() {
  if (stopped || historyBusy) return;
  let pointer;
  try { pointer = JSON.parse(await fs.readFile(path.join(directory, 'private/roi/history/current'), 'utf8')); }
  catch { return; } // Initial backfill is an explicit command; never compete with it.
  const now = new Date();
  const parts = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',hourCycle:'h23'}).formatToParts(now);
  const part = type => parts.find(item => item.type === type).value;
  const today = `${part('year')}-${part('month')}-${part('day')}`;
  if (Number(part('hour')) < 7 || pointer.successfulDate === today || Date.now() - Date.parse(pointer.lastAttempt) < 55 * 60000) return;
  historyBusy = true;
  console.log('[electricity local] Daily ROI history collection started.');
  try {
    const code = await new Promise((resolve,reject) => {
      historyCollector = spawn(python, ['-u','electricity/roi_cloud.py','history','--local-dir',directory], {env,stdio:'inherit',timeout:25*60*1000});
      historyCollector.on('error',reject); historyCollector.on('exit',resolve);
    });
    if (code !== 0) throw new Error(`ROI history collector exited ${code}`);
    console.log('[electricity local] Daily ROI history collection completed.');
  } catch(error) {
    console.error(`[electricity local] ${error.message}. Accepted history retained.`);
    {
      const key = 'private/roi/history/current';
      try {
        const current = JSON.parse(await fs.readFile(path.join(directory,key),'utf8'));
        await write(key,JSON.stringify({...current,ok:false,lastAttempt:new Date().toISOString()}));
      } catch { /* No accepted state to replace. */ }
    }
  } finally { historyBusy = false; }
}
async function checkReplay() {
  const now=new Date(),parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/London',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',hourCycle:'h23'}).formatToParts(now);
  const part=type=>parts.find(p=>p.type===type).value;
  const today=`${part('year')}-${part('month')}-${part('day')}`;
  if(!replayDay){
    try{const audit=JSON.parse(await fs.readFile('outputs/electricity-replay/audit.json','utf8'));if(audit.generatedAt?.startsWith(today)&&!audit.failures?.length)replayDay=today;}catch{ /* First backfill runs below. */ }
  }
  if(stopped||replayBusy||Number(part('hour'))<7||replayDay===today||Date.now()-replayAttempt<55*60000)return;
  replayBusy=true;replayAttempt=Date.now();
  try {
    if(!await runReplay([]))return;
    const manifests=await Promise.all(['ni','roi'].map(async region=>JSON.parse(await fs.readFile(`public/data/electricity-replay/${region}/manifest.json`,'utf8'))));
    if(manifests.every(m=>m.generatedAt?.startsWith(today)))replayDay=today;
    await captureReplay();
  } finally {replayBusy=false;}
}
historyTimer = setInterval(()=>{void checkHistory();void checkReplay();},60000);
void checkHistory();
void checkReplay();
