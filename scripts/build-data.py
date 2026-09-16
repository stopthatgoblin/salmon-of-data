"""Build a reproducible local snapshot from archived public source files.
Scenario definitions are judgement-based, versioned and never rebased by this script.
"""
from pathlib import Path
import csv, io, json, re, zipfile, hashlib, calendar
import openpyxl
ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw'; OUT=ROOT/'public/data'; OUT.mkdir(parents=True,exist_ok=True)
FREEZE='2026-09-07'
WB='https://www.worldbank.org/en/research/commodity-markets'
NOAA='https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/'
FAO='https://www.fao.org/worldfoodsituation/foodpricesindex/en/'
ONS='https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7bu/mm23'
USDA='https://apps.fas.usda.gov/PSDOnline/app/index.html'
sources=[('world-bank.xlsx','World Bank Pink Sheet',WB,'https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx'),('fao.csv','FAO Food Price Index',FAO,'https://www.fao.org/media/docs/worldfoodsituationlibraries/default-document-library/food_price_indices_data.csv?download=true&sfvrsn=523ebd2a_83'),('ons.json','ONS D7BU',ONS,ONS+'/data'),('roni.html','NOAA RONI (ERSSTv6)',NOAA,NOAA),('grains.zip','USDA Production, Supply & Distribution',USDA,'https://apps.fas.usda.gov/psdonline/downloads/psd_grains_pulses_csv.zip')]
manifest=[dict(file=f,name=n,url=u,downloadUrl=d,retrieved=FREEZE,sha256=hashlib.sha256((RAW/f).read_bytes()).hexdigest()) for f,n,u,d in sources]
book=openpyxl.load_workbook(RAW/'world-bank.xlsx',read_only=True,data_only=True)
rows=list(book['Monthly Prices'].values); headers=[str(x).strip() for x in rows[4]]
def commodity(name):
 i=headers.index(name)
 return [dict(date=r[0].replace('M','-'),value=float(r[i])) for r in rows[6:] if isinstance(r[0],str) and re.fullmatch(r'\d{4}M\d{2}',r[0]) and isinstance(r[i],(int,float))]
def metric(id,label,title,unit,geography,source,url,history,**extra):
 return dict(id=id,label=label,title=title,unit=unit,geography=geography,source=source,sourceUrl=url,history=history,frequency='Monthly',kind='price',decimals=1,**extra)
metrics=[]
fao=[]
for r in csv.reader((RAW/'fao.csv').open()):
 if r and re.fullmatch(r'\d{4}-\d{2}',r[0]) and r[1]:fao.append(dict(date=r[0],value=float(r[1])))
metrics.append(metric('food','Food basket','Is the global food bill rising?','index','Global · 2014–16 = 100','FAO Food Price Index',FAO,fao,
 description='A broad measure of internationally traded food prices. It shows whether pressure is spreading across the food basket.',
 why='The headline outcome: a persistent rise across food categories would support the case for a wider price shock.',
 caveat='Export-weighted commodity prices, not supermarket prices. Energy, trade policy and currencies also matter. Recent meat prices include estimates and the index can be revised.',
 mechanism='Regional harvest losses → tighter internationally traded supplies → a more expensive food basket.',
 assumptions='Peak uplifts of 5%, 15% and 30% by June 2027. By August 2029, prices are 4%, 8% and 15% above the frozen anchor. These are judgement-based total-price scenarios, not estimates of the portion caused by El Niño.',
 rates={'low':[5,4,3,4],'medium':[15,12,7,8],'high':[30,25,16,15]},peak='2027-06'))
