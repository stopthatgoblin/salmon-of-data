"""Apply the source captures for the 2 October 2026 tracker refresh.

Downloads are retained under data/raw/2026-10-02 and data/ai/raw/2026-10-02.
This script recalculates actuals only; scenario anchors and paths stay frozen.
"""
from pathlib import Path
import csv, hashlib, json, re, statistics, subprocess

ROOT = Path(__file__).resolve().parents[1]
DAY = '2026-10-02'
AI_RAW = ROOT / 'data/ai/raw' / DAY
RAW = ROOT / 'data/raw' / DAY
PUBLIC = ROOT / 'public/data'
AI_PUBLIC = PUBLIC / 'ai'
previous_ai_report_path = AI_PUBLIC / f'refresh-{DAY}.json'

def read_json(path):
    return json.loads(path.read_text())

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def capture(path, url, note):
    base = ROOT / ('data/ai/raw' if AI_RAW in path.parents else 'data/raw')
    return {
        'file': path.relative_to(base).as_posix(),
        'url': url,
        'bytes': path.stat().st_size,
        'sha256': sha(path),
        'retrievedOn': DAY,
        'note': note,
    }

def rows(path):
    with path.open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

previous_ai_report = read_json(previous_ai_report_path) if previous_ai_report_path.exists() else None

def points(values):
    return [{'date': d, 'value': round(v, 6)} for d, v in sorted(values.items())]

def revisions(old, new):
    old = {p['date']: p['value'] for p in old}
    return [
        {'date': d, 'previousValue': old[d], 'currentValue': round(v, 6)}
        for d, v in sorted(new.items())
        if d in old and abs(old[d] - v) > 0.0000005
    ]

# Indeed recruitment: exact six-family basket divided by the SA all-US index.
families = ['Software Development', 'Accounting', 'Marketing',
            'Administrative Assistance', 'Customer Service', 'Banking & Finance']
all_rows = rows(AI_RAW / 'indeed-us-all.csv')
all_us = {
    r['date']: float(r['indeed_job_postings_index_SA'])
    for r in all_rows if r['jobcountry'] == 'US' and r['variable'] == 'total postings'
}
sector_rows = rows(AI_RAW / 'indeed-us-sectors.csv')
sector_values = {}
for r in sector_rows:
    if r['jobcountry'] == 'US' and r['variable'] == 'total postings' and r['display_name'] in families:
        sector_values.setdefault(r['date'], {})[r['display_name']] = float(r['indeed_job_postings_index'])
input_rows = []
recruitment = {}
for date, values in sorted(sector_values.items()):
    if date < '2020-02-01' or len(values) != 6 or date not in all_us:
        continue
    basket = statistics.mean(values[name] for name in families)
    recruitment[date] = basket / all_us[date] * 100
    input_rows.append([date, *[values[name] for name in families], all_us[date]])

snapshot_path = AI_PUBLIC / 'dashboard-snapshot.json'
snapshot = read_json(snapshot_path)
metrics = {m['id']: m for m in snapshot['metrics']}
recruitment_revisions = revisions(metrics['recruitment']['data'], recruitment)
old_recruitment_dates = {p['date'] for p in metrics['recruitment']['data']}
new_recruitment_dates = sorted(set(recruitment) - old_recruitment_dates)
metrics['recruitment']['data'] = points(recruitment)
metrics['recruitment']['actualsUpdatedAt'] = DAY
latest_day = max(recruitment)
latest_sector = sector_values[latest_day]
metrics['recruitment']['components'] = [
    {'label': 'White-collar basket', 'value': f"{statistics.mean(latest_sector[n] for n in families):.1f}",
     'detail': 'Source index · Feb 2020 = 100'},
    {'label': 'All US postings', 'value': f"{all_us[latest_day]:.1f}",
     'detail': 'Source index · Feb 2020 = 100'},
]

# Current payroll series: preserve each original 2019-mean indexing rule.
def series(path, column):
    return {r['observation_date']: float(r[column]) for r in rows(path) if r[column]}

