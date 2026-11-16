"""Apply verified 16 November source review; preserve frozen scenarios."""
from pathlib import Path
import csv, datetime, hashlib, json, statistics, subprocess, sys

ROOT=Path(__file__).resolve().parents[1]
DAY='2026-11-16'; PUB=ROOT/'public/data'; APUB=PUB/'ai'; RAW=ROOT/'data/raw'/DAY; ARAW=ROOT/'data/ai/raw'/DAY
if (PUB/f'refresh-{DAY}.json').exists() or (APUB/f'refresh-{DAY}.json').exists():
    raise SystemExit('Refresh already applied; refusing to overwrite its audit trail.')
def read(p): return json.loads(p.read_text())
def write(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def capture(p,url,note): return {'file':DAY+'/'+p.name,'url':url,'bytes':p.stat().st_size,'sha256':sha(p),'retrievedOn':DAY,'note':note}
frozen={str(p.relative_to(ROOT)):sha(p) for p in [PUB/'scenarios-v1.json',APUB/'frozen-metrics-v1.json']}
old_report=read(PUB/'refresh-2026-11-06.json')
for n in ['roni.html','fao.csv','world-bank.xlsx']:
    assert sha(RAW/n)==sha(ROOT/'data/raw/2026-11-06'/n),f'{n} changed; review before proceeding'
noaa='https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml'
source=capture(RAW/'ensodisc.html',noaa,'NOAA ENSO diagnostic discussion issued 12 November; next discussion scheduled 10 December.')
source.update(name='NOAA ENSO Diagnostic Discussion',downloadUrl=noaa)
write(PUB/f'refresh-{DAY}.json',{'checkedAt':DAY,'newActuals':{},'metricsUpdated':{},'sources':[source],'checks':{'noaa':'November diagnostic discussion published; monthly RONI table remains unchanged since 6 November.','worldBankAndFao':'Current downloaded source files match 6 November captures.','retail':'October UK consumer prices scheduled for 18 November.'},'frozenFileSha256':frozen['public/data/scenarios-v1.json'],'policy':'Source review only; original forecast anchors and paths remain unchanged.'})
subprocess.run([sys.executable,str(ROOT/'scripts/build-data.py')],check=True,cwd=ROOT)

snapshot=read(ROOT/'data/ai/dashboard.json'); metrics={m['id']:m for m in snapshot['metrics']}; updates={}
def update(name,values,unit):
 m=metrics[name]; before={p['date']:p['value'] for p in m['data']}; vals={d:round(v,6) for d,v in values.items() if d>='2015-01-01'}
 assert set(before)<=set(vals),f'{name} source would remove accepted observations'
 added=[{'date':d,'value':v} for d,v in sorted(vals.items()) if d not in before]
 revised=[{'date':d,'previousValue':before[d],'value':v} for d,v in sorted(vals.items()) if d in before and abs(v-before[d])>0.0000005]
 m['data']=[{'date':d,'value':v} for d,v in sorted(vals.items())];m['actualsUpdatedAt']=DAY
 updates[name]={'observationsAdded':added,'revisedObservations':revised,'revisedObservationCount':len(revised),'latestObservation':m['data'][-1]}
 with (APUB/(name+'.csv')).open('w',newline='',encoding='utf-8') as f:
  w=csv.writer(f);w.writerow(['observation_date','metric_value','unit']);w.writerows((d,f'{v:.6f}'.rstrip('0').rstrip('.'),unit) for d,v in sorted(vals.items()))
families=['Software Development','Accounting','Marketing','Administrative Assistance','Customer Service','Banking & Finance']
all_us={r['date']:float(r['indeed_job_postings_index_SA']) for r in rows(ARAW/'indeed-us-all.csv') if r['jobcountry']=='US' and r['variable']=='total postings'}
sectors={}
for r in rows(ARAW/'indeed-us-sectors.csv'):
 if r['jobcountry']=='US' and r['variable']=='total postings' and r['display_name'] in families: sectors.setdefault(r['date'],{})[r['display_name']]=float(r['indeed_job_postings_index'])
inputs=[];vals={}
for d,s in sorted(sectors.items()):
 if d>='2020-02-01' and len(s)==6 and d in all_us:
  vals[d]=statistics.mean(s[n] for n in families)/all_us[d]*100;inputs.append([d,*[s[n] for n in families],all_us[d]])
update('recruitment',vals,'Relative recruitment · 1 Feb 2020 = 100')
with (APUB/'recruitment-excel-inputs.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.writer(f);w.writerow(['date',*families,'All US postings, seasonally adjusted']);w.writerows(inputs)
d=max(vals);metrics['recruitment']['components']=[{'label':'White-collar basket','value':f'{statistics.mean(sectors[d][n] for n in families):.1f}','detail':'Source index · Feb 2020 = 100'},{'label':'All US postings','value':f'{all_us[d]:.1f}','detail':'Source index · Feb 2020 = 100'}]
# Full FRED exports were unavailable; combine prior captured history with official
# published observations. November's CPI is not published until December.
def series(n):return {r['observation_date']:float(r[n]) for r in rows(ROOT/'data/ai/raw/2026-10-16'/(n+'.csv')) if r[n] and r[n]!='.'}
earnings=series('CES6000000003');earnings.update({'2026-08-01':45.83,'2026-09-01':46.10,'2026-10-01':46.25})
cpi=series('CPIAUCSL'); cpi.update({'2026-06-01':332.568,'2026-07-01':332.813,'2026-08-01':334.131,'2026-09-01':336.298,'2026-10-01':337.476})
ratios={d:earnings[d]/cpi[d] for d in earnings.keys()&cpi.keys()};base=statistics.mean(v for d,v in ratios.items() if d.startswith('2019-'))
update('real-pay',{d:v/base*100 for d,v in ratios.items()},'Index · 2019 average = 100')
assert updates['real-pay']['latestObservation']['date']=='2026-10-01'
snapshot['actualsReviewedAt']=snapshot['actualsUpdatedAt']=DAY
write(ROOT/'data/ai/dashboard.json',snapshot);write(APUB/'dashboard-snapshot.json',snapshot)
urls={'indeed-us-all.csv':'https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/aggregate_job_postings_US.csv','indeed-us-sectors.csv':'https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/job_postings_by_sector_US.csv','graduate-unemployment.csv':'https://www.newyorkfed.org/medialibrary/research/interactives/data/college-labor-market/college-labor-unemployment-data.csv','graduate-underemployment.csv':'https://www.newyorkfed.org/medialibrary/research/interactives/data/college-labor-market/college-labor-underemployment-data.csv'}
sources=[capture(ARAW/n,u,'Current source capture, including published revisions.') for n,u in urls.items()]
manifest=read(ROOT/'data/ai/source-manifest.json');manifest.extend(s for s in sources if not any(x['file']==s['file'] for x in manifest));write(ROOT/'data/ai/source-manifest.json',manifest);write(APUB/'source-manifest.json',manifest)
write(APUB/f'refresh-{DAY}.json',{'checkedAt':DAY,'sources':sources,'metricsUpdated':updates,'checks':{'realPay':'October seasonally adjusted CPI 337.476 and earnings $46.25; full CPI FRED CSV timed out. Recent FRED table values overlaid on retained full 16 October source captures; 2019 base preserved.','cpiSource':'https://fred.stlouisfed.org/series/CPIAUCSL','earningsSource':'https://fred.stlouisfed.org/series/CES6000000003','graduates':'Both downloads are byte-identical to 6 November; September 2026 remains latest.','frozen':'Anchors, paths and definitions unchanged.'},'frozenFileSha256':frozen})
cal=read(ROOT/'data/release-calendar.json');completed=[]
for e in list(cal['entries']):
 if e.get('date')=='2026-11-10' and e['title']=='US consumer prices':
  cal['entries'].remove(e);e.update(checkedAt=DAY,publishedAt='2026-11-10',importedAt=DAY,actualsAdded=['real-pay: 2026-10-01'],revisionsIncluded=[f"real-pay: {v['date']}" for v in updates['real-pay']['revisedObservations']]);completed.append(e)
 elif e.get('date')=='2026-11-12' and e['title']=='NOAA ENSO Diagnostic Discussion':
  cal['entries'].remove(e);e.update(checkedAt=DAY,publishedAt='2026-11-12',importedAt=DAY,actualsAdded=[],revisionsIncluded=[],note='November discussion published; next discussion scheduled 10 December. Frozen paths unchanged.');completed.append(e)
 elif e['title']=='NOAA ENSO Diagnostic Discussion' and e.get('month')=='2026-12':
  e.update(date='2026-12-10',status='Confirmed',checkedAt=DAY,note='NOAA confirms 10 December in the November discussion.',sourceUrl='https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.html')
cal['completedReleases']+=completed;cal['completedReleases'].sort(key=lambda e:(e.get('date') or e.get('month') or '',e['title']));cal['checkedAt']=cal['lastReleaseReviewAt']=DAY
write(ROOT/'data/release-calendar.json',cal);write(PUB/'release-calendar.json',cal)
ai=read(ROOT/'data/ai/release-calendar.json');ai.update(checkedAt=DAY,lastReleaseReviewAt=DAY,entries=[e for e in cal['entries'] if e['tracker']=='ai' and e.get('date')],provisional=[e for e in cal['entries'] if e['tracker']=='ai' and not e.get('date')],completedReleases=[e for e in cal['completedReleases'] if e['tracker']=='ai']);write(ROOT/'data/ai/release-calendar.json',ai);write(APUB/'release-calendar.json',ai)
assert all(sha(ROOT/p)==h for p,h in frozen.items())
print(json.dumps({'updates':{k:{'latest':v['latestObservation'],'added':len(v['observationsAdded']),'revisions':v['revisedObservationCount']} for k,v in updates.items()},'completed':[e['title'] for e in completed]},indent=2))
