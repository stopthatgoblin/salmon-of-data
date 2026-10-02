#!/usr/bin/env python3
"""Snapshot public NIEA probe records, preserving responses and query provenance.

Uses only Python's standard library and curl. Run from any working directory:
  python3 research/lough_neagh/daera/fetch.py
  python3 research/lough_neagh/daera/fetch.py --refresh
No QC exclusions are silently applied. The source labels every observation
provisional/non-validated; an epoch timestamp is not proof of correct logger time.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import subprocess
import threading
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median, quantiles
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'data/lough-neagh/raw/daera'
BASE = 'https://services-eu1.arcgis.com/kswen6BYexuc1SUk/arcgis/rest/services/DAERA_Probes_and_Metrics_Master_Layers_View/FeatureServer'
ITEMS = {'master': 'a8601cf7ae174f38a4a66ba8daaf5b73', 'toome': '4e56a999cb994698b5522dec539e15b3', 'washing_bay': 'cf7708c5d32b4747b175e1c82b112e48', 'reas_wood': 'f4ab731e16e844609717ff1e50e94cfa'}
METRICS = ('Turbidity', 'BGA_PC_Fluorescence')
LOCK = threading.Lock()


def iso(epoch):
    return dt.datetime.fromtimestamp(epoch / 1000, dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def save_gzip(path, data):
    # mtime=0 and empty filename make the derived encoding deterministic.
    with path.open('wb') as target:
        with gzip.GzipFile(fileobj=target, mode='wb', mtime=0, filename='') as stream:
            stream.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='create a new dated snapshot instead of reusing existing cached responses')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / 'manifest.json'
    previous = json.loads(manifest_path.read_text()) if manifest_path.exists() else {'requests': []}
    entries = {entry['url']: entry for entry in previous['requests']}
    run_at = dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z')
    stamp = run_at.replace(':', '').replace('-', '').replace('.', '_')

    def get(name, endpoint, params=None):
        params = params or {'f': 'json'}
        url = endpoint + '?' + urlencode(params)
        old = entries.get(url)
        if not args.refresh and old and (OUT / old['file']).exists():
            raw = gzip.decompress((OUT / old['file']).read_bytes())
            if hashlib.sha256(raw).hexdigest() != old['sha256_uncompressed']:
                raise RuntimeError(f'Cached response hash mismatch: {old["file"]}')
        else:
            result = subprocess.run(['curl', '-L', '--fail', '--silent', '--show-error', '--retry', '3', '--max-time', '90', url], check=True, capture_output=True)
            raw = result.stdout
            parsed = json.loads(raw)
            if 'error' in parsed:
                raise RuntimeError(f'ArcGIS error at {url}: {parsed["error"]}')
            digest = hashlib.sha256(raw).hexdigest()
            file = f'{name}-{digest[:12]}.json.gz'
            save_gzip(OUT / file, raw)
            entry = {'url': url, 'file': file, 'retrieved_at_utc': dt.datetime.now(dt.timezone.utc).isoformat().replace('+00:00', 'Z'), 'sha256_uncompressed': digest, 'bytes_uncompressed': len(raw)}
            with LOCK:
                entries[url] = entry
                manifest_path.write_text(json.dumps({'snapshot_started_utc': run_at, 'source': BASE, 'requests': sorted(entries.values(), key=lambda e: e['url'])}, indent=2) + '\n')
        parsed = json.loads(raw)
        if 'error' in parsed:
            raise RuntimeError(parsed['error'])
        return parsed

    get('service', BASE)
    schema = get('metrics-schema', BASE + '/1')
    get('stations-schema', BASE + '/0')
    for name, item in ITEMS.items():
        get(f'item-{name}', f'https://www.arcgis.com/sharing/rest/content/items/{item}')
    stations = get('stations', BASE + '/0/query', {'f': 'json', 'where': '1=1', 'outFields': '*', 'outSR': '4326'})
    (OUT / 'stations.json').write_text(json.dumps(stations, indent=2) + '\n')
    observations = []
    for metric in METRICS:
        predicate = f"Metric_Type='{metric}'"
        ids = get(f'{metric}-ids', BASE + '/1/query', {'f': 'json', 'where': predicate, 'returnIdsOnly': 'true'})['objectIds']
        ids = sorted(ids)
        chunks = [ids[i:i + 1000] for i in range(0, len(ids), 1000)]
        def page(pair):
            index, object_ids = pair
            # ID-range windows avoid server/proxy URL-length limits while the
            # captured ID list below still detects truncation or changed rows.
            where = f"{predicate} AND OBJECTID >= {object_ids[0]} AND OBJECTID <= {object_ids[-1]}"
            response = get(f'{metric}-page-{index:04}', BASE + '/1/query', {'f': 'json', 'where': where, 'outFields': '*', 'returnGeometry': 'false', 'orderByFields': 'OBJECTID ASC', 'resultRecordCount': 1000})
            if response.get('exceededTransferLimit'):
                raise RuntimeError('ArcGIS truncated a page')
            rows = [f['attributes'] for f in response['features']]
            if set(row['OBJECTID'] for row in rows) != set(object_ids):
                raise RuntimeError('Snapshot changed during retrieval or rows missing; rerun with --refresh')
            return rows
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for rows in pool.map(page, enumerate(chunks)):
                observations.extend(rows)
        print(f'{metric}: {len(ids)} source rows', flush=True)

    observations.sort(key=lambda r: (r['Probe_Ref_No'], r['Date'], r['Metric_Type'], r['OBJECTID']))
    fields = ['OBJECTID', 'Probe_Ref_No', 'Location', 'Metric_Value', 'Metric_Unit', 'Metric_Type', 'Date', 'timestamp_utc', 'GlobalID', 'source_quality_status']
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for row in observations:
        writer.writerow({**row, 'timestamp_utc': iso(row['Date']), 'source_quality_status': 'provisional_non_validated'})
    data = stream.getvalue().encode()
    save_gzip(OUT / 'observations.csv.gz', data)
    groups = defaultdict(list)
    for row in observations:
        groups[row['Probe_Ref_No'], row['Metric_Type']].append(row)
    audit = {'audit_generated_utc': run_at, 'source': BASE, 'source_row_count': len(observations), 'observations_sha256_uncompressed': hashlib.sha256(data).hexdigest(), 'date_fields_time_reference': schema.get('dateFieldsTimeReference'), 'quality_fields': [f['name'] for f in schema['fields'] if any(s in f['name'].lower() for s in ('qual', 'valid', 'flag', 'review', 'threshold', 'publish'))], 'source_view_definition_query': schema.get('viewDefinitionQuery'), 'groups': []}
    for (station, metric), rows in sorted(groups.items()):
        valid = [r['Metric_Value'] for r in rows if r['Metric_Value'] is not None]
        dates = sorted(set(r['Date'] for r in rows))
        deltas = [(b - a) / 60000 for a, b in zip(dates[:-1], dates[1:])]
        gaps = [(b - a, a, b) for a, b in zip(dates[:-1], dates[1:]) if b - a > 1800000]
        audit['groups'].append({'station': station, 'location': rows[0]['Location'], 'metric': metric, 'units': sorted(set(r['Metric_Unit'] for r in rows)), 'row_count': len(rows), 'first_utc': iso(dates[0]), 'last_utc': iso(dates[-1]), 'unique_timestamps': len(dates), 'duplicate_timestamp_rows': len(rows) - len(dates), 'null_values': len(rows) - len(valid), 'negative_values': sum(v < 0 for v in valid), 'above_published_range': sum(v > (4000 if metric == 'Turbidity' else 100) for v in valid), 'minimum': min(valid), 'maximum': max(valid), 'median': median(valid), 'quartiles': quantiles(valid, n=4, method='inclusive'), 'median_interval_minutes': median(deltas), 'common_intervals_minutes': Counter(deltas).most_common(5), 'gaps_greater_than_30_minutes': len(gaps), 'largest_gaps': [{'hours': gap / 3600000, 'from_utc': iso(a), 'to_utc': iso(b)} for gap, a, b in sorted(gaps, reverse=True)[:10]], 'rows_by_year': dict(sorted(Counter(iso(r['Date'])[:4] for r in rows).items()))})
        values_by_time = defaultdict(list)
        for row in rows:
            values_by_time[row['Date']].append(row['Metric_Value'])
        conflicts = [date for date, values in values_by_time.items() if len(set(values)) > 1]
        zero_runs = []
        current = []
        for date in dates:
            values = values_by_time[date]
            if set(values) == {0}:
                if current and date - current[-1] > 1800000:
                    zero_runs.append(current)
                    current = []
                current.append(date)
            elif current:
                zero_runs.append(current)
                current = []
        if current:
            zero_runs.append(current)
        longest = max(zero_runs, key=len, default=[])
        audit['groups'][-1].update({'zero_values': sum(v == 0 for v in valid), 'conflicting_duplicate_timestamps': len(conflicts), 'conflicting_duplicate_examples': [iso(date) for date in conflicts[:10]], 'longest_contiguous_zero_run': {'rows': len(longest), 'from_utc': iso(longest[0]) if longest else None, 'to_utc': iso(longest[-1]) if longest else None, 'hours_first_to_last': (longest[-1] - longest[0]) / 3600000 if longest else 0}})
    (OUT / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    # Preserve each completed manifest so later refreshes do not erase the
    # request/response mapping underlying a previously generated audit.
    (OUT / f'manifest-{hashlib.sha256(data).hexdigest()[:12]}.json').write_text(manifest_path.read_text())
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    main()