naics54 = series(AI_RAW / 'CES6054000001.csv', 'CES6054000001')
private = series(AI_RAW / 'USPRIV.csv', 'USPRIV')
employment_ratio = {d: naics54[d] / private[d] for d in naics54.keys() & private.keys()}
employment_base = statistics.mean(v for d, v in employment_ratio.items() if d.startswith('2019-'))
employment = {d: v / employment_base * 100 for d, v in employment_ratio.items() if d >= '2015-01-01'}
employment_revisions = revisions(metrics['employment']['data'], employment)
employment_added = sorted(set(employment) - {p['date'] for p in metrics['employment']['data']})
metrics['employment']['data'] = points(employment)
metrics['employment']['actualsUpdatedAt'] = DAY

earnings = series(AI_RAW / 'CES6000000003.csv', 'CES6000000003')
cpi = series(AI_RAW / 'CPIAUCSL.csv', 'CPIAUCSL')
real_ratio = {d: earnings[d] / cpi[d] for d in earnings.keys() & cpi.keys()}
real_base = statistics.mean(v for d, v in real_ratio.items() if d.startswith('2019-'))
real_pay = {d: v / real_base * 100 for d, v in real_ratio.items() if d >= '2015-01-01'}
real_pay_revisions = revisions(metrics['real-pay']['data'], real_pay)
metrics['real-pay']['data'] = points(real_pay)
metrics['real-pay']['actualsUpdatedAt'] = DAY

# Re-running after outputs have been refreshed should retain the first-run audit deltas.
if previous_ai_report:
    prior_updates = previous_ai_report.get('metricsUpdated', {})
    recruitment_update = prior_updates.get('recruitment', {})
    employment_update = prior_updates.get('employment', {})
    realpay_update = prior_updates.get('real-pay', {})
    recruitment_revisions = recruitment_revisions or recruitment_update.get('revisedObservations', [])
    new_recruitment_dates = new_recruitment_dates or recruitment_update.get('observationsAdded', [])
    employment_revisions = employment_revisions or employment_update.get('revisedObservations', [])
    employment_added = employment_added or employment_update.get('observationsAdded', [])
    real_pay_revisions = real_pay_revisions or realpay_update.get('revisedObservations', [])

write_json(snapshot_path, snapshot)
write_json(ROOT / 'data/ai/dashboard.json', snapshot)

def write_actual_csv(path, values, unit):
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['observation_date', 'metric_value', 'unit'])
        for d, v in sorted(values.items()):
            w.writerow([d, f'{v:.6f}'.rstrip('0').rstrip('.'), unit])

