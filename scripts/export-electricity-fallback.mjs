// Export only validated accepted local ROI datasets, never source archives.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {validateUpdate} from '../components/roi-electricity/live.js';
const store=path.resolve(process.env.ELECTRICITY_LOCAL_KV_DIR || 'outputs/electricity-local');
const target=path.resolve('public/data/roi-electricity');
const datasets={};
await fs.mkdir(target,{recursive:true});
for(const name of ['snapshot','history']) {
  let rawPointer;
  try { rawPointer=await fs.readFile(path.join(store,`private/roi/${name}/current`),'utf8'); }
  catch(error) { if(error.code!=='ENOENT')throw error; rawPointer=await fs.readFile(path.join(store,`public/roi/${name}/current`),'utf8'); }
  const pointer=JSON.parse(rawPointer);
  const version=pointer.records?.[0]?.version;
  if(!/^[a-f0-9]{24}$/.test(version)) throw new Error(`No accepted local ROI ${name} version`);
  const raw=await fs.readFile(path.join(store,`public/roi/${name}/${version}`));
  if(createHash('sha256').update(raw).digest('hex').slice(0,24)!==version) throw new Error(`Local ROI ${name} checksum failed`);
  const data=JSON.parse(raw);
  validateUpdate(name,data,data);
  if(name==='history' && data.dataBasis!=='public-source-history') throw new Error('Collect real ROI history before exporting fallbacks');
  const output=JSON.stringify(data,null,name==='snapshot'?2:0)+'\n';
  const file=path.join(target,name+'.json');
  await fs.writeFile(file+'.tmp',output);await fs.rename(file+'.tmp',file);
  datasets[name+'.json']={sha256:createHash('sha256').update(output).digest('hex'),sourceVersion:version};
  console.log(`Exported accepted ROI ${name}: ${data.time || data.first+' to '+data.last}`);
}
const edition={schema:1,automaticUpdates:false,description:'Bundled accepted ROI overview and real historical data for API-outage fallback. The live API updates separately.',datasets};
await fs.writeFile(path.join(target,'edition.json'),JSON.stringify(edition,null,2)+'\n');
