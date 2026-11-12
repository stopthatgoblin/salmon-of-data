'use client';

import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ArrowDown, ArrowDownRight, ArrowRight, ArrowUpRight, ChevronDown, Flame, Info, Moon, X, Zap } from 'lucide-react';
import geography from '../roi-electricity/map-data.js';
import originalSnapshot from '@/public/data/ireland-gas/2026-11-08.json';
import { mountTheme } from '../electricity/theme.js';
import '../electricity/theme.css';
import './dashboard.css';

type Region = 'ni' | 'roi';
type View = 'overview' | 'sources';
type Flow = 'scotland' | 'corrib' | 'ni' | 'roi' | 'northSouth';
const f = (n: number, digits = 1) => n.toLocaleString('en-GB', { minimumFractionDigits: digits, maximumFractionDigits: digits });
const pct = (n: number) => `${Math.round(n)}%`;
const regions = { ni: { name: 'Northern Ireland', basis: 'Estimated' }, roi: { name: 'Republic of Ireland', basis: 'Reported' } };
const point = (lon: number, lat: number) => [(lon + 12.8) * 86 + 20, (56.1 - lat) * 150 + 20];
const at = (lon: number, lat: number) => point(lon, lat).join(',');
export type GasSnapshot = Omit<typeof originalSnapshot, 'sources' | 'units' | 'supplyUseComparison'> & {
  sources: Record<string, string>;
  units: {
    ni: { id: string; name: string; electricityGwh: number; gasGwh: number; starts: { time: string; gjLhv: number }[] }[];
    roi: { id: string; name: string | null; electricityGwh: number }[];
  };
  capturedAt?: string;
  version?: string;
  supplyUseComparison?: typeof originalSnapshot.supplyUseComparison;
  capacityReferences?: { key: string; label: string; quantityGwh: number; capacityGwhPerDay: number; percentage: number; numerator: string; source: string; note: string }[];
};

