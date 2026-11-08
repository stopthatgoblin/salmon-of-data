"""Publish only validated public replay day JSON and its commit manifests.

``--seed`` uploads the prepared static archive once. Normal runs reconstruct
only the last seven UTC days, merge those days with accepted public versions,
and preserve older manifest records without downloading the old archive.
No publication occurs on module import. Use --local-dir for an offline KV store.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from electricity import replay

# cloud.py also serves direct ``python electricity/cloud.py`` execution and
# imports its adjacent forecasts module. Keep that existing adapter unchanged.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cloud

PUBLIC_KEY = re.compile(r'public/replay/(ni|roi)/(manifest|\d{4}-\d{2}-\d{2}/[a-f0-9]{24})\Z')
VERSION = re.compile(r'[a-f0-9]{24}\Z')
DAY = re.compile(r'\d{4}-\d{2}-\d{2}\Z')
DAY_LIMIT = 1024 * 1024
NORMAL_WRITE_LIMIT = 16
SEED_WRITE_LIMIT = 160


def _day(value):
    if not isinstance(value, str) or not DAY.fullmatch(value):
        raise ValueError('Invalid public replay date')
    date.fromisoformat(value)
    return value


def _configuration(data, region):
    if data.get('schema') != 1 or data.get('region') != region or region not in replay.GRID_KEYS:
        raise ValueError('Invalid replay identity')
    mapping = data.get('stationUnits')
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError('Missing replay station mapping')
    for sid, members in mapping.items():
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', sid) or not isinstance(members, list) or not members:
            raise ValueError('Invalid replay station mapping')
        if any(not isinstance(uid, str) or not re.fullmatch(r'GU_[A-Z0-9_]{1,32}', uid) for uid in members):
            raise ValueError('Invalid public replay unit ID')
    units = list(dict.fromkeys(uid for members in mapping.values() for uid in members))
    if data.get('unitIds') != units or data.get('gridKeys') != replay.GRID_KEYS[region]:
        raise ValueError('Replay columns do not match the unit mapping')
    if 'stationIds' in data and data['stationIds'] != list(mapping):
        raise ValueError('Replay station IDs differ from the mapping')
    return deepcopy(mapping)


def public_day(data, region, day):
    """Copy an allowlist; unknown fields, source caches and secrets are dropped."""
    mapping = _configuration(data, region)
    if data.get('date') != _day(day):
        raise ValueError('Replay day differs from its requested date')
    rows = []
    for source in data.get('rows', []):
        row = {key: deepcopy(source[key]) for key in ['time', 'grid', 'outputs', 'available', 'maximum', 'moyleAvailable']}
        row['stationBasis'] = source.get('stationBasis', 'metered-half-hour')
        if row['stationBasis'] == 'captured-dispatch-proxy':
            if not isinstance(source.get('collectedAt'), str):
                raise ValueError('Captured replay lacks a collection timestamp')
            row['collectedAt'] = replay.iso(replay.stamp(source['collectedAt']))
        rows.append(row)
    result = dict(schema=1, region=region, date=day, stationUnits=mapping,
                  unitIds=list(data['unitIds']), gridKeys=list(data['gridKeys']), basis=dict(replay.BASIS), rows=rows)
    replay.validate_day(result)
    if len(replay.encode(result)) > DAY_LIMIT:
        raise ValueError('Public replay day exceeds the conservative 1 MiB limit')
    return result


def _entry(data, version):
    region, day = data['region'], data['date']
    return dict(date=day, count=len(data['rows']), first=data['rows'][0]['time'], last=data['rows'][-1]['time'],
                version=version, url=f'/api/electricity/replay/{region}/{day}.json?v={version}')


def _manifest(data, region, *, versioned):
    mapping = _configuration(data, region)
    entries, seen = [], set()
    for source in data.get('days', []):
        day = _day(source['date'])
        if day in seen or isinstance(source.get('count'), bool) or not isinstance(source.get('count'), int) or source['count'] <= 0:
            raise ValueError('Invalid replay manifest day coverage')
        seen.add(day)
        first, last = source['first'], source['last']
        for value in [first, last]:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None or parsed.astimezone(replay.LOCAL).date().isoformat() != day:
                raise ValueError('Replay manifest timestamp does not match its local day')
        if replay.stamp(first) > replay.stamp(last):
            raise ValueError('Replay manifest interval is reversed')
        entry = dict(date=day, count=source['count'], first=first, last=last)
        if versioned:
            version = source.get('version', '')
            if not isinstance(version, str) or not VERSION.fullmatch(version):
                raise ValueError('Invalid published replay version')
            entry.update(version=version, url=f'/api/electricity/replay/{region}/{day}.json?v={version}')
        entries.append(entry)
    if not entries:
        raise ValueError('Replay manifest has no complete days')
    entries.sort(key=lambda item: item['date'])
    return dict(schema=1, region=region, stationIds=list(mapping), stationUnits=mapping,
                unitIds=list(data['unitIds']), gridKeys=list(data['gridKeys']), basis=dict(replay.BASIS), days=entries,
                first=entries[0]['first'], last=entries[-1]['last'])


def merge_day(previous, current):
    """Use the existing archive merge rules, including meter-over-proxy priority."""
    region, day = current['region'], current['date']
    with tempfile.TemporaryDirectory(prefix='electricity-replay-merge-') as directory:
        output = Path(directory)
        replay.save(output / region / (day + '.json'), replay.encode(previous))
        replay.export_region(region, current['stationUnits'], {day: current['rows']}, output,
                             replay.iso(datetime.now(replay.UTC)))
        return public_day(json.loads((output / region / (day + '.json')).read_text()), region, day)


def publish(kv, output_root, *, max_writes=NORMAL_WRITE_LIMIT, now=None):
    """Stage immutable public days, then advance complete per-region manifests.

    Older remote days absent from a bounded local run remain in the manifest.
    Only locally touched days with a new hash require downloading their prior
    public version. Unchanged runs perform no writes. No delete is performed.
    """
    output_root = Path(output_root)
    generated = replay.iso(now or datetime.now(replay.UTC))
    plans = []
    for region in ['ni', 'roi']:
        path = output_root / region / 'manifest.json'
        if not path.exists():
            continue
        local = _manifest(json.loads(path.read_text()), region, versioned=False)
        manifest_key = f'public/replay/{region}/manifest'
        previous_raw = kv.get(manifest_key)
        previous = _manifest(json.loads(previous_raw), region, versioned=True) if previous_raw is not None else None
        if previous and any(previous[key] != local[key] for key in ['stationUnits', 'unitIds', 'gridKeys']):
            raise ValueError('Published replay unit mapping changed; backfill/migrate the complete historical archive before publishing')
        records = {entry['date']: entry for entry in previous['days']} if previous else {}
        artifacts = []
        for local_entry in local['days']:
            day = local_entry['date']
            source = public_day(json.loads((output_root / region / (day + '.json')).read_text()), region, day)
            if source['stationUnits'] != local['stationUnits']:
                raise ValueError('Local replay day and manifest station mappings differ')
            raw = replay.encode(source)
            version = hashlib.sha256(raw).hexdigest()[:24]
            old = records.get(day)
            if old and version == old['version']:
                continue
            if old:
                previous_key = f'public/replay/{region}/{day}/{old["version"]}'
                day_raw = kv.get(previous_key)
                if day_raw is None or hashlib.sha256(day_raw).hexdigest()[:24] != old['version']:
                    raise ValueError('Previously published replay day is unavailable or has a hash mismatch; manifest retained')
                accepted = public_day(json.loads(day_raw), region, day)
                if accepted['stationUnits'] != source['stationUnits']:
                    raise ValueError('Published replay day mapping does not match its manifest')
                source = merge_day(accepted, source)
                raw = replay.encode(source)
                version = hashlib.sha256(raw).hexdigest()[:24]
                if version == old['version']:
                    continue
            entry = _entry(source, version)
            records[day] = entry
            artifacts.append((f'public/replay/{region}/{day}/{version}', raw))
        if previous and not artifacts:
            plans.append(dict(region=region, changed=False, artifacts=[], manifest_key=manifest_key,
                              manifest=None, days=len(previous['days'])))
            continue
        entries = [records[day] for day in sorted(records)]
        manifest = dict(schema=1, region=region, generatedAt=generated,
                        stationIds=local['stationIds'], stationUnits=local['stationUnits'],
                        unitIds=local['unitIds'], gridKeys=local['gridKeys'], basis=dict(replay.BASIS),
                        first=entries[0]['first'], last=entries[-1]['last'], days=entries)
        _manifest(manifest, region, versioned=True)
        plans.append(dict(region=region, changed=True, artifacts=artifacts, manifest_key=manifest_key,
                          manifest=replay.encode(manifest), days=len(entries)))
    if not plans:
        raise ValueError('No prepared public replay manifests found')
    writes = sum(len(plan['artifacts']) + int(plan['changed']) for plan in plans)
    if writes > max_writes:
        raise ValueError(f'Replay publication needs {writes} writes, exceeding the {max_writes} write budget; use the explicit bounded --seed for initial upload')
    # Nothing may become visible through a manifest until all day bytes have
    # succeeded. A failed staging write leaves the previous manifests intact.
    for plan in plans:
        for key, raw in plan['artifacts']:
            kv.put(key, raw)
    for plan in plans:
        if plan['changed']:
            kv.put(plan['manifest_key'], plan['manifest'])
    return dict(writes=writes, regions=[dict(region=plan['region'], changed=plan['changed'],
                                            newDayVersions=len(plan['artifacts']), days=plan['days']) for plan in plans])


class ReplayKV(cloud.KV):
    """Existing account/credential setup, with a bounded public-only write plan."""
    def __init__(self, max_writes=NORMAL_WRITE_LIMIT):
        super().__init__()
        self.max_writes = max_writes

    def request(self, method, key, value=None):
        if method not in ['GET', 'PUT'] or not PUBLIC_KEY.fullmatch(key):
            raise ValueError('Replay client permits only allowlisted public replay reads/writes')
        if method == 'PUT':
            self.writes += 1
            if self.writes > self.max_writes:
                raise RuntimeError('Bounded replay KV write budget exceeded')
        request = urllib.request.Request(self.url + urllib.parse.quote(key, safe=''), data=value, method=method,
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/octet-stream',
                     'User-Agent': 'SalmonOfDataElectricityReplay/1'})
        for attempt in range(3):
            self.operations[method.lower()] += 1
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    raw = response.read()
                if method == 'PUT' and json.loads(raw).get('success') is not True:
                    raise RuntimeError('Cloudflare rejected the public replay write')
                return raw
            except urllib.error.HTTPError as error:
                if method == 'GET' and error.code == 404:
                    return None
                if error.code not in (500, 502, 503, 504) or attempt == 2:
                    raise RuntimeError(f'Cloudflare replay KV {method}: HTTP {error.code}') from None
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise RuntimeError(f'Cloudflare replay KV {method}: connection failed') from None
            time.sleep(2 ** attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', action='store_true', help='Upload the prepared static archive using an explicit 160-write ceiling')
    parser.add_argument('--source', type=Path, default=replay.ROOT / 'public/data/electricity-replay')
    parser.add_argument('--cache', type=Path, default=replay.ROOT / 'outputs/electricity-replay')
    parser.add_argument('--local-dir', type=Path, help='Publish to a local filesystem KV; never contacts Cloudflare')
    args = parser.parse_args()
    limit = SEED_WRITE_LIMIT if args.seed else NORMAL_WRITE_LIMIT
    kv = cloud.FileKV(args.local_dir) if args.local_dir else ReplayKV(limit)
    if args.seed:
        result = publish(kv, args.source, max_writes=limit)
    else:
        today = datetime.now(replay.UTC).date()
        with tempfile.TemporaryDirectory(prefix='electricity-replay-recent-') as directory:
            source = Path(directory)
            options = argparse.Namespace(start=today - timedelta(days=7), end=today - timedelta(days=1),
                regions=['ni', 'roi'], cache=args.cache, output=source, retained_root=[],
                refresh_days=7, offline=False, skip_capacity=False)
            audit = replay.collect(options)
            if audit['failures']:
                raise RuntimeError('Recent replay source collection failed; published manifests retained')
            result = publish(kv, source, max_writes=limit)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
