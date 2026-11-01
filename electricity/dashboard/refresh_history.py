"""Build a browser-local history fixture from public EirGrid/SONI and SEMO data.

No credentials, server at page-view time, or third-party data service is needed.
Grid requests are calendar-month chunks: longer requests can silently return no
rows. Only complete source-labelled calendar days become plotted averages.
"""

import argparse
import calendar
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
import gzip
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "history-cache"
sys.path.insert(0, str(ROOT.parent / "research" / "dispatch_proxy"))
from analyse import STATIONS

GRID = {
    "demand": ("demand", "demandactual", "SYSTEM_DEMAND"),
    "generation": ("generation", "generationactual", "GEN_EXP"),
    "wind": ("wind", "windactual", "WIND_ACTUAL"),
    "solar": ("solar", "solaractual", "SOLAR_ACTUAL"),
    "moyle": ("interconnection", "interconnection", "INTER_MOYLE"),
}
SERIES = [
    dict(key="wind", label="Wind generation", colour="#136b72", method="reported", expected=96),
    dict(key="solar", label="Solar generation", colour="#b78a3b", method="reported", expected=96),
    dict(key="otherNI", label="Other NI generation", colour="#738577", method="derived", expected=96),
    dict(key="moyle", label="Moyle Interconnector", colour="#527d8b", method="reported", expected=96),
    dict(key="northSouth", label="North-South Interconnector", colour="#708b91", method="estimated", expected=96),
    dict(key="demand", label="Electricity demand", colour="#182e32", method="reported", expected=96),
    dict(key="generation", label="Total NI generation", colour="#ad3930", method="reported", expected=96),
    dict(key="ballylumford", label="Ballylumford", colour="#ad3930", method="metered", expected=48),
    dict(key="coolkeeragh", label="Coolkeeragh", colour="#85705c", method="metered", expected=48),
    dict(key="kilroot", label="Kilroot", colour="#9d5d50", method="metered", expected=48),
]


def fetch(url, headers=None):
    request = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", **(headers or {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                raw = response.read()
                return gzip.decompress(raw) if response.headers.get("Content-Encoding") == "gzip" else raw
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def grid_month(job):
    key, year, month, refresh = job
    start = date(year, month, 1)
    end = min(date(year, month, calendar.monthrange(year, month)[1]), datetime.now(ZoneInfo('Europe/London')).date())
    cache = CACHE / f"{key}-{year}-{month:02}.json.gz"
    if cache.exists() and not refresh:
        cached = json.loads(gzip.decompress(cache.read_bytes()))
        if cached.get("rows") or cached.get("emptyRangeChecked"):
            return cached
    chart, areas, field = GRID[key]
    urls = []
    def request_window(first, last):
        query = urllib.parse.urlencode(dict(region="NI", chartType=chart, areas=areas, dateRange="custom",
                                           dateFrom=first.strftime("%d-%b-%Y"), dateTo=last.strftime("%d-%b-%Y")))
        url = "https://www.smartgriddashboard.com/api/chart/?" + query
        urls.append(url)
        payload = json.loads(fetch(url, {"Eirgrid-Content-Request": "Nextjs"}))
        if "Rows" not in payload:
            raise ValueError("Unexpected source response: " + url)
        return payload["Rows"]
    rows = request_window(start, end)
    empty_checked = False
    if not rows:
        # The upstream silently returns [] for some long windows, especially
        # 31-day wind/solar requests. Check smaller windows before calling it a gap.
        rows = []
        cursor = start
        while cursor <= end:
            last = min(end, cursor + timedelta(days=27))
            rows.extend(request_window(cursor, last))
            cursor = last + timedelta(days=1)
        empty_checked = True
    observations = []
    for row in rows:
        if row.get("FieldName") != field or row.get("Region") != "NI":
            continue
        stamp = datetime.strptime(row["EffectiveTime"], "%d-%b-%Y %H:%M:%S")
        if not start <= stamp.date() <= end:
            continue
        value = row.get("Value")
        if value is not None:
            value = float(value)
            if not math.isfinite(value):
                raise ValueError("Non-finite observation: " + url)
        observations.append([stamp.isoformat(), value])
    result = dict(key=key, year=year, month=month, urls=urls, emptyRangeChecked=empty_checked,
                  retrieved=datetime.utcnow().isoformat(timespec="seconds") + "Z", rows=observations)
    temporary = cache.with_suffix(".tmp")
    temporary.write_bytes(gzip.compress(json.dumps(result, separators=(",", ":")).encode()))
    temporary.replace(cache)
    return result