function presentation(snapshot: GasSnapshot, isLatest = false, isLive = false) {
const flows = snapshot.flows;
const total = snapshot.regions.ni.totalGas + snapshot.regions.roi.totalGas;
const power = snapshot.regions.ni.powerGas + snapshot.regions.roi.powerGas;
const corribUseShare = flows.corrib / total * 100;
const supplyUseGap = flows.scotland + flows.corrib - total;
const timeZone = 'Europe/Dublin';
const localDate = (value: string | Date, options: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat('en-GB', { timeZone, ...options }).format(new Date(value));
const gasStart = new Date(snapshot.fromUtc);
const gasEnd = new Date(snapshot.toUtc);
const gasHours = (gasEnd.getTime() - gasStart.getTime()) / 3_600_000;
const gasDate = localDate(gasStart, { day: 'numeric', month: 'long', year: 'numeric' });
const gasDateCompact = localDate(gasStart, { day: 'numeric', month: 'short', year: 'numeric' });
const gasDateWithWeekday = localDate(gasStart, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
const clock = (value: string | Date) => localDate(value, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const gasTimeZone = (new Intl.DateTimeFormat('en-GB', { timeZone, timeZoneName: 'short' }).formatToParts(gasStart).find(part => part.type === 'timeZoneName')?.value ?? '').replace(/GMT\+0$/, 'GMT');
const fullStamp = (value: Date) => localDate(value, { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'short' }).replace(/GMT\+0$/, 'GMT');
const extractionDate = snapshot.reuse.entsogExtractionDate.split('-').reverse().join('-');
const meteredHours = snapshot.electricityBasis.meteredHours;
const estimatedHours = snapshot.electricityBasis.dispatchEstimateHours;
const niUnitCount = snapshot.units.ni.length;
const snapshotUrl = snapshot.version ? `/api/gas/day/${snapshot.gasDay}.json?v=${snapshot.version}` : isLive ? '/data/ireland-gas/latest.json' : `/data/ireland-gas/${snapshot.gasDay}.json`;
const powerUseSummary = (() => {
  const share = power / total;
  const fractions: [number, string][] = [[.25, 'a quarter'], [1 / 3, 'a third'], [.5, 'half'], [2 / 3, 'two-thirds'], [.75, 'three-quarters']];
  const fraction = fractions.find(([value]) => Math.abs(share - value) < .015);
  return `About ${fraction ? fraction[1] : pct(share * 100)} of the island’s gas was used to generate electricity.*`;
})();
const gniReusePolicy = snapshot.reuse.gniPolicy;
const entsogReuseTerms = snapshot.reuse.entsogTerms;
const electricityLicence = snapshot.reuse.electricityLicence;

return { snapshot, isLatest, isLive, flows, total, power, corribUseShare, supplyUseGap, gasStart, gasEnd, gasHours, gasDate, gasDateCompact, gasDateWithWeekday, clock, localDate, gasTimeZone, fullStamp, extractionDate, meteredHours, estimatedHours, niUnitCount, snapshotUrl, powerUseSummary, gniReusePolicy, entsogReuseTerms, electricityLicence };
}
const GasContext = createContext(presentation(originalSnapshot));
const useGas = () => useContext(GasContext);

function Reading({ value, unit = 'GWh', estimated = false }: { value: number; unit?: string; estimated?: boolean }) {
  return <span className="gas-reading">{estimated && <span className="gas-approx" aria-label="approximately">≈</span>}{f(value)}<small>{unit}</small></span>;
}

function RegionCard({ region, open }: { region: Region; open: (region: Region) => void }) {
  const { snapshot } = useGas();
  const r = snapshot.regions[region];
  const info = regions[region];
  return <article className={`gas-region gas-region-${region}`}>
    <div className="gas-region-heading"><h3>{info.name}</h3><span className="gas-total"><b>{f(r.totalGas)}</b> GWh<small>{region === 'ni' ? 'gas allocated' : 'gas used'}</small></span></div>
    <div className="gas-split-track" role="img" aria-label={`${pct(r.powerShare)} of gas for electricity; ${pct(100 - r.powerShare)} for other uses`}><span style={{ width: `${r.powerShare}%` }} /><span style={{ width: `${100 - r.powerShare}%` }} /></div>
    <div className="gas-use-line"><span><Flame size={15} /> For electricity <em>{info.basis.toLowerCase()}</em></span><Reading value={r.powerGas} estimated={region === 'ni'} /></div>
    <div className="gas-electricity-result"><ArrowDownRight size={19} aria-hidden="true" /><div><p>Generated <strong>≈{f(r.electricity)} GWh</strong> of electricity</p><div className="gas-demand-line"><b>{pct(r.demandShare)}</b><span>of {region === 'ni' ? 'NI' : 'ROI'} electricity demand</span><Zap size={13} /></div><div className="gas-demand-track" aria-hidden="true"><span style={{ width: `${Math.min(100, r.demandShare)}%` }} /></div></div></div>
    <div className="gas-use-line gas-other-use"><span><span className="gas-colour-dot" /> Other uses <em>{region === 'ni' ? 'estimated remainder' : 'calculated remainder'}</em></span><Reading value={r.otherGas} estimated={region === 'ni'} /></div>
    <p className="gas-other-caption">Heating, business & industry{region === 'ni' ? ' · includes balancing' : ''}</p>
    <button className="gas-text-button gas-card-detail" onClick={() => open(region)}>How these figures are calculated <ArrowUpRight size={13} /></button>
  </article>;
}

function PipelineMap({ selected, select }: { selected: Flow | null; select: (flow: Flow | null) => void }) {
  const { flows, corribUseShare } = useGas();
  // Follow GNI's published overview: paired routes from Moffat, with Beattock
  // shown separately. This is a network schematic, not station inlet pipework.
  const scotlandStart = at(-3.44,55.33);
  // The cross-border link is drawn separately from its terminal connections for clarity.
  const northSouthPath = flows.southNorth < 0 ? 'M566 279 C548 306 541 340 550 371' : 'M550 371 C541 340 548 306 566 279';
  // GNI's network map shows two Scottish onshore pipes, IC1 to Loughshinny,
  // and IC2 to Gormanston with an Isle of Man tee. The sea routes cross
  // without a junction; a background casing on IC2 keeps that distinction clear.
  const isleOfManTee = at(-4.86, 54.30);
  const isleOfManSpur = `M${isleOfManTee} Q${at(-4.73,54.32)} 726,292`;
  const roiRoutes = [
    { id: 'IC1', route: `M${at(-4.12,54.79)} C${at(-5.15,54.4)} ${at(-5.4,53.82)} ${at(-6.08,53.55)}` },
    { id: 'IC2', route: `M${at(-4.12,54.79)} C${at(-4.45,54.55)} ${at(-4.60,54.48)} ${isleOfManTee} L${at(-4.98,54.19)} L${at(-5.15,54.21)} C${at(-5.55,53.99)} ${at(-5.98,53.75)} ${at(-6.22,53.64)}` },
  ];
  const dots = [
    { id: 'Moffat', lon: -3.44, lat: 55.33 }, { id: 'Beattock', lon: -3.43, lat: 55.26 }, { id: 'Twynholm', lon: -4.06, lat: 54.88 },
    { id: 'Brighouse Bay', lon: -4.12, lat: 54.79 }, { id: 'Ballylumford', lon: -5.78, lat: 54.85 },
    { id: 'Gormanston', lon: -6.22, lat: 53.64 }, { id: 'Loughshinny', lon: -6.08, lat: 53.55 },
    { id: 'Bellanaboy', lon: -9.78, lat: 54.23 },
  ];
  const buttonProps = (flow: Flow, name: string) => ({
    role: 'button', tabIndex: 0, 'aria-label': name, 'aria-pressed': selected === flow,
    onKeyDown: (e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(selected === flow ? null : flow); } },
  });
  const groupProps = (flow: Flow) => ({
    onClick: () => select(selected === flow ? null : flow),
    className: `gas-map-flow ${selected && selected !== flow ? 'gas-map-muted' : ''} ${selected === flow ? 'gas-map-selected' : ''}`,
  });
  return <svg className="gas-map" viewBox="85 70 830 710" role="group" aria-label="Gas pipelines from Scotland to Ireland, following GNI's overview schematic. Two Scottish routes are drawn from Moffat, with Beattock and Brighouse Bay compressor stations labelled separately and SNIP branching at Twynholm. IC1 lands at Loughshinny, IC2 at Gormanston, with an Isle of Man spur from IC2. The border between Northern Ireland and the Republic of Ireland is shown. Routes are approximate.">
    <defs>
      <marker id="gas-arrow-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M1 1 8 5 1 9" fill="none" stroke="var(--gas-import)" strokeWidth="1.7" /></marker>
      <marker id="gas-arrow-teal" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4" markerHeight="4" orient="auto"><path d="M1 1 8 5 1 9" fill="none" stroke="var(--teal)" strokeWidth="1.7" /></marker>
      <marker id="gas-arrow-north-south" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M1 1 8 5 1 9" fill="none" stroke="var(--gas-cross-border)" strokeWidth="1.7" /></marker>
    </defs>
    <g className="gas-map-geography" transform="matrix(.45263158 0 0 .45731707 288.86316 88.78049)">
      {(['Ireland', 'Scotland', 'England', 'Wales', 'Isle of Man'] as const).map(name => <path key={name} d={geography[name]} className={`gas-land ${name === 'Ireland' ? 'gas-roi-land' : ''}`} />)}
      <path d={geography['Northern Ireland']} className="gas-ni-land" />
      <path d={geography.lakes} className="gas-lakes" />
    </g>
    <text className="gas-map-country" x="810" y="99">SCOTLAND</text>
    <text className="gas-map-country gas-map-roi" x="450" y="530" textAnchor="middle"><tspan x="450">REPUBLIC</tspan><tspan x="450" dy="20">OF IRELAND</tspan></text>
    <text className="gas-map-country gas-map-ni" x="505" y="235" textAnchor="middle"><tspan x="505">NORTHERN</tspan><tspan x="505" dy="18">IRELAND</tspan></text>
    <text className="gas-map-sea" x="688" y="592" textAnchor="middle" transform="rotate(-9 688 592)">Irish Sea</text>
    <text className="gas-map-sea" x="165" y="590" transform="rotate(-80 165 590)">Atlantic Ocean</text>
    <g {...groupProps('scotland')}>
      <path className="gas-pipe gas-pipe-scotland" d={`M${scotlandStart} L${at(-3.70,55.19)} L${at(-3.84,55.04)} L${at(-4.06,54.88)} L${at(-4.12,54.79)}`} />
      <path className="gas-pipe gas-pipe-scotland" d={`M${scotlandStart} L${at(-3.43,55.26)} L${at(-3.59,55.18)} L${at(-3.72,55.04)} L${at(-3.93,54.88)} L${at(-4.12,54.79)}`} />
      <path className="gas-pipe-hit" d={`M${scotlandStart} L${at(-4.06,54.88)} L${at(-4.12,54.79)}`} />
      <g {...buttonProps('scotland', `Moffat: Scotland supply, ${f(flows.scotland)} GWh physical flow`)} className="gas-map-callout" transform="translate(560 80)"><rect width="192" height="83" /><text x="14" y="23" className="gas-map-callout-label">FROM SCOTLAND</text><text x="14" y="56" className="gas-map-callout-value">{f(flows.scotland)}<tspan className="gas-map-unit"> GWh</tspan></text><text x="14" y="73" className="gas-map-callout-note">Physical flow at Moffat</text></g>
      <path className="gas-map-leader" d={`M752 122 L${scotlandStart}`} />
    </g>
    <g {...groupProps('ni')}>
      <path className="gas-pipe gas-snip" d={`M${at(-4.06,54.88)} L${at(-4.63,54.87)} L${at(-5.05,54.86)} L${at(-5.78,54.85)}`} markerEnd="url(#gas-arrow-blue)" />
      <path className="gas-pipe-hit" d={`M${at(-4.06,54.88)} L${at(-5.78,54.85)}`} />
      <text x="700" y="193" className="gas-pipe-label">SNIP</text>
      <g {...buttonProps('ni', `SNIP pipeline to Northern Ireland; ${f(flows.niAllocated)} GWh allocated to NI`)} className="gas-map-callout gas-ni-callout"><rect x="560" y="215" width="151" height="39" /><text x="570" y="241" className="gas-route-value">{f(flows.niAllocated)}<tspan> GWh to NI*</tspan></text></g>
    </g>
    <g {...groupProps('roi')}>
      {roiRoutes.map(({ id, route }) => <g key={id}>{id === 'IC2' && <path className="gas-pipe-casing" d={route} />}<path className="gas-pipe gas-ic" data-pipeline={id} d={route} markerEnd="url(#gas-arrow-blue)" /><path className="gas-pipe-hit" d={route} /></g>)}
      <g {...buttonProps('roi', `IC1 and IC2 pipelines to Dublin and Meath; ${f(flows.roiAllocated)} GWh allocated to the Republic of Ireland`)} className="gas-map-callout gas-roi-callout" transform="translate(620 440)"><rect width="199" height="91" /><text x="14" y="23" className="gas-map-callout-label">TO THE REPUBLIC*</text><text x="14" y="55" className="gas-map-callout-value">{f(flows.roiAllocated)}<tspan className="gas-map-unit"> GWh</tspan></text><text x="14" y="78" className="gas-map-callout-note">IC1 + IC2 · combined allocation</text></g>
    </g>
    <g className="gas-iom-spur" role="group" aria-label="Isle of Man spur from IC2 to Glen Mooar. Route shown only; no measured flow is assigned.">
      <title>Isle of Man spur from IC2 to Glen Mooar. No measured flow is assigned.</title>
      <path className="gas-pipe gas-pipe-iom" d={isleOfManSpur} />
      <circle className="gas-iom-junction" cx={point(-4.86,54.30)[0]} cy={point(-4.86,54.30)[1]} r="3.5" />
      <circle className="gas-iom-terminal" cx="726" cy="292" r="3" />
    </g>
    <text className="gas-pipe-label" x="651" y="367" textAnchor="middle" transform="rotate(-48 651 367)">IC1</text>
    <text className="gas-pipe-label" x="631" y="334" textAnchor="middle" transform="rotate(-38 631 334)">IC2</text>
    <text className="gas-small-label gas-iom-label" x="776" y="307"><tspan x="776">Isle of Man</tspan><tspan x="776" dy="14">spur from IC2</tspan></text>
    <path className="gas-map-leader" d="M769 303 L744 303 L726 292" />
    <g {...groupProps('northSouth')}>
      <path className="gas-pipe gas-pipe-north-south" d={northSouthPath} markerEnd={flows.southNorth === 0 ? undefined : 'url(#gas-arrow-north-south)'} />
      <path className="gas-pipe-hit" d={northSouthPath} />
      <g {...buttonProps('northSouth', `North-South pipeline: ${f(Math.abs(flows.southNorth))} GWh, ${flows.southNorth === 0 ? 'no reported flow' : flows.southNorth > 0 ? 'towards Northern Ireland' : 'towards the Republic of Ireland'}`)} className="gas-map-callout gas-north-south-callout">
        <rect x="388" y="301" width="131" height="67" />
        <text x="402" y="320" className="gas-map-callout-label">North-South</text>
        <text x="402" y="345" className="gas-route-value">{f(Math.abs(flows.southNorth))}<tspan> GWh</tspan></text>
        <text x="402" y="359" className="gas-map-callout-note">{flows.southNorth === 0 ? 'No reported flow' : flows.southNorth > 0 ? 'ROI → NI' : 'NI → ROI'}</text>
      </g>
      <path className="gas-map-leader" d="M519 333 H545" />
    </g>
    <g {...groupProps('corrib')}>
      <path className="gas-pipe gas-pipe-corrib" d={`M${at(-11.05,54.35)} C${at(-10.67,54.35)} ${at(-10.25,54.27)} ${at(-9.78,54.23)}`} markerEnd="url(#gas-arrow-teal)" />
      <path className="gas-pipe-hit" d={`M${at(-11.05,54.35)} L${at(-9.78,54.23)}`} />
      <g transform={`translate(${at(-11.05,54.35)})`} className="gas-field"><circle r="20" /><circle r="5" /><path d="M-27 0h-7m61 0h7M0-27v-7m0 61v7" /></g>
      <g {...buttonProps('corrib', `Corrib gas field: ${f(flows.corrib)} GWh supplied via Bellanaboy, ${f(corribUseShare)}% of gas used across the island`)} className="gas-map-callout gas-corrib-callout" transform="translate(113 133)"><rect width="197" height="116" /><text x="14" y="24" className="gas-map-callout-label">CORRIB GAS FIELD</text><text x="14" y="58" className="gas-map-callout-value">{f(flows.corrib)}<tspan className="gas-map-unit"> GWh</tspan></text><text x="14" y="79" className="gas-map-callout-note">Irish offshore supply</text><text x="14" y="100" className="gas-map-callout-note">{f(corribUseShare)}% of gas used across the island*</text></g>
    </g>
    {dots.map(d => <circle key={d.id} cx={point(d.lon,d.lat)[0]} cy={point(d.lon,d.lat)[1]} r="3.8" className="gas-location-dot" />)}
    <g className="gas-place-labels">
      <text x="839" y="132">Moffat</text>
      <text x="845" y="158">Beattock</text><path className="gas-map-leader" d={`M838 155 L${at(-3.43,55.26)}`} />
      <text x="812" y="192">Twynholm</text><path className="gas-map-leader" d={`M805 194 L${at(-4.06,54.88)}`} />
      <text x="816" y="248"><tspan x="816">Brighouse</tspan><tspan x="816" dy="15">Bay</tspan></text><path className="gas-map-leader" d={`M810 241 L${at(-4.12,54.79)}`} />
      <text x="651" y="192" textAnchor="end">Ballylumford</text><path className="gas-map-leader" d={`M643 197 L${at(-5.78,54.85)}`} />
      <text x="526" y="411" textAnchor="end"><tspan x="526">Gormanston</tspan><tspan x="526" dy="15" className="gas-small-label">Co. Meath</tspan></text>
      <path className="gas-map-leader" d={`M533 407 L${at(-6.22,53.64)}`} />
      <text x="548" y="458" textAnchor="end"><tspan x="548">Loughshinny</tspan><tspan x="548" dy="15" className="gas-small-label">Co. Dublin</tspan></text>
      <path className="gas-map-leader" d={`M554 453 L${at(-6.08,53.55)}`} />
      <text x="315" y="346"><tspan x="315">Bellanaboy</tspan><tspan x="315" dy="15" className="gas-small-label">Co. Mayo</tspan></text><path className="gas-map-leader" d={`M312 336 L${at(-9.78,54.23)}`} />
    </g>
    <g className="gas-map-compass" transform="translate(130 695)"><text x="0" y="-12" textAnchor="middle">N</text><path d="M0 0v30m-5-23 5-7 5 7" /></g>
    <text className="gas-map-scale-note" x="882" y="746" textAnchor="end">Approximate routes · not to engineering scale</text>
  </svg>;
}

function HourlyChart() {
  const { snapshot, gasStart, gasEnd, clock, localDate } = useGas();
  const [hover, setHover] = useState<number | null>(null);
  const rows = snapshot.hourly;
  const chartMax = Math.max(4, Math.ceil(Math.max(...rows.map(row => row.scotland + row.corrib)) / 4) * 4);
  const active = rows[hover ?? 0] || rows[0];
  const hour = clock;
  const tickDates = Array.from({ length: 7 }, (_, i) => new Date(gasStart.getTime() + (gasEnd.getTime() - gasStart.getTime()) * i / 6));
  const tickDay = (date: Date) => localDate(date, { day: 'numeric', month: 'short' });
  return <section className="gas-hourly-section" aria-labelledby="gas-hourly-title">
    <div className="gas-section-heading"><div><span className="gas-kicker">THROUGH THE DAY</span><h2 id="gas-hourly-title">Gas arriving, hour by hour</h2></div><span className="gas-chart-unit">GWh in each hour <span>· reported physical flows</span></span></div>
    <div className="gas-chart-legend"><span><i className="gas-import-dot" /> From Scotland</span><span><i className="gas-corrib-dot" /> From Corrib</span><p>{hover === null ? 'Select an hour to see the figures' : `${hour(active.time)}-${hour(new Date(new Date(active.time).getTime()+3600000).toISOString())} · Scotland ${f(active.scotland,2)} · Corrib ${f(active.corrib,2)} GWh`}</p></div>
    <div className="gas-chart" onMouseLeave={() => setHover(null)}>
      <div className="gas-chart-grid" aria-hidden="true">{[4,3,2,1,0].map(n => <div key={n}><span>{n * chartMax / 4}</span></div>)}</div>
      <div className="gas-chart-bars">{rows.map((r,i) => <button key={r.time} className={hover === i ? 'is-active' : ''} onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)} onClick={() => setHover(i)} aria-label={`${localDate(r.time, { day: 'numeric', month: 'short', year: 'numeric' })}, ${hour(r.time)}: Scotland ${f(r.scotland,2)} GWh, Corrib ${f(r.corrib,2)} GWh`}><span className="gas-bar-corrib" style={{ height: `${r.corrib/chartMax*100}%` }} /><span className="gas-bar-import" style={{ height: `${r.scotland/chartMax*100}%` }} /></button>)}</div>
    </div>
    <div className="gas-chart-times" aria-hidden="true">{tickDates.map((date, i) => <span key={date.toISOString()}>{clock(date)}{(i === 0 || tickDay(date) !== tickDay(tickDates[i - 1])) && <><br /><small>{tickDay(date)}</small></>}</span>)}</div>
  </section>;
}

