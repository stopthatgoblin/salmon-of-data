"""Publish real ROI overview and historical data alongside the existing NI keys."""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile

import cloud
from roi import collect, history

ROOT = Path(__file__).resolve().parent.parent
PREFIX = 'roi/'


def accepted_ni(kv, name="snapshot"):
    pointer = kv.get_json(f'private/{name}/current') or kv.get_json(f'public/{name}/current')
    if not pointer or not pointer.get('records'):
        raise RuntimeError('Accepted NI snapshot is unavailable; ROI must use the same NI version')
    version = pointer['records'][0]['version']
    if not re.fullmatch('[a-f0-9]{24}', version):
        raise ValueError('Invalid NI version')
    raw = kv.get(f'public/{name}/{version}')
    if raw is None:
        raise RuntimeError('Newest NI version is still propagating; retry later')
    if hashlib.sha256(raw).hexdigest()[:24] != version:
        raise ValueError('Accepted NI snapshot checksum failed')
    data = json.loads(raw)
    cloud.validate(name, data)
    return {**data, 'version': version}


def validate(data, previous=None):
    finite = lambda value: isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if data.get('dataBasis') != 'public-source-capture':
        raise ValueError('ROI publication requires real public-source data')
    for key in ['demand', 'generation', 'wind', 'solar', 'other', 'otherGeneration', 'reconciliation']:
        if not finite(data.get(key)):
            raise ValueError('Invalid ROI reading: ' + key)
    at = cloud.stamp(data['time'])
    if at > datetime.now(cloud.UTC) + timedelta(minutes=5) or previous and at < cloud.stamp(previous['time']):
        raise ValueError('ROI observation moved backwards or into the future')
    cloud.stamp(data['retrievedAt'])
    ni = data['ni']
    if ni['time'] != data['time'] or not re.fullmatch('[a-f0-9]{24}', ni.get('version', '')):
        raise ValueError('ROI must reference an aligned accepted NI version')
    if not all(finite(ni.get(key)) for key in ['demand', 'generation', 'moyle']):
        raise ValueError('Incomplete accepted NI inputs')
    expected_sources = {'ROI:' + field for _, field in collect.FIELDS}
    sources = data['sources']['grid']
    if set(sources) != expected_sources or any(source['time'] != data['time'] or not finite(source['value']) for source in sources.values()):
        raise ValueError('Incomplete or misaligned ROI sources')
    for field, key in [('SYSTEM_DEMAND', 'demand'), ('GEN_EXP', 'generation'), ('WIND_ACTUAL', 'wind'), ('SOLAR_ACTUAL', 'solar')]:
        if sources['ROI:' + field]['value'] != data[key]:
            raise ValueError('ROI readings differ from retained source inputs')
    stations = data['stations']
    if len(stations) != len(collect.MAPPING) or {s['id'] for s in stations} != collect.MAPPING.keys():
        raise ValueError('Incomplete ROI station mapping')
    for station in stations:
        if [unit['id'] for unit in station['units']] != collect.MAPPING[station['id']]:
            raise ValueError('ROI unit mapping changed')
        for key in ['output', 'available', 'maximum']:
            values = [unit[key] for unit in station['units']]
            if any(value is not None and (not finite(value) or key != 'output' and value < 0) for value in values):
                raise ValueError('Invalid ROI unit reading')
            expected = sum(values) if all(finite(value) for value in values) else None
            if expected is None and station[key] is not None or expected is not None and (not finite(station[key]) or abs(expected - station[key]) > .001):
                raise ValueError('Invalid ROI station total')
    flows = {flow['id']: flow['value'] for flow in data['interconnectors']}
    if len(data['interconnectors']) != 3 or set(flows) != {'eastWest', 'greenlink', 'northSouth'} or not all(finite(v) for v in flows.values()):
        raise ValueError('Incomplete ROI interconnector flows')
    if flows['eastWest'] != sources['ROI:INTER_EWIC']['value'] or flows['greenlink'] != sources['ROI:INTER_GRNLK']['value']:
        raise ValueError('ROI flows differ from retained source inputs')
    checks = [flows['northSouth'] + ni['demand'] - ni['generation'] - ni['moyle'],
              data['demand'] - data['generation'] - sum(flows.values()) - data['reconciliation'],
              data['generation'] - data['wind'] - data['solar'] - sum(s['output'] or 0 for s in stations) - data['otherGeneration'],
              data['other'] - data['otherGeneration'] - data['reconciliation']]
    if any(abs(value) > .001 for value in checks):
        raise ValueError('Signed ROI balance failed')
    cloud.encode(data)


