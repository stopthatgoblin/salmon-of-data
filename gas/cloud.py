"""Collect, validate and publish immutable gas days and an append-only date index.

Use --local-dir to run the exact publication path without cloud credentials.
GitHub Actions uses GAS_KV_NAMESPACE_ID and the existing Cloudflare API secret.
"""
import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from gas.collect import Collection, validate
from gas.sources import GasDataPending, MeterDataPending, iso

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = 'public/gas/manifest'
STATUS = 'private/gas/status'
UTC = timezone.utc
LOCAL = ZoneInfo('Europe/Dublin')


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


class LocalStore:
    def __init__(self, root):
        self.root = Path(root)

    def get_json(self, key):
        path = self.root / key
        return json.loads(path.read_text()) if path.exists() else None

    def put_json(self, key, value):
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(encode(value))
        temporary.replace(path)


class CloudStore:
    def __init__(self):
        account = os.environ['CLOUDFLARE_ACCOUNT_ID']
        namespace = os.environ['GAS_KV_NAMESPACE_ID']
        if not all(re.fullmatch('[a-f0-9]{32}', v) for v in [account, namespace]):
            raise ValueError('Invalid Cloudflare gas configuration')
        self.base = f'https://api.cloudflare.com/client/v4/accounts/{account}/storage/kv/namespaces/{namespace}/values/'
        self.token = os.environ['CLOUDFLARE_API_TOKEN']
        self.writes = 0

    def request(self, key, value=None):
        method = 'GET' if value is None else 'PUT'
        if method == 'PUT':
            self.writes += 1
            if self.writes > 32 or len(value) > 1024 * 1024:
                raise ValueError('Gas publication exceeded its bounded write/size budget')
        request = urllib.request.Request(self.base + urllib.parse.quote(key, safe=''), data=value, method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json', 'User-Agent': 'SalmonOfDataGas/1'})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read()
                if method == 'PUT' and json.loads(body).get('success') is not True:
                    raise RuntimeError('Cloudflare rejected gas publication')
                return body
            except urllib.error.HTTPError as error:
                if method == 'GET' and error.code == 404:
                    return None
                if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise RuntimeError(f'Cloudflare gas {method}: HTTP {error.code}') from None
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise RuntimeError('Cloudflare gas connection failed') from None
            time.sleep(2 ** attempt)

    def get_json(self, key):
        raw = self.request(key)
        return json.loads(raw) if raw is not None else None

    def put_json(self, key, value):
        self.request(key, encode(value))


def missing_demand(data):
    return [region for region in ['ni', 'roi'] if data['regions'][region]['demand'] is None]


def missing_metrics(data):
    return sorted([region + '.' + field for region in ['ni', 'roi']
                  for field in ['demand', 'electricity', 'powerGas'] if data['regions'][region][field] is None]
                  + (['hourly'] if data['hourly'] == [] else []))


def fingerprint(data):
    # Observation and publication identities matter; the time we checked does
    # not turn an otherwise identical immutable edition into a new revision.
    stable = deepcopy(data)
    for key in ['version', 'capturedAt', 'snapshotAsOf', 'capacityReferences']:
        stable.pop(key, None)
    stable.get('reuse', {}).pop('entsogExtractionDate', None)
    return hashlib.sha256(encode(stable)).hexdigest()[:24]


def record_missing(record):
    return record.get('missingMetrics', [region + '.demand' for region in record.get('missingDemand', [])])


def estimates(data):
    basis = data['electricityBasis']
    return {region: (basis['regional'][region]['dispatchEstimateHours'] if basis.get('regional', {}).get(region) else None)
            if 'regional' in basis else basis['dispatchEstimateHours'] for region in ['ni', 'roi']}


def publish(store, snapshots, *, target=None, now=None, warnings=None, pending_days=None, checked_days=None):
    now = now or datetime.now(UTC)
    prepared = [deepcopy(validate(original)) for original in snapshots]
    manifest = store.get_json(MANIFEST) or dict(schema=1, days=[], latest=None)
    previous_status = store.get_json(STATUS) or {}
    records = {row['date']: deepcopy(row) for row in manifest['days']}
    changed = []
    for data in prepared:
        day = data['gasDay']
        previous = records.get(day)
        unavailable, coverage = missing_metrics(data), estimates(data)
        if previous:
            prior_estimates = previous.get('regionalEstimates', {region:previous.get('estimatedHours',24) for region in ['ni','roi']})
            if (not set(unavailable).issubset(record_missing(previous)) or any(
                    coverage[region] is not None and prior_estimates.get(region) is not None
                    and coverage[region] > prior_estimates[region] for region in ['ni','roi'])):
                continue
        version = fingerprint(data)
        previous_fingerprint = previous.get('fingerprint') if previous else None
        if previous and previous_fingerprint is None:
            accepted = store.get_json(f"public/gas/day/{day}/{previous['version']}")
            previous_fingerprint = fingerprint(accepted) if accepted else None
        if version == previous_fingerprint:
            # Do not rewrite an immutable object with a later capture time.
            continue
        data.pop('capacityReferences', None)
        data['version'] = version
        editions = list(previous.get('versions', []) if previous else [])
        if version in editions:
            accepted = store.get_json(f'public/gas/day/{day}/{version}')
            if accepted is None:raise RuntimeError('An accepted gas edition is missing')
            data = accepted
        else:
            store.put_json(f'public/gas/day/{day}/{version}', data)
            editions.append(version)
        records[day] = dict(date=day, version=version, fingerprint=version, versions=editions,
            collectedAt=data.get('capturedAt', data['snapshotAsOf']+'T00:00:00Z'),
            meteredHours=data['electricityBasis']['meteredHours'], estimatedHours=data['electricityBasis']['dispatchEstimateHours'],
            regionalEstimates=coverage, missingDemand=missing_demand(data),
            missingElectricity=[region for region in ['ni','roi'] if data['regions'][region]['electricity'] is None],
            missingHourly=data['hourly'] == [], missingMetrics=unavailable, sourcePending=data.get('sourceChecks',{}).get('pending',[]))
        changed.append(day)
    checked_days = set(checked_days or [row['gasDay'] for row in prepared])
    # Outstanding days survive the rolling revision window. A checked day is
    # removed only when its sources and all accepted metrics have recovered.
    pending_by_day = {row['gasDay']:row for row in previous_status.get('pendingDays',[]) if row['gasDay'] not in checked_days}
    pending_by_day.update({row['gasDay']:row for row in pending_days or []})
    incomplete = []
    for day, record in sorted(records.items()):
        missing = record_missing(record)
        if missing:
            row = dict(date=day, missingDemand=record.get('missingDemand',[]))
            if record.get('missingElectricity'):row['missingElectricity']=record['missingElectricity']
            if record.get('missingHourly'):row['missingHourly']=True
            incomplete.append(row)
            reason = next(iter(record.get('sourcePending',[])), None)
            pending_by_day.setdefault(day, reason or dict(source='Electricity demand',gasDay=day))
    pending_days = [pending_by_day[day] for day in sorted(pending_by_day, reverse=True)]
    latest = max(records) if records else None
    target_day = target.isoformat() if target else None
    target_complete = bool(target_day and target_day in records and not record_missing(records[target_day]))
    pending = bool(pending_days or incomplete or (target_day and target_day not in records))
    checked = iso(now)
    status = dict(schema=2, lastAttempt=checked, lastChecked=checked,
        lastSuccess=checked if target_complete else previous_status.get('lastSuccess'),
        lastComplete=checked if target_complete else previous_status.get('lastComplete'),
        lastDataChange=checked if changed else previous_status.get('lastDataChange', manifest.get('lastDataChange')),
        lastDateAdvance=checked if latest and (not manifest.get('latest') or latest > manifest['latest']) else previous_status.get('lastDateAdvance'),
        successfulDate=now.astimezone(LOCAL).date().isoformat() if target_complete else previous_status.get('successfulDate'),
        targetGasDay=target_day, targetComplete=target_complete, latestGasDay=latest,
        outcome='updated' if changed else 'waiting' if pending else 'unchanged',
        changedDays=sorted(changed), lastError=None,
        waitingForSource=next((row for row in pending_days if row['gasDay'] == target_day), None),
        pending=pending, pendingDays=pending_days, incompleteDays=incomplete, warnings=warnings or [])
    public_keys = ['lastAttempt','lastChecked','lastSuccess','lastComplete','lastDataChange','lastDateAdvance',
        'targetGasDay','targetComplete','latestGasDay','outcome','changedDays','lastError','waitingForSource',
        'pending','pendingDays','incompleteDays']
    manifest.update(days=[records[day] for day in sorted(records)], latest=latest,
                    **{key:status[key] for key in public_keys})
    store.put_json(MANIFEST,manifest)
    store.put_json(STATUS,status)
    return manifest


def failure(store, target, now, error=None):
    status = store.get_json(STATUS) or {}
    pending = source_wait(error) or dict(source='Source validation',gasDay=target.isoformat(),reason=type(error).__name__)
    by_day={row['gasDay']:row for row in status.get('pendingDays',[])}
    by_day[target.isoformat()]=pending
    status.update(schema=2,lastAttempt=iso(now),lastChecked=iso(now),targetGasDay=target.isoformat(),
                  targetComplete=False,waitingForSource=pending,pending=True,pendingDays=list(by_day.values()),
                  outcome='waiting' if source_wait(error) else 'failed',changedDays=[],
                  lastError=(str(error)+'; retaining the last accepted data.') if source_wait(error)
                  else 'Daily update failed; retaining the last accepted data.')
    store.put_json(STATUS,status)
    manifest=store.get_json(MANIFEST)
    if manifest:
        manifest.update(**{key:status[key] for key in ['lastAttempt','lastChecked','targetGasDay','targetComplete',
            'waitingForSource','pending','pendingDays','outcome','changedDays','lastError']})
        store.put_json(MANIFEST,manifest)


def source_wait(error):
    if isinstance(error,MeterDataPending):
        return dict(source='SEMO meter data',gasDay=error.gas_day,latestReportDate=error.latest_report_date,
                    **(dict(reason=error.reason) if error.reason else {}))
    if isinstance(error,GasDataPending):
        return dict(source='GNI daily data',gasDay=error.gas_day,**(dict(reason=error.reason) if error.reason else {}))
    return None


def collection_days(store,target,revision_days):
    if not 1 <= revision_days <= 14:raise ValueError('Invalid revision window')
    days=[target-timedelta(days=offset) for offset in range(revision_days)]
    status=store.get_json(STATUS) or {}
    outstanding={row['gasDay'] for row in status.get('pendingDays',[])}
    outstanding.update(row['date'] for row in status.get('incompleteDays',[]))
    # Rotate a bounded oldest-first batch; a single permanently broken date
    # must not starve other historical repairs.
    after=status.get('backlogCursor','')
    older=sorted(day for day in outstanding if day < days[-1].isoformat())
    ordered=[day for day in older if day > after]+[day for day in older if day <= after]
    return days+[date.fromisoformat(day) for day in ordered[:2]]


def collect_and_publish(store,target,cache,revision_days=7,offline=False,*,now=None):
    days=collection_days(store,target,revision_days)
    collection=Collection(target,cache,revision_days,offline,allow_older=True,gas_first=True)
    snapshots,warnings,pending_days,errors=[],[],[],[]
    for index,day in enumerate(days):
        try:
            runner=collection if index < revision_days else Collection(day,cache,1,offline,allow_older=True,gas_first=True)
            snapshots.append(runner.assemble(day))
        except Exception as error:
            errors.append(error)
            warnings.append(dict(date=day.isoformat(),reason=type(error).__name__))
            pending_days.append(source_wait(error) or dict(source='Source validation',gasDay=day.isoformat(),reason=str(error)))
            print(f'Gas day {day}: unavailable ({type(error).__name__}: {error}); retaining any accepted edition.',flush=True)
    if not snapshots:raise errors[0]
    manifest=publish(store,snapshots,target=target,now=now,warnings=warnings,pending_days=pending_days,
                     checked_days=[day.isoformat() for day in days])
    if len(days)>revision_days:
        status=store.get_json(STATUS)
        status['backlogCursor']=days[-1].isoformat()
        store.put_json(STATUS,status)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gas-day', type=date.fromisoformat)
    parser.add_argument('--revision-days', type=int, default=7)
    parser.add_argument('--cache', type=Path, default=ROOT / 'outputs/gas-live/sources')
    parser.add_argument('--local-dir', type=Path)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--seed', action='store_true')
    parser.add_argument('--seed-only', action='store_true')
    parser.add_argument('--automatic', action='store_true')
    parser.add_argument('--export', type=Path)
    args = parser.parse_args()
    now = datetime.now(UTC)
    target = args.gas_day or now.astimezone(LOCAL).date() - timedelta(days=1)
    if target >= now.astimezone(LOCAL).date():
        parser.error('Only completed gas days can be collected')
    store = LocalStore(args.local_dir) if args.local_dir else CloudStore()
    status = store.get_json(STATUS) or {}
    if args.automatic and not (status.get('pending') or status.get('lastError')) and status.get('successfulDate') == now.astimezone(LOCAL).date().isoformat() and status.get('targetGasDay') == target.isoformat():
        print('Gas: this local date already completed successfully.')
        return
    if args.seed or args.seed_only:
        seeds = [json.loads((ROOT / 'public/data/ireland-gas' / (day + '.json')).read_text()) for day in ['2026-11-08', '2026-11-09']]
        publish(store, seeds, now=now)
    if args.seed_only:
        return
    status.update(lastAttempt=iso(now), targetGasDay=target.isoformat())
    store.put_json(STATUS, status)
    try:
        manifest = collect_and_publish(store, target, args.cache, args.revision_days, args.offline)
        if args.export:
            args.export.parent.mkdir(parents=True, exist_ok=True)
            record = next(row for row in manifest['days'] if row['date'] == manifest['latest'])
            args.export.write_bytes(encode(store.get_json(f"public/gas/day/{record['date']}/{record['version']}")))
        print(json.dumps(dict(latest=manifest['latest'], target=target.isoformat(), acceptedDays=len(manifest['days']),
                              outcome=manifest['outcome'], changedDays=manifest['changedDays'], targetComplete=manifest['targetComplete'],
                              pending=manifest['pending'], pendingDays=manifest['pendingDays'],
                              incompleteDays=manifest['incompleteDays'])), flush=True)
        if os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as output:
                output.write('changed=' + str(bool(manifest['changedDays'])).lower() + '\n')
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            lines = ['## Gas collection', '', f"Requested gas day: **{target}**. Latest accepted: **{manifest['latest']}**.", '',
                     f"Collection outcome: **{manifest['outcome']}**. Requested day complete: **{manifest['targetComplete']}**.",
                     f"Last data change: {manifest.get('lastDataChange') or 'none'}.",
                     'Source recovery remains pending; scheduled retries continue.' if manifest['pending'] else 'All requested days and readings are complete.', '']
            lines += [f"- {row['gasDay']}: waiting for {row['source']}." + (' ' + row['reason'] if row.get('reason') else '')
                      for row in manifest['pendingDays']]
            lines += [f"- {row['date']}: electricity demand unavailable for {', '.join(r.upper() for r in row['missingDemand'])}."
                      for row in manifest['incompleteDays']]
            with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
                output.write('\n'.join(lines) + '\n')
    except Exception as error:
        failure(store, target, datetime.now(UTC), error)
        print('Gas collection failed: ' + str(error), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