def meter_index():
    items, page = [], 1
    while True:
        query = urllib.parse.urlencode(dict(name="PUB_DailyMeterDataD1", sort_by="PublishTime",
                                           order_by="ASC", page_size=300, page=page))
        result = json.loads(fetch("https://reports.sem-o.com/api/v1/documents/static-reports?" + query))
        items.extend(result["items"])
        if page >= result["pagination"]["totalPages"]:
            break
        page += 1
    # Keep the latest currently published D+1 revision for each settlement date.
    latest = {}
    for item in items:
        if item["Date"] not in latest or item["PublishTime"] > latest[item["Date"]]["PublishTime"]:
            latest[item["Date"]] = item
    return list(latest.values()), items


def meter_report(item):
    resource = item["ResourceName"]
    cache = CACHE / (resource + ".json.gz")
    if cache.exists():
        return json.loads(gzip.decompress(cache.read_bytes()))
    existing = ROOT.parent / "research" / "dispatch_proxy" / "cache" / resource
    raw = existing.read_bytes() if existing.exists() else fetch("https://reports.sem-o.com/documents/" + resource)
    root = ET.fromstring(raw)
    units = {unit for members in STATIONS.values() for unit in members}
    rows = []
    for element in root:
        row = element.attrib
        if row.get("ResourceName") not in units:
            continue
        start = datetime.fromisoformat(row["StartTime"])
        duration = (datetime.fromisoformat(row["EndTime"]) - start).total_seconds()
        if duration not in (1799, 1800):
            raise ValueError("Unexpected meter interval in " + resource)
        value = float(row["MeteredMW"]) * 2  # Field is interval MWh, per BM-086 guide.
        if not math.isfinite(value):
            raise ValueError("Non-finite metered value in " + resource)
        rows.append([row["ResourceName"], start.isoformat(), value])
    result = dict(resource=resource, published=root.attrib["PublishTime"], date=root.attrib["Date"], rows=rows)
    temporary = cache.with_suffix('.tmp')
    temporary.write_bytes(gzip.compress(json.dumps(result, separators=(",", ":")).encode()))
    temporary.replace(cache)
    return result


def daily_average(observations, expected):
    """Reject missing/duplicate/conflicting intervals; an actual zero is valid."""
    values, conflicts = {}, set()
    for stamp, value in observations:
        if value is None:
            continue
        if stamp in values and values[stamp] != value:
            conflicts.add(stamp)
        values[stamp] = value
    step = 1440 // expected
    required = {f"{minute // 60:02}:{minute % 60:02}:00" for minute in range(0, 1440, step)}
    if conflicts or set(values) != required:
        return None, len(values)
    return sum(values.values()) / expected, expected


