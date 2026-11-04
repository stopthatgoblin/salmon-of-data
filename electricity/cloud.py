"""Run the original collectors with durable, bounded Workers KV state.

Only this adapter knows about Cloudflare. Calculation code in dashboard/ and
research/ is copied unchanged from the local NI electricity project.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo
import forecasts

ROOT = Path(__file__).resolve().parent
UTC = timezone.utc
UK = ZoneInfo('Europe/London')
MAX_ARCHIVE = 20 * 1024 * 1024  # Fail before KV's 25 MiB ceiling.
PUBLIC_SERIES = {'wind', 'solar', 'otherNI', 'moyle', 'northSouth', 'demand', 'generation'}


def encode(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def stamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def iso(now=None):
    return (now or datetime.now(UTC)).isoformat(timespec='seconds').replace('+00:00', 'Z')


class KV:
    def __init__(self, namespace=None, token=None):
        account = os.environ['CLOUDFLARE_ACCOUNT_ID']
        namespace = namespace or os.environ['ELECTRICITY_KV_NAMESPACE_ID']
        if not all(re.fullmatch(r'[a-f0-9]{32}', value) for value in [account, namespace]):
            raise ValueError('Invalid Cloudflare account or namespace ID')
        self.url = f'https://api.cloudflare.com/client/v4/accounts/{account}/storage/kv/namespaces/{namespace}/values/'
        self.token = token or os.environ['CLOUDFLARE_API_TOKEN']
        self.writes = 0

    def request(self, method, key, value=None):
        if method != 'GET':
            self.writes += 1
            if self.writes > 16:
                raise RuntimeError('Per-run KV mutation budget exceeded')
        request = urllib.request.Request(self.url + urllib.parse.quote(key, safe=''),
            data=value, method=method, headers={'Authorization': 'Bearer ' + self.token,
                'Content-Type': 'application/octet-stream', 'User-Agent': 'SalmonOfDataElectricity/1'})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    body = response.read()
                if method != 'GET' and json.loads(body).get('success') is not True:
                    raise RuntimeError('Cloudflare rejected the KV operation')
                return body
            except urllib.error.HTTPError as error:
                if method == 'GET' and error.code == 404:
                    return None
                # Quota/authentication errors never cause a retry storm.
                if error.code not in (500, 502, 503, 504) or attempt == 2:
                    raise RuntimeError(f'Cloudflare KV {method}: HTTP {error.code}') from None
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise RuntimeError(f'Cloudflare KV {method}: connection failed') from None
            time.sleep(2 ** attempt)

    def get(self, key):
        return self.request('GET', key)

    def get_json(self, key):
        raw = self.get(key)
        return json.loads(raw) if raw is not None else None

    def put(self, key, value):
        if len(value) > MAX_ARCHIVE:
            raise ValueError('KV value exceeds the conservative 20 MiB limit')
        self.request('PUT', key, value)

    def delete(self, key):
        self.request('DELETE', key)


class FileKV:
    """Local preview adapter; never used by scheduled production jobs."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.writes = 0

    def get(self, key):
        path = self.directory / key
        return path.read_bytes() if path.exists() else None

    def get_json(self, key):
        raw = self.get(key)
        return json.loads(raw) if raw is not None else None

    def put(self, key, value):
        path = self.directory / key
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(value)
        temporary.replace(path)
        self.writes += 1

    def delete(self, key):
        (self.directory / key).unlink(missing_ok=True)
        self.writes += 1


