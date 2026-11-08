import {reconcileSnapshot} from '../roi-electricity/balance.js';

export const replayMarkup = `<details class="replay-controls"><summary><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 6a7 7 0 1 1-1 6M1 3v5h5M10 5v5l3 2"/></svg>Time machine<span class="replay-mode">Explore the archive</span></summary><div class="replay-panel"><div class="replay-fields"><label>Date<input type="date" data-replay-date disabled></label><label>Time<select data-replay-time disabled><option>Choose a date</option></select></label><div class="replay-steps"><button type="button" data-replay-previous aria-label="Previous reading" disabled>←</button><button type="button" data-replay-next aria-label="Next reading" disabled>→</button></div><button type="button" data-replay-live disabled>Return to live</button></div><p class="replay-message" role="status">Loading the historical archive…</p></div></details>`;

const numeric = value => typeof value === 'number' && Number.isFinite(value);
const sumKnown = values => values.every(numeric) ? values.reduce((a,b)=>a+b,0) : null;
const clock = new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Dublin',hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZoneName:'short'});
const dayName = date => new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Dublin',day:'numeric',month:'short',year:'numeric'}).format(new Date(date));

// A historical view carries no current dispatch, capacity or forecast readings.
export function replaySnapshot(day, row, live, region) {
  if (day.schema !== 1 || day.region !== region || !Number.isFinite(Date.parse(row.time))) throw new Error('Invalid historical reading');
  if (day.unitIds.length !== row.outputs.length || !row.outputs.every(numeric) || day.gridKeys.length !== row.grid.length || !row.grid.every(numeric)) throw new Error('Incomplete historical reading');
  const captured=row.stationBasis==='captured-dispatch-proxy';
  const inputs = Object.fromEntries(day.gridKeys.map((key,i)=>[key,row.grid[i]]));
  const ids = new Map(day.unitIds.map((id,i)=>[id,i]));
  const start = new Date(Math.floor(Date.parse(row.time)/1800000)*1800000).toISOString();
  const end = new Date(Date.parse(start)+1800000).toISOString();
  const stations = live.stations.map(station => {
    const units = station.units.map(unit => {
      if (!ids.has(unit.id)) throw new Error('Missing historical station unit');
      const i = ids.get(unit.id), output = row.outputs[i];
      return {...unit, output, available:numeric(row.available?.[i])?row.available[i]:null, maximum:numeric(row.maximum?.[i])?row.maximum[i]:null,
        status:captured?'Archived dispatch estimate':'Metered half-hour average',basis:captured?'archived-dispatch':'historical-meter',dispatch:captured?{}:{effective:start,until:end}, availabilityIssued:null,availabilitySource:null,technicalSource:null};
    });
    return {...station,units,output:sumKnown(units.map(u=>u.output)),available:sumKnown(units.map(u=>u.available)),maximum:sumKnown(units.map(u=>u.maximum)),
      outputBasis:captured?'archived-dispatch-target-proxy':'historical-metered-average',note:captured?'Archived grid observation and last-published station dispatch estimates, with the capacity declarations captured at collection.':`Metered average for ${clock.format(new Date(start))} to ${clock.format(new Date(end))}. Grid readings are quarter-hour observations. Capacity is shown only where archived declarations are available.`};
  });
  const data = {...live,...inputs,time:row.time,retrievedAt:day.generatedAt??day.sources?.retrievedAt??row.time,stations,replay:true,dataBasis:'historical-reconstruction',expectedPeaks:null,
    availabilityPublished:null,dispatchPublished:null,dispatchCoverageThrough:null,availabilityBaseline:null,availabilityLatestSource:null,technicalSource:null,
    replayMeter:captured?null:{start,end},replayStationBasis:captured?'dispatch':'meter',replaySources:day.sources,
    sources:{grid:day.sources,plants:{}},sourceSnapshot:null};
  for (const key of ['demand','generation','wind','solar','moyle']) if (!numeric(inputs[key])) throw new Error('Missing historical grid input');
  if (region === 'ni') {
    data.northSouth = data.demand-data.generation-data.moyle;
    data.other = data.generation-data.wind-data.solar-stations.reduce((total,s)=>total+s.output,0);
    data.moyleAvailable = numeric(row.moyleAvailable)?row.moyleAvailable:null;
    return data;
  }
  if (!['eastWest','greenlink','niDemand','niGeneration'].every(key=>numeric(inputs[key]))) throw new Error('Missing historical ROI inputs');
  data.ni = {time:row.time,demand:inputs.niDemand,generation:inputs.niGeneration,moyle:inputs.moyle,dataBasis:'historical-reconstruction'};
  data.interconnectors = live.interconnectors.map(flow=>({...flow,value:flow.id==='eastWest'?inputs.eastWest:flow.id==='greenlink'?inputs.greenlink:-(inputs.niDemand-inputs.niGeneration-inputs.moyle)}));
  return reconcileSnapshot(data);
}

