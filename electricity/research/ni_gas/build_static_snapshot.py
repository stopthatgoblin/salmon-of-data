"""Offline assembly of dated local previews from retained public source captures."""
import argparse, json, gzip, math, xml.etree.ElementTree as ET
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from collections import defaultdict
from electricity.research.ni_gas.estimate import GAS_UNITS,OIL_UNITS,model_parameters,fuel_rate,startup_fuel,gas_window
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--gas-day",type=date.fromisoformat,default=date(2026,11,8))
parser.add_argument("--source-dir",type=Path)
parser.add_argument("--capacity-references",action="store_true")
args=parser.parse_args()
if args.gas_day!=date(2026,11,8) and not args.source_dir:parser.error('Dated previews require --source-dir')
P=Path('outputs/gas-feasibility/static-2026-11-08');G=Path('outputs/gas-feasibility/2026-11-09')
if args.source_dir:P=G=args.source_dir
first,last=[t.replace(tzinfo=None) for t in gas_window(args.gas_day)]
cut=datetime.combine(args.gas_day+timedelta(days=1),datetime.min.time())
expected=[first+timedelta(minutes=30*n) for n in range(int((last-first).total_seconds()/1800))]
def stamp(s):return datetime.fromisoformat(s.replace('Z','+00:00')).replace(tzinfo=None)
register={e.get('UnitID'):e.get('UnitName') for e in ET.parse(P/'register.xml').getroot()}
tech={e.get('ResourceName'):e.attrib for e in ET.parse(P/'technical.xml').getroot() if e.get('ResourceType')=='GEN'}
# Technical offers contain some retired identifiers and one battery labelled MULTI_FUEL.
# Keep identifiers with meter coverage; exclude storage. Actual gas firing is an assumption.
roi={u for u,t in tech.items() if t.get('Jurisdiction')=='ROI' and t.get('FuelType') in ['GAS','MULTI_FUEL'] and u!='GU_404270'}
units=set(GAS_UNITS)|set(OIL_UNITS)|roi
meter={};meter_sources=[]
for p in sorted(Path('outputs/electricity-replay/reports').glob('PUB_DailyMeterDataD1*.gz')):
 d=json.loads(gzip.decompress(p.read_bytes()))
 for u,t,mw in d['rows']:
  if u in units:meter[u,stamp(t)]=mw
for name in [n for n in ['meter-6.xml','meter-7.xml','meter.xml'] if (P/n).exists()]:
 root=ET.parse(P/name).getroot();meter_sources.append(root.attrib['PublishTime'])
 for e in root:
  u=e.get('ResourceName')
  if u in units:meter[u,stamp(e.get('StartTime'))]=float(e.get('MeteredMW'))*2
roi={u for u in roi if (u,cut-timedelta(minutes=30)) in meter};units=set(GAS_UNITS)|set(OIL_UNITS)|roi
cut=next((t for t in expected if any((u,t) not in meter for u in units)),last)
assert all((u,t) in meter for u in units for t in expected if t<cut), 'Incomplete meter prefix'
assert all((u,t) not in meter for u in units for t in expected if t>=cut), 'Non-contiguous meter coverage'
estimated_hours=(last-cut).total_seconds()/3600
metered_hours=(cut-first).total_seconds()/3600
# Reconstruct the last five hours from effective targets, seeded at the final meter interval.
# Group status/target rows, with trips and desynchronisations handled explicitly.
groups=defaultdict(list)
for path in sorted(P.glob('dispatch-*.xml')):
 for e in ET.parse(path).getroot():
  if e.get('ResourceName') in units:
   groups[e.get('ResourceName'),stamp(e.get('InstructionTimeStamp')),stamp(e.get('InstructionIssueTime'))].append(e.attrib)
events=defaultdict(list)
for (u,t,issued),rows in groups.items():
 codes={r['InstructionCode'] for r in rows}
 nums=[float(r['DispatchInstruction']) for r in rows if r['InstructionCode']=='MWOF' and r.get('DispatchInstruction') is not None]
 value=0 if 'TRIP' in codes else max(nums) if nums else 0 if 'DESY' in codes else None
 events[u].append((t,issued,value,'+'.join(sorted(codes))))
for u in events:events[u].sort()
seed_at=cut-timedelta(minutes=30)
def target(u,t):
 eligible=[e for e in events[u] if seed_at<=e[0]<=t and e[1]<=t]
 if eligible:
  e=eligible[-1]
  if e[2] is None:raise ValueError(('Unknown dispatch state',u,t,e))
  return max(0,e[2])
 return max(0,meter[u,seed_at])