def validate(name, data, previous=None, now=None):
    now = now or datetime.now(UTC)
    def finite(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if name == 'snapshot':
        keys = ['demand', 'generation', 'wind', 'solar', 'other', 'moyle', 'northSouth']
        if not all(finite(data.get(key)) for key in keys):
            raise ValueError('Invalid snapshot readings')
        if len(data.get('stations', [])) != 3 or sum(len(s['units']) for s in data['stations']) != 13:
            raise ValueError('Incomplete station state')
        if abs(data['demand'] - data['generation'] - data['moyle'] - data['northSouth']) > .001:
            raise ValueError('Signed electricity balance failed')
        station_output = 0
        for station in data['stations']:
            for unit in station['units']:
                if not all(finite(unit[key]) and unit[key] >= 0 for key in ['output', 'available', 'maximum']):
                    raise ValueError('Invalid station unit')
            if abs(station['output'] - sum(unit['output'] for unit in station['units'])) > .001:
                raise ValueError('Station total failed')
            station_output += station['output']
        if abs(data['generation'] - data['wind'] - data['solar'] - data['other'] - station_output) > .001:
            raise ValueError('Generation balance failed')
        if stamp(data['time']) > now + timedelta(minutes=5):
            raise ValueError('Future grid reading')
        if previous and stamp(data['time']) < stamp(previous['time']):
            raise ValueError('Snapshot moved backwards')
        stamp(data['retrievedAt'])
    else:
        series = data.get('series', [])
        if not PUBLIC_SERIES <= {s['key'] for s in series} or not data.get('days') or data.get('requestFailures'):
            raise ValueError('Incomplete history')
        if data['last'] >= now.astimezone(UK).date().isoformat():
            raise ValueError('History includes an unfinished calendar day')
        prior_date = ''
        for row in data['days']:
            if not prior_date < row['date'] <= data['last'] or len(row['v']) != len(series) or len(row['n']) != len(series):
                raise ValueError('Invalid history dates or columns')
            prior_date = row['date']
            for index, value in enumerate(row['v']):
                if value is not None and (not finite(value) or row['n'][index] != series[index]['expected']):
                    raise ValueError('Partial history day passed as complete')
        if previous:
            if data['first'] > previous['first'] or data['last'] < previous['last']:
                raise ValueError('History range shrank')
            # Preserve collected history, including meter reports no longer in the rolling feed.
            indexes = {s['key']: i for i, s in enumerate(series)}
            rows = {row['date']: row for row in data['days']}
            for old in previous['days']:
                row = rows.get(old['date'])
                for i, value in enumerate(old['v']):
                    key = previous['series'][i]['key']
                    if value is not None and (row is None or key not in indexes or row['v'][indexes[key]] is None):
                        raise ValueError('Previously accepted historical day would be lost')
        stamp(data['generatedAt'])
    encode(data)


def archive(work, name, version):
    files = ['dashboard/dist/assets/' + name + '.json']
    if name == 'history':
        files += ['dashboard/history-cache', 'dashboard/history-audit.json']
    else:
        files += ['research/dispatch_proxy/cache']
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz', compresslevel=6) as tar:
        payload = encode({'schema': 1, 'version': version, 'dataset': name})
        info = tarfile.TarInfo('state.json')
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
        for relative in files:
            path = work / relative
            if path.exists():
                tar.add(path, arcname=relative, filter=lambda info: None if not (info.isfile() or info.isdir()) else info)
    raw = buffer.getvalue()
    if len(raw) > MAX_ARCHIVE:
        raise ValueError('Source state exceeds 20 MiB; retain the previous publication and review archive growth')
    return raw


def restore(raw, work, name, version):
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tar:
        info = json.load(tar.extractfile('state.json'))
        if info != {'schema': 1, 'version': version, 'dataset': name}:
            raise ValueError('KV state version mismatch')
        members = tar.getmembers()
        if sum(item.size for item in members) > 250 * 1024 * 1024:
            raise ValueError('Unreasonably large expanded state')
        allowed = ['dashboard/history-cache/', 'research/dispatch_proxy/cache/']
        exact = {'state.json', 'dashboard/history-cache', 'research/dispatch_proxy/cache',
                 'dashboard/history-audit.json', f'dashboard/dist/assets/{name}.json'}
        for item in members:
            path = PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or not (item.isfile() or item.isdir()):
                raise ValueError('Unsafe state archive path')
            if item.name not in exact and not any(item.name.startswith(prefix) for prefix in allowed):
                raise ValueError('Unexpected state archive member')
        for item in members:
            target = work / item.name
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(item).read())


def load_state(kv, name, work, require_latest=False, prefix=""):
    pointer = kv.get_json(f'private/{prefix}{name}/current')
    if not pointer:
        raise RuntimeError(f'{name} has not been seeded. Refusing a cold historical rebuild.')
    # Readers try the last accepted archive if a newer pointer arrived first.
    for record in pointer['records']:
        raw = kv.get(record['stateKey'])
        if raw is None or hashlib.sha256(raw).hexdigest() != record['stateSha256']:
            continue
        if require_latest and record['version'] != pointer['records'][0]['version']:
            raise RuntimeError('The newest durable state is still propagating; refusing to collect from an older archive')
        restore(raw, work, name, record['version'])
        data = json.loads((work / f'dashboard/dist/assets/{name}.json').read_bytes())
        return pointer, data
    raise RuntimeError('No complete durable state available; retry later without replacing published data')


