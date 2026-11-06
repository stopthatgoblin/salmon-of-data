"""Import source captures and BLS published tables reviewed on 6 November 2026."""
from pathlib import Path
from datetime import datetime
import csv, hashlib, json, re, statistics, subprocess, sys
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
DAY = '2026-11-06'
RAW = ROOT/'data/raw'/DAY
ARAW = ROOT/'data/ai/raw'/DAY
PUB = ROOT/'public/data'
APUB = PUB/'ai'
if (PUB/f'refresh-{DAY}.json').exists() or (APUB/f'refresh-{DAY}.json').exists():
    raise SystemExit('Refresh already applied; refusing to overwrite its audit trail.')
def read(p): return json.loads(p.read_text())
def write(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def rows(p):
    with p.open(encoding='utf-8-sig',newline='') as f: return list(csv.DictReader(f))
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def capture(path,url,note,global_source=False):
    d={'file':DAY+'/'+path.name,'url':url,'bytes':path.stat().st_size,'sha256':digest(path),'retrievedOn':DAY,'note':note}
    if global_source: d.update(name=note.split(':')[0],downloadUrl=url)
    return d
frozen={str(p.relative_to(ROOT)):digest(p) for p in [PUB/'scenarios-v1.json',APUB/'frozen-metrics-v1.json']}
old=read(ROOT/'data/dashboard.json'); old_metrics={m['id']:m for m in old['metrics']}
book=openpyxl.load_workbook(RAW/'world-bank.xlsx',read_only=True,data_only=True)
ws=list(book['Monthly Prices'].values); headers=[str(v).strip() for v in ws[4]]
current={}
for name,col in {'rice':'Rice, Thai 5%','maize':'Maize','sugar':'Sugar, world','palm':'Palm oil','coffee':'Coffee, Robusta'}.items():
    i=headers.index(col)
    current[name]={r[0].replace('M','-'):float(r[i]) for r in ws[6:] if isinstance(r[0],str) and re.fullmatch(r'\d{4}M\d{2}',r[0]) and isinstance(r[i],(float,int))}
current['food']={r[0]:float(r[1]) for r in csv.reader((RAW/'fao.csv').open(encoding='utf-8-sig')) if len(r)>1 and re.fullmatch(r'\d{4}-\d{2}',r[0]) and r[1]}
current['enso']={}
for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',(RAW/'roni.html').read_text(),re.S):
    cells=[re.sub(r'<[^>]+>','',x).strip() for x in re.findall(r'<t[hd]\b[^>]*>(.*?)</t[hd]>',row,re.S)]
    if cells and re.fullmatch(r'\d{4}',cells[0]):
        for i,v in enumerate(cells[1:]):
            if re.fullmatch(r'-?\d+\.\d+',v): current['enso'][f'{cells[0]}-{i+1:02d}']=float(v)
updates={}; new_actuals={}
for name,values in current.items():
    prior={p['date']:p['value'] for p in old_metrics[name]['history']}
    added=[{'date':d,'value':v} for d,v in sorted(values.items()) if d>=min(prior) and d not in prior]
    revised=[{'date':d,'previousValue':prior[d],'value':v} for d,v in sorted(values.items()) if d in prior and abs(v-prior[d])>0.0000005]
    updates[name]={'observationsAdded':added,'revisedObservations':revised,'latestObservation':{'date':max(values),'value':values[max(values)]}}
    new_actuals[name]=added+[{'date':x['date'],'value':x['value']} for x in revised]
assert all(updates[n]['latestObservation']['date']=='2026-10' for n in ('food','rice','maize','sugar','palm','coffee'))
assert updates['enso']['latestObservation']=={'date':'2026-09','value':2.0}
urls={'world-bank.xlsx':'https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx','fao.csv':'https://www.fao.org/media/docs/worldfoodsituationlibraries/wfs-library/food_price_indices_data.csv?download=true&sfvrsn=523ebd2a_85','roni.html':'https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/'}
sources=[capture(RAW/n,u,{'world-bank.xlsx':'World Bank Pink Sheet: October commodity prices','fao.csv':'FAO Food Price Index: October index and revisions','roni.html':'NOAA RONI: August–October 2026 season'}[n],True) for n,u in urls.items()]
write(PUB/f'refresh-{DAY}.json',{'checkedAt':DAY,'newActuals':new_actuals,'metricsUpdated':updates,'sources':sources,'frozenFileSha256':frozen['public/data/scenarios-v1.json'],'policy':'Published observations and revisions only; frozen paths unchanged.'})
subprocess.run([sys.executable,str(ROOT/'scripts/build-data.py')],check=True,cwd=ROOT)

snapshot=read(ROOT/'data/ai/dashboard.json'); metrics={m['id']:m for m in snapshot['metrics']}; ai_updates={}
def update(name,values):
    metric=metrics[name]; old={p['date']:p['value'] for p in metric['data']}; vals={d:round(v,6) for d,v in values.items() if d>='2015-01-01'}
    assert set(old)<=set(vals), f'{name}: source would drop existing data'
    added=[{'date':d,'value':v} for d,v in sorted(vals.items()) if d not in old]
    revised=[{'date':d,'previousValue':old[d],'value':v} for d,v in sorted(vals.items()) if d in old and abs(old[d]-v)>0.0000005]
    metric['data']=[{'date':d,'value':v} for d,v in sorted(vals.items())]; metric['actualsUpdatedAt']=DAY
    ai_updates[name]={'observationsAdded':added,'revisedObservations':revised,'revisedObservationCount':len(revised),'latestObservation':metric['data'][-1]}
    with (APUB/(name+'.csv')).open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['observation_date','metric_value','unit']);
        units={'hiring':'Index · 2019 average = 100','employment':'Index · 2019 average = 100','real-pay':'Index · 2019 average = 100','recruitment':'Relative recruitment · 1 Feb 2020 = 100','graduates':'Recent minus all-graduate unemployment · percentage points','underemployment':'Employed recent graduates in non-graduate jobs · %'}
        w.writerows((d,f'{v:.6f}'.rstrip('0').rstrip('.'),units[name]) for d,v in sorted(vals.items()))
