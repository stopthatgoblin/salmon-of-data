'use client';
import { useRef, useState } from 'react';
import { ChartDownload } from '@/components/chart-download';
import { ChartLicence } from '@/components/chart-licence';


import { buildChartData, scenarioAt } from '@/lib/ai-chart-data';

import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
} from 'recharts';
import observedSnapshot from '@/data/ai/dashboard.json';
import frozenSnapshot from '@/public/data/ai/frozen-metrics-v1.json';
import { niceScale } from '@/lib/axis';
const snapshot={...observedSnapshot,horizon:frozenSnapshot.horizon,metrics:observedSnapshot.metrics.map(m=>{const original=frozenSnapshot.metrics.find(f=>f.id===m.id)!;return {...m,anchor:original.anchor,endpoints:original.endpoints};})};
import sources from '@/data/ai/source-manifest.json';

type Metric = (typeof snapshot.metrics)[number];
const colours = ['#267267', '#b07819', '#bf483b'];
const names = ['Low displacement', 'Medium displacement', 'High displacement'];
const monthNames=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const dateLabel=(d:string)=>`${monthNames[Number(d.slice(5,7))-1]} ${d.slice(0,4)}`;
const fmt = (v: number, m: Metric) =>
  `${v.toFixed(1)}${m.format === 'percent' ? '%' : m.format === 'pp' ? ' pp' : ''}`;
