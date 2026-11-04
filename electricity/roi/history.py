"""Collect real ROI grid history and the sign-reversed accepted NI daily flow.

Only complete source-labelled days (96 quarter-hours) are accepted. Monthly raw
inputs are retained in compressed state. No station targets or sample history
are used for these regional series.
"""
import calendar
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import gzip
import json
import math
import re
from pathlib import Path
import sys
import urllib.parse
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))
from refresh_history import fetch, daily_average

GRID = {
    'demand': ('demand', 'demandactual', 'SYSTEM_DEMAND'),
    'generation': ('generation', 'generationactual', 'GEN_EXP'),
    'wind': ('wind', 'windactual', 'WIND_ACTUAL'),
    'solar': ('solar', 'solaractual', 'SOLAR_ACTUAL'),
    'eastWest': ('interconnection', 'interconnection', 'INTER_EWIC'),
    'greenlink': ('interconnection', 'interconnection', 'INTER_GRNLK'),
}
SERIES = [
    dict(key='wind', label='Wind generation', colour='#136b72', method='reported', expected=96),
    dict(key='solar', label='Solar generation', colour='#b78a3b', method='reported', expected=96),
    dict(key='otherROI', label='Non-wind/solar generation', colour='#738577', method='derived', expected=96),
    dict(key='generation', label='Total ROI generation', colour='#ad3930', method='reported', expected=96),
    dict(key='demand', label='Electricity demand', colour='#182e32', method='reported', expected=96),
    dict(key='eastWest', label='East–West Interconnector', colour='#527d8b', method='reported', expected=96),
    dict(key='greenlink', label='Greenlink Interconnector', colour='#738b71', method='reported', expected=96),
    dict(key='northSouth', label='North–South Interconnector', colour='#708b91', method='estimated', expected=96),
]
KEYS = {series['key'] for series in SERIES}


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)


def grid_month(job, cache, today):
    key, year, month, refresh = job
    start = date(year, month, 1)
    end = min(date(year, month, calendar.monthrange(year, month)[1]), today)
    target = cache / f'{key}-{year}-{month:02}.json.gz'
    if target.exists() and not refresh:
        cached = json.loads(gzip.decompress(target.read_bytes()))
        if cached.get('rows') or cached.get('emptyRangeChecked'):
            return cached
    chart, areas, field = GRID[key]
    urls = []

    def request_window(first, last):
        query = urllib.parse.urlencode(dict(region='ROI', chartType=chart, areas=areas, dateRange='custom',
            dateFrom=first.strftime('%d-%b-%Y'), dateTo=last.strftime('%d-%b-%Y')))
        url = 'https://www.smartgriddashboard.com/api/chart/?' + query
        urls.append(url)
        payload = json.loads(fetch(url, {'Eirgrid-Content-Request': 'Nextjs'}))
        if not isinstance(payload.get('Rows'), list):
            raise ValueError('Unexpected ROI historical source response')
        return [row for row in payload['Rows'] if row.get('Region') == 'ROI' and row.get('FieldName') == field]

    rows = request_window(start, end)
    empty_checked = False
    if not rows:
        cursor = start
        while cursor <= end:
            last = min(end, cursor + timedelta(days=27))
            rows.extend(request_window(cursor, last))
            cursor = last + timedelta(days=1)
        empty_checked = True
    observations = []
    for row in rows:
        stamp = datetime.strptime(row['EffectiveTime'], '%d-%b-%Y %H:%M:%S')
        if not start <= stamp.date() <= end:
            continue
        value = row.get('Value')
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError('Non-finite ROI historical observation')
        observations.append([stamp.isoformat(), value])
    result = dict(key=key, year=year, month=month, urls=urls, emptyRangeChecked=empty_checked,
        retrieved=datetime.now(ZoneInfo('UTC')).isoformat(timespec='seconds').replace('+00:00', 'Z'), rows=observations)
    save(target, gzip.compress(json.dumps(result, separators=(',', ':'), allow_nan=False).encode()))
    return result


