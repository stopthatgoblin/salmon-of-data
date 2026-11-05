"""Today's peak estimates from the official NI demand, wind and solar feeds.

This optional enrichment never changes the original actuals or dispatch math.
Demand combines observations so far with the remaining half-hourly forecast.
Wind and solar must have a complete, matching quarter-hourly forecast day.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

FEEDS = {
    'demand': ('demand', 'demandforecast', 'DEMAND_FORECAST_VALUE'),
    'wind': ('wind', 'windforecast', 'WIND_FCAST'),
    'solar': ('solar', 'solarforecast', 'SOLAR_FCAST'),
}


def readings(payload, field, day):
    if not isinstance(payload.get('Rows'), list):
        raise ValueError('Unexpected forecast response')
    result = {}
    for row in payload['Rows']:
        if row.get('Region') != 'NI' or row.get('FieldName') != field or row.get('Value') is None:
            continue
        stamp = datetime.strptime(row['EffectiveTime'], '%d-%b-%Y %H:%M:%S')
        if stamp.date().isoformat() != day:
            continue
        value = row['Value']
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid peak input')
        clock = stamp.strftime('%H:%M:%S')
        if clock in result and result[clock] != value:
            raise ValueError('Conflicting peak input')
        result[clock] = value
    return result


def demand_peak(actual, forecast):
    required = {f'{minute // 60:02}:{minute % 60:02}:00' for minute in range(0, 1440, 30)}
    missing = required - (actual.keys() | forecast.keys())
    if missing:
        # The rolling forecast can start just after the newest actual reading.
        # Allow only that short publication boundary, never holes elsewhere in
        # the day. No value is inferred or inserted for the missing interval.
        if not actual or not forecast:
            return None
        boundary = {clock for clock in required if max(actual) < clock < min(forecast)}
        if not missing <= boundary or len(boundary) > 2:
            return None
    # Actual observations replace forecasts for periods already reported.
    values = {**forecast, **actual}
    return max(values.values())


def wind_solar_peak(wind, solar):
    required = {f'{minute // 60:02}:{minute % 60:02}:00' for minute in range(0, 1440, 15)}
    if not required <= wind.keys() & solar.keys():
        return None
    peak = max(wind[clock] + solar[clock] for clock in required)
    return peak if math.isfinite(peak) else None


def fetch_forecast(name, day):
    chart, area, _ = FEEDS[name]
    source_day = datetime.fromisoformat(day).strftime('%d-%b-%Y')
    query = urllib.parse.urlencode(dict(region='NI', chartType=chart, areas=area,
        dateRange='custom', dateFrom=source_day, dateTo=source_day))
    url = 'https://www.smartgriddashboard.com/api/chart/?' + query
    request = urllib.request.Request(url, headers={'Eirgrid-Content-Request': 'Nextjs', 'User-Agent': 'SalmonOfDataElectricity/1'})
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response), url


def collect(source_snapshot, previous=None, now=None):
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(ZoneInfo('Europe/London')).date().isoformat()
    previous = previous if previous and previous.get('date') == day else {}
    result = {'date': day, 'demand': previous.get('demand'), 'windSolar': previous.get('windSolar')}
    feeds, urls = {}, {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {name: pool.submit(fetch_forecast, name, day) for name in FEEDS}
        for name, job in jobs.items():
            try:
                payload, url = job.result()
                feeds[name] = readings(payload, FEEDS[name][2], day)
                urls[name] = url
            except Exception as error:
                # Forecast availability must not prevent publication of valid actuals.
                print(f'Optional {name} forecast unavailable ({type(error).__name__}); retaining same-day accepted peak if available.')
    collected = now.isoformat(timespec='seconds').replace('+00:00', 'Z')
    if 'demand' in feeds:
        try:
            actual, actual_urls = {}, []
            for payload in source_snapshot.get('source_grid_payloads', []):
                values = readings(payload['data'], 'SYSTEM_DEMAND', day)
                if values:
                    actual.update(values)
                    actual_urls.append(payload['url'])
            peak = demand_peak(actual, feeds['demand'])
            if peak is not None:
                values = {**feeds['demand'], **actual}
                # Keep the source's 24-hour clock, choosing the first tied peak.
                peak_time = min(clock for clock, value in values.items() if value == peak)[:5]
                result['demand'] = {'value': peak, 'time': peak_time, 'retrievedAt': collected,
                    'basis': 'Highest available reported demand or remaining published forecast today; a short publication gap can exist between the two feeds.',
                    'observations': len(actual), 'forecastReadings': len(feeds['demand']),
                    'sources': [urls['demand'], *dict.fromkeys(actual_urls)]}
            else:
                required = {f'{minute // 60:02}:{minute % 60:02}:00' for minute in range(0, 1440, 30)}
                print('Optional demand peak coverage:', json.dumps({'actualCount': len(actual),
                    'actualFirst': min(actual, default=None), 'actualLast': max(actual, default=None),
                    'forecastCount': len(feeds['demand']), 'forecastFirst': min(feeds['demand'], default=None),
                    'forecastLast': max(feeds['demand'], default=None),
                    'missingHalfHours': sorted(required - (actual.keys() | feeds['demand'].keys()))}))
        except (ValueError, KeyError, TypeError) as error:
            print(f'Optional demand peak unavailable: {type(error).__name__}: {error}')
    if 'wind' in feeds and 'solar' in feeds:
        peak = wind_solar_peak(feeds['wind'], feeds['solar'])
        if peak is not None:
            result['windSolar'] = {'value': peak, 'retrievedAt': collected,
                'basis': 'Highest combined NI wind and solar forecast at matching quarter-hours today.',
                'forecastReadings': 96, 'sources': [urls['wind'], urls['solar']]}
    return result
