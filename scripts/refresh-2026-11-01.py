"""Replay the November source review from retained captures; never rebase forecasts."""
from pathlib import Path
import calendar, csv, hashlib, json, statistics

ROOT = Path(__file__).resolve().parents[1]
DAY = '2026-11-01'
PUBLIC = ROOT / 'public/data'
AI_PUBLIC = PUBLIC / 'ai'
RAW = ROOT / 'data/raw' / DAY
AI_RAW = ROOT / 'data/ai/raw' / DAY

def read(path):
    return json.loads(path.read_text())

def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rows(path):
    with path.open(newline='', encoding='utf-8-sig') as handle:
        return list(csv.DictReader(handle))

frozen = {str(path.relative_to(ROOT)): sha(path) for path in [
    PUBLIC / 'scenarios-v1.json', AI_PUBLIC / 'frozen-metrics-v1.json']}
old_global = read(ROOT / 'data/dashboard.json')
snapshot = read(ROOT / 'data/ai/dashboard.json')
metric = next(item for item in snapshot['metrics'] if item['id'] == 'recruitment')
old = {point['date']: point['value'] for point in metric['data']}
families = ['Software Development', 'Accounting', 'Marketing',
            'Administrative Assistance', 'Customer Service', 'Banking & Finance']
all_us = {row['date']: float(row['indeed_job_postings_index_SA'])
          for row in rows(AI_RAW / 'indeed-us-all.csv')
          if row['jobcountry'] == 'US' and row['variable'] == 'total postings'}
sectors = {}
for row in rows(AI_RAW / 'indeed-us-sectors.csv'):
    if row['jobcountry'] == 'US' and row['variable'] == 'total postings' and row['display_name'] in families:
        sectors.setdefault(row['date'], {})[row['display_name']] = float(row['indeed_job_postings_index'])
values, inputs = {}, []
for date, basket in sorted(sectors.items()):
    if date < '2020-02-01' or len(basket) != 6 or date not in all_us:
        continue
    values[date] = round(statistics.mean(basket[name] for name in families) / all_us[date] * 100, 6)
    inputs.append([date, *[basket[name] for name in families], all_us[date]])
assert set(old) <= set(values), 'Refusing loss of accepted recruitment observations'
added = sorted(set(values) - set(old))
revised = [{'date': date, 'previousValue': old[date], 'currentValue': value}
           for date, value in sorted(values.items()) if date in old and old[date] != value]
prior_path = AI_PUBLIC / f'refresh-{DAY}.json'
if prior_path.exists():
    prior = read(prior_path)['metricsUpdated']['recruitment']
    added = added or prior['observationsAdded']
    revised = revised or prior['revisedObservations']
metric['data'] = [{'date': date, 'value': value} for date, value in sorted(values.items())]
metric['actualsUpdatedAt'] = DAY
latest = max(values)
metric['components'] = [
    {'label': 'White-collar basket', 'value': f"{statistics.mean(sectors[latest][name] for name in families):.1f}", 'detail': 'Source index · Feb 2020 = 100'},
    {'label': 'All US postings', 'value': f'{all_us[latest]:.1f}', 'detail': 'Source index · Feb 2020 = 100'},
]
snapshot['actualsUpdatedAt'] = snapshot['actualsReviewedAt'] = DAY
write(ROOT / 'data/ai/dashboard.json', snapshot)
write(AI_PUBLIC / 'dashboard-snapshot.json', snapshot)
with (AI_PUBLIC / 'recruitment.csv').open('w', newline='') as handle:
    writer = csv.writer(handle)
    writer.writerow(['observation_date', 'metric_value', 'unit'])
    writer.writerows([date, f'{value:.6f}'.rstrip('0').rstrip('.'), 'Relative recruitment · 1 Feb 2020 = 100'] for date, value in sorted(values.items()))
with (AI_PUBLIC / 'recruitment-excel-inputs.csv').open('w', newline='') as handle:
    writer = csv.writer(handle)
    writer.writerow(['date', *families, 'All US postings, seasonally adjusted'])
    writer.writerows(inputs)

def captures(previous, directory):
    result = []
    for item in previous:
        path = directory / Path(item['file']).name
        if not path.exists():
            continue
        current = dict(item, file=f'{DAY}/{path.name}', bytes=path.stat().st_size,
                       sha256=sha(path), retrievedOn=DAY)
        current['note'] = 'Source recaptured for the 1 November 2026 review; original capture retained.'
        result.append(current)
    return result

ai_sources = captures(read(AI_PUBLIC / 'refresh-2026-10-16.json')['sources'], AI_RAW)
manifest = read(ROOT / 'data/ai/source-manifest.json')
known = {item['file'] for item in manifest}
manifest.extend(item for item in ai_sources if item['file'] not in known)
write(ROOT / 'data/ai/source-manifest.json', manifest)
write(AI_PUBLIC / 'source-manifest.json', manifest)
ai_report = {
    'checkedAt': DAY, 'sources': ai_sources,
    'metricsUpdated': {'recruitment': {
        'latestObservation': latest, 'latestValue': values[latest],
        'observationsAdded': added, 'revisedObservations': revised,
        'revisedObservationCount': len(revised), 'components': metric['components'],
    }},
    'checks': {
        'employmentAndPay': 'FRED series pages still show September payroll/earnings updated 2 October and September CPI updated 14 October. Latest values match the accepted 16 October captures. No newer release is available.',
        'hiring': 'FRED JOLTS pages still show August data updated 29 September; the next release is 3 November.',
        'graduates': 'Both New York Fed downloads are byte-identical to 16 October. Q2 remains the latest quarter; a November update is expected without a confirmed day.',
        'canada': 'Statistics Canada table 14-10-0444-01 still lists 15 September as its release date. The Q2 release confirms the next quarterly release for 15 December. Accepted Q2 values retained.',
    },
    'retainedSources': [
        {'file': f'2026-10-16/{name}.csv', 'verificationUrl': f'https://fred.stlouisfed.org/series/{name}',
         'checkedAt': DAY, 'reason': 'CSV re-download timed out; official series page confirms the same latest release and values. Original source capture and observations retained.'}
        for name in ['CES6054000001', 'USPRIV', 'CES6000000003', 'CPIAUCSL', 'JTS1000HIR', 'JTS540099HIR']
    ],
    'frozenFileSha256': frozen,
    'policy': 'Only published observations and source revisions were imported. Frozen anchors, paths, definitions and review dates are unchanged.',
}
write(prior_path, ai_report)