def run(kv, force=False):
    pointer = kv.get_json('private/roi/snapshot/current')
    if not force and pointer and cloud.snapshot_recent(pointer):
        print('A recent ROI overview collection already completed.')
        return
    attempt = cloud.iso()
    try:
        ni = accepted_ni(kv)
        with tempfile.TemporaryDirectory(prefix='roi-electricity-') as directory:
            work = Path(directory)
            output = work / 'dashboard/dist/assets/snapshot.json'
            output.parent.mkdir(parents=True)
            previous = None
            if pointer:
                pointer, previous = cloud.load_state(kv, 'snapshot', work, require_latest=True, prefix=PREFIX)
            else:
                # Only layout and reviewed asset mapping come from the fallback.
                # No initial publication occurs until fresh sources pass validation.
                shutil.copyfile(ROOT / 'public/data/roi-electricity/snapshot.json', output)
            collect.CACHE = work / 'research/dispatch_proxy/cache'
            collect.SNAPSHOT = output
            collect.NOW = datetime.now(cloud.UTC).replace(tzinfo=None)
            collect.collect()
            data = collect.build(ni)
            validate(data, previous)
            output.write_bytes(cloud.encode(data))
            cloud.prune_snapshot_cache(work)
            cloud.publish(kv, 'snapshot', work, data, pointer, prefix=PREFIX)
    except Exception:
        if pointer:
            key = 'private/roi/snapshot/current'
            current = kv.get_json(key)
            if current:
                kv.put(key, cloud.encode({**current, 'ok': False, 'lastAttempt': attempt}))
        raise


def run_history(kv, force=False, work_dir=None, start_year=2010):
    pointer = kv.get_json('private/roi/history/current')
    if pointer and not force and not cloud.history_due(pointer):
        print('ROI history already collected today, before 07:00, or within the retry interval.')
        return
    attempt = cloud.iso()
    temporary = None
    try:
        ni = accepted_ni(kv, 'history')
        if work_dir:
            work = Path(work_dir)
            work.mkdir(parents=True, exist_ok=True)
        else:
            temporary = tempfile.TemporaryDirectory(prefix='roi-history-')
            work = Path(temporary.name)
        previous = None
        if pointer:
            pointer, previous = cloud.load_state(kv, 'history', work, require_latest=True, prefix=PREFIX)
            start_year = min(start_year, int(previous['first'][:4]))
        data = history.collect(work, ni, start_year)
        if previous:
            history.retain_complete(data, previous)
        history.validate(data, previous)
        output = work / 'dashboard/dist/assets/history.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(cloud.encode(data))
        if data.get('retainedCompleteDays'):
            audit_path = work / 'dashboard/history-audit.json'
            audit = json.loads(audit_path.read_bytes())
            audit['retainedCompleteDays'] = data['retainedCompleteDays']
            audit_path.write_bytes(cloud.encode(audit))
        cloud.publish(kv, 'history', work, data, pointer, prefix=PREFIX)
        print(json.dumps({'region': 'ROI', 'first': data['first'], 'last': data['last'],
            'completeDays': {series['key']: series['days'] for series in data['series']}}))
    except Exception:
        if pointer:
            key = 'private/roi/history/current'
            current = kv.get_json(key)
            if current:
                kv.put(key, cloud.encode({**current, 'ok': False, 'lastAttempt': attempt}))
        raise
    finally:
        if temporary:
            temporary.cleanup()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['snapshot', 'history'])
    parser.add_argument('--local-dir', type=Path)
    parser.add_argument('--work-dir', type=Path, help='Retain history month caches across an initial backfill retry')
    parser.add_argument('--start-year', type=int, default=2010)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    kv = cloud.FileKV(args.local_dir) if args.local_dir else cloud.KV()
    force = args.force or os.environ.get('ELECTRICITY_FORCE') == 'true'
    if args.command == 'history':
        if not 2010 <= args.start_year <= datetime.now(cloud.UTC).year:
            parser.error('start-year must be between 2010 and the current year')
        run_history(kv, force, args.work_dir, args.start_year)
    else:
        run(kv, force)


if __name__ == '__main__':
    main()