# Mid-minute integration gives the average target over each nominal half-hour.
for u in units:
 for n in range(int((last-cut).total_seconds()/1800)):
  t=cut+timedelta(minutes=30*n)
  meter[u,t]=sum(target(u,t+timedelta(minutes=m,seconds=30)) for m in range(30))/30
assert all((u,t) in meter for u in units for t in expected)
params=model_parameters(Path('outputs/gas-feasibility/unit-model/PUBLIC Validation 2024-2032 Model 2025-03-14.xml'))
ni_units=[]
for u,name in GAS_UNITS.items():
 curve=params[name];running=sum(fuel_rate(meter[u,t],curve)*.5 for t in expected);starts=[]
 for t in expected:
  if meter[u,t]<=1 or meter[u,t-timedelta(minutes=30)]>1:continue
  cursor=t-timedelta(minutes=30)
  while (u,cursor) in meter and meter[u,cursor]<=1:cursor-=timedelta(minutes=30)
  offline=(t-timedelta(minutes=30)-cursor).total_seconds()/3600
  fuel=startup_fuel(curve,offline,(u,cursor) in meter);starts.append({'time':t.isoformat(),'gjLhv':fuel})
 ni_units.append(dict(id=u,name=name,electricityGwh=sum(max(0,meter[u,t])*.5/1000 for t in expected),gasGwh=(running+sum(s['gjLhv'] for s in starts))*1.11/3600,starts=starts))
def gni(file,name=None,location=None,group=None):
 rows=json.loads((G/(file+'.json')).read_text())
 s=next(r for r in rows if (name is None or r['name']==name) and (location is None or r.get('location')==location) and (group is None or r.get('group')==group))
 values=[v/1e6 for epoch,v in s['data'] if datetime.fromtimestamp(epoch/1000,timezone.utc).date().isoformat()==args.gas_day.isoformat()]
 assert len(values)==1,(file,name,values)
 return values[0]
def demand(region):
 d=json.loads((P/(region+'-demand.json')).read_text());v={datetime.strptime(r['EffectiveTime'],'%d-%b-%Y %H:%M:%S'):r['Value'] for r in d['Rows'] if r['Region']==region.upper() and r['FieldName']=='SYSTEM_DEMAND'}
 ts=[first+timedelta(minutes=15*n) for n in range(int((last-first).total_seconds()/900))];assert all(t in v for t in ts)
 return sum(v[t]*.25/1000 for t in ts)
ni_total=gni('followup-commercialentry-fresh',name='Northern Ireland');ni_power=sum(u['gasGwh'] for u in ni_units)
roi_total=sum(gni('followup-gasconsumption-daily',location=k,group='Gas Consumption') for k in ['DM','NDM','ROI LDM'])
roi_power=gni('followup-gasconsumption-daily',location='ROI Power Gen',group='Gas Consumption')
print('ROI',roi_total,roi_power)
ni_elec=sum(u['electricityGwh'] for u in ni_units)
roi_units=[dict(id=u,name=register.get(u,u),electricityGwh=sum(max(0,meter[u,t])*.5/1000 for t in expected)) for u in sorted(roi)]
roi_elec=sum(u['electricityGwh'] for u in roi_units)
hourly=[]
d=json.loads((P/'physical-hourly.json').read_text())
for n in range(int((last-first).total_seconds()/3600)):
 t=first+timedelta(hours=n);v={}
 for loc,key in [('Moffat','scotland'),('Bellanaboy','corrib')]:
  s=next(r for r in d if r['location']==loc and r['group']=='Hourly Delivered Quantity of Gas')
  vals=[q/1e6 for epoch,q in s['data'] if datetime.fromtimestamp(epoch/1000,timezone.utc).replace(tzinfo=None)==t]
  assert len(vals)==1,(t,loc,vals);v[key]=vals[0]
 hourly.append(dict(time=t.isoformat()+'Z',**v))
def entsog_flow(file,point,direction):
 rows=json.loads((G/(file+'.json')).read_text())['operationaldatas']
 selected=[r for r in rows if r['pointKey']==point and r['directionKey']==direction and r['indicator']=='Physical Flow' and datetime.fromisoformat(r['periodFrom']).astimezone(timezone.utc).replace(tzinfo=None)==first]
 assert len(selected)==1 and not selected[0].get('isNA') and isinstance(selected[0]['value'],(int,float)),(file,point,selected)
 assert selected[0]['unit']=='kWh/d' and datetime.fromisoformat(selected[0]['periodTo']).astimezone(timezone.utc).replace(tzinfo=None)==last,(file,point,'Unexpected unit or period')
 return selected[0]['value']/1e6