for spec in [
 ('rice','Rice','The price of a staple','Rice, Thai 5%','US$/tonne','Thai 5% broken · export benchmark',
  'Rice connects Asian growing conditions with the food bills of import-dependent countries.',
  'Drought in exposed Asian growing regions → lower rice availability → pressure on export prices.',
  'Export restrictions, government stocks and exchange rates can dominate weather effects. One benchmark does not represent all rice varieties.',[0,-2,0,3],[18,12,5,6],[40,30,15,12],'2027-06'),
 ('maize','Maize','From the harvest to the feed bill','Maize','US$/tonne','International · US maize benchmark',
  'Maize is both a staple and animal feed, connecting harvest conditions with meat and dairy costs.',
  'Poor harvests → tighter grain and feed supplies → higher costs across the food chain.',
  'This global benchmark may stay stable while southern African prices rise. US harvests, ethanol demand and Black Sea trade are major influences.',[-3,-5,0,2],[12,8,4,5],[30,22,10,10],'2027-06'),
 ('sugar','Sugar','A sweet crop, a volatile market','Sugar, world','US$/kg','World · raw sugar benchmark',
  'Sugar adds a weather-sensitive ingredient used widely in processed food.',
  'Stress in cane-growing regions → less sugar available for export → higher ingredient costs.',
  'Brazilian harvests, ethanol economics and trade policy can offset or intensify losses elsewhere.',[-5,-8,-3,0],[20,12,5,5],[45,30,15,10],'2027-06'),
 ('palm','Palm oil','Pressure in the cooking-oil market','Palm oil','US$/tonne','International · palm oil benchmark',
  'A key cooking oil and food ingredient, with production exposed to Southeast Asian weather.',
  'Water stress in oil-palm regions → delayed production losses → tighter edible-oil supplies.',
  'Biodiesel mandates, competing vegetable oils and export policies also influence the price. Production effects can arrive with a lag.',[0,-3,0,3],[18,16,8,7],[35,32,18,12],'2027-09'),
 ('coffee','Coffee','What happens to the morning coffee?','Coffee, Robusta','US$/kg','International · Robusta coffee',
  'Robusta offers a focused link to drought exposure in Vietnam and a familiar household purchase.',
  'Hot, dry growing conditions → lower Robusta supply → pressure on wholesale coffee prices.',
  'Wholesale beans are only part of the retail price. Stocks, Brazilian supply, currencies and the preceding price cycle can outweigh new weather damage.',[-10,-15,-10,-5],[20,12,5,5],[50,35,20,12],'2027-06')]:
 id,label,title,col,unit,geo,desc,mechanism,caveat,low,med,high,peak=spec
 metrics.append(metric(id,label,title,unit,geo,'World Bank Pink Sheet',WB,commodity(col),description=desc,why=desc,mechanism=mechanism,caveat=caveat,assumptions=f'At the {peak} peak checkpoint, low / medium / high paths are {low[0]:+d}% / {med[0]:+d}% / {high[0]:+d}% versus the frozen anchor. Paths then allow supply recovery; endpoint assumptions are available below. These are judgement-based stress scenarios, not fitted forecasts.',rates={'low':low,'medium':med,'high':high},peak=peak))
months={name.lower():i for i,name in enumerate(calendar.month_name) if name}
ons=json.loads((RAW/'ons.json').read_text())
h=[dict(date=f"{x['year']}-{months[x['month'].lower()]:02d}",value=float(x['value'])) for x in ons['months'] if x['value']]
metrics.append(metric('retail','UK groceries','Does the shock reach the checkout?','index','United Kingdom · 2015 = 100','ONS · D7BU',ONS,h,
 description='The price level of food and non-alcoholic drinks bought by UK households.',why='The final link in the chain: do higher commodity costs reach the household food bill?',mechanism='Imported ingredients → manufacturing and distribution costs → household food prices.',caveat='UK only. Sterling, wages, energy and retailer margins all affect this index. Falling inflation does not mean falling prices.',assumptions='By December 2027: low +3%, medium +7%, high +12% versus July 2026. By August 2029: +7%, +12%, +20%. All are cumulative price-level changes, not annual inflation rates or causal estimates.',rates={'low':[3,3,5,7],'medium':[7,7,10,12],'high':[12,12,17,20]},peak='2027-12'))
roni=[]
for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',(RAW/'roni.html').read_text(),re.S):
 cells=re.findall(r'<t[hd]\b[^>]*>(.*?)</t[hd]>',row,re.S)
 texts=[re.sub('<[^>]+>','',x).strip() for x in cells]
 if texts and re.fullmatch(r'\d{4}',texts[0]):
  year=int(texts[0])
  for i,v in enumerate(texts[1:]):
   if re.fullmatch(r'-?\d+\.\d+',v):roni.append(dict(date=f'{year}-{i+1:02d}',value=float(v)))
metrics.append(metric('enso','El Niño','The Pacific signal behind the story','°C','Equatorial Pacific · relative anomaly','NOAA CPC · RONI',NOAA,roni,
 description='Three-month relative sea-surface temperature anomalies in the Niño 3.4 region. Each point is dated to the middle month of its season.',why='Tracks the climate driver. Greater strength raises the risk of impacts, but does not guarantee damage in every region.',mechanism='Warmer relative Pacific temperatures → shifted rainfall patterns → changing risks for growing regions.',caveat='RONI adjusts for tropical background warming; do not compare it directly with unadjusted Niño 3.4 values. Recent observations are provisional. Climate scenarios stop in July 2027.',assumptions='Illustrative strength paths peak in November 2026 at 2.0°C / 2.6°C / 3.0°C, then decline to −0.2°C / 0.3°C / 1.0°C in July 2027. The official August NOAA outlook informs the peak range; these paths are our conditional illustrations, not NOAA forecast quantiles.',climate=True))
