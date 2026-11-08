"""Export retained, source-backed NI/ROI dashboard replay as static day files.

Run ``python -m electricity.replay`` after daily collection. The public SEMO
index rolls forward, so the compressed report cache and exported day files are
retained rather than pruned. Missing inputs never become zero. A replay is a
retrospective reconstruction (including later meter revisions), not a record
of the dispatch estimate visitors saw at the time.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import gzip
import json
import math
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

from electricity.research.dispatch_proxy.analyse import STATIONS as NI_STATIONS

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
LOCAL = ZoneInfo('Europe/Dublin')
REPORTS = 'https://reports.sem-o.com'
GRID = {
    'demand': ('demand', 'demandactual', 'SYSTEM_DEMAND'),
    'generation': ('generation', 'generationactual', 'GEN_EXP'),
    'wind': ('wind', 'windactual', 'WIND_ACTUAL'),
    'solar': ('solar', 'solaractual', 'SOLAR_ACTUAL'),
    'moyle': ('interconnection', 'interconnection', 'INTER_MOYLE'),
    'eastWest': ('interconnection', 'interconnection', 'INTER_EWIC'),
    'greenlink': ('interconnection', 'interconnection', 'INTER_GRNLK'),
}
GRID_KEYS = {
    'ni': ['demand', 'generation', 'wind', 'solar', 'moyle'],
    'roi': ['demand', 'generation', 'wind', 'solar', 'eastWest', 'greenlink', 'niDemand', 'niGeneration', 'moyle'],
}
REPORT_NAMES = ['PUB_DailyMeterDataD1', 'PUB_DailyTechnicalOfferData', 'PUB_DlyGenUnitTechCharDataTrans']
BASIS = {
    'grid': 'Reported EirGrid/SONI quarter-hour observations; signed GB interconnector flows.',
    'stations': 'Row stationBasis distinguishes retrospective SEMO D+1 half-hour average MW from captured live dispatch proxies. Later meter data upgrades captured proxy outputs.',
    'availability': 'Historical SEMO outturn declarations where archived; null means unavailable, never today\'s declaration.',
    'maximum': 'Historical SEMO technical offer MaximumGeneration for the selected interval where archived; null means unavailable.',
    'time': 'Explicit Europe/Dublin offsets; source UTC timestamps aligned before local calendar grouping. DST repeats remain distinct instants.',
    'coverage': 'Only timestamps with all regional inputs and numeric meter outputs for every mapped unit are selectable. Other historical fields can be unavailable.',
}


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def stamp(text):
    """SEMO XML and source EffectiveTime are UTC without an offset."""
    value = datetime.fromisoformat(text.replace('Z', '+00:00'))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def encode(value):
    return json.dumps(value, separators=(',', ':'), allow_nan=False).encode()


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)


def read_gzip(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def fetch(url, headers=None):
    request = urllib.request.Request(url, headers={'Accept-Encoding': 'gzip', **(headers or {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
                return gzip.decompress(raw) if response.headers.get('Content-Encoding') == 'gzip' else raw
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def station_mapping(region):
    if region == 'ni':
        return {name.lower(): units for name, units in NI_STATIONS.items()}
    return json.loads((ROOT / 'electricity/roi/units.json').read_text())['stations']


def report_index(name, cache, offline=False):
    path = cache / (name + '-index.json')
    if offline:
        return json.loads(path.read_text())['items']
    items, page = [], 1
    while True:
        url = REPORTS + '/api/v1/documents/static-reports?' + urllib.parse.urlencode(dict(
            name=name, sort_by='PublishTime', order_by='ASC', page_size=300, page=page))
        data = json.loads(fetch(url))
        if not isinstance(data.get('items'), list):
            raise ValueError('Unexpected report index: ' + name)
        items.extend(data['items'])
        if page >= data['pagination']['totalPages']:
            break
        page += 1
    save(path, encode(dict(items=items, retrieved=iso(datetime.now(UTC)))))
    return items


def latest_per_date(items, first, last):
    latest = {}
    for item in items:
        if not first.isoformat() <= item['Date'] <= last.isoformat():
            continue
        if item['Date'] not in latest or item['PublishTime'] > latest[item['Date']]['PublishTime']:
            latest[item['Date']] = item
    return [latest[day] for day in sorted(latest)]


def parse_report(raw, resource, units):
    """Keep only relevant values, not the large complete-market XML reports."""
    root = ET.fromstring(raw)
    kind = root.attrib['DatasetName']
    rows, seen = [], {}
    for element in root:
        row = element.attrib
        uid = row.get('ResourceName')
        if uid not in units and not (kind == 'PUB_DlyGenUnitTechCharDataTrans' and uid == 'I_NIMOYLE'):
            continue
        if kind == 'PUB_DailyMeterDataD1':
            start = stamp(row['StartTime'])
            duration = (stamp(row['EndTime']) - start).total_seconds()
            if duration not in (1799, 1800):
                raise ValueError('Unexpected meter interval: ' + resource)
            if row.get('MeteredMW') in (None, ''):
                continue
            value = float(row['MeteredMW']) * 2  # BM-086 is interval MWh despite its field name.
            result = [uid, iso(start), value]
            key = (uid, result[1])
        elif kind == 'PUB_DailyTechnicalOfferData':
            if row.get('MaximumGeneration') in (None, ''):
                continue
            result = [uid, iso(stamp(row['StartTime'])), float(row['MaximumGeneration']), iso(stamp(row['EndTime']))]
            value = result[2]
            key = (uid, result[1], result[3])
        elif kind == 'PUB_DlyGenUnitTechCharDataTrans':
            if row.get('OutturnAvailability') in (None, ''):
                continue
            result = [uid, iso(stamp(row['EffectiveTime'])), float(row['OutturnAvailability']), iso(stamp(row['IssueTime']))]
            value = result[2]
            key = (uid, result[1], result[3])
        else:
            raise ValueError('Unexpected replay report: ' + kind)
        if not finite(value):
            raise ValueError('Non-finite report value: ' + resource)
        if key in seen and seen[key] != value:
            raise ValueError('Conflicting rows in ' + resource)
        if key not in seen:
            rows.append(result)
        seen[key] = value
    return dict(schema=1, kind=kind, resource=resource, date=root.attrib['Date'],
                published=root.attrib['PublishTime'], capturedUnits=sorted(units), rows=rows)


def load_report(item, cache, units, search_roots, offline=False):
    resource = item['ResourceName']
    target = cache / 'reports' / (resource + '.json.gz')
    if target.exists():
        data = read_gzip(target)
        if set(data.get('capturedUnits', [])) >= units:
            return data
    found = next((base / resource for base in search_roots if (base / resource).exists()), None)
    if found:
        raw = found.read_bytes()
    elif offline:
        raise FileNotFoundError('Replay report not cached: ' + resource)
    else:
        raw = fetch(REPORTS + '/documents/' + resource)
    result = parse_report(raw, resource, units)
    save(target, gzip.compress(encode(result)))
    return result


def month_jobs(start, end):
    cursor = start.replace(day=1)
    while cursor <= end:
        next_month = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        yield max(cursor, start), min(next_month - timedelta(days=1), end)
        cursor = next_month


def grid_month(region, key, first, last, cache, refresh, search_roots, offline=False):
    """Use <=28-day requests: upstream can silently return [] for long ranges."""
    target = cache / 'grid' / f'{region}-{key}-{first.year}-{first.month:02}.json.gz'
    if target.exists():
        result = read_gzip(target)
        if not refresh and result.get('rows') and result['first'] <= first.isoformat() and result['last'] >= last.isoformat():
            return result
    # Reuse retained monthly history when its bounded cache covers the range.
    if not refresh:
        for base in search_roots:
            old = base / f'{key}-{first.year}-{first.month:02}.json.gz'
            if old.exists():
                result = read_gzip(old)
                if result.get('rows') and max(row[0] for row in result['rows'])[:10] >= last.isoformat():
                    result = dict(result, first=first.isoformat(), last=last.isoformat(), region=region)
                    save(target, gzip.compress(encode(result)))
                    return result
    if offline:
        if target.exists():
            return read_gzip(target)
        raise FileNotFoundError('Replay grid month not cached: ' + target.name)
    chart, areas, field = GRID[key]
    rows, urls = [], []

    def request_window(window_start, window_end):
        url = 'https://www.smartgriddashboard.com/api/chart/?' + urllib.parse.urlencode(dict(
            region=region.upper(), chartType=chart, areas=areas, dateRange='custom',
            dateFrom=window_start.strftime('%d-%b-%Y'), dateTo=window_end.strftime('%d-%b-%Y')))
        urls.append(url)
        # The operator occasionally returns an empty successful response even
        # for a date range that succeeds moments later. Retry its body too.
        for attempt in range(3):
            data = json.loads(fetch(url, {'Eirgrid-Content-Request': 'Nextjs'}))
            if not isinstance(data.get('Rows'), list):
                raise ValueError('Unexpected grid response: ' + url)
            observations = []
            for row in data['Rows']:
                if row.get('Region') != region.upper() or row.get('FieldName') != field:
                    continue
                at = datetime.strptime(row['EffectiveTime'], '%d-%b-%Y %H:%M:%S')
                value = row.get('Value')
                if first <= at.date() <= last and finite(value):
                    observations.append([at.isoformat(), value])
            if observations:
                return observations
            if attempt < 2:
                time.sleep(attempt + 1)
        return []

    cursor = first
    while cursor <= last:
        window_end = min(last, cursor + timedelta(days=27))
        observations = request_window(cursor, window_end)
        if not observations and cursor < window_end:
            day = cursor
            while day <= window_end:
                observations.extend(request_window(day, day))
                day += timedelta(days=1)
        rows.extend(observations)
        cursor = window_end + timedelta(days=1)
    result = dict(region=region, key=key, first=first.isoformat(), last=last.isoformat(),
                  retrieved=iso(datetime.now(UTC)), rows=rows, urls=urls)
    save(target, gzip.compress(encode(result)))
    return result


def merge_meter(reports):
    """Latest revision wins; conflicting rows within a report are rejected earlier."""
    values = {}
    for report in sorted(reports, key=lambda item: item['published']):
        for uid, at, value, *_ in report['rows']:
            if finite(value):
                values[uid, stamp(at)] = (value, report['resource'])
    return values


def merge_grid(reports):
    values = defaultdict(dict)
    for report in sorted(reports, key=lambda item: item.get('retrieved', '')):
        local = {}
        for at, value in report['rows']:
            if not finite(value):
                continue
            at = stamp(at)
            if at in local and value != local[at]:
                raise ValueError('Conflicting observations in one grid response')
            local[at] = value
        values[report['region'], report['key']].update(local)
    return values


def declared_at(reports, units):
    """Return interval lookup for maximums and retrospective availability.

    A baseline report only applies to its own local trading day. This prevents
    the last declaration from a much later report leaking across a missing day.
    """
    maximum, availability = defaultdict(list), defaultdict(list)
    for report in sorted(reports, key=lambda item: item['published']):
        kind = report['kind']
        if kind == 'PUB_DailyTechnicalOfferData':
            for uid, at, value, until in report['rows']:
                maximum[uid].append((stamp(at), stamp(until), value, report['resource'], report['published']))
        elif kind == 'PUB_DlyGenUnitTechCharDataTrans':
            day = date.fromisoformat(report['date'])
            day_start = datetime.combine(day, datetime.min.time(), LOCAL).astimezone(UTC)
            day_end = datetime.combine(day + timedelta(days=1), datetime.min.time(), LOCAL).astimezone(UTC)
            grouped = defaultdict(dict)
            for uid, at, value, issued in report['rows']:
                at = stamp(at)
                previous = grouped[uid].get(at)
                if previous is None or issued > previous[1]:
                    grouped[uid][at] = (value, issued)
            for uid, events in grouped.items():
                times = sorted(events)
                for index, at in enumerate(times):
                    end = min(day_end, times[index + 1]) if index + 1 < len(times) else day_end
                    start = max(day_start, at)
                    if start < end:
                        availability[uid].append((start, end, events[at][0], report['resource'], report['published']))

    def read(mapping, uid, at):
        eligible = [entry for entry in mapping.get(uid, []) if entry[0] <= at < entry[1]]
        return max(eligible, key=lambda entry: (entry[4], entry[0]))[2] if eligible else None
    return lambda uid, at: read(availability, uid, at), lambda uid, at: read(maximum, uid, at)


def assemble(region, mapping, grid, meter, declarations, first, last):
    keys = GRID_KEYS[region]
    unit_ids = list(dict.fromkeys(uid for units in mapping.values() for uid in units))
    dependencies = [(('ni', key[2:].lower()) if key.startswith('ni') else
                     ('ni', 'moyle') if key == 'moyle' else (region, key)) for key in keys]
    common = set.intersection(*(set(grid.get(key, {})) for key in dependencies))
    days, omitted = defaultdict(list), defaultdict(int)
    available_at, maximum_at = declarations
    for at in sorted(common):
        local = at.astimezone(LOCAL)
        if not first <= local.date() <= last:
            continue
        half_hour = at.replace(minute=at.minute // 30 * 30, second=0, microsecond=0)
        if any((uid, half_hour) not in meter for uid in unit_ids):
            omitted[local.date().isoformat()] += 1
            continue
        days[local.date().isoformat()].append(dict(
            time=local.isoformat(timespec='seconds'),
            stationBasis='metered-half-hour',
            grid=[grid[key][at] for key in dependencies],
            outputs=[round(meter[uid, half_hour][0], 4) for uid in unit_ids],
            available=[available_at(uid, at) for uid in unit_ids],
            maximum=[maximum_at(uid, at) for uid in unit_ids],
            moyleAvailable=available_at('I_NIMOYLE', at),
        ))
    return days, omitted


def validate_day(data):
    if data.get('schema') != 1 or data.get('region') not in GRID_KEYS or not data.get('rows'):
        raise ValueError('Invalid replay day')
    mapped_units = list(dict.fromkeys(uid for units in data.get('stationUnits', {}).values() for uid in units))
    if data['gridKeys'] != GRID_KEYS[data['region']] or data['unitIds'] != mapped_units:
        raise ValueError('Invalid replay columns')
    previous = None
    for row in data['rows']:
        at = datetime.fromisoformat(row['time'])
        if at.tzinfo is None or at.astimezone(LOCAL).date().isoformat() != data['date']:
            raise ValueError('Replay timestamp must identify its local day and UTC offset')
        instant = at.astimezone(UTC)
        if instant.minute % 15 or instant.second or instant.microsecond:
            raise ValueError('Replay timestamp must be an exact quarter-hour')
        if previous and instant <= previous:
            raise ValueError('Replay times must be strictly chronological instants')
        previous = instant
        if len(row['grid']) != len(data['gridKeys']) or not all(finite(value) for value in row['grid']):
            raise ValueError('Incomplete grid input cannot be replayed')
        for key in ['outputs', 'available', 'maximum']:
            if len(row[key]) != len(data['unitIds']) or any(
                not finite(value) and not (key != 'outputs' and value is None) for value in row[key]
            ):
                raise ValueError('Incomplete replay unit outputs or invalid nullable declaration')
        if row['moyleAvailable'] is not None and not finite(row['moyleAvailable']):
            raise ValueError('Invalid Moyle declaration')
        basis = row.get('stationBasis', 'metered-half-hour')
        if basis not in ['metered-half-hour', 'captured-dispatch-proxy']:
            raise ValueError('Unknown replay station basis')
        if basis == 'captured-dispatch-proxy':
            collected = row.get('collectedAt')
            if not isinstance(collected, str) or datetime.fromisoformat(collected.replace('Z', '+00:00')).tzinfo is None:
                raise ValueError('Captured replay requires an explicit collection timestamp')


def export_region(region, mapping, days, output, generated, previous=True):
    unit_ids = list(dict.fromkeys(uid for units in mapping.values() for uid in units))
    directory = output / region
    accepted = {}
    # Preserve complete accepted timestamps if a rolling upstream window or a
    # temporary missing input would otherwise shrink replay coverage.
    for path in sorted(directory.glob('????-??-??.json')) if previous else []:
        data = json.loads(path.read_text())
        if data.get('unitIds') == unit_ids and data.get('stationUnits') == mapping:
            validate_day(data)
            accepted[data['date']] = data
    for day, rows in sorted(days.items()):
        merged = {iso(stamp(row['time'])): row for row in accepted.get(day, {}).get('rows', [])}
        for row in rows:
            key = iso(stamp(row['time']))
            old = merged.get(key)
            if old:
                old_basis = old.get('stationBasis', 'metered-half-hour')
                new_basis = row.get('stationBasis', 'metered-half-hour')
                if old_basis == 'metered-half-hour' and new_basis == 'captured-dispatch-proxy':
                    continue
                if old_basis == new_basis == 'captured-dispatch-proxy' and stamp(old['collectedAt']) > stamp(row['collectedAt']):
                    continue
                # A temporary absent declaration must not erase a previously
                # archived value for this same instant and identical unit set.
                row = dict(row)
                for column in ['available', 'maximum']:
                    row[column] = [new if new is not None else previous
                                   for new, previous in zip(row[column], old[column])]
                if row['moyleAvailable'] is None:
                    row['moyleAvailable'] = old['moyleAvailable']
            merged[key] = row
        data = dict(schema=1, region=region, date=day, gridKeys=GRID_KEYS[region], unitIds=unit_ids,
                    stationUnits=mapping, basis=BASIS, rows=[merged[key] for key in sorted(merged)])
        validate_day(data)
        accepted[day] = data
        save(directory / (day + '.json'), encode(data))
    if not accepted:
        raise ValueError('No complete replay timestamps for ' + region)
    records = [dict(date=day, count=len(data['rows']), first=data['rows'][0]['time'], last=data['rows'][-1]['time'],
                    url=f'/data/electricity-replay/{region}/{day}.json') for day, data in sorted(accepted.items())]
    manifest = dict(schema=1, region=region, generatedAt=generated,
                    first=records[0]['first'], last=records[-1]['last'],
                    stationIds=list(mapping), stationUnits=mapping, unitIds=unit_ids,
                    gridKeys=GRID_KEYS[region], basis=BASIS, days=records)
    save(directory / 'manifest.json', encode(manifest))
    return manifest


def snapshot_row(region, snapshot, mapping, collected_at=None):
    """Convert a complete accepted public snapshot; no private state is exposed."""
    at = stamp(snapshot['time'])
    local = at.astimezone(LOCAL)
    if at.minute % 15 or at.second or at.microsecond:
        raise ValueError('Accepted snapshot is not an exact quarter-hour')
    unit_ids = list(dict.fromkeys(uid for units in mapping.values() for uid in units))
    stations = {}
    for station in snapshot.get('stations', []):
        sid = station.get('id')
        if sid in stations:
            raise ValueError('Duplicate accepted snapshot station')
        stations[sid] = station
    units = {}
    for sid, members in mapping.items():
        if sid not in stations:
            raise ValueError('Accepted snapshot lacks mapped station: ' + sid)
        station_units = {unit['id']: unit for unit in stations[sid].get('units', [])}
        for uid in members:
            if uid not in station_units or not finite(station_units[uid].get('output')):
                raise ValueError('Accepted snapshot lacks numeric mapped unit: ' + uid)
            units[uid] = station_units[uid]
    values = {key: snapshot.get(key) for key in ['demand', 'generation', 'wind', 'solar', 'moyle']}
    if region == 'roi':
        ni = snapshot.get('ni', {})
        if not ni.get('time') or stamp(ni['time']) != at:
            raise ValueError('Accepted ROI snapshot lacks its matching NI grid cohort')
        links = {link['id']: link for link in snapshot.get('interconnectors', [])}
        values.update(eastWest=links.get('eastWest', {}).get('value'),
                      greenlink=links.get('greenlink', {}).get('value'),
                      niDemand=ni.get('demand'), niGeneration=ni.get('generation'), moyle=ni.get('moyle'))
    if not all(finite(values[key]) for key in GRID_KEYS[region]):
        raise ValueError('Accepted snapshot lacks complete numeric regional inputs')
    collected = collected_at or snapshot.get('capturedAt') or snapshot.get('retrievedAt')
    if not collected:
        raise ValueError('Accepted snapshot lacks a collection time')
    collected = iso(stamp(collected))

    def declaration(uid, key):
        value = units[uid].get(key)
        return value if finite(value) else None

    row = dict(time=local.isoformat(timespec='seconds'), stationBasis='captured-dispatch-proxy',
               collectedAt=collected, grid=[values[key] for key in GRID_KEYS[region]],
               outputs=[units[uid]['output'] for uid in unit_ids],
               available=[declaration(uid, 'available') for uid in unit_ids],
               maximum=[declaration(uid, 'maximum') for uid in unit_ids],
               moyleAvailable=snapshot.get('moyleAvailable') if finite(snapshot.get('moyleAvailable')) else None)
    return local.date().isoformat(), row


def journal_local(local_dir, output_root=ROOT / 'public/data/electricity-replay'):
    """Journal accepted local overview editions without fetching/backfilling.

    NI's mirror has a public pointer. ROI uses the canonical private commit
    pointer, but only its allowlisted *public JSON* records are opened. Private
    archive keys, archive contents and credentials never enter replay assets.
    """
    local_dir, output_root = Path(local_dir), Path(output_root)
    generated = iso(datetime.now(UTC))
    result = dict(generatedAt=generated, regions=[], skipped=[])
    for region, pointer_key in [('ni', 'public/snapshot/current'), ('roi', 'private/roi/snapshot/current')]:
        pointer_path = local_dir / pointer_key
        if not pointer_path.exists():
            result['skipped'].append(dict(region=region, reason='Accepted local pointer not yet available'))
            continue
        mapping = station_mapping(region)
        days = defaultdict(list)
        pointer = json.loads(pointer_path.read_text())
        prefix = 'public/roi/snapshot/' if region == 'roi' else 'public/snapshot/'
        for record in pointer.get('records', []):
            key = record.get('key', '')
            version = record.get('version', '')
            if not re.fullmatch(r'[a-f0-9]{24}', version) or key != prefix + version:
                result['skipped'].append(dict(region=region, reason='Pointer does not reference an allowlisted public snapshot'))
                continue
            try:
                snapshot = json.loads((local_dir / key).read_text())
                if not record.get('time') or stamp(snapshot['time']) != stamp(record['time']):
                    raise ValueError('Accepted pointer and public JSON observation times differ')
                day, row = snapshot_row(region, snapshot, mapping,
                                        snapshot.get('capturedAt') or snapshot.get('retrievedAt') or record.get('collectedAt'))
                days[day].append(row)
            except (OSError, ValueError, KeyError, TypeError) as error:
                result['skipped'].append(dict(region=region, version=version, reason=str(error)))
        if days or (output_root / region / 'manifest.json').exists():
            manifest = export_region(region, mapping, days, output_root, generated)
            result['regions'].append(dict(region=region, captured=sum(len(rows) for rows in days.values()),
                                          first=manifest['first'], last=manifest['last'], days=len(manifest['days'])))
    return result


def collect(args):
    cache, output = args.cache.resolve(), args.output.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    today = datetime.now(LOCAL).date()
    last = args.end or today - timedelta(days=1)
    mappings = {region: station_mapping(region) for region in args.regions}
    units = {uid for mapping in mappings.values() for members in mapping.values() for uid in members}
    indexes, failures = {}, []
    names = REPORT_NAMES[:1] if args.skip_capacity else REPORT_NAMES
    for name in names:
        indexes[name] = report_index(name, cache, args.offline)
    jobs = [(name, item) for name, items in indexes.items()
            for item in latest_per_date(items, args.start - timedelta(days=1), last + timedelta(days=1))]
    search_roots = [cache, ROOT / 'outputs/electricity-coverage-audit']
    reports = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(load_report, item, cache, units, search_roots, args.offline): (name, item)
                   for name, item in jobs}
        for number, future in enumerate(as_completed(futures), 1):
            try:
                reports.append(future.result())
            except Exception as error:
                name, item = futures[future]
                failures.append(dict(source=name, resource=item['ResourceName'], error=str(error)))
            if number % 15 == 0 or number == len(jobs):
                print(f'Replay reports {number}/{len(jobs)}; failed {len(failures)}', flush=True)

    # The source index is a rolling window. Reuse our accepted parsed reports
    # after they disappear upstream, including their historical declarations.
    retained_reports = {report['resource']: report for report in reports}
    for path in sorted((cache / 'reports').glob('*.xml.json.gz')):
        data = read_gzip(path)
        if data.get('schema') == 1 and set(data.get('capturedUnits', [])) >= units:
            retained_reports.setdefault(data['resource'], data)
    reports = list(retained_reports.values())
    meter_reports = [report for report in reports if report['kind'] == 'PUB_DailyMeterDataD1']
    # Parsed NI meter caches predate the current rolling public SEMO index.
    for base in args.retained_root:
        for path in base.glob('PUB_DailyMeterDataD1_*.xml.json.gz'):
            data = read_gzip(path)
            if data.get('rows'):
                meter_reports.append(dict(data, kind='PUB_DailyMeterDataD1'))
    meter = merge_meter(meter_reports)
    grid_jobs = []
    regions = {'ni': ['demand', 'generation', 'wind', 'solar', 'moyle']}
    if 'roi' in mappings:
        regions['roi'] = ['demand', 'generation', 'wind', 'solar', 'eastWest', 'greenlink']
    for region, keys in regions.items():
        for first, end in month_jobs(args.start - timedelta(days=1), last):
            for key in keys:
                refresh = (today - end).days <= args.refresh_days
                roots = ([ROOT / 'outputs/roi-history-backfill/dashboard/history-cache'] if region == 'roi' else [])
                roots.extend(base for base in args.retained_root if region == 'ni')
                grid_jobs.append((region, key, first, end, cache, refresh, roots, args.offline))
    grid_reports = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(grid_month, *job): job for job in grid_jobs}
        for number, future in enumerate(as_completed(futures), 1):
            try:
                grid_reports.append(future.result())
            except Exception as error:
                region, key, first, end = futures[future][:4]
                failures.append(dict(source='grid', region=region, key=key,
                                     first=first.isoformat(), last=end.isoformat(), error=str(error)))
            if number % 15 == 0 or number == len(grid_jobs):
                print(f'Replay grid months {number}/{len(grid_jobs)}; failed {len(failures)}', flush=True)
    grid = merge_grid(grid_reports)
    declarations = declared_at([report for report in reports if report['kind'] != 'PUB_DailyMeterDataD1'], units)
    generated = iso(datetime.now(UTC))
    summaries = []
    for region, mapping in mappings.items():
        days, omitted = assemble(region, mapping, grid, meter, declarations, args.start, last)
        manifest = export_region(region, mapping, days, output, generated)
        summary = dict(region=region, first=manifest['first'], last=manifest['last'],
                       days=len(manifest['days']), timestamps=sum(day['count'] for day in manifest['days']),
                       stations=len(mapping), units=len(manifest['unitIds']), omittedMissingMeters=dict(omitted))
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    audit = dict(generatedAt=generated, summaries=summaries, failures=failures,
                 meterReports=[{key: report[key] for key in ['resource', 'date', 'published']} for report in meter_reports],
                 gridSources=[{key: value for key, value in report.items() if key != 'rows'} for report in grid_reports])
    save(cache / 'audit.json', encode(audit))
    return audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', type=date.fromisoformat, default=date(2026, 9, 1))
    parser.add_argument('--end', type=date.fromisoformat)
    parser.add_argument('--regions', nargs='+', choices=['ni', 'roi'], default=['ni', 'roi'])
    parser.add_argument('--cache', type=Path, default=ROOT / 'outputs/electricity-replay')
    parser.add_argument('--output', type=Path, default=ROOT / 'public/data/electricity-replay')
    parser.add_argument('--retained-root', type=Path, action='append', default=[])
    parser.add_argument('--refresh-days', type=int, default=7)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--skip-capacity', action='store_true', help='Leave historical availability/maximum null when not cached')
    parser.add_argument('--journal-local', type=Path, help='Append accepted local snapshots only; no network or backfill')
    args = parser.parse_args()
    if args.end and args.end < args.start:
        parser.error('--end must not be before --start')
    if args.journal_local:
        print(json.dumps(journal_local(args.journal_local, args.output)), flush=True)
        return
    audit = collect(args)
    if audit['failures']:
        print(f"{len(audit['failures'])} requests failed; complete prior timestamps were retained. See {args.cache / 'audit.json'}", flush=True)


if __name__ == '__main__':
    main()