months = {name.lower(): index for index, name in enumerate(calendar.month_name) if name}
retail = {f"{row['year']}-{months[row['month'].lower()]:02d}": float(row['value'])
          for row in read(RAW / 'ons.json')['months'] if row['value']}
old_retail = {point['date']: point['value'] for item in old_global['metrics'] if item['id'] == 'retail' for point in item['history']}
retail_changes = [dict(date=date, value=value, **({'previousValue': old_retail[date]} if date in old_retail else {}))
                  for date, value in sorted(retail.items())
                  if date >= '2015-01' and (date not in old_retail or value != old_retail[date])]
report_path = PUBLIC / f'refresh-{DAY}.json'
if report_path.exists():
    retail_changes = retail_changes or read(report_path)['newActuals']['retail']
global_sources = captures(read(PUBLIC / 'refresh-2026-10-16.json')['sources'], RAW)
for item in global_sources:
    if Path(item['file']).name != 'ons.json':
        assert item['sha256'] == sha(ROOT / 'data/raw/2026-10-16' / Path(item['file']).name), 'Unexpected source revision: review before importing'
write(report_path, {
    'checkedAt': DAY, 'newActuals': {'retail': retail_changes}, 'sources': global_sources,
    'checks': {
        'retail': 'September 2026 D7BU = 144.3, released 21 October, imported from the official ONS time series.',
        'otherSources': 'FAO, World Bank, NOAA RONI, NOAA discussion and USDA PSD captures are byte-identical to 16 October. No newer observations or revisions to import.',
    },
    'frozenFileSha256': frozen,
    'policy': 'Source review updates current observations only. Original frozen forecast anchors and scenarios remain unchanged.',
})

cal = read(ROOT / 'data/release-calendar.json')
for event in list(cal['entries']):
    if event.get('date') == '2026-10-21' and event['title'] == 'UK consumer prices':
        cal['entries'].remove(event)
        event.update(checkedAt=DAY, importedAt=DAY, publishedAt='2026-10-21',
                     actualsAdded=[f"retail: {point['date']} = {point['value']}" for point in retail_changes if 'previousValue' not in point],
                     revisionsIncluded=[point['date'] for point in retail_changes if 'previousValue' in point])
        cal.setdefault('completedReleases', []).append(event)
# The harvest panel is retired; only releases affecting displayed metrics belong here.
cal['entries'] = [event for event in cal['entries'] if event['title'] != 'USDA World Agricultural Supply and Demand Estimates' and event['tracker'] in ['ai', 'el-nino']]
for event in cal['entries']:
    event['checkedAt'] = DAY
    if event['title'] == 'Canadian vacancies and offered wages':
        event['sourceUrl'] = 'https://www150.statcan.gc.ca/n1/daily-quotidien/260915/dq260915a-eng.pdf'
if not any(event['title'] == 'NOAA ENSO Diagnostic Discussion' and event.get('month') == '2026-12' for event in cal['entries']):
    cal['entries'].append(dict(tracker='el-nino', frequency='monthly', date=None, month='2026-12',
        title='NOAA ENSO Diagnostic Discussion', referencePeriod='November 2026 conditions and outlook',
        metrics=['El Niño outlook'], sourceUrl='https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml',
        status='Expected month', checkedAt=DAY, note='Monthly release expected; the December date is not yet confirmed.'))
cal['entries'].sort(key=lambda event: (event.get('date') or event.get('month') + '-01', event['title']))
cal['checkedAt'] = cal['lastReleaseReviewAt'] = DAY
cal['scope'] = 'Monthly and quarterly releases affecting displayed AI and El Niño metrics. Daily electricity updates and the retired harvest panel are excluded.'
write(ROOT / 'data/release-calendar.json', cal)
write(PUBLIC / 'release-calendar.json', cal)
ai_cal = dict(checkedAt=DAY, year=2026, lastReleaseReviewAt=DAY,
              entries=[event for event in cal['entries'] if event['tracker'] == 'ai' and event.get('date')],
              provisional=[event for event in cal['entries'] if event['tracker'] == 'ai' and not event.get('date')],
              completedReleases=[event for event in cal['completedReleases'] if event['tracker'] == 'ai'])
write(ROOT / 'data/ai/release-calendar.json', ai_cal)
write(AI_PUBLIC / 'release-calendar.json', ai_cal)
assert all(sha(ROOT / path) == digest for path, digest in frozen.items())
print(json.dumps({'recruitmentLatest': latest, 'addedRecruitmentDays': len(added), 'recruitmentRevisions': len(revised), 'retailChanges': retail_changes, 'upcomingReleases': len(cal['entries'])}))
