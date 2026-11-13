'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, History } from 'lucide-react';
import IrelandGasDashboard from './dashboard';
import type { GasSnapshot } from './types';

type Day = { date: string; version: string; collectedAt: string; meteredHours: number; estimatedHours: number };
type Manifest = { schema: number; days: Day[]; latest: string; lastAttempt: string; lastSuccess: string; lastError: string | null;
  waitingForSource?: { source: string; gasDay: string; latestReportDate: string | null } | null };
const validDate = (value: string | null): value is string => !!value && /^\d{4}-\d{2}-\d{2}$/.test(value)
  && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10) === value;
const label = (value: string) => new Intl.DateTimeFormat('en-GB',{day:'numeric',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(value+'T12:00:00Z'));

function validSnapshot(input: unknown, day: string, version: string): input is GasSnapshot {
  const value = input as GasSnapshot;
  if (value?.schema !== 1 || value.gasDay !== day || value.version !== version || !Array.isArray(value.hourly) || value.hourly.length < 23 || value.hourly.length > 25) return false;
  return (['ni','roi'] as const).every(region=>{
    const row=value.regions?.[region];
    return row && ['totalGas','powerGas','otherGas','electricity','demand','demandShare','powerShare'].every(key=>Number.isFinite(row[key as keyof typeof row]));
  }) && ['scotland','corrib','niAllocated','roiAllocated','snipPhysical','stranraer','southNorth'].every(key=>Number.isFinite(value.flows?.[key as keyof typeof value.flows]))
    && !!value.reuse && !!value.sources && !!value.electricityBasis && !!value.niGasBasis && !!value.units?.ni && !!value.units?.roi;
}

export default function GasLiveDashboard() {
  const [snapshot,setSnapshot] = useState<GasSnapshot | null>(null);
  const [manifest,setManifest] = useState<Manifest | null>(null);
  const [selected,setSelected] = useState<string | null>(null);
  const [message,setMessage] = useState('Checking the daily archive…');
  const [loading,setLoading] = useState(true);
  const [problem,setProblem] = useState(false);
  const selection = useRef<string | null>(null);
  const epoch = useRef(0);
  const current = useRef({day:'',version:''});
  const controller = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const generation = ++epoch.current;
    setLoading(true);
    try {
      const response = await fetch('/api/gas/manifest.json',{cache:'no-cache',signal:abort.signal});
      if (!response.ok) throw new Error('archive');
      const index: Manifest = await response.json();
      if (index.schema !== 1 || !Array.isArray(index.days) || !index.days.length || !validDate(index.latest)
          || index.days.some(row=>!validDate(row.date)||!/^[a-f0-9]{24}$/.test(row.version))) throw new Error('archive');
      if (generation !== epoch.current) return;
      setManifest(index);
      const wanted = selection.current || index.latest;
      const record = index.days.find(row=>row.date === wanted);
      if (!record) {setProblem(true);setMessage('This date is not in the archive. Choose an available day.');return;}
      if (current.current.day !== wanted || current.current.version !== record.version) {
        let data: GasSnapshot | null = null;
        for (let attempt=0;attempt<3;attempt++) {
          const result=await fetch(`/api/gas/day/${wanted}.json?v=${record.version}`,{cache:'no-cache',signal:abort.signal});
          if (result.ok) {const value=await result.json();if(validSnapshot(value,wanted,record.version)){data=value;break;}}
          // A manifest can propagate before its immutable object. Retain the UI.
          if(attempt<2) await new Promise<void>((resolve,reject)=>{
            const timer=setTimeout(resolve,1500*(attempt+1));
            abort.signal.addEventListener('abort',()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));},{once:true});
          });
        }
        if (!data) throw new Error('day');
        if (generation !== epoch.current) return;
        setSnapshot(data);current.current={day:wanted,version:record.version};
      }
      const today = new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Dublin',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
      const due = new Date(today+'T12:00:00Z');due.setUTCDate(due.getUTCDate()-1);
      const localHour=Number(new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Dublin',hour:'2-digit',hourCycle:'h23'}).format(new Date()));
      if(localHour<19)due.setUTCDate(due.getUTCDate()-1);
      const late = index.latest < due.toISOString().slice(0,10);
      setProblem(!!index.lastError || late);
      const waiting = index.waitingForSource?.source === 'SEMO meter data' && validDate(index.waitingForSource.gasDay)
        ? `Waiting for SEMO meter data for ${label(index.waitingForSource.gasDay)}. Showing the last accepted day.` : null;
      setMessage(waiting || (index.lastError || late ? 'Update delayed. Showing the last accepted day.' : selection.current ? 'Historical view. Includes accepted revisions.' : 'Choose a gas day from the archive.'));
    } catch (error) {
      if (abort.signal.aborted || generation !== epoch.current) return;
      setProblem(true);
      setMessage(current.current.day ? 'Could not refresh. Showing the last loaded day.' : 'Gas data could not be loaded. Please retry.');
    } finally {if(generation===epoch.current)setLoading(false);}
  },[]);

  const choose = useCallback((day: string | null) => {
    selection.current=day;setSelected(day);
    const url=new URL(window.location.href);
    if(day)url.searchParams.set('date',day);else url.searchParams.delete('date');
    window.history.pushState({},'',url.pathname+url.search);
    void refresh();
  },[refresh]);

  useEffect(()=>{
    const readUrl=()=>{
      const requested=new URLSearchParams(window.location.search).get('date');
      selection.current=validDate(requested)?requested:null;setSelected(selection.current);void refresh();
    };
    readUrl();
    const poll=setInterval(()=>{if(!document.hidden)void refresh();},5*60*1000);
    const visible=()=>{if(!document.hidden)void refresh();};
    document.addEventListener('visibilitychange',visible);window.addEventListener('popstate',readUrl);
    return()=>{clearInterval(poll);controller.current?.abort();document.removeEventListener('visibilitychange',visible);window.removeEventListener('popstate',readUrl);};
  },[refresh]);

  useEffect(()=>{if(snapshot)document.title=`All-Ireland gas · ${label(snapshot.gasDay)} | Salmon of Data`;},[snapshot?.gasDay]);
  if(!snapshot)return <main className="wrap ireland-gas-page"><div className="ireland-gas gas-loading" aria-busy={loading}>
    <h1 className="gas-sr-only">All-Ireland gas</h1><p role="status">{loading?'Loading the gas archive…':message}</p>
    {!loading&&<><button type="button" className="gas-text-button" onClick={()=>void refresh()}>Retry</button>{selected&&<button type="button" className="gas-text-button" onClick={()=>choose(null)}>Show latest day</button>}</>}
    <noscript>This dashboard needs JavaScript. <a href="/api/gas/manifest.json">Download the daily archive index.</a></noscript>
  </div></main>;
  const days=manifest?.days || [];
  const active=days.findIndex(row=>row.date===(selected || manifest?.latest || snapshot.gasDay));
  const controls=<>
    <details className="gas-replay-controls" aria-label="Gas time machine">
      <summary><History size={17}/> Time machine <span className="gas-replay-mode">{selected?label(selected):'Explore the archive'}</span></summary>
      <div className="gas-replay-panel"><div className="gas-date-controls"><label htmlFor="gas-day">Gas day
      <select id="gas-day" value={selected||manifest?.latest||snapshot.gasDay} disabled={!days.length||loading} onChange={event=>choose(event.target.value)}>
        {days.map(row=><option key={row.date} value={row.date}>{label(row.date)}</option>)}
      </select></label>
      <button type="button" aria-label="Previous available gas day" disabled={loading||active<=0} onClick={()=>choose(days[active-1].date)}><ArrowLeft size={15}/></button>
      <button type="button" aria-label="Next available gas day" disabled={loading||active<0||active>=days.length-1} onClick={()=>choose(days[active+1].date)}><ArrowRight size={15}/></button>
      <button type="button" className="gas-return-latest" disabled={loading||!selected} onClick={()=>choose(null)}>Latest</button>
      </div><p role="status">{loading?'Loading…':message}</p></div>
    </details>
    {problem&&!loading&&<p className="gas-update-note" role="status">{message} Displayed: {label(snapshot.gasDay)}.</p>}
  </>;
  return <IrelandGasDashboard snapshot={snapshot} controls={controls}/>;
}