export function validateReplayManifest(data, region, live) {
  if (data.schema!==1 || data.region!==region || !data.days?.length || !Number.isFinite(Date.parse(data.first)) || !Number.isFinite(Date.parse(data.last))) throw new Error('Historical archive is unavailable');
  const stationIds=live.stations.map(s=>s.id);
  if (data.stationIds?.length!==stationIds.length || !stationIds.every(id=>data.stationIds.includes(id))) throw new Error('The archive is being updated for these stations');
  let previous='';
  for (const day of data.days) {
    const publicPath=new RegExp(`^(?:/data/electricity-replay/${region}/${day.date}\\.json|/api/electricity/replay/${region}/${day.date}\\.json\\?v=[a-f0-9]{24})$`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day.date)||day.date<=previous||!(day.count>0)||!publicPath.test(day.url??'')) throw new Error('Invalid archive index');
    previous=day.date;
  }
  return data;
}

export function mountReplay(root, region, initial, events, signal) {
  const bridge=new EventTarget();
  const controls=root.querySelector('.replay-controls');
  const date=controls.querySelector('[data-replay-date]'),time=controls.querySelector('[data-replay-time]');
  const previous=controls.querySelector('[data-replay-previous]'),next=controls.querySelector('[data-replay-next]'),liveButton=controls.querySelector('[data-replay-live]');
  const message=controls.querySelector('.replay-message'),mode=controls.querySelector('.replay-mode');
  let latest=initial,manifest,selectedDay,selectedRow,request=0,busy=false;
  const days=new Map();
  root.dataset.replayMode='live';
  const notify=()=>bridge.dispatchEvent(new CustomEvent('dashboard:replaymode'));
  function setBusy(value) {busy=value;controls.setAttribute('aria-busy',String(value));date.disabled=value||!manifest;time.disabled=value||!selectedDay;previous.disabled=value||!selectedDay;next.disabled=value||!selectedDay;}
  function renderSteps() {
    if (!selectedDay||!manifest) return;
    const dayIndex=manifest.days.findIndex(d=>d.date===selectedDay.date);
    previous.disabled=busy||(dayIndex===0&&selectedRow===0);
    next.disabled=busy||(dayIndex===manifest.days.length-1&&selectedRow===selectedDay.rows.length-1);
  }
  function show(rowIndex) {
    const data=replaySnapshot(selectedDay,selectedDay.rows[rowIndex],latest,region);
    selectedRow=rowIndex;time.value=String(rowIndex);root.dataset.replayMode='historical';
    mode.textContent='Historical view';liveButton.disabled=false;
    message.textContent=`Archive from ${dayName(manifest.first)}. Grid: 15-minute readings. Stations: ${data.replayStationBasis==='dispatch'?'archived dispatch estimates':'metered half-hour averages'}. Gaps are omitted.`;
    events.dispatchEvent(new CustomEvent('dashboard:snapshot',{detail:data}));
    notify();renderSteps();
  }
  async function fetchJSON(url) {
    const response=await fetch(url,{signal,cache:'no-cache'});
    if (!response.ok) throw new Error('This historical reading could not be loaded');
    return response.json();
  }
  async function chooseDay(value, index) {
    const entry=manifest?.days.find(d=>d.date===value),token=++request;
    if (!entry) {message.textContent='No complete dashboard is archived for this date. Choose another date; the current view is retained.';return;}
    setBusy(true);
    try {
      let data=days.get(value);
      if (!data || data.rows.length!==entry.count || data.rows.at(-1).time!==entry.last) {data=await fetchJSON(entry.url);if(token!==request||signal.aborted)return;days.set(value,data);}
      if(data.date!==value||!data.rows?.length||data.rows.length!==entry.count)throw new Error('Incomplete historical day');
      selectedDay=data;date.value=value;
      time.replaceChildren(...data.rows.map((row,i)=>{const option=document.createElement('option');option.value=String(i);option.textContent=clock.format(new Date(row.time));return option;}));
      const desired=Number.isInteger(index)?index:Math.max(0,data.rows.findLastIndex(row=>clock.format(new Date(row.time)).slice(0,5)<=clock.format(new Date(latest.time)).slice(0,5)));
      show(Math.min(data.rows.length-1,Math.max(0,desired)));
    } catch(error) {
      if (!signal.aborted&&token===request) message.textContent=`${error.message}. The current view is retained; choose the date again to retry.`;
    } finally {if(token===request&&!signal.aborted){setBusy(false);renderSteps();}}
  }
  async function loadArchive() {
    setBusy(true);
    try {
      let data;
      try {data=validateReplayManifest(await fetchJSON(`/api/electricity/replay/${region}/manifest.json`),region,latest);}
      catch(error){if(signal.aborted)throw error;data=validateReplayManifest(await fetchJSON(`/data/electricity-replay/${region}/manifest.json`),region,latest);}
      manifest=data;
      if (signal.aborted)return;
      date.min=manifest.days[0].date;date.max=manifest.days.at(-1).date;
      if (!selectedDay) {
        date.value=manifest.days.at(-1).date;
        await chooseDay(date.value);
      }
    } catch(error) {if(!signal.aborted)message.textContent=`${error.message}. Live readings remain available.`;}
    finally {if(!signal.aborted){setBusy(false);renderSteps();}}
  }
  controls.addEventListener('toggle',()=>{if(controls.open&&!busy)void loadArchive();},{signal});
  date.addEventListener('change',()=>void chooseDay(date.value),{signal});
  time.addEventListener('change',()=>{try{show(Number(time.value));}catch(error){message.textContent=error.message;}},{signal});
  async function step(direction) {
    if (busy||!selectedDay)return;
    const index=selectedRow+direction;
    if(index>=0&&index<selectedDay.rows.length){show(index);return;}
    const dayIndex=manifest.days.findIndex(d=>d.date===selectedDay.date)+direction;
    const entry=manifest.days[dayIndex];
    if(entry)await chooseDay(entry.date,direction>0?0:entry.count-1);
  }
  previous.addEventListener('click',()=>void step(-1),{signal});next.addEventListener('click',()=>void step(1),{signal});
  liveButton.addEventListener('click',()=>{++request;setBusy(false);renderSteps();root.dataset.replayMode='live';mode.textContent='Explore the archive';liveButton.disabled=true;events.dispatchEvent(new CustomEvent('dashboard:snapshot',{detail:latest}));message.textContent='Showing the latest live readings. Select a date to explore again.';notify();},{signal});
  for(const name of ['snapshot','history','clock'])bridge.addEventListener(`dashboard:${name}`,event=>{
    if(name==='snapshot'){latest=event.detail;if(root.dataset.replayMode==='historical')return;}
    events.dispatchEvent(new CustomEvent(`dashboard:${name}`,{detail:event.detail}));
  },{signal});
  return bridge;
}