def assemble(grid, ni, start_year, yesterday):
    ni_columns = {series['key']: i for i, series in enumerate(ni['series'])}
    ni_rows = {row['date']: row for row in ni['days']}
    output = []
    cursor = date(start_year, 1, 1)
    while cursor <= yesterday:
        day = cursor.isoformat()
        daily = {key: daily_average(values.get(day, []), 96) for key, values in grid.items()}
        dependencies = ['generation', 'wind', 'solar']
        complete = all(daily[key][0] is not None for key in dependencies)
        daily['otherROI'] = (daily['generation'][0] - daily['wind'][0] - daily['solar'][0] if complete else None,
            min(daily[key][1] for key in dependencies))
        row, column = ni_rows.get(day), ni_columns['northSouth']
        value = row['v'][column] if row else None
        count = row['n'][column] if row else 0
        daily['northSouth'] = (-value if value is not None and count == 96 else None, count)
        output.append(dict(date=day,
            v=[round(daily[s['key']][0], 4) if daily[s['key']][0] is not None else None for s in SERIES],
            n=[daily[s['key']][1] for s in SERIES]))
        cursor += timedelta(days=1)
    valid = [i for i, row in enumerate(output) if any(value is not None for value in row['v'])]
    if not valid:
        raise ValueError('No complete ROI historical days; previous edition retained')
    return output[valid[0]:]


def refresh_coverage(data):
    for index, series in enumerate(data['series']):
        dates = [row['date'] for row in data['days'] if row['v'][index] is not None]
        series.update(first=dates[0] if dates else None, last=dates[-1] if dates else None, days=len(dates))


def validate(data, previous=None):
    if data.get('dataBasis') != 'public-source-history' or data.get('requestFailures') != 0:
        raise ValueError('ROI history requires successfully collected public sources')
    series = data.get('series', [])
    if len(series) != 8 or {s['key'] for s in series} != KEYS or any(s['expected'] != 96 for s in series) or not data.get('days'):
        raise ValueError('Incomplete ROI historical schema')
    if data['last'] >= datetime.now(ZoneInfo('Europe/Dublin')).date().isoformat():
        raise ValueError('ROI history includes an unfinished calendar day')
    if data['first'] != data['days'][0]['date'] or data['last'] != data['days'][-1]['date']:
        raise ValueError('ROI history range differs from its rows')
    if not re.fullmatch('[a-f0-9]{24}', data.get('niSource', {}).get('version', '')):
        raise ValueError('ROI history must reference its accepted NI source version')
    datetime.fromisoformat(data['generatedAt'].replace('Z', '+00:00'))
    prior_date = None
    columns = {s['key']: i for i, s in enumerate(series)}
    for row in data['days']:
        parsed = date.fromisoformat(row['date'])
        if prior_date and parsed != prior_date + timedelta(days=1):
            raise ValueError('ROI history dates must be continuous; missing observations stay null')
        prior_date = parsed
        if len(row['v']) != 8 or len(row['n']) != 8:
            raise ValueError('ROI history column mismatch')
        for value, count in zip(row['v'], row['n']):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError('Invalid ROI historical observation count')
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or count != 96):
                raise ValueError('Partial ROI historical day passed as complete')
        values = {key: row['v'][index] for key, index in columns.items()}
        if all(values[key] is not None for key in ['generation', 'wind', 'solar', 'otherROI']):
            if abs(values['generation'] - values['wind'] - values['solar'] - values['otherROI']) > .001:
                raise ValueError('ROI historical generation balance failed')
    if previous:
        if data['first'] > previous['first'] or data['last'] < previous['last']:
            raise ValueError('ROI historical range shrank')
        rows = {row['date']: row for row in data['days']}
        for old in previous['days']:
            row = rows.get(old['date'])
            for index, value in enumerate(old['v']):
                key = previous['series'][index]['key']
                if value is not None and (row is None or row['v'][columns[key]] is None):
                    raise ValueError('Previously accepted ROI historical day would be lost')
    json.dumps(data, allow_nan=False)