function MetricView({ m }: { m: Metric }) {
  const chartRef=useRef<HTMLElement>(null);
  const last = m.data.at(-1)!;
  const shown = last;
  const anchor = m.anchor;
  const records = buildChartData(m, snapshot.horizon);
  const scale=niceScale(records.flatMap(r=>[r.observed,r.s0,r.s1,r.s2]).filter((v):v is number=>typeof v==='number'),m.id==='canada-vacancies'?.1:1);
  const years = Array.from(
    { length: 2030 - Number(m.data[0].date.slice(0, 4)) },
    (_, i) => Date.UTC(Number(m.data[0].date.slice(0, 4)) + i, 0, 1),
  );
  const endpoint = scenarioAt(
    m,
    Date.parse(snapshot.horizon),
    snapshot.horizon,
  );
  const oneYear = Date.parse(
    m.period === 'quarter' ? '2027-09-30' : snapshot.checkpoint,
  );
  const proportion = Math.min(
    1,
    (oneYear - Date.parse(anchor.date)) /
      (Date.parse(snapshot.horizon) - Date.parse(anchor.date)),
  );
  const periodLabel = (d: string) =>
    m.period === 'quarter'
      ? `Q${Math.ceil(Number(d.slice(5, 7)) / 3)} ${d.slice(0, 4)}`
      : m.period === 'day'
        ? `${Number(d.slice(8,10))} ${dateLabel(d)}`
      : dateLabel(d);
  return (
    <>
      <section className="metric-intro">
        <div>
          <div className="eyebrow">
            {m.country} <span> / </span> {m.frequency}
          </div>
          <h2>{m.title}</h2>
          <p className="dek">{m.description}</p>
          <p className="source">
            Source:{' '}
            <a href={m.sourceUrl} target="_blank" rel="noreferrer">
              {m.source} ↗
            </a>{' '}
            <span>· Latest observation {periodLabel(last.date)}</span>
          </p>
        </div>
        <div className="metric-latest">
          <span>Latest reading</span>
          <strong>{fmt(shown.value, m)}</strong>
          <small>{periodLabel(shown.date)}</small>
        </div>
      </section>

      <section
        className="chart-shell" ref={chartRef}
        aria-label={`${m.title} historical chart and scenarios`}
      >
        <h3 className="chart-title">{m.tab} — historical data and projections</h3><p className="chart-subtitle">{m.country} · {m.unit} · Latest data: {periodLabel(last.date)}</p>
        <div className="chart-toolbar">
          <span>{m.unit}</span>
          <div className="chart-legend">
            <span>
              <i style={{ background: '#162f43' }} />
              Observed
            </span>
            {names.map((n, i) => (
              <span key={n}>
                <i className="dashed" style={{ borderColor: colours[i] }} />
                {n.replace(' displacement', '')}
              </span>
            ))}
          </div>
        </div>
        <div className="chart-frame">
          <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{width:1000,height:335}}>
            <LineChart
              data={records}
              margin={{ top: 28, right: 24, bottom: 8, left: 0 }}
            >
              <CartesianGrid vertical={false} stroke="#dce1e5" />
              <XAxis
                dataKey="time"
                type="number"
                scale="time"
                domain={['dataMin', 'dataMax']}
                ticks={years}
                tickFormatter={(v) => String(new Date(v).getUTCFullYear())}
                axisLine={false}
                tickLine={false}
                minTickGap={25}
                tick={{ fill: '#66737e', fontSize: 13 }}
              />
              <YAxis
                domain={scale.domain}
                ticks={scale.ticks}
                axisLine={false}
                tickLine={false}
                width={52}
                tick={{ fill: '#66737e', fontSize: 13 }}
                tickFormatter={(v) =>
                  Number(v).toFixed(m.id === 'canada-vacancies' ? 1 : 0)
                }
              />
              <ReferenceArea
                x1={Date.parse(anchor.date)}
                x2={Date.parse(snapshot.horizon)}
                fill="#edf1f3"
                fillOpacity={0.6}
              />
              <ReferenceLine
                x={Date.parse(anchor.date)}
                stroke="#8a969f"
                strokeDasharray="3 4"
                label={{
                  value: 'Scenarios →',
                  position: 'insideTopRight',
                  fill: '#65727d',
                  fontSize: 13,
                }}
              />
              <Tooltip
                labelFormatter={(v) =>
                  periodLabel(new Date(Number(v)).toISOString().slice(0, 10))
                }
                formatter={(v, name) => [fmt(Number(v), m), name]}
                contentStyle={{
                  border: '1px solid #dce1e5',
                  borderRadius: 2,
                  fontSize: 14,
                }}
              />
              {names.map((n, i) => (
                <Line
                  key={n}
                  name={n}
                  dataKey={'s' + i}
                  stroke={colours[i]}
                  strokeWidth={2}
                  strokeDasharray={i === 0 ? '8 4' : i === 1 ? '5 4' : '2 4'}
                  dot={false}
                  isAnimationActive={false}
                />
              ))}
              <Line
                name="Observed"
                dataKey="observed"
                stroke="#162f43"
                strokeWidth={2.6}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-caption">
          <span className="chart-caption-text">
            Solid line: published history. Dashed lines: illustrative paths, not
            estimated probabilities.
          </span>
          <span className="chart-actions"><a href={`/data/ai/${m.id}.csv`} download>Download CSV ↓</a><ChartDownload chartRef={chartRef} filename={'salmonofdata-ai-'+m.id} freezeNote={`Forecast frozen 6 September 2026. Latest data at the freeze: ${periodLabel(anchor.date)} — ${fmt(anchor.value,m)}. Future actuals overlay unchanged predictions. Horizon: December 2029.`}/></span>
        </div>
        <ChartLicence tracker="ai" metric={m.id}/><div className="chart-brand">SALMONOFDATA.COM</div>
      </section>
      <p className="freeze-note"><strong>Forecast frozen 6 September 2026.</strong> The most recent data then was {periodLabel(anchor.date)}: {fmt(anchor.value,m)}. Future actuals extend the solid line over these unchanged dashed predictions. Source revisions do not move the original forecast anchor.</p>
<div className="reading-strip">
        <p>
          <b>Reading the line:</b> {m.deltas[2] < 0 ? 'Lower' : 'Higher'} values
          are consistent with greater displacement pressure.
        </p>

      </div>
      {m.components.length > 0 && (
        <div className="components">
          {m.components.map((c) => (
            <div key={c.label}>
              <span>{c.label}</span>
              <b>{c.value}</b>
              <small>{c.detail}</small>
            </div>
          ))}
        </div>
      )}
      <section className="scenario-section">
        <div className="section-line">
          <h2>
            Tracking against three potential scenarios fixed in September 2026.
          </h2>
          <span>High / medium / low refers to displacement</span>
        </div>
        <div className="scenario-grid">
          {names.map((n, i) => (
            <article className="scenario-card" key={n} style={{ borderTopColor: colours[i] }}>
              <div className="scenario-name" style={{ color: colours[i] }}>
                {n}
              </div>
              <div className="target">
                {fmt(endpoint['s' + i], m)} <span>by Dec 2029</span>
              </div>
              <p>{m.impacts[i]}</p>
              <div className="checkpoint">
                {m.period === 'quarter' ? 'Q3' : 'Sep'} 2027 checkpoint{' '}
                <b>
                  {fmt(
                    anchor.value + (m.endpoints[i] - anchor.value) * proportion,
                    m,
                  )}
                </b>
              </div>
            </article>
          ))}
        </div>
      </section>
      <section className="interpretation">
        <div>
          <h3>What would change the evidence?</h3>
          <p>{m.test}</p>
        </div>
        <div>
          <h3>What this cannot tell us</h3>
          <p>{m.caveat}</p>
        </div>
      </section>
      <details className="data-details ai-method">
        <summary>
          Frozen definition & source notes{' '}
          <span>Version {snapshot.version} · 6 September 2026</span>
        </summary>
        <div>
          <p>{m.definition}</p>
          {m.id === 'recruitment' && (
            <p>
              <a
                className="worked-example-link"
                href="/data/ai/recruitment-worked-example.md"
                download
              >
                Worked Excel example ↓
              </a>{' '}
              ·{' '}
              <a
                className="worked-example-link"
                href="/data/ai/recruitment-excel-inputs.csv"
                download
              >
                Source inputs for Excel ↓
              </a>
            </p>
          )}
          {m.notes.map((n) => (
            <p key={n}>{n}</p>
          ))}
          <p>
            Scenario rule: a straight-line path from the frozen{' '}
            {periodLabel(anchor.date)} observation ({fmt(anchor.value, m)}) to
            December 2029. Endpoint changes are{' '}
            {m.deltas
              .map(
                (d) =>
                  `${d > 0 ? '+' : ''}${d}${m.mode === 'percent' ? '%' : ' percentage points'}`,
              )
              .join(', ')}{' '}
            for low, medium and high displacement. These are judgement-based,
            falsifiable scenario assumptions, not fitted forecasts or a no-AI
            counterfactual.
          </p>
          <p>
            The metric definition, source snapshot and forecast anchors are
            saved together. Future releases should be appended as observations
            without moving these original lines. Source revisions should be
            reported separately. Review sustained changes, not a single monthly
            surprise.
          </p>
          <p>
            <b>September 2027 review:</b> {snapshot.reviewRule}
          </p>
          <p className="source-downloads">
            Source downloads:{' '}
            {sources
              .filter((s) => m.sourceFiles.includes(s.file))
              .map((s) => (
                <a key={s.file} href={s.url} target="_blank" rel="noreferrer">
                  {s.file} ↗
                </a>
              ))}
          </p>
          <p>
            Displayed history starts in 2015 where available; original source
            files retain the longer published record. Missing periods are not
            interpolated. All plotted history is downloaded data or a disclosed
            calculation from it.
          </p>
        </div>
      </details>
    </>
  );
}
export function AITracker() {
 const [tab,setTab]=useState(snapshot.metrics[0].id);
 return <div className="ai-tracker"><Tabs value={tab} onValueChange={v=>setTab(String(v))} className="tracker-tabs"><div className="tabs-scroll"><TabsList variant="line" className="metric-tabs" aria-label="AI displacement metrics">{snapshot.metrics.map((m,i)=><TabsTrigger key={m.id} value={m.id}><span className="tab-number">{String(i+1).padStart(2,'0')}</span>{m.tab}</TabsTrigger>)}</TabsList></div>{snapshot.metrics.map(m=><TabsContent key={m.id} value={m.id}><div className="metric-panel"><MetricView m={m}/></div></TabsContent>)}</Tabs><section className="methodology"><p className="freeze-note">Actuals updated 13 September 2026: recruitment through 4 September and real pay through August. Forecasts remain frozen. <a href="/data/ai/refresh-2026-09-13.json" download>Download update details ↓</a></p><p className="eyebrow">Reading the evidence</p><h2>Evidence of displacement is not proof of AI causation.</h2><p>Read hiring, worker outcomes and adoption together. These are the original eight metrics, definitions and scenarios frozen on 6 September 2026. Forecasts end in December 2029; the first review is September 2027.</p><p className="freeze-note">{snapshot.reviewRule}</p><div className="method-links"><a href="/data/ai/frozen-metrics-v1.json" download>Frozen definitions ↓</a><a href="/data/ai/source-manifest.json" download>Source manifest ↓</a><a href="/#calendar">Data release calendar →</a><a href="/blog/">Why I built this tracker →</a></div></section></div>
}