function Sources() {
  const { snapshot, snapshotUrl, fullStamp, gasStart, gasEnd, gasHours, flows, total, supplyUseGap, niUnitCount, meteredHours, estimatedHours, extractionDate, gniReusePolicy, entsogReuseTerms, electricityLicence } = useGas();
  return <section className="gas-sources" id="gas-sources" aria-labelledby="gas-sources-heading">
    <div className="gas-section-heading"><div><span className="gas-kicker">THE SMALL PRINT, IN PLAIN ENGLISH</span><h2 id="gas-sources-heading">What the numbers mean</h2></div><a href={snapshotUrl} download className="gas-text-button">Download this snapshot <ArrowDown size={14} /></a></div>
    <div className="gas-source-grid">
      <article><span className="gas-source-number">01</span><h3>One complete gas day</h3><p>All totals cover <strong>{fullStamp(gasStart)} to {fullStamp(gasEnd)}</strong>. A GWh is a million kWh. Gas energy going into a power station and electricity coming out are different measures; some energy is lost as heat.</p></article>
      <article><span className="gas-source-number">02</span><h3>Why supply and use differ</h3><p>Shown supply is {f(flows.scotland + flows.corrib)} GWh and usage is {f(total)} GWh, leaving a <strong>{f(supplyUseGap)} GWh difference</strong>. That is not a measurement of Isle of Man use. The supply readings and usage figures have different boundaries; Scottish offtakes, changes in gas stored in pipelines, system use and revisions can also contribute. The Isle of Man’s share has not been verified.</p></article>
      <article><span className="gas-source-number">03</span><h3>Reported in ROI, estimated in NI</h3><p>ROI gas use comes from GNI’s published sectors. Other use is total consumption less power use. NI uses its entry allocation as a supply proxy; power gas is calculated from <strong>{niUnitCount} individual units’ heat-input curves</strong> and estimated starts. The remaining NI gas includes non-electricity use and balancing differences.</p></article>
      <article><span className="gas-source-number">04</span><h3>Electricity output</h3><p>Electricity output uses <strong>{meteredHours} hours of SEMO meter data{estimatedHours > 0 && ` and ${estimatedHours} hours of reconstructed dispatch targets`}</strong>. Gas and multi-fuel units are assumed to burn gas. The demand percentages compare regional gas-fired output with all regional EirGrid/SONI electricity demand over the same {gasHours}-hour period; they do not trace where that electricity was consumed.</p></article>
    </div>
    <details className="gas-method-details"><summary>Calculation details & source links <ChevronDown size={16} /></summary><div><p>NI heat inputs use the public SEM 2024-2032 PLEXOS model, including no-load heat input, incremental heat rates and inferred start-up fuel. The gross/net gas energy conversion is {snapshot.niGasBasis.grossNetFactor}. Oil-only units and storage are excluded. NI’s other-use residual is entry allocation minus estimated power gas. These are research estimates and the model’s actual fuel switching is unobserved.</p><p>Electricity output divided by power-sector gas input is approximately {f(snapshot.regions.ni.electricity / snapshot.regions.ni.powerGas * 100)}% for NI and {f(snapshot.regions.roi.electricity / snapshot.regions.roi.powerGas * 100)}% for ROI. This is a different ratio from the electricity-demand percentages in the cards. Plant type, loading and start-up fuel affect conversion. NI gas is modelled while ROI gas is reported, and the gas and electricity coverage can differ, especially for CHP exports. These are indicative ratios, not audited fleet efficiencies.</p><p>SEMO’s MeteredMW field contains half-hour interval energy. Its interval MWh values are summed directly; reconstructed MW targets are integrated over time. ROI electricity includes gas/multi-fuel generating units with meter coverage, including CHP exports; it excludes unobserved on-site consumption. The {estimatedHours}-hour estimate starts on {fullStamp(new Date(snapshot.electricityBasis.estimateFromUtc))} and is seeded from the final published meter interval. Hourly and daily physical-flow series can differ slightly because of source precision and revisions; they are checked for agreement before publication.</p><p>SNIP physical entry at Twynholm was {f(flows.snipPhysical,3)} GWh, including a {f(flows.stranraer,3)} GWh offtake at Stranraer in Scotland. NI’s {f(flows.niAllocated,3)} GWh commercial allocation is used for the usage calculation. No zero physical flow is inferred from the Isle of Man’s zero commercial allocation. The North-South source reports {f(Math.abs(flows.southNorth),3)} GWh at entry for this day. It is shown separately and is not added to the NI commercial allocation without confirmation of its accounting boundary.</p><ul>
      <li><a href={snapshot.sources.gniDailyPhysical} target="_blank" rel="noreferrer">Gas Networks Ireland · physical entry flows ↗</a></li>
      <li><a href={snapshot.sources.gniConsumption} target="_blank" rel="noreferrer">Gas Networks Ireland · daily market-sector consumption ↗</a></li>
      <li><a href={snapshot.sources.gniAllocations} target="_blank" rel="noreferrer">Gas Networks Ireland · commercial entry allocations ↗</a></li>
      <li><a href={snapshot.sources.snip} target="_blank" rel="noreferrer">ENTSOG / Premier Transmission · SNIP physical flows ↗</a></li>
      <li><a href={snapshot.sources.northSouth} target="_blank" rel="noreferrer">ENTSOG / GNI (UK) · North-South physical flow ↗</a></li>
      <li><a href={snapshot.sources['meter.xml']} target="_blank" rel="noreferrer">SEMO · unit meter report ↗</a></li>
      <li><a href="https://www.smartgriddashboard.com/" target="_blank" rel="noreferrer">EirGrid Group · electricity demand ↗</a> · Supported by EirGrid Group Data · <a href={electricityLicence} target="_blank" rel="noreferrer">Open Data Licence ↗</a></li>
    </ul><h3 className="gas-reuse-heading">Pipeline layout</h3><p>The Scottish routes follow GNI’s published overview: two routes are drawn from Moffat, with Beattock and Brighouse Bay compressor stations labelled separately. The onshore system interconnects at Cluden. This is a network schematic, not a station piping or valve diagram. SNIP branches at Twynholm towards Ballylumford. IC1 lands at Loughshinny, Co. Dublin, and IC2 at Gormanston, Co. Meath. The Isle of Man spur connects IC2 to Glen Mooar on the Isle of Man; its flow has not been established here. The offshore routes cross without a junction. Routes and spacing are schematic. Sources: <a href="https://www.gasnetworks.ie/about/projects/south-west-scotland-onshore-system-security-upgrade" target="_blank" rel="noreferrer">GNI: Scottish system and Cluden interconnection ↗</a>, <a href="https://www.gasnetworks.ie/sites/default/files/2025-11/Action-17-SGER-Detailed-Proposal-April-2024-Strategic-Case.pdf#page=20" target="_blank" rel="noreferrer">GNI interconnector description and map ↗</a>, <a href="https://www.awjmarine.co.uk/wp-content/uploads/2021/06/CS0600_GNI_PipelineInspection_NtM_TitanDiscovery.pdf#page=2" target="_blank" rel="noreferrer">GNI survey notice: IC1/IC2 landfalls ↗</a>, <a href="https://www.mutual-energy.com/gas/" target="_blank" rel="noreferrer">Mutual Energy: SNIP ↗</a>.</p><h3 className="gas-reuse-heading">Data reuse</h3><p>Copyright Gas Networks Ireland. Source: <a href="https://www.gasnetworks.ie/" target="_blank" rel="noreferrer">gasnetworks.ie</a>. GNI’s <a href={gniReusePolicy} target="_blank" rel="noreferrer">open-data policy</a> provides CC BY 4.0 for covered datasets; it does not explicitly identify these operational API series. Their specific licence coverage has not been confirmed. GNI disclaims responsibility for data errors, omissions, availability and resulting loss. This presentation converts units, combines sectors and estimates NI power use.</p><p>North-South and SNIP: ENTSOG TP [{extractionDate}], <a href="https://transparency.entsog.eu/" target="_blank" rel="noreferrer">transparency.entsog.eu</a>, under the <a href={entsogReuseTerms} target="_blank" rel="noreferrer">Transparency Platform reuse terms</a>. Electricity: Supported by EirGrid Group Data, under its <a href={electricityLicence} target="_blank" rel="noreferrer">Open Data Licence</a>. These links describe the providers’ terms; no provider endorsement is implied.</p></div></details>
  </section>;
}