flows=dict(scotland=gni('gni-physical-daily',location='Moffat',group='Daily Delivered Quantity of Gas'),corrib=gni('gni-physical-daily',location='Bellanaboy',group='Daily Delivered Quantity of Gas'),roiAllocated=gni('followup-commercialentry-fresh',name='Moffat'),niAllocated=ni_total,snipPhysical=entsog_flow('all-island-UK-TSO-0002-daily','ITP-00077','entry'),stranraer=entsog_flow('all-island-UK-TSO-0002-daily','DIS-00017','exit'),southNorth=entsog_flow('all-island-IE-TSO-0001-daily','ITP-00222','entry'))
assert abs(sum(r['scotland'] for r in hourly)-flows['scotland'])<.01
assert abs(sum(r['corrib'] for r in hourly)-flows['corrib'])<.01
regions={}
for key,total,power,elec in [('ni',ni_total,ni_power,ni_elec),('roi',roi_total,roi_power,roi_elec)]:
 dem=demand(key);regions[key]=dict(totalGas=total,powerGas=power,otherGas=total-power,electricity=elec,demand=dem,demandShare=elec/dem*100,powerShare=power/total*100)
data=dict(schema=1,gasDay=args.gas_day.isoformat(),fromUtc=first.isoformat()+'Z',toUtc=last.isoformat()+'Z',snapshotAsOf=(args.gas_day+timedelta(days=1)).isoformat(),flows=flows,regions=regions,hourly=hourly,units=dict(ni=ni_units,roi=roi_units),electricityBasis=dict(meteredHours=metered_hours,dispatchEstimateHours=estimated_hours,estimateFromUtc=cut.isoformat()+'Z',description=f'SEMO half-hour meters cover {metered_hours:g} hours; reconstructed dispatch targets cover the final {estimated_hours:g} hours, beginning {cut.isoformat()} UTC. Targets are seeded with the final meter half-hour. Gas firing is assumed for gas/multi-fuel units; battery storage is excluded.'),niGasBasis=dict(description='Unit-specific public SEM PLEXOS heat-input curves plus inferred start-up fuel; gross/net gas energy factor 1.11. NI other use is the entry allocation less estimated power use and includes balancing differences.',grossNetFactor=1.11),sources=json.loads((P/'fetch-sources.json').read_text()),notes=['GWh means one million kWh. All gas quantities use gross calorific energy; electricity output is a separate energy measure.','Scotland headline is physical flow at Moffat, including NI and ROI downstream and other small offtakes. NI/ROI branch amounts are commercial allocations, not separately measured IC1/IC2 landfalls. They cannot be used as an exact physical balance.','The SNIP entry at Twynholm includes a 0.332 GWh Scottish offtake at Stranraer. The displayed NI supply allocation is used for the usage residual.','IC1 and IC2 are shown geographically; no measured split is available. Isle of Man is outside the dashboard usage totals; its zero commercial allocation is not treated as proof of zero physical flow.','ROI total and power use are GNI reported market-sector consumption. NI total is a commercial entry allocation; NI power gas is estimated and the non-power figure is a residual, not a sector meter.','ROI electricity includes technical-offer gas/multi-fuel generating units with meter coverage, including CHP exports. Actual fuel switching, embedded own-use and unit operating behaviour can differ.','Reported gas supply, commercial allocations and consumer demand differ because of their measurement boundaries, linepack, balancing and revisions. No discrepancy is assigned to other use in ROI.'])
data['sources'].update(gniDailyPhysical='https://www.gasnetworks.ie/api/v1/physicalflows?date=2026-11-09&frequency=daily',gniConsumption='https://www.gasnetworks.ie/api/v1/gasconsumption?date=2026-11-09&frequency=daily',gniAllocations='https://www.gasnetworks.ie/api/v1/commercialentrypoint?date=2026-11-09&frequency=daily',snip='https://transparency.entsog.eu/api/v1/operationaldatas?operatorKey=UK-TSO-0002&from=2026-11-08&to=2026-11-09&periodType=day&indicator=Physical%20Flow&limit=500')
data['sources']['northSouth']='https://transparency.entsog.eu/api/v1/operationaldatas?operatorKey=IE-TSO-0001&pointKey=ITP-00222&directionKey=entry&from=2026-11-08&to=2026-11-09&periodType=day&indicator=Physical%20Flow&limit=100'
data['supplyUseComparison']=dict(shownSupplyGwh=flows['scotland']+flows['corrib'],shownUsageGwh=sum(r['totalGas'] for r in regions.values()),unreconciledDifferenceGwh=flows['scotland']+flows['corrib']-sum(r['totalGas'] for r in regions.values()),isleOfManPhysicalGwh=None,description='The difference mixes physical entry, commercial allocation and consumption boundaries. It is not a measure of Isle of Man use; Scottish offtakes, linepack, system use, timing and revisions also require reconciliation.')
if args.source_dir:
 data['sources'].update(gniDailyPhysical=data['sources']['gni-physical-daily.json'],gniConsumption=data['sources']['followup-gasconsumption-daily.json'],gniAllocations=data['sources']['followup-commercialentry-fresh.json'],snip=data['sources']['all-island-UK-TSO-0002-daily.json'],northSouth=data['sources']['all-island-IE-TSO-0001-daily.json'])
 data['capturedAt']=json.loads((P/'captured.json').read_text())['capturedAt']
 data['snapshotAsOf']=data['capturedAt'][:10]
