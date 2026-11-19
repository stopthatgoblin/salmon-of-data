"""Fetch public gas/electricity sources with a reproducible local response cache."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

UTC = timezone.utc
SEMO = 'https://reports.sem-o.com'


class MeterDataPending(ValueError):
    """Required meter readings are unpublished or incomplete."""
    def __init__(self, gas_day, latest_report_date=None, reason=None):
        self.gas_day = gas_day.isoformat()
        self.latest_report_date = latest_report_date
        self.reason = reason
        super().__init__('Waiting for SEMO meter data for ' + self.gas_day + (': ' + reason if reason else ''))


class GasDataPending(ValueError):
    def __init__(self, gas_day, reason=None):
        self.gas_day = gas_day.isoformat()
        self.reason = reason
        super().__init__('Waiting for GNI daily data for ' + self.gas_day + (': ' + reason if reason else ''))


def demand_url(region, first, last):
    # `custom` is rejected. `week` truncates an eight-calendar-day gas window.
    return 'https://www.smartgriddashboard.com/api/chart/?' + urllib.parse.urlencode(dict(
        region=region.upper(), chartType='demand', areas='demandactual', dateRange='day',
        dateFrom=first.strftime('%d-%b-%Y'), dateTo=last.strftime('%d-%b-%Y')))


def stamp(value):
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)


def iso(value):
    return value.astimezone(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


class Sources:
    def __init__(self, cache, offline=False):
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.urls = {}

    def fetch(self, url, *, immutable=False, headers=None):
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / (key + '.gz')
        self.urls[url] = key
        if path.exists() and (self.offline or immutable):
            return gzip.decompress(path.read_bytes())
        if self.offline:
            raise ValueError('Source response is not in the offline cache: ' + url)
        request = urllib.request.Request(url, headers={
            'User-Agent': 'SalmonOfDataGas/1.0', 'Accept-Encoding': 'gzip', **(headers or {}),
        })
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    raw = response.read()
                    if response.headers.get('Content-Encoding') == 'gzip':
                        raw = gzip.decompress(raw)
                if not raw:
                    raise ValueError('Empty source response')
                temporary = path.with_suffix('.tmp')
                temporary.write_bytes(gzip.compress(raw))
                temporary.replace(path)
                (self.cache / (key + '.url')).write_text(url)
                return raw
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)

    def json(self, url, **kwargs):
        return json.loads(self.fetch(url, **kwargs))

    def index(self, name, first):
        if not name.replace('_', '').isalnum():
            raise ValueError('Invalid report catalog name')
        catalog_path = self.cache / ('catalog-' + name + '.json')
        catalog = json.loads(catalog_path.read_text()) if catalog_path.exists() else []
        def retain(items):
            merged = {row['ResourceName']: row for row in catalog + items}
            result = sorted(merged.values(), key=lambda row: (row['Date'], row['PublishTime']), reverse=True)
            temporary = catalog_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(result))
            temporary.replace(catalog_path)
            return result
        items = []
        for page in range(1, 101):
            url = SEMO + '/api/v1/documents/static-reports?' + urllib.parse.urlencode(dict(
                name=name, sort_by='PublishTime', order_by='DESC', page_size=100, page=page))
            try:
                data = self.json(url)
            except (urllib.error.URLError, TimeoutError):
                if catalog:
                    return retain(items)
                raise
            rows = data.get('items')
            if not isinstance(rows, list):
                raise ValueError('Invalid SEMO index: ' + name)
            items.extend(rows)
            # Descending publication order; allow later publications of old data.
            if not rows or page >= data['pagination']['totalPages'] or all(r['Date'] < first.isoformat() for r in rows):
                return retain(items)
        raise ValueError('SEMO index exceeded bounded pagination')

    def report(self, item):
        resource = item['ResourceName']
        if not resource.endswith('.xml') or '/' in resource or '\\' in resource:
            raise ValueError('Invalid SEMO report name')
        url = SEMO + '/documents/' + resource
        root = ET.fromstring(self.fetch(url, immutable=True))
        return root, url

    def gni(self, series, day, frequency='daily'):
        # Daily endpoint date is an upper bound; select the gas-day label later.
        query_day = day + timedelta(days=1) if frequency == 'daily' else day
        url = 'https://www.gasnetworks.ie/api/v1/' + series + '?' + urllib.parse.urlencode(dict(
            date=query_day.isoformat(), frequency=frequency))
        result = self.json(url)
        if not isinstance(result, list) or not result:
            raise ValueError('Missing GNI ' + series)
        return result, url

    def entsog(self, operator, day, **extra):
        query = dict(operatorKey=operator, **{'from': day.isoformat()},
                     to=(day + timedelta(days=1)).isoformat(), periodType='day',
                     indicator='Physical Flow', limit=100, **extra)
        url = 'https://transparency.entsog.eu/api/v1/operationaldatas?' + urllib.parse.urlencode(query)
        data = self.json(url)
        if not isinstance(data.get('operationaldatas'), list) or len(data['operationaldatas']) >= 100:
            raise ValueError('Invalid or truncated ENTSOG response')
        return data['operationaldatas'], url

    def demand(self, region, first, last):
        url = demand_url(region, first, last)
        for attempt in range(3):
            data = self.json(url, headers={'Eirgrid-Content-Request': 'Nextjs'})
            if isinstance(data.get('Rows'), list) and data['Rows']:
                values = {}
                for row in data['Rows']:
                    if row['Region'] != region.upper() or row['FieldName'] != 'SYSTEM_DEMAND':
                        continue
                    at = datetime.strptime(row['EffectiveTime'], '%d-%b-%Y %H:%M:%S').replace(tzinfo=UTC)
                    value = row['Value']
                    if at in values and values[at] != value:
                        raise ValueError('Conflicting regional demand readings')
                    values[at] = value
                if values:
                    return values, url
            if self.offline or attempt == 2:
                raise ValueError('Empty regional demand response: ' + region)
            time.sleep(2 ** attempt)


def newest(items, day):
    selected = [i for i in items if i['Date'] == day.isoformat()]
    return max(selected, key=lambda i: i['PublishTime']) if selected else None


def parallel(jobs):
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda job: job(), jobs))
