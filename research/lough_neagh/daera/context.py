#!/usr/bin/env python3
"""Archive metadata, official guidance, and older DAERA data discovery.

Read-only public endpoints; use --refresh to recheck changing metadata.
No missing records or private source data are inferred from public views.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'data/lough-neagh/raw/daera/context'
ARCGIS = 'https://services-eu1.arcgis.com/kswen6BYexuc1SUk/arcgis/rest/services/'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / 'manifest.json'
    records = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    entries = {r['url']: r for r in records}

    def get(name, endpoint, params=None, html=False):
        url = endpoint + ('?' + urlencode(params or {'f': 'json'}) if not html else '')
        if url in entries and not args.refresh:
            raw = gzip.decompress((OUT / entries[url]['file']).read_bytes())
            if hashlib.sha256(raw).hexdigest() != entries[url]['sha256']:
                raise RuntimeError('Metadata cache hash mismatch')
        else:
            raw = subprocess.run(['curl', '-L', '--fail', '--silent', '--show-error', '--retry', '3', '--max-time', '90', url], capture_output=True, check=True).stdout
            digest = hashlib.sha256(raw).hexdigest()
            file = f'{name}-{digest[:12]}.{"html" if html else "json"}.gz'
            with (OUT / file).open('wb') as target:
                with gzip.GzipFile(fileobj=target, mode='wb', mtime=0, filename='') as output:
                    output.write(raw)
            entries[url] = {'url': url, 'file': file, 'sha256': digest, 'retrieved_at_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
            manifest_path.write_text(json.dumps(list(entries.values()), indent=2) + '\n')
        if html:
            return None
        result = json.loads(raw)
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result

    summary = {'station_views': []}
    for name, service in [('reas-wood', 'Reas_Wood_AquaTROLL_Metrics_View_'), ('washing-bay', 'Washing_Bay_AquaTROLL_Metrics_View'), ('toome', 'Toome_AquaTROLL_Metrics_View')]:
        layer = ARCGIS + service + '/FeatureServer/1'
        schema = get(name + '-schema', layer)
        stats = get(name + '-stats', layer + '/query', {'f': 'json', 'where': "Metric_Type='Turbidity'", 'outStatistics': json.dumps([{'statisticType': s, 'onStatisticField': f, 'outStatisticFieldName': n} for s, f, n in [('count', 'OBJECTID', 'rows'), ('min', 'Date', 'first'), ('max', 'Date', 'last'), ('min', 'Metric_Value', 'minimum'), ('max', 'Metric_Value', 'maximum')]])})
        summary['station_views'].append({'name': name, 'url': layer, 'definition': schema.get('viewDefinitionQuery'), 'statistics': stats.get('features')})
    get('official-faq', 'https://www.daera-ni.gov.uk/articles/lough-neagh-water-quality-dashboard-faq', html=True)
    get('official-launch', 'https://www.daera-ni.gov.uk/news/daera-launches-lough-neagh-blue-green-data-viewer', html=True)
    for topic, query in [('monitoring', 'orgid:kswen6BYexuc1SUk AND (title:Monitoring OR title:Quality)'), ('lake', 'orgid:kswen6BYexuc1SUk AND (title:Lough OR title:Lake OR title:Master)')]:
        get('discovery-' + topic, 'https://www.arcgis.com/sharing/rest/search', {'f': 'json', 'q': query, 'num': 100})
    older = ARCGIS + 'River_Water_Quality_Monitoring_1990_to_2024_All_Parameters/FeatureServer/0'
    schema = get('older-river-schema', older)
    summary['older_river_fields'] = [f['name'] for f in schema['fields']]
    get('older-river-example', older + '/query', {'f': 'json', 'where': '1=1', 'outFields': '*', 'returnGeometry': 'false', 'resultRecordCount': 1})
    stats = [{'statisticType': s, 'onStatisticField': f, 'outStatisticFieldName': n} for s, f, n in [('count', 'OBJECTID', 'rows'), ('min', 'Date', 'first'), ('max', 'Date', 'last')]]
    summary['older_river_statistics'] = get('older-river-statistics', older + '/query', {'f': 'json', 'where': '1=1', 'outStatistics': json.dumps(stats)}).get('features')
    summary['older_neagh_named_stations'] = get('older-neagh-named-stations', older + '/query', {'f': 'json', 'where': "Location LIKE '%NEAGH%'", 'outFields': 'StationCode,Location,PrimaryBasin', 'returnDistinctValues': 'true', 'returnGeometry': 'false'}).get('features')
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
