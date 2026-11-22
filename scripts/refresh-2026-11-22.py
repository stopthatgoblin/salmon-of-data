"""Import the 22 November source review without rebasing frozen scenarios."""
from pathlib import Path
import calendar
import csv
import hashlib
import json
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DAY = '2026-11-22'
PUB = ROOT / 'public/data'
APUB = PUB / 'ai'
RAW = ROOT / 'data/raw' / DAY
ARAW = ROOT / 'data/ai/raw' / DAY

def read(path):
    return json.loads(path.read_text())

def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))

def capture(path, url, note):
    return dict(file=f'{DAY}/{path.name}', url=url, bytes=path.stat().st_size,
                sha256=sha(path), retrievedOn=DAY, note=note)

if (PUB / f'refresh-{DAY}.json').exists() or (APUB / f'refresh-{DAY}.json').exists():
    raise SystemExit('Refresh already applied; refusing to overwrite its audit trail.')
frozen = {str(p.relative_to(ROOT)): sha(p) for p in [PUB / 'scenarios-v1.json', APUB / 'frozen-metrics-v1.json']}
for name in ['roni.html', 'fao.csv', 'world-bank.xlsx']:
    assert sha(RAW / name) == sha(ROOT / 'data/raw/2026-11-06' / name), f'{name} changed; review before importing'
for name in ['graduate-unemployment.csv', 'graduate-underemployment.csv']:
    assert sha(ARAW / name) == sha(ROOT / 'data/ai/raw/2026-11-16' / name), f'{name} changed; review before importing'

months = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
retail = {f"{r['year']}-{months[r['month'].lower()]:02d}": float(r['value'])
          for r in read(RAW / 'ons.json')['months'] if r['value']}
old = {p['date']: p['value'] for m in read(ROOT / 'data/dashboard.json')['metrics'] if m['id'] == 'retail' for p in m['history']}
changes = [dict(date=d, value=v, **({'previousValue': old[d]} if d in old else {}))
           for d, v in sorted(retail.items()) if d >= min(old) and (d not in old or old[d] != v)]
assert changes == [{'date': '2026-10', 'value': 144.6}], 'Review unexpected ONS revisions or observations'
url = 'https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7bu/mm23/data'
source = capture(RAW / 'ons.json', url, 'ONS D7BU: October 2026 food and non-alcoholic beverages index.')
source.update(name='ONS D7BU', downloadUrl=url)
write(PUB / f'refresh-{DAY}.json', {
    'checkedAt': DAY, 'newActuals': {'retail': changes}, 'sources': [source],
    'checks': {'retail': 'October 2026 D7BU = 144.6, released 18 November.',
               'otherSources': 'NOAA RONI, FAO and World Bank captures match the 6 November files.'},
    'frozenFileSha256': frozen['public/data/scenarios-v1.json'],
    'policy': 'Published observations only; original forecast anchors and scenarios remain unchanged.'})
subprocess.run([sys.executable, str(ROOT / 'scripts/build-data.py')], check=True, cwd=ROOT)

snapshot = read(ROOT / 'data/ai/dashboard.json')
metric = next(m for m in snapshot['metrics'] if m['id'] == 'recruitment')
before = {p['date']: p['value'] for p in metric['data']}
families = ['Software Development', 'Accounting', 'Marketing', 'Administrative Assistance', 'Customer Service', 'Banking & Finance']
all_us = {r['date']: float(r['indeed_job_postings_index_SA']) for r in rows(ARAW / 'indeed-us-all.csv')
          if r['jobcountry'] == 'US' and r['variable'] == 'total postings'}
sectors = {}
for r in rows(ARAW / 'indeed-us-sectors.csv'):
    if r['jobcountry'] == 'US' and r['variable'] == 'total postings' and r['display_name'] in families:
        sectors.setdefault(r['date'], {})[r['display_name']] = float(r['indeed_job_postings_index'])
values, inputs = {}, []
for date, basket in sorted(sectors.items()):
    if date >= '2020-02-01' and len(basket) == 6 and date in all_us:
        values[date] = round(statistics.mean(basket[n] for n in families) / all_us[date] * 100, 6)
        inputs.append([date, *[basket[n] for n in families], all_us[date]])
assert set(before) <= set(values), 'Refusing loss of accepted recruitment observations'
added = [dict(date=d, value=v) for d, v in sorted(values.items()) if d not in before]
revised = [dict(date=d, previousValue=before[d], value=v) for d, v in sorted(values.items())
           if d in before and abs(v - before[d]) > .0000005]