function DataCredits() {
  const { extractionDate, gniReusePolicy, entsogReuseTerms, electricityLicence } = useGas();
  return <section className="gas-data-credits" aria-label="Data sources and reuse terms">
    <p>Gas: © <a href="https://www.gasnetworks.ie/about/data-transparency" target="_blank" rel="noreferrer">Gas Networks Ireland</a> · <a href={gniReusePolicy} target="_blank" rel="noreferrer">Data reuse policy ↗</a> <span>North-South: <a href="https://transparency.entsog.eu/" target="_blank" rel="noreferrer">ENTSOG TP [{extractionDate}]</a> · <a href={entsogReuseTerms} target="_blank" rel="noreferrer">Reuse terms ↗</a></span></p>
    <p>Electricity: Supported by EirGrid Group Data · <a href={electricityLicence} target="_blank" rel="noreferrer">Open Data Licence ↗</a> <span>Map: <a href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noreferrer">Natural Earth · public domain ↗</a></span></p>
  </section>;
}

export default function IrelandGasDashboard({ snapshot = originalSnapshot, isLatest = false, live = false, controls }: { snapshot?: GasSnapshot; isLatest?: boolean; live?: boolean; controls?: ReactNode }) {
  const value = useMemo(() => presentation(snapshot, isLatest, live), [snapshot, isLatest, live]);
  return <GasContext.Provider value={value}><GasDashboardContents controls={controls} /></GasContext.Provider>;
}