def publish(kv, name, work, data, pointer=None, now=None, prefix=""):
    now = now or datetime.now(UTC)
    raw = encode(data)
    version = hashlib.sha256(raw).hexdigest()[:24]
    records = (pointer or {}).get('records', [])
    slot = ((records[0]['slot'] + 1) % 3) if records else 0
    packed = archive(work, name, version)
    record = {'version': version, 'slot': slot, 'stateKey': f'private/{prefix}{name}/state-{slot}',
              'stateSha256': hashlib.sha256(packed).hexdigest(), 'key': f'public/{prefix}{name}/{version}',
              'time': data.get('time', data.get('last')), 'collectedAt': data.get('retrievedAt', data.get('generatedAt'))}
    # All required bytes precede either pointer. Public versions never expose archives.
    kv.put(record['stateKey'], packed)
    kv.put(record['key'], raw)
    retained = [record] + [item for item in records if item['version'] != version][:2]
    next_pointer = {'schema': 1, 'records': retained, 'ok': True, 'lastSuccess': iso(now),
                    'successfulDate': now.astimezone(UK).date().isoformat(), 'lastAttempt': iso(now)}
    kv.put(f'private/{prefix}{name}/current', encode(next_pointer))
    public = {key: value for key, value in next_pointer.items() if key != 'records'}
    public['records'] = [{key: value for key, value in item.items() if key not in ('stateKey', 'stateSha256', 'slot')} for item in retained]
    kv.put(f'public/{prefix}{name}/current', encode(public))
    for old in records:
        if not any(item['version'] == old['version'] for item in retained):
            kv.delete(old['key'])
    print(json.dumps({'dataset': name, 'version': version, 'sourceTime': record['time'],
                      'stateBytes': len(packed), 'mutations': kv.writes}))


def history_due(pointer, now=None):
    now = now or datetime.now(UTC)
    local = now.astimezone(UK)
    if local.hour < 7 or (pointer or {}).get('successfulDate') == local.date().isoformat():
        return False
    # One bounded catch-up attempt per hour after the 07:00 primary run.
    last = (pointer or {}).get('lastAttempt')
    return not last or now - stamp(last) >= timedelta(minutes=55)


def preserve_complete_history(data, previous):
    """Retain accepted complete days when a later source refresh omits them.

    Grid inputs and their derived flows are one cohort: preserve its original
    vintage together instead of combining revised inputs with older residuals.
    Complete revisions still replace old values; genuinely missing days remain
    gaps. Range/schema/quality validation below continues to fail closed.
    """
    # Reject malformed/non-finite fresh values before a retained cohort could
    # replace them. Missing values are permitted; invalid values are not.
    validate('history', data)
    columns = {series['key']: i for i, series in enumerate(data['series'])}
    old_columns = {series['key']: i for i, series in enumerate(previous['series'])}
    old_rows = {row['date']: row for row in previous['days']}
    retained = {}
    for row in data['days']:
        old = old_rows.get(row['date'])
        if not old:
            continue
        missing = {key for key, index in columns.items() if key in old_columns
                   and old['v'][old_columns[key]] is not None and row['v'][index] is None}
        restore = (PUBLIC_SERIES & columns.keys() & old_columns.keys()) if missing & PUBLIC_SERIES else set()
        restore = restore | (missing - PUBLIC_SERIES)
        for key in sorted(restore):
            index, old_index = columns[key], old_columns[key]
            row['v'][index], row['n'][index] = old['v'][old_index], old['n'][old_index]
            if row['v'][index] is not None:
                retained.setdefault(key, []).append(row['date'])
    for index, series in enumerate(data['series']):
        dates = [row['date'] for row in data['days'] if row['v'][index] is not None]
        series.update(first=dates[0] if dates else None, last=dates[-1] if dates else None, days=len(dates))
    if retained:
        data['retainedCompleteDays'] = {'previousGeneratedAt': previous['generatedAt'], 'series': retained}
        print(json.dumps({'retainedCompleteHistory': {key: len(days) for key, days in retained.items()}}))


def prune_snapshot_cache(work, now=None):
    cutoff = ((now or datetime.now(UTC)) - timedelta(days=14)).strftime('%Y%m%d')
    for path in (work / 'research/dispatch_proxy/cache').glob('*.xml'):
        match = re.search(r'_(\d{8})\d*\.xml$', path.name)
        if match and match[1] < cutoff:
            path.unlink()


