"""Collect ROI actuals and SEMO station proxies against an accepted NI version.

Cloud publication and scheduling are handled by electricity/roi_cloud.py.
Dispatch semantics follow the NI dispatch_proxy/analyse.py implementation.
"""
import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import math
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / 'runtime'
SNAPSHOT = ROOT.parent.parent / 'public/data/roi-electricity/snapshot.json'
REPORTS = 'https://reports.sem-o.com'
MAPPING = json.loads((ROOT/'units.json').read_text())['stations']
LAYOUT = json.loads((ROOT/'layout.json').read_text())
STATIONS = LAYOUT['stations']
UNITS = {unit for units in MAPPING.values() for unit in units}
FIELDS = [('ROI', name) for name in ['SYSTEM_DEMAND','GEN_EXP','WIND_ACTUAL','SOLAR_ACTUAL','INTER_EWIC','INTER_GRNLK']]
NOW = datetime.now(timezone.utc).replace(tzinfo=None)

def iso(value):
    return value.isoformat(timespec='seconds')+'Z'

def stamp(text):
    return datetime.fromisoformat(text.removesuffix('Z'))

def finite(value):
    return isinstance(value, (float,int)) and not isinstance(value,bool) and math.isfinite(value)

def fetch(url):
    request = Request(url, headers={'Eirgrid-Content-Request':'Nextjs','User-Agent':'SalmonOfDataROI/1'})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt+1)

def save_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    temporary.replace(path)

def report_index(name, **filters):
    items, page = [], 1
    while True:
        query = dict(name=name,sort_by='PublishTime',order_by='DESC',page_size=300,page=page,**filters)
        data = json.loads(fetch(REPORTS+'/api/v1/documents/static-reports?'+urlencode(query)))
        if page > 20:
            raise ValueError('Report pagination exceeds the collection bound')
        items.extend(data['items'])
        if page >= data['pagination']['totalPages']:
            return items
        page += 1

def download_report(item):
    path = CACHE/item['ResourceName']
    if not path.exists():
        raw = fetch(REPORTS+'/documents/'+item['ResourceName'])
        ET.fromstring(raw)
        path.write_bytes(raw)
    return item

def latest_report(name):
    url = REPORTS+'/api/v1/documents/static-reports?'+urlencode(dict(name=name,sort_by='PublishTime',order_by='DESC',page_size=1,page=1))
    items = json.loads(fetch(url))['items']
    if not items:
        raise ValueError('No public report: '+name)
    download_report(items[0])
    save_json(CACHE/(name+'-index.json'), {'items':[items[0]]})
    return items[0]

def download_grid(job):
    region, chart = job
    field = {'demand':'SYSTEM_DEMAND','generation':'GEN_EXP','wind':'WIND_ACTUAL','solar':'SOLAR_ACTUAL','interconnection':'INTER_MOYLE' if region=='NI' else 'INTER_EWIC'}[chart]
    for days in [0,1,7,27]:
        query = dict(region=region,chartType=chart,dateRange='custom',dateFrom=(NOW-timedelta(days=days)).strftime('%d-%b-%Y'),dateTo=NOW.strftime('%d-%b-%Y'),areas=chart+'actual' if chart!='interconnection' else 'interconnection')
        url = 'https://www.smartgriddashboard.com/api/chart/?'+urlencode(query)
        data = json.loads(fetch(url))
        save_json(CACHE/f'{region}-{chart}-{days}d.json',dict(url=url,retrievedAt=iso(datetime.utcnow()),data=data))
        actual = [datetime.strptime(r['EffectiveTime'],'%d-%b-%Y %H:%M:%S') for r in data.get('Rows',[]) if r.get('Region')==region and r.get('FieldName')==field and finite(r.get('Value'))]
        if actual and max(actual)>=NOW-timedelta(hours=1):
            return