metric['data'] = [dict(date=d, value=v) for d, v in sorted(values.items())]
metric['actualsUpdatedAt'] = DAY
latest = max(values)
metric['components'] = [
    dict(label='White-collar basket', value=f'{statistics.mean(sectors[latest][n] for n in families):.1f}', detail='Source index · Feb 2020 = 100'),
    dict(label='All US postings', value=f'{all_us[latest]:.1f}', detail='Source index · Feb 2020 = 100')]
snapshot['actualsReviewedAt'] = snapshot['actualsUpdatedAt'] = DAY
write(ROOT / 'data/ai/dashboard.json', snapshot)
write(APUB / 'dashboard-snapshot.json', snapshot)
with (APUB / 'recruitment.csv').open('w', newline='', encoding='utf-8') as handle:
    w = csv.writer(handle); w.writerow(['observation_date', 'metric_value', 'unit'])
    w.writerows((d, f'{v:.6f}'.rstrip('0').rstrip('.'), 'Relative recruitment · 1 Feb 2020 = 100') for d, v in sorted(values.items()))
with (APUB / 'recruitment-excel-inputs.csv').open('w', newline='', encoding='utf-8') as handle:
    w = csv.writer(handle); w.writerow(['date', *families, 'All US postings, seasonally adjusted']); w.writerows(inputs)
urls = {
    'indeed-us-all.csv': 'https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/aggregate_job_postings_US.csv',
    'indeed-us-sectors.csv': 'https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/job_postings_by_sector_US.csv',
    'graduate-unemployment.csv': 'https://www.newyorkfed.org/medialibrary/research/interactives/data/college-labor-market/college-labor-unemployment-data.csv',
    'graduate-underemployment.csv': 'https://www.newyorkfed.org/medialibrary/research/interactives/data/college-labor-market/college-labor-underemployment-data.csv'}
sources = [capture(ARAW / name, url, 'Source capture, including published revisions.') for name, url in urls.items()]
manifest = read(ROOT / 'data/ai/source-manifest.json')
manifest.extend(s for s in sources if not any(x['file'] == s['file'] for x in manifest))
write(ROOT / 'data/ai/source-manifest.json', manifest); write(APUB / 'source-manifest.json', manifest)
write(APUB / f'refresh-{DAY}.json', {
    'checkedAt': DAY, 'sources': sources,
    'metricsUpdated': {'recruitment': {'latestObservation': dict(date=latest, value=values[latest]),
                       'observationsAdded': added, 'revisedObservations': revised, 'revisedObservationCount': len(revised)}},
    'checks': {'graduates': 'Both source files match the 16 November captures; September remains latest.',
               'employmentAndPay': 'October remains the latest released employment and CPI data.',
               'hiring': 'September remains the latest JOLTS release; the next release is 1 December.',
               'canada': 'Q2 remains the latest quarterly release; Q3 is due 15 December.',
               'frozen': 'Anchors, paths and definitions unchanged.'}, 'frozenFileSha256': frozen})

cal = read(ROOT / 'data/release-calendar.json')
event = next(e for e in cal['entries'] if e['title'] == 'UK consumer prices' and e.get('date') == '2026-11-18')
cal['entries'].remove(event)
event.update(checkedAt=DAY, publishedAt='2026-11-18', importedAt=DAY,
             actualsAdded=['retail: 2026-10 = 144.6'], revisionsIncluded=[])
cal['completedReleases'].append(event)
cal['completedReleases'].sort(key=lambda e: (e.get('date') or e.get('month') or '', e['title']))
for e in cal['entries']:
    e['checkedAt'] = DAY
    if e['title'] == 'FAO Food Price Index':
        e['sourceUrl'] = 'https://www.fao.org/statistics/data-releases'
cal['entries'].sort(key=lambda e: (e.get('date') or e['month'] + '-01', e['title']))
cal['checkedAt'] = cal['lastReleaseReviewAt'] = DAY
write(ROOT / 'data/release-calendar.json', cal); write(PUB / 'release-calendar.json', cal)
ai = read(ROOT / 'data/ai/release-calendar.json')
ai.update(checkedAt=DAY, lastReleaseReviewAt=DAY,
          entries=[e for e in cal['entries'] if e['tracker'] == 'ai' and e.get('date')],
          provisional=[e for e in cal['entries'] if e['tracker'] == 'ai' and not e.get('date')],
          completedReleases=[e for e in cal['completedReleases'] if e['tracker'] == 'ai'])
write(ROOT / 'data/ai/release-calendar.json', ai); write(APUB / 'release-calendar.json', ai)
assert all(sha(ROOT / path) == digest for path, digest in frozen.items())
print(json.dumps({'retail': changes, 'recruitmentLatest': metric['data'][-1],
                  'recruitmentAdded': len(added), 'recruitmentRevisions': len(revised)}, indent=2))