function GasDashboardContents({ controls }: { controls?: ReactNode }) {
  const { snapshot, isLatest, isLive, flows, total, power, corribUseShare, supplyUseGap, gasStart, gasEnd, gasHours, gasDate, gasDateCompact, gasDateWithWeekday, clock, gasTimeZone, powerUseSummary, meteredHours, estimatedHours, niUnitCount } = useGas();
  const pageRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    if (pageRef.current) mountTheme(pageRef.current, controller.signal);
    return () => controller.abort();
  }, [snapshot.gasDay, snapshot.version]);
  const [view, setView] = useState<View>('overview');
  const [selected, setSelected] = useState<Flow | null>(null);
  const [detail, setDetail] = useState<Region | null>(null);
  const dialogRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!detail) return;
    const opener = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialogRef.current?.focus();
    return () => { document.body.style.overflow = previousOverflow; opener?.focus(); };
  }, [detail]);
  const flowNotes: Record<Flow,string> = {
    scotland: `Moffat received ${f(flows.scotland)} GWh from the Scottish system. The paired Scottish routes follow GNI’s overview, with Beattock and Brighouse Bay compressor stations labelled separately. The onshore system interconnects at Cluden. SNIP branches off at Twynholm towards NI; IC1 and IC2 leave Brighouse Bay towards ROI.`,
    ni: `The SNIP route leaves the Scottish network at Twynholm and lands at Ballylumford. ${f(flows.niAllocated)} GWh was commercially allocated to NI; this is the basis for the NI usage calculation.`,
    roi: `IC1 lands at Loughshinny, Co. Dublin; IC2 at Gormanston, Co. Meath, with a separate spur to the Isle of Man. ${f(flows.roiAllocated)} GWh was allocated to ROI through Moffat. Separate pipe flows and Isle of Man use are not assigned here.`,
    corrib: `The Corrib field, off the Mayo coast, supplied ${f(flows.corrib)} GWh through Bellanaboy. From there it enters the Republic’s transmission network.`,
    northSouth: `The North-South Pipeline connects the ROI and NI gas networks. GNI (UK) reported ${f(Math.abs(flows.southNorth))} GWh at the South North CSEP entry for this gas day. ${flows.southNorth === 0 ? 'No flow is reported, so no direction arrow is shown.' : flows.southNorth > 0 ? 'The arrow shows flow towards NI.' : 'The arrow shows flow towards ROI.'} Terminal connections are separated on this schematic for clarity.`,
  };
  return <main className="wrap ireland-gas-page"><div className="ireland-gas" ref={pageRef}>
    <div className="gas-page-heading"><div><span className="gas-eyebrow">ENERGY · DAILY BRIEFING</span><h1>The island’s <em>gas</em>, in a day.</h1><p>Where it came from, what it powered.</p></div><div className="gas-edition"><span><i /> {isLive ? 'Daily update · 19:00 Ireland time' : isLatest ? 'Latest data preview' : 'Original design preview'}</span><time dateTime={snapshot.gasDay}>{gasDateWithWeekday}</time><small>{gasHours} hours · {clock(gasStart)} to {clock(gasEnd)} {gasTimeZone}</small></div></div>
    <div className="gas-preview-controls">{isLive ? <span className="gas-kicker">ALL-IRELAND GAS</span> : <a href={isLatest ? '/dashboards/ireland-gas/' : '/dashboards/ireland-gas/latest/'}>{isLatest ? 'Compare with 8 November preview' : 'Open latest data preview'} <ArrowUpRight size={12} /></a>}<button type="button" className="theme-toggle" aria-label="Dark mode" aria-pressed="false" title="Switch to dark mode"><Moon size={15} /><span>Dark mode</span><span className="theme-toggle-track" aria-hidden="true" /></button></div>
    {controls}
    <div className="gas-toolbar"><div className="gas-tabs" role="tablist" aria-label="Gas dashboard views"><button role="tab" aria-selected={view === 'overview'} aria-controls="gas-overview" id="gas-tab-overview" onClick={() => setView('overview')}>Daily overview</button><button role="tab" aria-selected={view === 'sources'} aria-controls="gas-sources-panel" id="gas-tab-sources" onClick={() => setView('sources')}>Definitions & sources</button></div><a href="/dashboards/ni-electricity/" className="gas-electricity-link">Electricity dashboards <ArrowUpRight size={14} /></a><span className="gas-date-pill">{gasDateCompact.toUpperCase()} <span>·</span> {gasHours}H</span></div>
    <div className="gas-headlines" aria-label="All-island daily gas summary">
      <div><span><i className="gas-import-dot" /> From Scotland</span><Reading value={flows.scotland} /><p>Physical flow at Moffat</p></div>
      <div><span><i className="gas-corrib-dot" /> From Corrib</span><Reading value={flows.corrib} /><p>Irish offshore supply<br />{f(corribUseShare)}% of gas used across the island*</p></div>
      <div><span>Gas used across the island*</span><Reading value={total} estimated /><p>NI allocation + ROI consumption</p></div>
      <div><span><i className="gas-power-dot" /> Gas going to electricity</span><Reading value={power} estimated /><p><b>{pct(power/total*100)}</b> of all-island gas use*</p></div>
    </div>
    <section role="tabpanel" aria-labelledby="gas-tab-overview" id="gas-overview" hidden={view !== 'overview'}>
      <div className="gas-day-takeaway"><span className="gas-kicker">AT A GLANCE</span><p>{powerUseSummary}</p></div>
      <div className="gas-main-grid"><section className="gas-map-section" aria-labelledby="gas-map-title"><div className="gas-section-heading gas-map-heading"><h2 id="gas-map-title">The route to Ireland</h2><span>Select a pipeline to explore <ArrowUpRight size={12} /></span></div><PipelineMap selected={selected} select={setSelected} /><div className={`gas-flow-note ${selected ? 'is-selected' : ''}`} aria-live="polite"><Info size={15} /><p>{selected ? flowNotes[selected] : '*NI and ROI branch values are commercial allocations. IC1 and IC2 have no separate measured flow figures here. The Isle of Man spur branches from IC2; no flow is assigned. The North-South link is drawn apart for clarity.'}</p>{selected && <button onClick={() => setSelected(null)} aria-label="Clear selected pipeline"><X size={14} /></button>}</div></section>
      <aside className="gas-usage-section" aria-labelledby="gas-usage-title"><div className="gas-section-heading gas-usage-heading"><h2 id="gas-usage-title">How the gas was used</h2><span>{gasHours}-hour totals</span></div><RegionCard region="ni" open={setDetail} /><RegionCard region="roi" open={setDetail} /><p className="gas-usage-footnote"><span className="gas-colour-dot gas-power-dot" /> Gas for electricity <span className="gas-colour-dot" /> Other gas use<br />{estimatedHours > 0 ? `≈ Electricity totals include ${estimatedHours} hours of dispatch estimates.` : 'Electricity totals use metered output.'}</p></aside></div>
      <HourlyChart />
      <div className="gas-bottom-note"><p>*All-island usage combines reported ROI consumption with NI’s entry allocation. NI other use includes balancing differences. The {f(supplyUseGap)} GWh gap between supply and usage is not a measured Isle of Man flow.</p><button className="gas-text-button" onClick={() => { setView('sources'); window.scrollTo({ top: 190, behavior: 'smooth' }); }}>Read the methodology <ArrowUpRight size={14} /></button></div>
    </section>
    <section role="tabpanel" aria-labelledby="gas-tab-sources" id="gas-sources-panel" hidden={view !== 'sources'}><Sources /></section>
    <DataCredits />
    <div className="gas-dashboard-footer"><span>{isLive ? 'Daily snapshot' : 'Static snapshot'} · {gasDate} · {snapshot.capturedAt ? `sources fetched ${new Date(snapshot.capturedAt).toISOString().slice(0,16).replace('T',' ')} UTC` : 'no automatic refresh'}</span><span>SALMONOFDATA.COM</span></div>
    {detail && <div className="gas-dialog-backdrop" onClick={() => setDetail(null)}><section className="gas-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="gas-detail-title" ref={dialogRef} tabIndex={-1} onClick={e => e.stopPropagation()} onKeyDown={e => { if (e.key === 'Escape') setDetail(null); if (e.key === 'Tab') { const buttons = e.currentTarget.querySelectorAll<HTMLButtonElement>('button'); const first = buttons[0]; const last = buttons[buttons.length - 1]; if (e.shiftKey && (document.activeElement === first || document.activeElement === e.currentTarget)) { e.preventDefault(); last.focus(); } else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); } } }}><button className="gas-dialog-close" onClick={() => setDetail(null)} aria-label="Close calculation details"><X size={20} /></button><span className="gas-kicker">{gasDateCompact.toUpperCase()} · {gasHours}-HOUR GAS DAY</span><h2 id="gas-detail-title">{regions[detail].name}</h2><dl><div><dt>{detail === 'ni' ? 'Gas allocated to NI' : 'Reported total gas use'}</dt><dd>{f(snapshot.regions[detail].totalGas)} GWh</dd></div><div><dt>Gas used for electricity{detail === 'ni' ? ' · estimated' : ' · reported'}</dt><dd>{f(snapshot.regions[detail].powerGas)} GWh</dd></div><div><dt>Other use · difference</dt><dd>{f(snapshot.regions[detail].otherGas)} GWh</dd></div><div><dt>Gas-fired electricity · estimated</dt><dd>{f(snapshot.regions[detail].electricity)} GWh</dd></div><div><dt>All regional electricity demand</dt><dd>{f(snapshot.regions[detail].demand)} GWh</dd></div></dl><p>{detail === 'ni' ? `Power gas is calculated from ${niUnitCount} NI units’ heat-input curves and estimated starts. Other use is the entry allocation less this estimate, including balancing differences.` : 'GNI reports total and power-sector gas consumption. Other use is total consumption minus power-sector gas; it is not supply minus consumption.'}</p><p>Electricity uses {meteredHours} hours of metered output{estimatedHours > 0 && ` and ${estimatedHours} hours of reconstructed dispatch targets`}. Gas firing is assumed. Output ÷ regional demand gives the percentage shown.</p><button className="gas-text-button" onClick={() => { setDetail(null); setView('sources'); }}>Full definitions & sources <ArrowRight size={14} /></button></section></div>}
  </div></main>;
}