# Indeed original basket and unmodified methodology.
families=['Software Development','Accounting','Marketing','Administrative Assistance','Customer Service','Banking & Finance']
all_us={r['date']:float(r['indeed_job_postings_index_SA']) for r in rows(ARAW/'indeed-us-all.csv') if r['jobcountry']=='US' and r['variable']=='total postings'}
sectors={}
for r in rows(ARAW/'indeed-us-sectors.csv'):
    if r['jobcountry']=='US' and r['variable']=='total postings' and r['display_name'] in families: sectors.setdefault(r['date'],{})[r['display_name']]=float(r['indeed_job_postings_index'])
inputs=[]; recruitment={}
for d,s in sorted(sectors.items()):
    if d>='2020-02-01' and len(s)==6 and d in all_us:
        recruitment[d]=statistics.mean(s[n] for n in families)/all_us[d]*100; inputs.append([d,*[s[n] for n in families],all_us[d]])
update('recruitment',recruitment)
with (APUB/'recruitment-excel-inputs.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.writer(f);w.writerow(['date',*families,'All US postings, seasonally adjusted']);w.writerows(inputs)
d=max(recruitment);metrics['recruitment']['components']=[{'label':'White-collar basket','value':f'{statistics.mean(sectors[d][n] for n in families):.1f}','detail':'Source index · Feb 2020 = 100'},{'label':'All US postings','value':f'{all_us[d]:.1f}','detail':'Source index · Feb 2020 = 100'}]
def date(s): return datetime.strptime(s,'%m/%d/%Y').strftime('%Y-%m-%d')
grad=rows(ARAW/'graduate-unemployment.csv');under=rows(ARAW/'graduate-underemployment.csv')
update('graduates',{date(r['Date']):float(r['Recent graduates'])-float(r['College graduates']) for r in grad})
update('underemployment',{date(r['Date']):float(r['Recent graduates']) for r in under})
g=grad[-1];metrics['graduates']['components']=[{'label':'Recent graduates','value':f"{float(g['Recent graduates']):.1f}%",'detail':'Unemployment · ages 22–27'},{'label':'All graduates','value':f"{float(g['College graduates']):.1f}%",'detail':'Unemployment · ages 22–65'}]
# FRED CSV retrieval timed out. Retain the previous full captures and overlay the
# latest and revised values transcribed from the official BLS release tables.
base=ROOT/'data/ai/raw/2026-10-16'
def series(n): return {r['observation_date']:float(r[n]) for r in rows(base/(n+'.csv')) if r[n] and r[n]!='.'}
pro=series('JTS540099HIR');priv=series('JTS1000HIR');pro.update({'2026-08-01':4.3,'2026-09-01':4.1});priv['2026-09-01']=3.7
dates=sorted(pro.keys() & priv.keys()); ratios={}
for i in range(2,len(dates)):
    ds=dates[i-2:i+1]
    if all((int(ds[j][:4])*12+int(ds[j][5:7]))-(int(ds[j-1][:4])*12+int(ds[j-1][5:7]))==1 for j in (1,2)):
        ratios[dates[i]]=statistics.mean(pro[x] for x in ds)/statistics.mean(priv[x] for x in ds)
baseline=statistics.mean(v for d,v in ratios.items() if d.startswith('2019-'))
update('hiring',{d:v/baseline*100 for d,v in ratios.items()})
metrics['hiring']['components']=[{'label':'Professional & business','value':f"{statistics.mean(pro[x] for x in dates[-3:]):.2f}%",'detail':'Hires per employee · 3-month mean'},{'label':'Total private sector','value':f"{statistics.mean(priv[x] for x in dates[-3:]):.2f}%",'detail':'Hires per employee · 3-month mean'}]
sector=series('CES6054000001');private=series('USPRIV')
sector.update({'2026-08-01':10843.8,'2026-09-01':10848.4,'2026-10-01':10881.3});private.update({'2026-08-01':135724,'2026-09-01':135802,'2026-10-01':135961})
ratio={d:sector[d]/private[d] for d in sector.keys()&private.keys()};baseline=statistics.mean(v for d,v in ratio.items() if d.startswith('2019-')); update('employment',{d:v/baseline*100 for d,v in ratio.items()})
metrics['employment']['components']=[{'label':'Sector payroll jobs','value':'10.88m','detail':'Actual headcount level · latest month'},{'label':'High-path scale','value':'1.09m','detail':'Fewer jobs if total private jobs stay flat'}]
earnings=series('CES6000000003');earnings.update({'2026-08-01':45.83,'2026-09-01':46.10,'2026-10-01':46.25});cpi=series('CPIAUCSL');ratio={d:earnings[d]/cpi[d] for d in earnings.keys()&cpi.keys()};baseline=statistics.mean(v for d,v in ratio.items() if d.startswith('2019-')); update('real-pay',{d:v/baseline*100 for d,v in ratio.items()})
snapshot['actualsUpdatedAt']=snapshot['actualsReviewedAt']=DAY
write(ROOT/'data/ai/dashboard.json',snapshot);write(APUB/'dashboard-snapshot.json',snapshot)
ai_urls={'indeed-us-all.csv':'https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/aggregate_job_postings_US.csv','indeed-us-sectors.csv':'https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/job_postings_by_sector_US.csv','graduate-unemployment.csv':'https://www.newyorkfed.org/medialibrary/research/interactives/data/college-labor-market/college-labor-unemployment-data.csv','graduate-underemployment.csv':'https://www.newyorkfed.org/medialibrary/research/interactives/data/college-labor-market/college-labor-underemployment-data.csv'}
ai_sources=[capture(ARAW/n,u,'Exact source capture, including revisions.') for n,u in ai_urls.items()]
manifest=read(ROOT/'data/ai/source-manifest.json');manifest.extend(s for s in ai_sources if not any(x['file']==s['file'] for x in manifest));write(ROOT/'data/ai/source-manifest.json',manifest);write(APUB/'source-manifest.json',manifest)
bls={'jolts':'https://www.bls.gov/news.release/jolts.t02.htm','employment':'https://www.bls.gov/news.release/empsit.t17.htm','earnings':'https://www.bls.gov/news.release/empsit.t19.htm'}
write(APUB/f'refresh-{DAY}.json',{'checkedAt':DAY,'sources':ai_sources,'metricsUpdated':ai_updates,'checks':{'bls':'FRED CSV downloads timed out. Latest published BLS table values and revisions were transcribed over the retained 16 October full-series captures. October real pay awaits October CPI on 10 November.','blsTableUrls':bls,'graduates':'New York Fed source files now contain Q3; exact release day not supplied.','forecast':'Frozen anchors and paths unchanged.'},'frozenFileSha256':frozen})
# Move imported events to the audit trail; preserve exact dates only when known.
cal=read(ROOT/'data/release-calendar.json');completed=[]
for e in list(cal['entries']):
    t=e['title']; result=None
    if t=='NOAA Relative Oceanic Niño Index' and e.get('month')=='2026-11': result=['enso: 2026-09 = 2.0°C']
    elif t=='World Bank commodity prices' and e.get('date')=='2026-11-03': result=[f'{n}: 2026-10' for n in ('rice','maize','sugar','palm','coffee')]
    elif t=='FAO Food Price Index' and e.get('date')=='2026-11-06': result=['food: 2026-10 = 133.9']
    elif t=='US job openings and labour turnover' and e.get('date')=='2026-11-03': result=['hiring: 2026-09-01']
    elif t=='US employment situation' and e.get('date')=='2026-11-06': result=['employment: 2026-10-01','real-pay earnings input: 2026-10-01']
    elif t=='US graduate labour market' and e.get('month')=='2026-11': result=['graduates: 2026-09-01','underemployment: 2026-09-01']
    if result is not None:
        cal['entries'].remove(e); e.update(checkedAt=DAY,importedAt=DAY,actualsAdded=result)
        if t=='US graduate labour market': e['note']='Q3 data available in New York Fed source downloads; exact publication day not confirmed.'
        if t=='US employment situation': e['note']='October earnings captured; October real pay awaits the CPI release.'
        completed.append(e)
    elif t=='World Bank commodity prices' and e.get('month')=='2026-12':
        e.update(date='2026-12-02',status='Confirmed',checkedAt=DAY,note='Next update confirmed by the World Bank.')
cal['completedReleases']+=completed;cal['completedReleases'].sort(key=lambda x:(x.get('date') or x.get('month') or '',x['title']));cal['checkedAt']=cal['lastReleaseReviewAt']=DAY
write(ROOT/'data/release-calendar.json',cal);write(PUB/'release-calendar.json',cal)
ai_cal=read(ROOT/'data/ai/release-calendar.json');ai_cal.update(checkedAt=DAY,lastReleaseReviewAt=DAY,entries=[e for e in cal['entries'] if e['tracker']=='ai' and e.get('date')],provisional=[e for e in cal['entries'] if e['tracker']=='ai' and not e.get('date')],completedReleases=[e for e in cal['completedReleases'] if e['tracker']=='ai']);write(ROOT/'data/ai/release-calendar.json',ai_cal);write(APUB/'release-calendar.json',ai_cal)
assert all(digest(ROOT/p)==h for p,h in frozen.items())
print(json.dumps({'global':{k:v['latestObservation'] for k,v in updates.items()},'ai':{k:v['latestObservation'] for k,v in ai_updates.items()},'completed':[e['title'] for e in completed]},indent=2))