def build(start_year, refresh_years):
    CACHE.mkdir(exist_ok=True)
    today = datetime.now(ZoneInfo('Europe/London')).date()
    yesterday = today - timedelta(days=1)
    grid = {key: defaultdict(list) for key in GRID}
    provenance, errors = [], []
    jobs = [(key, year, month, year in refresh_years or
             (today.year * 12 + today.month) - (year * 12 + month) <= 1)
            for year in range(start_year, today.year + 1)
            for month in range(1, 13)
            if date(year, month, 1) <= yesterday for key in GRID]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(grid_month, job): job for job in jobs}
        for number, future in enumerate(as_completed(futures), 1):
            job = futures[future]
            try:
                result = future.result()
                provenance.append({key: value for key, value in result.items() if key != "rows"})
                for stamp, value in result["rows"]:
                    day, clock = stamp.split("T")
                    if day <= yesterday.isoformat():
                        grid[result["key"]][day].append((clock, value))
            except Exception as exc:
                errors.append(dict(job=job[:3], error=str(exc)))
            if number % 30 == 0 or number == len(jobs):
                print(f"Grid months: {number}/{len(jobs)}; request failures: {len(errors)}", flush=True)

    station_periods = {name.lower(): defaultdict(list) for name in STATIONS}
    try:
        reports, original_index = meter_index()
    except Exception as exc:
        reports, original_index = [], []
        errors.append(dict(source="SEMO meter index", error=str(exc)))
    meter = {}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(meter_report, item): item for item in reports}
        for number, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()
                for unit, stamp, value in result["rows"]:
                    key = (unit, stamp)
                    if key not in meter or result["published"] > meter[key][1]:
                        meter[key] = (value, result["published"])
            except Exception as exc:
                errors.append(dict(resource=futures[future]["ResourceName"], error=str(exc)))
            if number % 15 == 0 or number == len(reports):
                print(f"Meter reports: {number}/{len(reports)}", flush=True)
    # Retain already collected station history when files leave the rolling index.
    for cached in sorted(CACHE.glob("PUB_DailyMeterDataD1_*.xml.json.gz")):
        try:
            result = json.loads(gzip.decompress(cached.read_bytes()))
            for unit, stamp, value in result["rows"]:
                key = (unit, stamp)
                if key not in meter or result["published"] > meter[key][1]:
                    meter[key] = (value, result["published"])
        except Exception as exc:
            errors.append(dict(resource=cached.name, error=str(exc)))
    stamps = sorted({stamp for _, stamp in meter})
    for name, units in STATIONS.items():
        for stamp in stamps:
            day, clock = stamp.split("T")
            if day > yesterday.isoformat():
                continue
            if all((unit, stamp) in meter for unit in units):
                station_periods[name.lower()][day].append((clock, sum(meter[(unit, stamp)][0] for unit in units)))

    output = []
    cursor = date(start_year, 1, 1)
    while cursor <= yesterday:
        day = cursor.isoformat()
        daily = {key: daily_average(values.get(day, []), 96) for key, values in grid.items()}
        # Derive only from complete, identically timed grid days; never assume missing solar is zero.
        for key, dependencies, fn in [
            ("otherNI", ("generation", "wind", "solar"), lambda g, w, s: g - w - s),
            ("northSouth", ("demand", "generation", "moyle"), lambda d, g, m: d - g - m),
        ]:
            valid = all(daily[k][0] is not None for k in dependencies)
            daily[key] = (fn(*(daily[k][0] for k in dependencies)) if valid else None,
                          min(daily[k][1] for k in dependencies))
        for key, values in station_periods.items():
            daily[key] = daily_average(values.get(day, []), 48)
        output.append(dict(date=day, v=[round(daily[s["key"]][0], 4) if daily[s["key"]][0] is not None else None for s in SERIES],
                           n=[daily[s["key"]][1] for s in SERIES]))
        cursor += timedelta(days=1)
    # Trim years with no accepted readings; keep internal gaps explicit.
    valid = [i for i, row in enumerate(output) if any(value is not None for value in row["v"])]
    if not valid:
        raise ValueError("No complete historical days. Previous fixture preserved.")
    output = output[valid[0]:]
    for i, series in enumerate(SERIES):
        dates = [row["date"] for row in output if row["v"][i] is not None]
        series.update(first=dates[0] if dates else None, last=dates[-1] if dates else None, days=len(dates))
    if errors:
        (ROOT / "history-failed-audit.json").write_text(json.dumps(dict(errors=errors), indent=2))
        raise RuntimeError(f"{len(errors)} history requests or cached reports failed; previous fixture preserved. See history-failed-audit.json.")
    result = dict(schema=1, generatedAt=datetime.utcnow().isoformat(timespec="seconds") + "Z",
                  first=output[0]["date"], last=yesterday.isoformat(), series=SERIES, days=output,
                  requestFailures=len(errors), gridDayBasis="source-labelled calendar dates; 96 quarter-hour observations",
                  stationDayBasis="calendar dates of SEMO StartTime; 48 half-hour settlement intervals",
                  meterIndexFirst=min((item["Date"] for item in original_index), default=None),
                  meterIndexLast=max((item["Date"] for item in original_index), default=None))
    target = ROOT / "dist" / "assets" / "history.js"
    temporary = target.with_suffix(".tmp")
    temporary.write_text("window.ELECTRICITY_HISTORY = " + json.dumps(result, separators=(",", ":")) + ";\n")
    temporary.replace(target)
    target = target.with_suffix('.json')
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, separators=(",", ":")))
    temporary.replace(target)
    audit = dict(generatedAt=result["generatedAt"], series=SERIES, gridRequests=provenance,
                 meterReports=reports, errors=errors, rules=dict(gridSamples=96, meterSamples=48, incompleteDays="null", currentDay="excluded"))
    (ROOT / "history-audit.json").write_text(json.dumps(audit, indent=2))
    print(json.dumps({key: result[key] for key in ("generatedAt", "first", "last", "series", "requestFailures")}, indent=2), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-year", type=int, default=2010)
    parser.add_argument("--refresh-year", type=int, action="append", default=[])
    args = parser.parse_args()
    build(args.start_year, set(args.refresh_year))
