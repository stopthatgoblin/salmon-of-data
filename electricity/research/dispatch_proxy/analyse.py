"""Validate a deliberately simple, publication-aware thermal dispatch proxy.

This is a research prototype, not a settlement instruction-profile calculator.
Only the three mapped NI thermal stations are in scope. Wind instructions can
be output limits and must not be treated as measured wind generation.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import csv
import json
import math
import statistics
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
STATIONS = {
    "Ballylumford": ["GU_500283", "GU_500284", "GU_503720", "GU_503730", "GU_503740"],
    "Coolkeeragh": ["GU_500040", "GU_500041"],
    "Kilroot": ["GU_504110", "GU_504120", "GU_500820", "GU_500821", "GU_500824", "GU_500825"],
}
UNITS = {unit for units in STATIONS.values() for unit in units}
START = datetime(2026, 10, 28)
END = datetime(2026, 10, 30)


def dt(text):
    # The selected evaluation dates are after the 25 October clock change.
    # SEMO XML timestamps have no offset; this prototype does not resolve
    # duplicated/ambiguous local timestamps on a clock-change day.
    return datetime.fromisoformat(text)


@dataclass(frozen=True)
class Event:
    unit: str
    effective: datetime
    issued: datetime
    published: datetime
    value: object  # float or None, where None means unknown, never zero.
    code: str
    until: object = None


def load_events(paths=None):
    groups = defaultdict(list)
    reports = []
    delays = []
    for path in sorted(paths if paths is not None else CACHE.glob("PUB_HrlyDispatchInstr_*.xml")):
        root = ET.parse(path).getroot()
        published = dt(root.attrib["PublishTime"])
        issue_hour = datetime.strptime(path.stem.rsplit("_", 1)[1], "%Y%m%d%H%M")
        reports.append({"file": path.name, "issue_hour": issue_hour,
                        "published": published})
        for element in root:
            row = element.attrib
            unit = row.get("ResourceName")
            if unit not in UNITS:
                continue
            effective = dt(row["InstructionTimeStamp"])
            issued = dt(row["InstructionIssueTime"])
            groups[(unit, effective, issued, published)].append(row)
            delays.append((published - issued).total_seconds() / 60)
    events = defaultdict(list)
    for (unit, effective, issued, published), rows in groups.items():
        codes = {row.get("InstructionCode", "") for row in rows}
        numeric = [float(row["DispatchInstruction"]) for row in rows
                   if row.get("InstructionCode") == "MWOF"
                   and row.get("DispatchInstruction") is not None]
        untils = [dt(row["InstructionEndTime"]) for row in rows
                  if row.get("InstructionEndTime")]
        if "TRIP" in codes:
            value = 0.0
        elif numeric:
            # Pair SYNC/DESY with its MWOF where effective and issue times match.
            # A missing numeric field on a status instruction is not 0 MW.
            value = max(numeric)
        elif "DESY" in codes:
            value = 0.0
        else:
            value = None
        events[unit].append(Event(unit, effective, issued, published, value,
                                  "+".join(sorted(codes)), max(untils) if untils else None))
    for unit in events:
        events[unit].sort(key=lambda e: (e.effective, e.issued, e.published))
    return events, reports, delays


def load_meter(paths=None):
    """The guide defines MeteredMW as interval MWh despite the field name.

    Selected rows are half-hour settlement intervals: divide MWh by 0.5 h
    to obtain average MW. Some XML EndTime values use xx:29:59; the nominal
    settlement period remains 30 minutes, rather than 1,799 seconds.
    """
    candidates = {}
    metadata = []
    for path in sorted(paths if paths is not None else CACHE.glob("PUB_DailyMeterDataD1_*.xml")):
        root = ET.parse(path).getroot()
        published = dt(root.attrib["PublishTime"])
        metadata.append({"file": path.name, "date": root.attrib["Date"],
                         "published": published})
        for element in root:
            row = element.attrib
            unit = row.get("ResourceName")
            if unit not in UNITS:
                continue
            start = dt(row["StartTime"])
            # Nominal half-hour duration, explicitly checked rather than inferred
            # from the misleading MeteredMW column name.
            seconds = (dt(row["EndTime"]) - start).total_seconds()
            if seconds not in (1799, 1800):
                raise ValueError("Unexpected settlement interval: " + str(row))
            key = (unit, start)
            if key not in candidates or published > candidates[key][1]:
                candidates[key] = (float(row["MeteredMW"]) / 0.5, published, path.name)
    return candidates, metadata


def seeds_before(meter, at):
    seeds = {}
    for (unit, start), (power, published, filename) in meter.items():
        end = start + timedelta(minutes=30)
        if published > at or end > at:
            continue
        if unit not in seeds or end > seeds[unit]["time"]:
            seeds[unit] = {"time": end, "value": power, "published": published,
                           "file": filename}
    return seeds


def value_at(unit, time, events, seeds, publication_aware=True):
    seed = seeds.get(unit)
    eligible = [event for event in events.get(unit, [])
                if event.effective <= time and event.issued <= time
                and (not publication_aware or event.published <= time)
                and (seed is None or event.effective >= seed["time"])]
    if eligible:
        event = eligible[-1]
        if event.until is not None and time >= event.until:
            return None, "expired"
        return event.value, event.code
    if seed and seed["time"] <= time and seed["published"] <= time:
        return seed["value"], "meter_seed"
    return None, "no_initial_state"


def station_at(station, time, events, seeds, publication_aware=True):
    values = [value_at(unit, time, events, seeds, publication_aware)[0]
              for unit in STATIONS[station]]
    return None if any(value is None for value in values) else sum(values)


def instruction_status(reason):
    if reason == "meter_seed":
        return "initial state from an earlier meter report"
    if "SYNC" in reason:
        return "start-up instructed; target is not confirmation of achieved output"
    if "DESY" in reason or "TRIP" in reason:
        return "shutdown or trip reported"
    if reason == "MWOF":
        return "last published MW target"
    return "output state unavailable"


def mean_available(values):
    return None if any(value is None for value in values) else statistics.mean(values)


def percentile(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, math.ceil(p * len(values)) - 1)] if values else None


def metrics(rows, field):
    pairs = [(row[field], row["actual_mw"]) for row in rows if row[field] is not None]
    errors = [prediction - actual for prediction, actual in pairs]
    absolute = [abs(error) for error in errors]
    active = [abs(prediction - actual) for prediction, actual in pairs if actual >= 10]
    return {
        "periods": len(rows), "available_periods": len(pairs),
        "active_periods_actual_at_least_10mw": len(active),
        "mae_mw": statistics.mean(absolute) if absolute else None,
        "active_mae_mw": statistics.mean(active) if active else None,
        "median_absolute_error_mw": statistics.median(absolute) if absolute else None,
        "p90_absolute_error_mw": percentile(absolute, 0.9),
        "max_absolute_error_mw": max(absolute) if absolute else None,
        "bias_mw": statistics.mean(errors) if errors else None,
        "rmse_mw": math.sqrt(statistics.mean(error ** 2 for error in errors)) if errors else None,
        "fraction_within_25mw": sum(error <= 25 for error in absolute) / len(absolute) if absolute else None,
    }


def validate_causality():
    """A future publication cannot change an estimate for an earlier time."""
    t = datetime(2026, 10, 28, 12)
    seed = {"u": {"time": t - timedelta(days=1), "value": 50,
                  "published": t - timedelta(hours=1)}}
    future = Event("u", t - timedelta(minutes=10), t - timedelta(minutes=12),
                   t + timedelta(minutes=15), 200.0, "MWOF")
    assert value_at("u", t, {"u": [future]}, seed)[0] == 50
    assert value_at("u", t + timedelta(minutes=15), {"u": [future]}, seed)[0] == 200
    sync = Event("u", t, t - timedelta(minutes=10), t - timedelta(minutes=5), None, "SYNC")
    assert value_at("u", t, {"u": [sync]}, seed)[0] is None
    assert value_at("missing", t, {}, {})[0] is None


def main():
    validate_causality()
    events, reports, delays = load_events()
    meter, meter_metadata = load_meter()
    seeds = seeds_before(meter, START)
    if set(seeds) != UNITS:
        raise ValueError("Missing initial states: " + str(UNITS - set(seeds)))
    assert all(seed["published"] <= START for seed in seeds.values())
    rows = []
    seed_usage = Counter()
    start = START
    while start < END:
        times = [start + timedelta(minutes=minute, seconds=30) for minute in range(30)]
        for station, units in STATIONS.items():
            actuals = [meter.get((unit, start)) for unit in units]
            if any(value is None for value in actuals):
                raise ValueError("Missing actuals: " + str((station, start)))
            actual = sum(value[0] for value in actuals)
            live = mean_available([station_at(station, t, events, seeds) for t in times])
            retrospective = mean_available([station_at(station, t, events, seeds, False) for t in times])
            for unit in units:
                seed_usage[unit] += sum(value_at(unit, t, events, seeds)[1] == "meter_seed" for t in times)
            rows.append({"start_utc": start.isoformat() + "Z", "station": station,
                         "actual_mw": actual, "published_target_mw": live,
                         "retrospective_target_mw": retrospective})
        start += timedelta(minutes=30)
    with (ROOT / "validation.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    stats = {}
    for station in STATIONS:
        selected = [row for row in rows if row["station"] == station]
        stats[station] = {"as_available": metrics(selected, "published_target_mw"),
                          "retrospective": metrics(selected, "retrospective_target_mw")}
    total_rows = []
    for time in sorted({row["start_utc"] for row in rows}):
        selected = [row for row in rows if row["start_utc"] == time]
        total_rows.append({field: (None if any(row[field] is None for row in selected)
                                         else sum(row[field] for row in selected))
                           for field in ("actual_mw", "published_target_mw", "retrospective_target_mw")})
    stats["Three-station total"] = {
        "as_available": metrics(total_rows, "published_target_mw"),
        "retrospective": metrics(total_rows, "retrospective_target_mw")}
    now = datetime.utcnow()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    live_seeds = seeds_before(meter, now)
    published_reports = [report for report in reports if report["published"] <= now]
    latest_report = max(published_reports, key=lambda report: report["issue_hour"])
    latest_coverage = latest_report["issue_hour"] + timedelta(hours=1)
    expected = set()
    hour = min(report["issue_hour"] for report in reports)
    while hour <= latest_report["issue_hour"]:
        expected.add(hour)
        hour += timedelta(hours=1)
    missing_windows = sorted(expected - {report["issue_hour"] for report in reports})
    live_units = {}
    for unit in sorted(UNITS):
        value, reason = value_at(unit, now, events, live_seeds)
        live_units[unit] = {"target_proxy_mw": value, "basis": reason,
                            "status": instruction_status(reason)}
    snapshot = {"as_of_utc": now.isoformat() + "Z",
                "data_retrieved_at_utc": manifest["retrieved_at_utc"],
                "last_report_published_utc": latest_report["published"].isoformat() + "Z",
                "issue_windows_complete_through_utc": latest_coverage.isoformat() + "Z",
                "coverage_age_minutes": (now - latest_coverage).total_seconds() / 60,
                "stations": {station: station_at(station, now, events, live_seeds)
                             for station in STATIONS},
                "units": live_units}
    summary = {"evaluation_start_utc": START, "evaluation_end_exclusive_utc": END,
               "method": "Stepwise last published target, actual half-hour seed, no ramp model",
               "meter_units": "SEMO MeteredMW is interval MWh; half-hour values multiplied by 2",
               "stations": STATIONS, "metrics": stats,
               "instruction_publication_lag_minutes": {
                   "min": min(delays), "median": statistics.median(delays), "p90": percentile(delays, .9),
                   "max": max(delays)},
               "initial_states": seeds, "meter_seed_minutes_by_unit": seed_usage,
               "meter_reports": meter_metadata, "snapshot": snapshot,
               "hourly_report_count": len(reports),
               "missing_hourly_windows": missing_windows,
               "thermal_event_count": sum(len(values) for values in events.values()),
               "causality_checks": "passed"}
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({"metrics": stats, "snapshot": snapshot,
                      "instruction_publication_lag_minutes": summary["instruction_publication_lag_minutes"]},
                     indent=2))


if __name__ == "__main__":
    main()