def retain_complete(data, previous):
    validate(data)
    rows = {row['date']: row for row in previous['days']}
    columns = {s['key']: i for i, s in enumerate(data['series'])}
    old_columns = {s['key']: i for i, s in enumerate(previous['series'])}
    retained = []
    for row in data['days']:
        old = rows.get(row['date'])
        if old and any(old['v'][old_columns[key]] is not None and row['v'][index] is None for key, index in columns.items()):
            # Preserve the entire regional cohort, including the NI-derived flow.
            row['v'] = [old['v'][old_columns[key]] for key in columns]
            row['n'] = [old['n'][old_columns[key]] for key in columns]
            retained.append(row['date'])
    if retained:
        data['retainedCompleteDays'] = dict(previousGeneratedAt=previous['generatedAt'], previousNI=previous['niSource'], dates=retained)
    refresh_coverage(data)


def collect(work, ni, start_year=2010):
    today = datetime.now(ZoneInfo('Europe/Dublin')).date()
    yesterday = today - timedelta(days=1)
    if ni['last'] < yesterday.isoformat():
        raise ValueError('Accepted NI history does not cover yesterday yet; retry after NI history collection')
    cache = work / 'dashboard/history-cache'
    cache.mkdir(parents=True, exist_ok=True)
    jobs = [(key, year, month, (today.year * 12 + today.month) - (year * 12 + month) <= 1)
        for year in range(start_year, today.year + 1) for month in range(1, 13)
        if date(year, month, 1) <= yesterday for key in GRID]
    grid = {key: defaultdict(list) for key in GRID}
    provenance, errors = [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(grid_month, job, cache, today): job for job in jobs}
        for number, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()
                provenance.append({key: value for key, value in result.items() if key != 'rows'})
                for stamp, value in result['rows']:
                    day, clock = stamp.split('T')
                    if day <= yesterday.isoformat():
                        grid[result['key']][day].append((clock, value))
            except Exception as error:
                errors.append(dict(job=futures[future][:3], error=str(error)))
            if number % 60 == 0 or number == len(jobs):
                print(f'ROI grid months: {number}/{len(jobs)}; request failures: {len(errors)}', flush=True)
    if errors:
        save(work / 'dashboard/history-failed-audit.json', json.dumps(errors, indent=2).encode())
        raise RuntimeError(f'{len(errors)} ROI history requests failed; prior publication retained. Cached successful months can be reused.')
    generated = datetime.now(ZoneInfo('UTC')).isoformat(timespec='seconds').replace('+00:00', 'Z')
    days = assemble(grid, ni, start_year, yesterday)
    data = dict(schema=1, dataBasis='public-source-history', generatedAt=generated, first=days[0]['date'],
        last=yesterday.isoformat(), series=[dict(series) for series in SERIES], days=days, requestFailures=0,
        gridDayBasis='source-labelled calendar dates; 96 quarter-hour observations; unfinished and incomplete days excluded',
        niSource={key: ni[key] for key in ['version', 'generatedAt', 'first', 'last']},
        northSouthBasis='negative of the accepted NI daily balance estimate at the same 96 source-labelled quarter-hours')
    refresh_coverage(data)
    save(cache / 'accepted-ni-history.json.gz', gzip.compress(json.dumps(ni, separators=(',', ':')).encode()))
    audit = dict(generatedAt=generated, gridRequests=provenance, niSource=data['niSource'],
        rules=dict(gridSamples=96, incompleteDays='null', currentDay='excluded', minimumMonthlyAnnualCoverage=.95))
    save(work / 'dashboard/history-audit.json', json.dumps(audit, separators=(',', ':')).encode())
    return data