data['reuse']=dict(gniPolicy='https://www.gasnetworks.ie/about/open-data',gniOperationalApiLicenceCoverageConfirmed=False,entsogTerms='https://transparency.entsog.eu/pdf/TRA0394_20161115_ENTSOG_TP_TC_of_Use_Rev_2_KNS_LG_KNS.pdf',entsogExtractionDate=data.get('capturedAt','2026-11-09')[:10],electricityLicence='https://www.smartgriddashboard.com/ni/open-data-license/')
if args.capacity_references:
 caprows=json.loads((P/'entsog-ptl-daily-capacity.json').read_text())['operationaldatas']
 cap=next(r for r in caprows if r['pointKey']=='ITP-00496' and r['directionKey']=='entry' and r['indicator']=='Firm Technical')
 assert not cap.get('isNA') and cap['unit']=='kWh/d' and isinstance(cap['value'],(int,float)) and cap['value']>0
 assert datetime.fromisoformat(cap['periodFrom']).astimezone(timezone.utc).replace(tzinfo=None)<=first and datetime.fromisoformat(cap['periodTo']).astimezone(timezone.utc).replace(tzinfo=None)>=last
 ni_cap=cap['value']/1e6;roi_cap=gni('gni-capacity-daily',location='Moffat',group='Technical Capacity');corrib_cap=gni('gni-capacity-daily',location='Bellanaboy',group='Technical Capacity')
 data['capacityReferences']=[]
 for key,label,quantity,capacity,numerator,source,note in [
  ('ni','SNIP inlet',flows['snipPhysical'],ni_cap,'Twynholm physical inflow',data['sources']['entsog-ptl-daily-capacity.json'],'NI entry-capacity reference at Moffat (NI). Twynholm does not publish a firm capacity; this ratio is a reference, not a measured SNIP hydraulic maximum. Includes the Scottish Stranraer offtake in the inlet flow.'),
  ('roi','ROI via Moffat',flows['roiAllocated'],roi_cap,'ROI Moffat allocation',data['sources']['gni-capacity-daily.json'],'ROI Moffat entry-capacity reference against the commercial ROI allocation. No per-IC1/per-IC2 measured flow split or corresponding operational pipe maximum is verified.'),
  ('corrib','Corrib / Bellanaboy',flows['corrib'],corrib_cap,'Bellanaboy physical inflow',data['sources']['gni-capacity-daily.json'],'Bellanaboy physical entry against its published technical entry capacity, not offshore reservoir production capacity.')]:
  assert math.isfinite(capacity) and capacity>0
  data['capacityReferences'].append(dict(key=key,label=label,quantityGwh=quantity,capacityGwhPerDay=capacity,percentage=quantity/capacity*100,numerator=numerator,source=source,note=note))
 data['notes'].append('Capacity percentages use published entry references and the named daily flow/allocation. They are not IC1/IC2 individual pipe maximum utilisation. North-South physical flow is shown separately and is not added to the NI commercial allocation without confirming its accounting boundary.')
out=Path('public/data/ireland-gas')/(args.gas_day.isoformat()+'.json');out.parent.mkdir(exist_ok=True,parents=True);out.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
print(json.dumps(dict(flows=flows,regions=regions,roiUnitCount=len(roi)),indent=2))