z=zipfile.ZipFile(RAW/'grains.zip'); grain=list(csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]),encoding='utf-8-sig')))
yields=[r for r in grain if r['Country_Name']=='South Africa' and r['Commodity_Description']=='Corn' and r['Attribute_Description']=='Yield']
h=[dict(date=r['Market_Year']+'-01',value=float(r['Value'])) for r in yields if int(r['Market_Year'])<=2025]
h.sort(key=lambda x:x['date'])
official=next(float(r['Value']) for r in yields if r['Market_Year']=='2026')
metrics.append(metric('harvest','Maize harvest','The harvest on the front line','tonnes/ha','South Africa · maize yield','USDA · PSD',USDA,h,
 description='Annual maize yield in South Africa, an exposed producer and regional supplier. Points use USDA marketing-year labels, not calendar-month observations.',why='Tests the physical harvest link. In this panel, a lower line means a higher impact.',mechanism='Summer heat and drought → lower yields → less maize for domestic use and regional exports.',caveat=f'Historical points are USDA estimates and remain revisable. The separate 2026/27 USDA forecast is {official:.2f} tonnes/ha; it is not shown as an observed harvest. A local crop loss does not imply a global shortage.',assumptions='2026/27 yields: low-impact 5.9, medium 5.5, high-impact 4.3 tonnes/ha. The medium scenario matches the archived USDA forecast. Subsequent seasons assume recovery; high impact means lower yield. Annual paths are illustrative, not monthly forecasts.',annual=True,officialForecast=official))
# Apply verified post-freeze observations; retain the original archive and scenario anchors.
refresh=json.loads((OUT/'refresh-2026-09-16.json').read_text())
for m in metrics:
 for point in refresh['newActuals'].get(m['id'],[]):
  m['history']=[p for p in m['history'] if p['date']!=point['date']]+[point]
manifest.extend(s for s in refresh['sources'] if s.get('name')=='ONS D7BU')
# Strip future source periods and freeze the original anchors, without overwriting them on refresh.
for m in metrics:
 m['history']=[p for p in m['history'] if p['date']<='2026-08'];m['history'].sort(key=lambda x:x['date'])
 m['decimals']=2 if m['unit'] in ('US$/kg','tonnes/ha') else 1
 m['frequency']='Annual harvest · estimates reviewed monthly' if m.get('annual') else ('Monthly · three-month seasons' if m.get('climate') else 'Monthly')
 m['historyStart']=m['history'][0]['date'];m['latest']=m['history'][-1]
 if m['id'] in ('rice','maize','sugar','palm','coffee'):
  lookup={p['date']:p['value'] for p in m['history']}; analogs=[]
  for year in (1982,1997,2015,2023):
   a=lookup.get(f'{year}-08'); b=lookup.get(f'{year+1}-06')
   if a and b:analogs.append({'period':f'Aug {year} → Jun {year+1}','change':round((b/a-1)*100,1)})
  m['analogues']=analogs
freezePath=OUT/'scenarios-v1.json'
if freezePath.exists():
 freeze=json.loads(freezePath.read_text())
else:
 freeze={'version':1,'date':FREEZE,'method':'Judgement-based conditional scenarios; linear interpolation between explicit dated checkpoints. No probability or causal interpretation. Original anchors remain fixed.','metrics':{}}
 for m in metrics:
  a=m['latest']; anchor=dict(a); paths={}
  for key in ('low','medium','high'):
   if m.get('climate'):
    vals={'low':[2.0,1.0,-.2],'medium':[2.6,1.8,.3],'high':[3,2.4,1]}[key];ds=['2026-11','2027-03','2027-07']
   elif m.get('annual'):
    vals={'low':[5.9,6,6.1],'medium':[5.5,5.7,5.95],'high':[4.3,5,5.7]}[key];ds=['2026-01','2027-01','2028-01']
   else:
    vals=[round(a['value']*(1+r/100),4) for r in m['rates'][key]];ds=[m['peak'],'2027-12','2028-08','2029-08']
   paths[key]=[anchor]+[dict(date=d,value=v) for d,v in dict(zip(ds,vals)).items()]
  freeze['metrics'][m['id']]={'anchor':anchor,'paths':paths,'assumptions':m['assumptions']}
 freezePath.write_text(json.dumps(freeze,indent=2)+'\n')
for m in metrics:
 f=freeze['metrics'][m['id']];m['anchor']=f['anchor'];m['paths']=f['paths'];m['assumptions']=f['assumptions']
 m.pop('rates',None)
 with (OUT/(m['id']+'.csv')).open('w') as file:
  writer=csv.writer(file);writer.writerow(['period','value','unit','type'])
  for p in m['history']:writer.writerow([p['date'],p['value'],m['unit'],'USDA estimate (marketing year)' if m.get('annual') else 'published observation'])
  for key,path in m['paths'].items():
   for p in path:writer.writerow([p['date'],p['value'],m['unit'],key+' scenario checkpoint'])
 m['history']=[p for p in m['history'] if p['date']>='2015-01']
payload={'asOf':refresh['checkedAt'],'version':1,'metrics':metrics,'sources':manifest}
(ROOT/'data/dashboard.json').write_text(json.dumps(payload,indent=2)+'\n')
(OUT/'dashboard.json').write_text(json.dumps(payload,indent=2)+'\n');(OUT/'sources.json').write_text(json.dumps(manifest,indent=2)+'\n')
for m in metrics: print(m['id'],m['latest'],'history',len(m['history']))