def make_work(path):
    for directory in ['dashboard', 'research/dispatch_proxy']:
        (path / directory).mkdir(parents=True, exist_ok=True)
        for source in (ROOT / directory).glob('*.py'):
            if not source.name.startswith('test_'):
                shutil.copyfile(source, path / directory / source.name)
    (path / 'dashboard/dist/assets').mkdir(parents=True, exist_ok=True)


def run(kv, name, force=False):
    pointer = kv.get_json(f'private/{name}/current')
    if name == 'history' and not force and not history_due(pointer):
        print('History already collected today, before 07:00, or within the retry interval.')
        return
    # Do not start duplicated overview jobs less than 10 minutes apart.
    if name == 'snapshot' and not force and pointer and pointer.get('lastSuccess') and datetime.now(UTC) - stamp(pointer['lastSuccess']) < timedelta(minutes=10):
        print('A recent overview run already completed.')
        return
    attempt = iso()
    try:
        with tempfile.TemporaryDirectory(prefix='ni-electricity-') as directory:
            work = Path(directory)
            make_work(work)
            pointer, previous = load_state(kv, name, work, require_latest=True)
            script = work / f'dashboard/refresh_{name}.py'
            subprocess.run([sys.executable, str(script)], check=True, timeout=600 if name == 'snapshot' else 1800)
            data = json.loads((work / f'dashboard/dist/assets/{name}.json').read_bytes())
            if name == 'snapshot':
                source = work / 'dashboard/runtime/source-snapshots' / data['sourceSnapshot']
                data['expectedPeaks'] = forecasts.collect(json.loads(source.read_bytes()), previous.get('expectedPeaks'))
            else:
                preserve_complete_history(data, previous)
                if data.get('retainedCompleteDays'):
                    audit_path = work / 'dashboard/history-audit.json'
                    audit = json.loads(audit_path.read_bytes())
                    audit['retainedCompleteDays'] = data['retainedCompleteDays']
                    audit_path.write_bytes(encode(audit))
            validate(name, data, previous)
            (work / f'dashboard/dist/assets/{name}.json').write_bytes(encode(data))
            if name == 'snapshot':
                prune_snapshot_cache(work)
            publish(kv, name, work, data, pointer)
    except Exception:
        # Independent health updates leave accepted data and state pointers intact.
        if pointer:
            pointer = {**(kv.get_json(f'private/{name}/current') or pointer), 'ok': False, 'lastAttempt': attempt}
            kv.put(f'private/{name}/current', encode(pointer))
            public = kv.get_json(f'public/{name}/current')
            if public:
                kv.put(f'public/{name}/current', encode({**public, 'ok': False, 'lastAttempt': attempt}))
        raise


def seed(kv, source, names):
    for name in names:
        if kv.get(f'private/{name}/current') is not None:
            raise RuntimeError(f'{name} already seeded; refusing to overwrite its accepted history')
        with tempfile.TemporaryDirectory(prefix='ni-seed-') as directory:
            work = Path(directory)
            make_work(work)
            data_file = source / f'dashboard/dist/assets/{name}.json'
            data = json.loads(data_file.read_bytes())
            validate(name, data)
            shutil.copyfile(data_file, work / f'dashboard/dist/assets/{name}.json')
            if name == 'history':
                shutil.copytree(source / 'dashboard/history-cache', work / 'dashboard/history-cache')
                shutil.copyfile(source / 'dashboard/history-audit.json', work / 'dashboard/history-audit.json')
            else:
                shutil.copytree(source / 'research/dispatch_proxy/cache', work / 'research/dispatch_proxy/cache')
                prune_snapshot_cache(work)
            # A seed is accepted historical state, not a successful fresh collection.
            publish(kv, name, work, data, now=stamp(data.get('retrievedAt', data.get('generatedAt'))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['snapshot', 'history', 'seed'])
    parser.add_argument('--source', type=Path, help='Root containing accepted dashboard/ and research/ directories')
    parser.add_argument('--force', action='store_true', help='Manual retry, bypass scheduling guard')
    parser.add_argument('--local-dir', type=Path, help='Use a filesystem KV store for local preview, without Cloudflare credentials')
    args = parser.parse_args()
    kv = FileKV(args.local_dir) if args.local_dir else KV()
    if args.command == 'seed':
        if not args.source:
            parser.error('seed requires --source')
        seed(kv, args.source, ['snapshot', 'history'])
    else:
        run(kv, args.command, args.force or os.environ.get('ELECTRICITY_FORCE') == 'true')


if __name__ == '__main__':
    main()
