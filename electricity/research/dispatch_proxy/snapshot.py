"""Fetch a timestamped grid snapshot and last-published thermal-unit targets."""

from concurrent.futures import ThreadPoolExecutor
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import json
import urllib.parse
import urllib.request

import analyse
import collect

ROOT = Path(__file__).resolve().parent
LABELS = {
    "GU_500283": "BGT1", "GU_500284": "BGT2", "GU_503720": "B31",
    "GU_503730": "B32", "GU_503740": "B10", "GU_500040": "C30",
    "GU_500041": "CGT8", "GU_504110": "NIGT6", "GU_504120": "NIGT7",
    "GU_500824": "KGT1", "GU_500825": "KGT2", "GU_500820": "KGT3",
    "GU_500821": "KGT4",
}


def fetch_grid(chart, areas, day):
    target = datetime.strptime(day, '%d-%b-%Y')
    field = {'demand':'SYSTEM_DEMAND', 'generation':'GEN_EXP', 'wind':'WIND_ACTUAL',
             'solar':'SOLAR_ACTUAL', 'interconnection':'INTER_MOYLE'}[chart]
    best, best_time, attempted = None, datetime.min, []
    # The website can return empty or stale data for an otherwise valid range.
    # Try bounded alternatives, validating the actual field rather than row count.
    for lookback in ([1, 7, 27] if chart == 'interconnection' else [0, 1, 7]):
        query = urllib.parse.urlencode({"region":"NI", "chartType":chart, "dateRange":"custom",
                                       "dateFrom":(target - timedelta(days=lookback)).strftime('%d-%b-%Y'),
                                       "dateTo":day, "areas":areas})
        url = "https://www.smartgriddashboard.com/api/chart/?" + query
        attempted.append(url)
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={"Eirgrid-Content-Request":"Nextjs"})
                with urllib.request.urlopen(request, timeout=25) as response:
                    data = json.load(response)
                if not isinstance(data.get('Rows'), list):
                    raise ValueError('Unexpected grid response: ' + url)
                break
            except Exception:
                if attempt == 2:
                    raise
        actual = [datetime.strptime(row['EffectiveTime'], '%d-%b-%Y %H:%M:%S')
                  for row in data['Rows'] if row.get('FieldName') == field and row.get('Value') is not None]
        latest = max(actual, default=datetime.min)
        if best is None or latest > best_time:
            best_time = latest
            best = dict(url=url, retrieved_at_utc=datetime.utcnow().isoformat() + 'Z', data=data)
        if latest >= min(datetime.utcnow() - timedelta(minutes=60), target + timedelta(hours=23)):
            break
    best['attempted_urls'] = attempted
    return best