write_actual_csv(AI_PUBLIC / 'recruitment.csv', recruitment, 'Relative recruitment · 1 Feb 2020 = 100')
write_actual_csv(AI_PUBLIC / 'employment.csv', employment, 'Index · 2019 average = 100')
write_actual_csv(AI_PUBLIC / 'real-pay.csv', real_pay, 'Index · 2019 average = 100')
with (AI_PUBLIC / 'recruitment-excel-inputs.csv').open('w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['date', *families, 'All US postings, seasonally adjusted'])
    w.writerows(input_rows)

ai_urls = {
    'indeed-us-all.csv': 'https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/aggregate_job_postings_US.csv',
    'indeed-us-sectors.csv': 'https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/job_postings_by_sector_US.csv',
    'CES6054000001.csv': 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=CES6054000001',
    'USPRIV.csv': 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=USPRIV',
    'CES6000000003.csv': 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=CES6000000003',
    'CPIAUCSL.csv': 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL',
}
ai_notes = {
    'indeed-us-all.csv': 'Exact source capture; observations and historical revisions through 2026-09-25.',
    'indeed-us-sectors.csv': 'Exact source capture; six-family inputs and historical revisions through 2026-09-25.',
    'CES6054000001.csv': 'Current CES source capture after the 2026-10-02 Employment Situation release.',
    'USPRIV.csv': 'Current CES source capture after the 2026-10-02 Employment Situation release.',
    'CES6000000003.csv': 'Current average hourly earnings input through 2026-09; real pay remains through August pending September CPI.',
    'CPIAUCSL.csv': 'Current CPI source capture; the latest observation remains 2026-08.',
}
ai_captures = [capture(AI_RAW / name, url, ai_notes[name]) for name, url in ai_urls.items()]
manifest_path = ROOT / 'data/ai/source-manifest.json'
manifest = read_json(manifest_path)
for item in ai_captures:
    if not any(x.get('file') == item['file'] for x in manifest):
        manifest.append(item)
write_json(manifest_path, manifest)
write_json(AI_PUBLIC / 'source-manifest.json', manifest)

def source(path, name, page, download, note):
    item = capture(path, download, note)
    item['name'] = name
    item['downloadUrl'] = item.pop('url')
    item['url'] = page
    return item

global_sources = [
    source(RAW / 'fao.csv', 'FAO Food Price Index',
           'https://www.fao.org/worldfoodsituation/foodpricesindex/en/',
           'https://www.fao.org/media/docs/worldfoodsituationlibraries/wfs-library/food_price_indices_data.csv?download=true&sfvrsn=523ebd2a_84',
           'September 2026 actual and latest revised monthly history.'),
    source(RAW / 'world-bank.xlsx', 'World Bank Pink Sheet',
           'https://www.worldbank.org/en/research/commodity-markets',
           'https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx',
           'Checked 2026-10-02; byte-identical to the prior archive and still ends in 2026-08.'),
    source(RAW / 'ons.json', 'ONS D7BU',
           'https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7bu/mm23',
           'https://www.ons.gov.uk/economy/inflationandpriceindices/timeseries/d7bu/mm23/data',
           'Latest observation remains 2026-08 = 144.6, already included in the 2026-09-16 refresh.'),
]
old_dashboard = read_json(ROOT / 'data/dashboard.json')
food = next(m for m in old_dashboard['metrics'] if m['id'] == 'food')
fao = {}
with (RAW / 'fao.csv').open(newline='', encoding='utf-8-sig') as f:
    for row in csv.reader(f):
        if len(row) > 1 and re.fullmatch(r'\d{4}-\d{2}', row[0]) and row[1]:
            fao[row[0]] = float(row[1])
food_old = {p['date']: p['value'] for p in food['history']}
food_changes = [
    {'date': d, 'value': v, **({'previousValue': food_old[d]} if d in food_old and food_old[d] != v else {})}
    for d, v in sorted(fao.items())
    if d >= '2015-01' and (d not in food_old or food_old[d] != v)
]
previous_global_report_path = PUBLIC / f'refresh-{DAY}.json'
if not food_changes and previous_global_report_path.exists():
    previous_food = read_json(previous_global_report_path).get('newActuals', {}).get('food', [])
    food_changes = [p for p in previous_food if p.get('date', '') >= '2015-01']
    if food_changes:
        try:
            baseline = json.loads(subprocess.run(
                ['git', 'show', 'HEAD:data/dashboard.json'], cwd=ROOT,
                check=True, capture_output=True, text=True
            ).stdout)
            baseline_food = {p['date']: p['value'] for m in baseline['metrics'] if m['id'] == 'food' for p in m['history']}
            for point in food_changes:
                old_value = baseline_food.get(point['date'])
                if old_value is not None and old_value != point['value']:
                    point['previousValue'] = old_value
        except (OSError, subprocess.CalledProcessError, KeyError, ValueError):
            pass
fao_rows = [[r['date'], r['value']] for r in food_changes]

us_employment = next(m for m in snapshot['metrics'] if m['id'] == 'employment')
real_metric = next(m for m in snapshot['metrics'] if m['id'] == 'real-pay')
ai_report = {
    'checkedAt': DAY,
    'sources': ai_captures,
    'metricsUpdated': {
        'recruitment': {
            'latestObservation': latest_day, 'latestValue': round(recruitment[latest_day], 6),
            'observationsAdded': new_recruitment_dates,
            'revisedObservationCount': len(recruitment_revisions),
            'revisedObservations': recruitment_revisions,
            'components': metrics['recruitment']['components'],
        },
        'employment': {
            'latestObservation': employment_added[-1], 'latestValue': round(employment[employment_added[-1]], 6),
            'observationsAdded': employment_added,
            'revisedObservationCount': len(employment_revisions), 'revisedObservations': employment_revisions,
        },
        'real-pay': {
            'latestObservation': max(real_pay), 'latestValue': round(real_pay[max(real_pay)], 6),
            'observationsAdded': [],
            'revisedObservationCount': len(real_pay_revisions), 'revisedObservations': real_pay_revisions,
            'earningsInputLatest': {'date': max(earnings), 'value': earnings[max(earnings)]},
            'cpiLatest': {'date': max(cpi), 'value': cpi[max(cpi)]},
            'note': 'September earnings input is available, but September CPI is not; no September real-pay observation is calculated.',
        },
    },
    'checks': {
        'jolts': 'No new JOLTS release; August 2026 remains the latest actual. Next release is scheduled for 2026-11-03.',
        'graduates': 'No new New York Fed graduate labour-market release; the next expected quarter is Q3 2026 in November.',
        'canada': 'No new Statistics Canada quarterly release; Q2 2026 remains latest and Q3 release is scheduled for 2026-12-15.',
        'forecasts': 'Original frozen metric anchors, scenario paths and review date are unchanged.',
    },
    'policy': 'Recalculated current recruitment, employment and real-pay actuals from exact 2026-10-02 source captures. Included source revisions and new observations; forecast anchors and conditional paths remain unchanged.',
}
write_json(AI_PUBLIC / f'refresh-{DAY}.json', ai_report)

# Global El Niño series: source revisions and the new FAO month are overlaid by build-data.py.
worldbank = global_sources[1]
ons = global_sources[2]
global_report = {
    'checkedAt': DAY,
    'newActuals': {'food': food_changes},
    'sources': global_sources,
    'checks': {
        'food': 'FAO September index is 136.0. July was revised from 130.8 to 131.7 and August from 133.3 to 134.0.',
        'commodities': 'World Bank workbook is unchanged and ends in August 2026; the scheduled October 2 update was not present in the source at check time.',
        'enso': 'NOAA RONI source is unchanged; latest displayed season remains JJA 2026 at 1.4°C. The next table update is due by October 5.',
        'usda': 'Current USDA grain ZIP matches the September 13 archive; the 2026/27 South African maize yield forecast remains 5.50 tonnes/ha.',
        'retail': 'ONS D7BU latest observation is August 2026 = 144.6, already included in the September 16 refresh; the next release is October 21.',
        'forecasts': 'Original frozen metric anchors and conditional paths remain unchanged.',
    },
    'frozenFileSha256': {
        'public/data/scenarios-v1.json': sha(PUBLIC / 'scenarios-v1.json'),
        'public/data/ai/frozen-metrics-v1.json': sha(AI_PUBLIC / 'frozen-metrics-v1.json'),
    },
    'policy': 'Updated the FAO actual history using its exact October 2 source capture, including publisher revisions. The original frozen forecast anchor and scenarios remain unchanged.',
}
write_json(PUBLIC / f'refresh-{DAY}.json', global_report)

# Record the October 2 publications in the shared calendar and leave the still-missing
# World Bank file listed with an explicit note rather than inventing September values.
calendar_path = ROOT / 'data/release-calendar.json'
cal = read_json(calendar_path)
completed = []
for event in list(cal['entries']):
    if event.get('date') == DAY and event.get('title') in ('US employment situation', 'FAO Food Price Index'):
        cal['entries'].remove(event)
        event['checkedAt'] = DAY
        event['importedAt'] = DAY
        if event['title'] == 'US employment situation':
            event['actualsAdded'] = ['employment: 2026-09-01', 'real-pay input: earnings 2026-09-01']
            event['revisionsIncluded'] = ['employment: 2026-07-01 and 2026-08-01', 'real pay: 2026-07-01 and 2026-08-01']
        else:
            event['actualsAdded'] = ['food: 2026-09']
            event['revisionsIncluded'] = ['food: 2026-07-01', 'food: 2026-08-01']
        completed.append(event)
    elif event.get('date') == DAY and event.get('title') == 'World Bank commodity prices':
        event['checkedAt'] = DAY
        event['note'] = 'Checked 2 October: the workbook still ends in August 2026 and is unchanged; September values have not appeared in the source yet.'
cal['completedReleases'] = sorted(cal.get('completedReleases', []) + completed,
                                  key=lambda x: (x.get('date', ''), x.get('title', '')))
cal['checkedAt'] = DAY
cal['lastReleaseReviewAt'] = DAY
write_json(calendar_path, cal)
write_json(PUBLIC / 'release-calendar.json', cal)

print('Indeed', latest_day, round(recruitment[latest_day], 6), 'added', len(new_recruitment_dates), 'revised', len(recruitment_revisions))
print('Employment', employment_added[-1], round(employment[employment_added[-1]], 6), 'revised', len(employment_revisions))
print('Real pay through', max(real_pay), round(real_pay[max(real_pay)], 6), 'revised', len(real_pay_revisions))
print('FAO actuals/revisions', food_changes)
