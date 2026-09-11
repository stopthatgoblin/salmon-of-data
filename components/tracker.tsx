'use client';
import { useRef, useState } from 'react';
import { ChartDownload } from '@/components/chart-download';
import { ChartLicence } from '@/components/chart-licence';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ReferenceArea } from 'recharts';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { chartRows, monthNumber, monthDate, type Point, type Paths } from '@/lib/chart-data';
import snapshot from '@/data/dashboard.json';
import frozen from '@/public/data/scenarios-v1.json';
import { niceScale } from '@/lib/axis';

type Metric={id:string;label:string;title:string;unit:string;geography:string;source:string;sourceUrl:string;history:Point[];latest:Point;anchor:Point;paths:Paths;description:string;why:string;mechanism:string;caveat:string;assumptions:string;frequency:string;decimals:number;historyStart:string;annual?:boolean;climate?:boolean;officialForecast?:number;analogues?:{period:string;change:number}[]};
const frozenMetrics=frozen.metrics as Record<string,{anchor:Point;paths:Paths;assumptions:string}>;
const metrics=(snapshot.metrics as Metric[]).map(m=>({...m,...frozenMetrics[m.id],latest:m.history[m.history.length-1]})).filter(m=>m.id!=='harvest').sort((a,b)=>a.id==='enso'?-1:b.id==='enso'?1:0);
const colours={actual:'#173e46',high:'#b03931',medium:'#bd8124',low:'#287d7e'};
const names={actual:'Published data',high:'High impact',medium:'Medium impact',low:'Low impact'};
const monthNames=['January','February','March','April','May','June','July','August','September','October','November','December'];
const monthLabel=(d:string,short=false)=>{const [y,m]=d.split('-').map(Number);return `${short?monthNames[m-1].slice(0,3):monthNames[m-1]} ${y}`};
function period(m:Metric,date:string){if(m.annual)return `${date.slice(0,4)}/${String(Number(date.slice(0,4))+1).slice(2)}`;if(m.climate){const n=monthNumber(date);return `${monthNames[(n-1)%12].slice(0,3)}–${monthLabel(monthDate(n+1),true)}`;}return monthLabel(date,true)}
const number=(v:number,m:Metric)=>new Intl.NumberFormat('en-GB',{minimumFractionDigits:m.decimals,maximumFractionDigits:m.decimals}).format(v);
function change(m:Metric){const prev=m.history.find(p=>monthNumber(p.date)===monthNumber(m.latest.date)-12);return prev?((m.latest.value/prev.value-1)*100):null}
function MetricChart({m}:{m:Metric}){
 const start=monthNumber('2023-01');
 const end=Math.max(monthNumber(m.climate?'2027-07':'2029-08'),monthNumber(m.latest.date));
 const rows=chartRows(m.history,m.paths,start,end,!!m.annual);
 const ticks:number[]=[];for(let x=start;x<=end;x+=12)ticks.push(x);
 const vals=rows.flatMap(r=>[r.actual,r.high,r.medium,r.low]).filter((v):v is number=>v!==null);
 const scale=niceScale(vals,m.climate?.5:m.id==='sugar'?.05:1);
 return <div className="chart-frame" role="img" aria-label={`${m.title}. Published history and three conditional scenarios. Exact values are available in the data table below.`}>
  <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{width:1000,height:335}}>
   <LineChart data={rows} margin={{top:22,right:20,left:3,bottom:8}} accessibilityLayer>
    <ReferenceArea x1={monthNumber(m.anchor.date)} x2={end} fill="#e8eee9" fillOpacity={.5}/>
    <CartesianGrid vertical={false} stroke="#d8dcd4" strokeDasharray="2 3"/>
    <XAxis dataKey="x" type="number" domain={[start,end]} ticks={ticks} tickFormatter={x=>m.annual?`${Math.floor(x/12)}/${String(Math.floor(x/12)+1).slice(2)}`:monthLabel(monthDate(x),true)} tickLine={false} axisLine={{stroke:'#a6b4b0'}} tick={{fill:'#596c70',fontSize:12}} minTickGap={32} dy={10}/>
    <YAxis domain={scale.domain} ticks={scale.ticks} tickFormatter={v=>m.id==='sugar'?`${Math.round(v*100)}¢`:m.unit.startsWith('US$')?`$${Math.round(v).toLocaleString('en-GB')}`:String(v)} tick={{fill:'#596c70',fontSize:12}} tickLine={false} axisLine={false} width={m.unit==='US$/tonne'?62:48} tickCount={5}/>
    {m.climate&&<ReferenceLine y={.5} stroke="#8b9690" strokeDasharray="3 4" label={{value:'El Niño threshold',position:'insideBottomLeft',fill:'#61716c',fontSize:12}}/>}
    <ReferenceLine x={monthNumber(m.anchor.date)} stroke="#93a39b" strokeDasharray="3 4"/>
    <Tooltip content={({active,payload,label})=>{if(!active||!payload?.length)return null;return <div className="chart-tooltip"><strong>{period(m,monthDate(Number(label)))}</strong>{[...payload].reverse().map(p=><div key={String(p.dataKey)}><span style={{color:p.color}}>{names[p.dataKey as keyof typeof names]}</span><b>{number(Number(p.value),m)} <small>{m.unit}</small></b></div>)}</div>}}/>
    {(['high','medium','low'] as const).map(k=><Line key={k} dataKey={k} type="linear" stroke={colours[k]} strokeWidth={2} strokeDasharray={k==='medium'?'7 4':k==='high'?'3 4':'10 5'} dot={m.annual?{r:3}:false} activeDot={{r:4}} connectNulls={false} isAnimationActive={false}/>)}
    <Line dataKey="actual" type="linear" stroke={colours.actual} strokeWidth={3} dot={m.annual?{r:4}:false} activeDot={{r:5,stroke:'#fffdf8',strokeWidth:2}} connectNulls={false} isAnimationActive={false}/>
   </LineChart>
  </ResponsiveContainer>
 </div>
}
function MetricPanel({m}:{m:Metric}){
 const chartRef=useRef<HTMLDivElement>(null);
 const freezeText=`Forecast frozen 7 September 2026. The most recent data then was ${period(m,m.anchor.date)}: ${number(m.anchor.value,m)} ${m.unit}. Later actuals extend the solid line over the unchanged dashed predictions; the original anchor never moves.`;
 const yoy=change(m);
 const checkpoint=m.paths.medium[1];
 return <div className="metric-panel">
  <div className="metric-intro"><div><p className="eyebrow">{m.geography}</p><h2>{m.title}</h2><p>{m.description}</p><p className="source">Source: <a href={m.sourceUrl} target="_blank" rel="noreferrer">{m.source} ↗</a> · Latest observation {period(m,m.latest.date)}</p></div><div className="metric-latest"><span>{m.annual?'Latest historical estimate':'Latest published'}</span><strong>{number(m.latest.value,m)}<small>{m.unit}</small></strong><span>{period(m,m.latest.date)}{!m.climate&&yoy!==null&&<> · <b>{yoy>=0?'+':''}{yoy.toFixed(1)}% YoY</b></>}</span></div></div>
<div className="chart-shell" ref={chartRef}><h3 className="chart-title">{m.label} — historical data and projections</h3><p className="chart-subtitle">{m.geography} · {m.id==='sugar'?'US cents/kg':m.unit} · Latest data: {period(m,m.latest.date)}</p><div className="chart-toolbar"><div className="chart-legend">{(['actual','high','medium','low'] as const).map(k=><span key={k}><i style={{borderColor:colours[k],borderTopStyle:k==='actual'?'solid':'dashed'}}/>{m.annual&&k==='actual'?'USDA estimates':names[k]}</span>)}</div></div>
  <div className="chart-labels"><span>{m.id==='sugar'?'US cents/kg':m.unit}{m.annual?' · marketing year':''}</span><span>Shaded area: conditional scenarios</span></div>
  <MetricChart key={m.id} m={m}/>
  <div className="chart-caption"><span className="chart-caption-text">{m.climate?'Seasons dated to their middle month. Scenarios end July 2027.':m.annual?'Annual estimates; connecting lines do not imply monthly observations.':'January 2023 – August 2029. Historical values are never interpolated.'}</span><span className="chart-actions"><a href={'/data/'+m.id+'.csv'} download>Download CSV ↓</a><ChartDownload chartRef={chartRef} filename={'salmonofdata-el-nino-'+m.id} freezeNote={freezeText}/></span></div><ChartLicence tracker="el-nino" metric={m.id}/><div className="chart-brand">SALMONOFDATA.COM</div></div>
  <p className="freeze-note"><strong>Forecast frozen 7 September 2026.</strong> The most recent data then was {period(m,m.anchor.date)}: {number(m.anchor.value,m)} {m.unit}. Later actuals extend the solid line over the unchanged dashed predictions; the original anchor never moves.</p><div className="scenario-heading"><h3>Three possible paths</h3><span>{period(m,checkpoint.date)} checkpoint · frozen 7 September 2026</span></div>
  <div className="scenario-grid">{(['low','medium','high'] as const).map(k=>{const p=m.paths[k][1];const delta=(p.value/m.anchor.value-1)*100;return <div className={'scenario-card '+k} key={k}><span>{names[k]}</span><strong>{number(p.value,m)} <small>{m.unit}</small></strong><p>{m.climate?`${k==='low'?'Earlier easing':k==='medium'?'Strong peak, then easing':'Higher, more persistent warming'}`:`${delta>=0?'+':''}${delta.toFixed(1)}% from the frozen anchor`}</p></div>})}</div>
  <div className="interpretation"><div><p className="eyebrow">What to watch</p><h3>{m.annual?'A lower yield means a bigger impact.':m.climate?'Strength is a signal, not a verdict.':'Watch for persistence, not a single jump.'}</h3><p>{m.why}</p><p className="mechanism">{m.mechanism}</p></div><div><p className="eyebrow">Keep in mind</p><p>{m.caveat}</p></div></div>
  <details className="data-details"><summary>Scenario assumptions & source notes <span>+</span></summary><div className="details-body"><p>{m.assumptions}</p><p>All paths are conditional illustrations. They are neither confidence intervals nor estimates of effects attributable solely to El Niño. Monthly paths interpolate linearly between saved checkpoints; annual harvest paths use annual checkpoints.</p><div className="source-grid"><div><span>Source</span><a href={m.sourceUrl} target="_blank" rel="noreferrer">{m.source} ↗</a></div><div><span>Update frequency</span><strong>{m.frequency}</strong></div><div><span>Available source history</span><strong>{m.historyStart.slice(0,4)} onwards</strong></div><div><span>Original anchor</span><strong>{number(m.anchor.value,m)} {m.unit} · {period(m,m.anchor.date)}</strong></div></div><div className="table-scroll"><table><caption>Frozen scenario checkpoints</caption><thead><tr><th>Period</th><th>Low impact</th><th>Medium impact</th><th>High impact</th></tr></thead><tbody>{m.paths.medium.slice(1).map((p,i)=><tr key={p.date}><th>{period(m,p.date)}</th><td>{number(m.paths.low[i+1].value,m)}</td><td>{number(p.value,m)}</td><td>{number(m.paths.high[i+1].value,m)}</td></tr>)}</tbody></table></div>{m.analogues&&<><h4>Historical context, not a forecasting model</h4><p>Price changes across four past El Niño episodes. Other shocks are included; this small sample is not used to assign probabilities to our scenarios.</p><div className="analogue-grid">{m.analogues.map(a=><div key={a.period}><span>{a.period}</span><strong>{a.change>=0?'+':''}{a.change}%</strong></div>)}</div></>}<a className="text-link" href="/data/scenarios-v1.json" download>Download the frozen assumptions ↓</a></div></details>
  <details className="data-details"><summary>View historical data <span>+</span></summary><div className="table-scroll history-table"><table><caption>{m.annual?'Historical USDA estimates':'Published observations'} · {m.unit}</caption><thead><tr><th>Period</th><th>Value</th></tr></thead><tbody>{[...m.history].reverse().map(p=><tr key={p.date}><th>{period(m,p.date)}</th><td>{number(p.value,m)}</td></tr>)}</tbody></table></div></details>
 </div>
}
export function Tracker(){const [active,setActive]=useState('enso');return <>

 <Tabs value={active} onValueChange={value=>setActive(String(value))} className="tracker-tabs"><div className="tabs-scroll"><TabsList className="metric-tabs" aria-label="Tracker metrics" variant="line">{metrics.map((m,i)=><TabsTrigger key={m.id} value={m.id}><span className="tab-number">{String(i+1).padStart(2,'0')}</span>{m.label}</TabsTrigger>)}</TabsList></div>{metrics.map(m=><TabsContent key={m.id} value={m.id}><MetricPanel m={m}/></TabsContent>)}</Tabs>
 </>}