def main(output_dir=None):
    now = datetime.utcnow()
    date = now.strftime("%Y-%m-%d")
    day = now.strftime("%d-%b-%Y")
    # Reconstruct from recent published meter seeds and every subsequent command.
    # Keep requests bounded as the service runs beyond the original pilot dates.
    start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    specs = [("PUB_HrlyDispatchInstr", start, date),
             ("PUB_DailyMeterDataD1", start, date)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        indexes = list(pool.map(lambda args: collect.index(*args), specs))
    manifest = [item for items in indexes for item in items]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(collect.download, manifest))
    charts = [("demand", "demandactual"),
              ("generation", "generationactual"),
              ("wind", "windactual"), ("solar", "solaractual"),
              ("interconnection", "interconnection")]
    with ThreadPoolExecutor(max_workers=3) as pool:
        grid_payloads = list(pool.map(lambda args: fetch_grid(*args, day), charts))
    observed = {}
    def ingest(payloads):
        for payload in payloads:
            for row in payload["data"]["Rows"]:
                if row.get("Value") is None:
                    continue
                field = row["FieldName"]
                time = datetime.strptime(row["EffectiveTime"], "%d-%b-%Y %H:%M:%S")
                observed.setdefault(field, {})[time] = row["Value"]
    ingest(grid_payloads)
    required = ["SYSTEM_DEMAND", "GEN_EXP", "WIND_ACTUAL", "SOLAR_ACTUAL", "INTER_MOYLE"]
    common = set.intersection(*(set(observed.get(field, {})) for field in required))
    if not common:
        # Around midnight the new source date may not yet have a complete reading.
        previous_day = (now - timedelta(days=1)).strftime("%d-%b-%Y")
        with ThreadPoolExecutor(max_workers=3) as pool:
            previous = list(pool.map(lambda args: fetch_grid(*args, previous_day), charts))
        grid_payloads.extend(previous)
        ingest(previous)
    missing = [field for field in required if not observed.get(field)]
    if missing:
        raise ValueError("Missing grid series: " + str(missing))
    common = set.intersection(*(set(observed[field]) for field in required))
    if not common:
        raise ValueError("No common observation time; refusing to combine unmatched readings")
    matched_time = max(time for time in common if time <= datetime.utcnow())
    grid = {field: observed[field][matched_time] for field in required}
    grid["NI_OTHER_GENERATION"] = grid["GEN_EXP"] - grid["WIND_ACTUAL"] - grid["SOLAR_ACTUAL"]
    grid["ROI_NET_IMPORT_ESTIMATE"] = grid["SYSTEM_DEMAND"] - grid["GEN_EXP"] - grid["INTER_MOYLE"]
    assert grid["GEN_EXP"] + grid["INTER_MOYLE"] + grid["ROI_NET_IMPORT_ESTIMATE"] == grid["SYSTEM_DEMAND"]
    events, reports, delays = analyse.load_events([collect.CACHE / item["ResourceName"] for item in indexes[0]])
    meter, meter_metadata = analyse.load_meter([collect.CACHE / item["ResourceName"] for item in indexes[1]])
    as_of = datetime.utcnow()
    seeds = analyse.seeds_before(meter, as_of)
    if set(seeds) != analyse.UNITS:
        raise ValueError("Incomplete thermal-unit initial state")
    station_rows = []
    for station, units in analyse.STATIONS.items():
        for unit in units:
            value, basis = analyse.value_at(unit, as_of, events, seeds)
            eligible = [event for event in events.get(unit, [])
                        if event.effective <= as_of and event.issued <= as_of
                        and event.published <= as_of
                        and event.effective >= seeds[unit]["time"]]
            last = eligible[-1] if eligible else None
            station_rows.append({"station": station, "unit": LABELS[unit],
                                 "resource_id": unit, "target_proxy_mw": value,
                                 "basis": basis, "status": analyse.instruction_status(basis),
                                 "instruction_effective_utc": last.effective.isoformat() + "Z" if last else None,
                                 "instruction_published_utc": last.published.isoformat() + "Z" if last else None,
                                 "meter_seed": seeds[unit]})
    latest = max((report for report in reports if report["published"] <= as_of),
                 key=lambda report: report["issue_hour"])
    coverage = latest["issue_hour"] + timedelta(hours=1)
    expected = set()
    hour = min(report["issue_hour"] for report in reports)
    while hour <= latest["issue_hour"]:
        expected.add(hour)
        hour += timedelta(hours=1)
    gaps = sorted(expected - {report["issue_hour"] for report in reports})
    result = {
        "retrieved_at_utc": as_of.isoformat() + "Z",
        "grid_time_utc": matched_time.isoformat() + "Z", "grid_mw": grid,
        "latest_observation_time_by_series": {field: max(values).isoformat() + "Z"
                                               for field, values in observed.items()},
        "station_proxy_time_utc": as_of.isoformat() + "Z",
        "latest_dispatch_publication_utc": latest["published"].isoformat() + "Z",
        "instruction_issue_coverage_through_utc": coverage.isoformat() + "Z",
        "dispatch_coverage_age_minutes": (as_of - coverage).total_seconds() / 60,
        "missing_hourly_windows": gaps, "units": station_rows,
        "station_totals_mw": {station: analyse.station_at(station, as_of, events, seeds)
                              for station in analyse.STATIONS},
        "latest_meter_reports": meter_metadata,
        "source_grid_payloads": grid_payloads,
        "source_report_manifest": manifest,
    }
    stamp = as_of.strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(output_dir) if output_dir else ROOT
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ("snapshot_" + stamp + ".json")
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2, default=str))
    temporary.replace(path)
    small = {key: value for key, value in result.items()
             if key not in {"source_grid_payloads", "source_report_manifest", "latest_meter_reports"}}
    print(json.dumps(small, indent=2, default=str))
    print("Saved", path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path)
    main(parser.parse_args().output_dir)
