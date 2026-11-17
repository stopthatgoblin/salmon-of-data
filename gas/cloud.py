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


def publish(store, snapshots, *, target=None, now=None, warnings=None, pending_days=None, checked_days=None):
    now = now or datetime.now(UTC)
    # Validate all candidates before making any new object visible.
    prepared = []
    for original in snapshots:
        data = deepcopy(validate(original))
        data.pop('version', None)
        data.pop('capacityReferences', None)
        version = hashlib.sha256(encode(data)).hexdigest()[:24]
        data['version'] = version
        prepared.append(data)
    manifest = store.get_json(MANIFEST) or dict(schema=1, days=[], latest=None)
    records = {row['date']: deepcopy(row) for row in manifest['days']}
    for data in prepared:
        day, version = data['gasDay'], data['version']
        unavailable = missing_demand(data)
        previous = records.get(day)
        # A temporary source failure must not downgrade an accepted edition.
        if previous and (not set(unavailable).issubset(previous.get('missingDemand', []))
                         or data['electricityBasis']['dispatchEstimateHours'] > previous.get('estimatedHours', 24)):
            continue
        store.put_json(f'public/gas/day/{day}/{version}', data)
        editions = list(records.get(day, {}).get('versions', []))
        if version not in editions:
            editions.append(version)
        records[day] = dict(date=day, version=version, versions=editions,
                            collectedAt=data.get('capturedAt', data['snapshotAsOf'] + 'T00:00:00Z'),
                            meteredHours=data['electricityBasis']['meteredHours'],
                            estimatedHours=data['electricityBasis']['dispatchEstimateHours'], missingDemand=unavailable)
    checked_days = checked_days or [row['gasDay'] for row in prepared]
    incomplete = [dict(date=day, missingDemand=records[day]['missingDemand']) for day in checked_days
                  if records.get(day, {}).get('missingDemand')]
    pending_days = pending_days or []
    pending = bool(pending_days or incomplete or (target and target.isoformat() not in records))
    require_primary = target is not None and target.isoformat() in records and not pending
    previous_status = store.get_json(STATUS) or {}
    status = dict(schema=1, lastAttempt=iso(now), lastSuccess=iso(now),
                  successfulDate=now.astimezone(LOCAL).date().isoformat() if require_primary else previous_status.get('successfulDate'),
                  targetGasDay=target.isoformat() if target else None,
                  lastError='Some gas days or electricity-demand readings are delayed; available gas data has been updated.' if pending else None,
                  waitingForSource=next((row for row in pending_days if target and row['gasDay'] == target.isoformat()
                                         and row['source'] in ('SEMO meter data', 'GNI daily data')), None),
                  pending=pending, pendingDays=pending_days, incompleteDays=incomplete, warnings=warnings or [])
    manifest.update(days=[records[day] for day in sorted(records)], latest=max(records) if records else None,
                    **{key: status[key] for key in ['lastAttempt', 'lastSuccess', 'lastError', 'waitingForSource',
                                                   'pending', 'pendingDays', 'incompleteDays']})
    # Objects first, public index last. KV propagation is handled by API/client retry.
    store.put_json(MANIFEST, manifest)
    store.put_json(STATUS, status)
    return manifest


def failure(store, target, now, error=None):
    status = store.get_json(STATUS) or {}
    pending = source_wait(error)
    status.update(schema=1, lastAttempt=iso(now), targetGasDay=target.isoformat(),
                  waitingForSource=pending, pending=True,
                  lastError=(str(error) + '; retaining the last accepted data.') if pending
                  else 'Daily update failed; retaining the last accepted data.')
    store.put_json(STATUS, status)
    manifest = store.get_json(MANIFEST)
    if manifest:
        manifest.update(lastAttempt=status['lastAttempt'], lastError=status['lastError'], waitingForSource=pending, pending=True)
        store.put_json(MANIFEST, manifest)


def source_wait(error):
    if isinstance(error, MeterDataPending):
        return dict(source='SEMO meter data', gasDay=error.gas_day, latestReportDate=error.latest_report_date)
    if isinstance(error, GasDataPending):
        return dict(source='GNI daily data', gasDay=error.gas_day)
    return None


def collect_and_publish(store, target, cache, revision_days=7, offline=False, *, now=None):
    collection = Collection(target, cache, revision_days, offline, allow_older=True)
    snapshots, warnings, pending_days, errors = [], [], [], []
    days = [target - timedelta(days=offset) for offset in range(revision_days)]
    for day in days:
        try:
            snapshots.append(collection.assemble(day))
        except Exception as error:
            errors.append(error)
            warnings.append(dict(date=day.isoformat(), reason=type(error).__name__))
            pending_days.append(source_wait(error) or dict(source='Source validation', gasDay=day.isoformat()))
            print(f'Gas day {day}: unavailable ({type(error).__name__}: {error}); retaining any accepted edition.', flush=True)
    if not snapshots:
        raise errors[0]
    return publish(store, snapshots, target=target, now=now, warnings=warnings,
                   pending_days=pending_days, checked_days=[day.isoformat() for day in days])


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
                              pending=manifest['pending'], pendingDays=manifest['pendingDays'],
                              incompleteDays=manifest['incompleteDays'])), flush=True)
        if os.environ.get('GITHUB_STEP_SUMMARY'):
            lines = ['## Gas collection', '', f"Requested gas day: **{target}**. Latest accepted: **{manifest['latest']}**.", '',
                     'Source recovery remains pending; scheduled retries continue.' if manifest['pending'] else 'All requested days and demand readings are complete.', '']
            lines += [f"- {row['gasDay']}: waiting for {row['source']}." for row in manifest['pendingDays']]
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