def download_forecast(chart):
    for days in [0,1]:
        query = dict(region='ROI',chartType=chart,dateRange='custom',dateFrom=(NOW-timedelta(days=days)).strftime('%d-%b-%Y'),dateTo=NOW.strftime('%d-%b-%Y'),areas=chart+'forecast')
        url = 'https://www.smartgriddashboard.com/api/chart/?'+urlencode(query)
        data = json.loads(fetch(url))
        save_json(CACHE/f'ROI-{chart}-forecast.json',dict(url=url,retrievedAt=iso(datetime.utcnow()),data=data))
        if data.get('Rows'):
            return

def collect():
    CACHE.mkdir(exist_ok=True,parents=True)
    jobs = [('ROI',c) for c in ['demand','generation','wind','solar','interconnection']]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(download_grid,jobs))
    names = ['PUB_DailyRegisteredUnits','PUB_DlyGenUnitTechCharDataTrans','PUB_DailyTechnicalOfferData','PUB_DailyMeterDataD1']
    with ThreadPoolExecutor(max_workers=3) as pool:
        registered, baseline, technical, meter = list(pool.map(latest_report,names))
    start = min(baseline['Date'], (stamp(meter['Date'])+timedelta(days=1)).date().isoformat())
    if stamp(start) < NOW-timedelta(days=7):
        raise ValueError('SEMO baseline is too old for bounded collection')
    reports = []
    for name in ['PUB_HrlyDispatchInstr','PUB_HrlyOutturnAvailability']:
        reports.extend(report_index(name,date_from=start,date_to=NOW.date().isoformat()))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(download_report,reports))
    save_json(CACHE/'plant-report-manifest.json',reports)
    for chart in ['demand','wind','solar']:
        try:
            download_forecast(chart)
        except Exception as error:
            print('Optional forecast unavailable:',chart,type(error).__name__,flush=True)

def grid_capture(ni):
    values, provenance = {}, {}
    payloads = [json.loads(p.read_text()) for p in CACHE.glob('*.json') if p.name.startswith(('ROI-','NI-')) and 'forecast' not in p.name]
    for payload in sorted(payloads,key=lambda p:p['retrievedAt']):
        local = {}
        for row in payload['data'].get('Rows',[]):
            key = (row.get('Region'),row.get('FieldName'))
            if key not in FIELDS or not finite(row.get('Value')):
                continue
            at = datetime.strptime(row['EffectiveTime'],'%d-%b-%Y %H:%M:%S')
            if at>NOW:
                continue
            if (key,at) in local and local[key,at]!=row['Value']:
                raise ValueError('Conflicting values within a grid response')
            local[key,at] = row['Value']
        for (key,at),value in local.items():
            values.setdefault(key,{})[at] = value
            provenance[key,at] = dict(url=payload['url'],retrievedAt=payload['retrievedAt'])
    common = set.intersection(*(set(values.get(key,{})) for key in FIELDS))
    if not common:
        raise ValueError('No complete common ROI/NI timestamp; previous preview preserved')
    at = stamp(ni['time'])
    if at not in common:
        raise ValueError('ROI inputs do not cover the accepted NI observation time; retaining prior ROI')
    return at, {key:values[key][at] for key in FIELDS}, {':'.join(key):dict(time=iso(at),value=values[key][at],**provenance[key,at]) for key in FIELDS}

def report(name):
    meta = json.loads((CACHE/(name+'-index.json')).read_text())['items'][0]
    return meta, ET.parse(CACHE/meta['ResourceName']).getroot()

