"""Refresh the prototype fixture from public, timestamped grid and SEMO reports."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import math
from pathlib import Path
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
RESEARCH = ROOT.parent / "research" / "dispatch_proxy"
sys.path.insert(0, str(RESEARCH))
import analyse
import collect


def latest(name):
    query = urllib.parse.urlencode(dict(name=name, sort_by="PublishTime", order_by="DESC", page_size=1, page=1))
    result = json.loads(collect.fetch(collect.BASE + "/api/v1/documents/static-reports?" + query))
    item = result["items"][0]
    collect.download(item)
    return item, ET.parse(collect.CACHE / item["ResourceName"]).getroot()


def build(snapshot_path):
    snapshot = json.loads(snapshot_path.read_text())
    at = datetime.fromisoformat(snapshot["grid_time_utc"].removesuffix("Z"))
    retrieved = datetime.utcnow()
    keys = ["PUB_DlyGenUnitTechCharDataTrans", "PUB_DailyTechnicalOfferData"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        (baseline_meta, baseline), (technical_meta, technical) = list(pool.map(latest, keys))
    availability = {}
    for row in baseline:
        unit = row.get("ResourceName")
        if unit not in analyse.UNITS or row.get("OutturnAvailability") is None:
            continue
        effective = datetime.fromisoformat(row.get("EffectiveTime"))
        if effective > at:
            continue
        key = (effective.isoformat(), row.get("IssueTime", ""))
        if unit not in availability or key > availability[unit]["key"]:
            availability[unit] = dict(key=key, value=float(row.get("OutturnAvailability")),
                                      issued=row.get("IssueTime"), source=baseline_meta["ResourceName"])
    reports = collect.index("PUB_HrlyOutturnAvailability", baseline_meta["Date"], at.strftime("%Y-%m-%d"))
    reports = [r for r in reports if datetime.fromisoformat(r["PublishTime"]) <= retrieved]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(collect.download, reports))
    for report in sorted(reports, key=lambda r: r["PublishTime"]):
        for row in ET.parse(collect.CACHE / report["ResourceName"]).getroot():
            unit = row.get("ResourceName")
            if unit not in analyse.UNITS or row.get("OutturnAvailability") is None:
                continue  # A missing field in a change row is not zero.
            issued = row.get("IssueTime")
            if datetime.fromisoformat(issued) > at:
                continue
            if unit not in availability or issued > availability[unit]["issued"]:
                availability[unit] = dict(key=(issued, issued), value=float(row.get("OutturnAvailability")),
                                          issued=issued, source=report["ResourceName"])
    parameters = {}
    for row in technical:
        unit = row.get("ResourceName")
        if unit in analyse.UNITS and row.get("MaximumGeneration") is not None:
            parameters[unit] = row.attrib
    if set(availability) != analyse.UNITS or set(parameters) != analyse.UNITS:
        raise ValueError("Missing unit availability or technical data; preserve the previous fixture")

    manifest = snapshot["source_report_manifest"]
    events, _, _ = analyse.load_events([collect.CACHE / row["ResourceName"] for row in manifest if row["ResourceName"].startswith("PUB_HrlyDispatchInstr_")])
    # Estimate the grid timestamp using all instructions published by collection.
    events = {u: [e for e in es if e.published <= retrieved] for u, es in events.items()}
    meter, _ = analyse.load_meter([collect.CACHE / row["ResourceName"] for row in manifest if row["ResourceName"].startswith("PUB_DailyMeterDataD1_")])
    seeds = analyse.seeds_before(meter, at)
    names = {row["resource_id"]: row["unit"] for row in snapshot["units"]}
    order = {name: i for i, name in enumerate(["B31", "B32", "B10", "BGT1", "BGT2", "C30", "CGT8", "NIGT6", "NIGT7", "KGT1", "KGT2", "KGT3", "KGT4"])}
    stations = []
    for station in ["Coolkeeragh", "Ballylumford", "Kilroot"]:
        units = []
        for unit in sorted(analyse.STATIONS[station], key=lambda u: order[names[u]]):
            output, basis = analyse.value_at(unit, at, events, seeds, publication_aware=False)
            if output is None:
                raise ValueError("Unknown output for " + unit)
            p = parameters[unit]
            a = availability[unit]
            status = "Unavailable" if not a["value"] else "Start instructed" if "SYNC" in basis else "Generation indicated" if output else "No generation indicated"
            units.append(dict(id=unit, name=names[unit], output=output, available=a["value"],
                              maximum=float(p["MaximumGeneration"]),
                              fuel="Distillate oil" if p["FuelType"] == "DISTILLATE" else "Natural gas" + (" · multi-fuel" if p["FuelType"] == "MULTI_FUEL" else ""),
                              status=status, basis=basis, availabilityIssued=a["issued"], availabilitySource=a["source"],
                              coldStartHours=float(p["SynchronousStartUpTimeCold"]), hotStartHours=float(p["SynchronousStartUpTimeHot"])))
        stations.append(dict(id=station.lower(), name=station, units=units,
                             output=sum(u["output"] for u in units), available=sum(u["available"] for u in units),
                             maximum=round(sum(u["maximum"] for u in units), 2)))
    grid = snapshot["grid_mw"]
    data = dict(time=snapshot["grid_time_utc"], label=at.strftime("%d %B %Y · %H:%M UTC"), mode="scheduled",
                demand=grid["SYSTEM_DEMAND"], generation=grid["GEN_EXP"], wind=grid["WIND_ACTUAL"], solar=grid["SOLAR_ACTUAL"],
                other=grid["NI_OTHER_GENERATION"] - sum(s["output"] for s in stations), moyle=grid["INTER_MOYLE"],
                northSouth=grid["ROI_NET_IMPORT_ESTIMATE"], moyleAvailable=250, moyleRated=500,
                northSouthReferenceCapacity=300,
                northSouthCapacityBasis="EirGrid/SONI AIRAA 2026–2035: published NTC reference; not a live operating limit",
                availabilityPublished=max([baseline_meta["PublishTime"]] + [r["PublishTime"] for r in reports]) + "Z",
                availabilityLatestSource=max(reports, key=lambda r: r["PublishTime"])["ResourceName"] if reports else baseline_meta["ResourceName"],
                availabilityBaseline=baseline_meta["ResourceName"], technicalSource=technical_meta["ResourceName"],
                dispatchPublished=snapshot["latest_dispatch_publication_utc"],
                dispatchCoverageThrough=snapshot["instruction_issue_coverage_through_utc"],
                retrievedAt=retrieved.isoformat() + "Z", stations=stations, sourceSnapshot=snapshot_path.name)
    if not all(math.isfinite(data[key]) for key in ("demand", "generation", "wind", "solar", "other", "moyle", "northSouth")):
        raise ValueError("Non-finite grid data; previous fixture preserved")
    if abs(data["generation"] + data["moyle"] + data["northSouth"] - data["demand"]) >= .001 or abs(sum(s["output"] for s in stations) + data["wind"] + data["solar"] + data["other"] - data["generation"]) >= .001:
        raise ValueError("Electricity balance failed; previous fixture preserved")
    destination = ROOT / "dist" / "assets" / "snapshot.js"
    if destination.exists():
        old = json.loads(destination.read_text().split("=", 1)[1].strip().removesuffix(";"))
        if old["time"] > data["time"]:
            raise ValueError("Source moved backwards; previous fixture preserved")
    temporary = destination.with_suffix(".tmp")
    temporary.write_text("window.ELECTRICITY = " + json.dumps(data, indent=2, ensure_ascii=False) + ";\n")
    temporary.replace(destination)
    destination = destination.with_suffix('.json')
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False))
    temporary.replace(destination)
    print(json.dumps({k: data[k] for k in ["time", "demand", "generation", "wind", "solar", "other", "moyle", "northSouth", "dispatchPublished", "availabilityPublished"]}, indent=2))
    print("Stations:", ", ".join(f'{s["name"]} {s["output"]:g}/{s["available"]:g} MW' for s in stations))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-snapshot", type=Path)
    args = parser.parse_args()
    if args.from_snapshot is None:
        source_dir = ROOT / 'runtime' / 'source-snapshots'
        subprocess.run([sys.executable, str(RESEARCH / "snapshot.py"), '--output-dir', str(source_dir)], check=True, stdout=subprocess.DEVNULL)
        args.from_snapshot = max(source_dir.glob("snapshot_*.json"), key=lambda p: p.name)
    build(args.from_snapshot.resolve())