def station_capture(at):
    register_meta, register = report('PUB_DailyRegisteredUnits')
    baseline_meta, baseline = report('PUB_DlyGenUnitTechCharDataTrans')
    tech_meta, technical = report('PUB_DailyTechnicalOfferData')
    meter_meta, meter = report('PUB_DailyMeterDataD1')
    registered = {r.get('UnitID'):r.attrib for r in register if r.get('Status')=='Registered'}
    if not UNITS<=registered.keys():
        raise ValueError('Selected unit missing from current register')
    parameters, available, seeds = {}, {}, {}
    for row in technical:
        uid = row.get('ResourceName')
        if uid in UNITS and row.get('MaximumGeneration') is not None and stamp(row.get('StartTime'))<=at:
            if uid not in parameters or row.get('StartTime')>parameters[uid].get('StartTime'):
                parameters[uid] = row.attrib
    for row in baseline:
        uid = row.get('ResourceName')
        if uid in UNITS and row.get('OutturnAvailability') is not None and stamp(row.get('EffectiveTime'))<=at:
            key = (row.get('EffectiveTime'),row.get('IssueTime'))
            if uid not in available or key>available[uid]['key']:
                available[uid] = dict(key=key,value=float(row.get('OutturnAvailability')),issued=row.get('IssueTime'),source=baseline_meta['ResourceName'])
    for row in meter:
        uid = row.get('ResourceName')
        if uid not in UNITS or row.get('MeteredMW') is None:
            continue
        start = stamp(row.get('StartTime'))
        duration = (stamp(row.get('EndTime'))-start).total_seconds()
        if duration not in (1799,1800):
            raise ValueError('Unexpected meter interval')
        end = start+timedelta(minutes=30)
        if end<=at and stamp(meter_meta['PublishTime'])<=at and (uid not in seeds or end>seeds[uid]['time']):
            seeds[uid] = dict(time=end,value=float(row.get('MeteredMW'))/0.5,source=meter_meta['ResourceName'])
    groups = defaultdict(list)
    manifest = json.loads((CACHE/'plant-report-manifest.json').read_text())
    dispatch_reports = []
    for meta in sorted(manifest,key=lambda r:r['PublishTime']):
        if stamp(meta['PublishTime'])>NOW:
            continue
        dispatch = meta['ResourceName'].startswith('PUB_HrlyDispatchInstr_')
        if dispatch:
            dispatch_reports.append(meta)
        for row in ET.parse(CACHE/meta['ResourceName']).getroot():
            uid = row.get('ResourceName')
            if uid not in UNITS:
                continue
            if dispatch:
                effective, issued = stamp(row.get('InstructionTimeStamp')), stamp(row.get('InstructionIssueTime'))
                if effective<=at and issued<=at and (uid not in seeds or effective>=seeds[uid]['time']):
                    groups[uid,effective,issued,stamp(meta['PublishTime'])].append((row.attrib,meta['ResourceName']))
            elif row.get('OutturnAvailability') is not None and stamp(row.get('IssueTime'))<=at:
                issued = row.get('IssueTime')
                if uid not in available or issued>available[uid]['issued']:
                    available[uid] = dict(key=(issued,issued),value=float(row.get('OutturnAvailability')),issued=issued,source=meta['ResourceName'])
    events = {}
    for (uid,effective,issued,published),rows in sorted(groups.items()):
        codes = {r.get('InstructionCode') for r,_ in rows}
        numeric = [float(r['DispatchInstruction']) for r,_ in rows if r.get('InstructionCode')=='MWOF' and r.get('DispatchInstruction') is not None]
        value = 0.0 if 'TRIP' in codes else max(numeric) if numeric else 0.0 if 'DESY' in codes else None
        until = [stamp(r['InstructionEndTime']) for r,_ in rows if r.get('InstructionEndTime')]
        expired = bool(until and at>=max(until))
        events[uid] = dict(value=None if expired else value,basis='expired' if expired else '+'.join(sorted(codes)),effective=iso(effective),issued=iso(issued),published=iso(published),source=rows[0][1])
    result = {}
    fuel_names = {'GAS':'Natural gas','OIL':'Oil','MULTI_FUEL':'Multi-fuel','DISTILLATE':'Distillate oil','HYDRO':'Hydro','PUMP_STORAGE':'Pumped-storage hydro','BIOMASS':'Biomass'}
    for uid in UNITS:
        p, a = parameters.get(uid), available.get(uid)
        if p is None or a is None:
            raise ValueError('Missing published technical/availability data: '+uid)
        proxy = events.get(uid)
        if proxy is None:
            seed = seeds.get(uid)
            proxy = dict(value=seed['value'],basis='meter_seed',effective=iso(seed['time']),source=seed['source']) if seed else dict(value=None,basis='no_initial_state')
        name = registered[uid].get('UnitName') or uid
        if name=='TH':
            name += ' · '+uid.removeprefix('GU_')
        result[uid] = dict(id=uid,name=name,output=proxy['value'],available=a['value'],maximum=float(p['MaximumGeneration']),fuel=fuel_names.get(p.get('FuelType'),p.get('FuelType','Unknown')),basis=proxy['basis'],dispatch=proxy,availabilityIssued=a['issued'],availabilitySource=a['source'],technicalSource=tech_meta['ResourceName'])
    latest = max(dispatch_reports,key=lambda r:r['PublishTime'])
    coverage = datetime.strptime(Path(latest['ResourceName']).stem.rsplit('_',1)[1],'%Y%m%d%H%M')+timedelta(hours=1)
    first_hour = min(s['time'] for s in seeds.values()).replace(minute=0,second=0)
    expected = {first_hour+timedelta(hours=i) for i in range(int((coverage-first_hour).total_seconds()//3600))}
    present = {datetime.strptime(Path(m['ResourceName']).stem.rsplit('_',1)[1],'%Y%m%d%H%M') for m in dispatch_reports}
    missing = sorted(t for t in expected if t<coverage and t not in present)
    if missing:
        raise ValueError('Missing hourly dispatch reports; previous preview preserved')
    return result,dict(register=register_meta['ResourceName'],technical=tech_meta['ResourceName'],availabilityBaseline=baseline_meta['ResourceName'],meterSeed=meter_meta['ResourceName'],dispatchPublished=latest['PublishTime']+'Z',dispatchCoverageThrough=iso(coverage),dispatchCoverageAgeMinutes=round((at-coverage).total_seconds()/60,1),reportManifest='private-source-archive/plant-report-manifest.json')

def peaks(at):
    if at.date()!=NOW.date():
        return dict(demand=None,windSolar=None,date=at.date().isoformat())
    values, sources = {}, []
    for chart,field in [('demand','DEMAND_FORECAST_VALUE'),('wind','WIND_FCAST'),('solar','SOLAR_FCAST')]:
        path = CACHE/f'ROI-{chart}-forecast.json'
        payload = json.loads(path.read_text()) if path.exists() else None
        rows = payload['data'].get('Rows',[]) if payload else []
        if payload:
            sources.append(dict(chart=chart,url=payload['url'],retrievedAt=payload['retrievedAt']))
        values[chart] = {datetime.strptime(r['EffectiveTime'],'%d-%b-%Y %H:%M:%S'):r['Value'] for r in rows if r.get('Region')=='ROI' and r.get('FieldName')==field and finite(r.get('Value')) and datetime.strptime(r['EffectiveTime'],'%d-%b-%Y %H:%M:%S').date()==at.date()}
    periods = {at.replace(hour=0,minute=0,second=0)+timedelta(minutes=i) for i in range(0,1440,15)}
    renewable = max(values['wind'][t]+values['solar'][t] for t in periods) if periods<=values['wind'].keys()&values['solar'].keys() else None
    actual = {}
    for path in CACHE.glob('ROI-demand*.json'):
        if 'forecast' in path.name:
            continue
        for r in json.loads(path.read_text())['data'].get('Rows',[]):
            if r.get('Region')=='ROI' and r.get('FieldName')=='SYSTEM_DEMAND' and finite(r.get('Value')):
                t = datetime.strptime(r['EffectiveTime'],'%d-%b-%Y %H:%M:%S')
                if t.date()==at.date() and t<=at:
                    actual[t] = r['Value']
    required = {at.replace(hour=0,minute=0,second=0)+timedelta(minutes=i) for i in range(0,1440,30)}
    forecast = values['demand']
    missing = required-(actual.keys()|forecast.keys())
    boundary = {t for t in required if actual and forecast and max(actual)<t<min(forecast)}
    demand = max({**forecast,**actual}.values()) if actual and forecast and (not missing or missing<=boundary and len(boundary)<=2) else None
    combined = {**forecast,**actual}
    demand_time = min(t for t,value in combined.items() if value==demand).strftime('%H:%M') if demand is not None else None
    return dict(demand=demand,demandTime=demand_time,windSolar=renewable,date=at.date().isoformat(),sources=sources,basis='Demand combines reported actuals with remaining ROI forecasts; wind/solar uses matching quarter-hours across the whole forecast day. Missing forecasts are omitted.')

def build(ni):
    at, grid, provenance = grid_capture(ni)
    units, plant_sources = station_capture(at)
    snapshot = json.loads(SNAPSHOT.read_text())
    # Restored archives can predate station additions and layout changes.
    snapshot['stations'] = [dict(station) for station in STATIONS]
    for station in snapshot['stations']:
        station['units'] = [units[uid] for uid in MAPPING[station['id']]]
        for field in ['output','available','maximum']:
            station[field] = round(sum(u[field] for u in station['units']),4) if all(finite(u[field]) for u in station['units']) else None
        station['outputBasis'] = 'last-published-dispatch-target-proxy'
        station['note'] = 'Selected registered units. Output is a last-published dispatch-target estimate, seeded from the latest available meter report; it is not live metered output. A dash means the latest instruction does not establish a numeric output. Batteries are included in Other/Unallocated.'
        if station['id'] == 'aughinish':
            station['note'] += ' Aughinish Alumina CHP uses registered generating units SK3 and SK4. The demand-side unit is excluded. CHP generation and surplus grid export are different measures.'
        if station['id'] == 'tarbert-teg':
            station['note'] += ' Tarbert TEG is the existing temporary emergency plant, registered as TARBERT TEG 2. It is separate from the retired oil station and future HVO project. An earlier meter seed does not establish current operating status.'
        if station['id'] in ['north-wall-teg','shannonbridge-teg']:
            station['note'] += ' Temporary emergency generation, operated on the system operator\'s instruction. Earlier meter readings do not establish current operating status.'
    snapshot.update(dataBasis='public-source-capture',time=iso(at),capturedAt=iso(datetime.utcnow()),retrievedAt=max(p['retrievedAt'] for p in provenance.values()),demand=grid['ROI','SYSTEM_DEMAND'],generation=grid['ROI','GEN_EXP'],wind=grid['ROI','WIND_ACTUAL'],solar=grid['ROI','SOLAR_ACTUAL'],ni=dict(time=ni['time'],version=ni['version'],demand=ni['demand'],generation=ni['generation'],moyle=ni['moyle'],dataBasis='accepted-ni-snapshot'),expectedPeaks=peaks(at),sources=dict(grid=provenance,plants=plant_sources),northSouthBasis='ni-balance-reversed')
    for flow in snapshot['interconnectors']:
        flow['card'] = LAYOUT['interconnectorCards'][flow['id']]
        if flow['id'] == 'eastWest':
            flow['remoteLocation'] = [-4.64, 53.32]
        flow['value'] = grid['ROI','INTER_EWIC'] if flow['id']=='eastWest' else grid['ROI','INTER_GRNLK'] if flow['id']=='greenlink' else -(snapshot['ni']['demand']-snapshot['ni']['generation']-snapshot['ni']['moyle'])
    allocated = sum(s['output'] for s in snapshot['stations'] if finite(s['output']))
    snapshot['otherGeneration'] = snapshot['generation']-snapshot['wind']-snapshot['solar']-allocated
    snapshot['reconciliation'] = snapshot['demand']-snapshot['generation']-sum(f['value'] for f in snapshot['interconnectors'])
    snapshot['other'] = snapshot['otherGeneration']+snapshot['reconciliation']
    snapshot['unallocatedStations'] = [s['id'] for s in snapshot['stations'] if s['output'] is None]
    save_json(SNAPSHOT,snapshot)
    save_json(CACHE/'capture-summary.json',dict(time=snapshot['time'],capturedAt=snapshot['capturedAt'],grid=provenance,plants=plant_sources,unavailableStations=snapshot['unallocatedStations']))
    print(json.dumps({key:snapshot[key] for key in ['time','demand','generation','wind','solar','other','reconciliation','unallocatedStations']},indent=2))
    return snapshot
