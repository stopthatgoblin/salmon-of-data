"""Import NOAA RONI and World Bank commodity updates checked on 5 October 2026."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-10-05"
RAW = ROOT / "data/raw" / DAY
PUBLIC = ROOT / "public/data"
REPORT_PATH = PUBLIC / f"refresh-{DAY}.json"
CALENDAR_PATH = ROOT / "data/release-calendar.json"
CALENDAR_PUBLIC = PUBLIC / "release-calendar.json"
WORLD_BANK_URL = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
WORLD_BANK_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
NOAA_URL = "https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def capture(path: Path, name: str, page: str, download: str, note: str):
    return {
        "file": path.relative_to(ROOT / "data/raw").as_posix(),
        "name": name,
        "url": page,
        "downloadUrl": download,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "retrievedOn": DAY,
        "note": note,
    }


def parse_roni(path: Path):
    values = {}
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", path.read_text(encoding="utf-8"), re.S):
        cells = re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row, re.S)
        texts = [re.sub(r"<[^>]+>", "", cell).strip() for cell in cells]
        if texts and re.fullmatch(r"\d{4}", texts[0]):
            year = int(texts[0])
            for i, value in enumerate(texts[1:]):
                if re.fullmatch(r"-?\d+\.\d+", value):
                    values[f"{year}-{i + 1:02d}"] = float(value)
    return values


def parse_world_bank(path: Path):
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(workbook["Monthly Prices"].values)
    headers = [str(value).strip() for value in rows[4]]
    columns = {
        "rice": "Rice, Thai 5%",
        "maize": "Maize",
        "sugar": "Sugar, world",
        "palm": "Palm oil",
        "coffee": "Coffee, Robusta",
    }
    output = {}
    for metric, column in columns.items():
        i = headers.index(column)
        output[metric] = {
            row[0].replace("M", "-"): float(row[i])
            for row in rows[6:]
            if isinstance(row[0], str)
            and re.fullmatch(r"\d{4}M\d{2}", row[0])
            and isinstance(row[i], (int, float))
        }
    return output


def changes(old_points, current):
    old = {point["date"]: point["value"] for point in old_points}
    first_published = min(old) if old else "0000-00"
    added = [
        {"date": date, "value": value}
        for date, value in sorted(current.items())
        if date >= first_published and date not in old
    ]
    revised = [
        {"date": date, "previousValue": old[date], "value": value}
        for date, value in sorted(current.items())
        if date >= first_published and date in old and abs(old[date] - value) > 0.0000005
    ]
    return added, revised


dashboard = read_json(ROOT / "data/dashboard.json")
metrics = {metric["id"]: metric for metric in dashboard["metrics"]}
current = {"enso": parse_roni(RAW / "roni.html"), **parse_world_bank(RAW / "world-bank.xlsx")}
metric_updates = {}
new_actuals = {}
for metric_id, values in current.items():
    added, revised = changes(metrics[metric_id]["history"], values)
    prior = read_json(REPORT_PATH).get("metricsUpdated", {}).get(metric_id, {}) if REPORT_PATH.exists() else {}
    added = added or prior.get("observationsAdded", [])
    revised = revised or prior.get("revisedObservations", [])
    if added or revised:
        new_actuals[metric_id] = added + [{"date": p["date"], "value": p["value"]} for p in revised]
    metric_updates[metric_id] = {
        "observationsAdded": added,
        "revisedObservations": revised,
        "latestObservation": {"date": max(values), "value": values[max(values)]},
    }

noaa_previous = parse_roni(ROOT / "data/raw/2026-10-02/roni.html")
noaa_current = current["enso"]
noaa_revisions = [
    {"date": date, "previousValue": noaa_previous[date], "value": value}
    for date, value in noaa_current.items()
    if date in noaa_previous and abs(noaa_previous[date] - value) > 0.0000005
]
indeed_hashes = {}
for name in ("indeed-us-all.csv", "indeed-us-sectors.csv"):
    old = ROOT / "data/ai/raw/2026-10-02" / name
    latest = ROOT / "data/ai/raw" / DAY / name
    indeed_hashes[name] = {
        "unchangedSinceOctober2": hashlib.sha256(old.read_bytes()).hexdigest()
        == hashlib.sha256(latest.read_bytes()).hexdigest(),
        "latestDate": max(
            line.split(",", 1)[0]
            for line in latest.read_text(encoding="utf-8-sig").splitlines()[1:]
        ),
    }
graduate_hashes = {
    name: hashlib.sha256((ROOT / "data/ai/raw" / name).read_bytes()).hexdigest()
    == hashlib.sha256((ROOT / "data/ai/raw" / DAY / name).read_bytes()).hexdigest()
    for name in ("graduate-unemployment.csv", "graduate-underemployment.csv")
}

sources = [
    capture(
        RAW / "world-bank.xlsx",
        "World Bank Pink Sheet",
        WORLD_BANK_PAGE,
        WORLD_BANK_URL,
        "Workbook now includes September 2026 prices; compared with the 2 October capture, palm-oil history for March–August was revised.",
    ),
    capture(
        RAW / "roni.html",
        "NOAA RONI (ERSSTv6)",
        NOAA_URL,
        NOAA_URL,
        "Updated by 5 October: added JAS 2026 = 1.7°C; no earlier observations changed from the 2 October capture.",
    ),
]

previous_report = read_json(REPORT_PATH) if REPORT_PATH.exists() else {}
report = {
    "checkedAt": DAY,
    "newActuals": new_actuals or previous_report.get("newActuals", {}),
    "metricsUpdated": metric_updates if any(new_actuals.values()) else previous_report.get("metricsUpdated", metric_updates),
    "sources": sources,
    "checks": {
        "worldBank": "The current workbook differs from the 2 October capture and now ends at 2026-09. September values were added for rice, maize, sugar, palm oil and Robusta coffee; March–August palm-oil values were revised.",
        "noaa": "The RONI page now includes JAS 2026 = 1.7°C. It adds 2026-08; no previously captured RONI values changed.",
        "indeed": indeed_hashes,
        "newYorkFedGraduates": graduate_hashes,
        "otherSources": "FAO September 2026 (136.0) was published and imported on 2 October; ONS, BLS and Statistics Canada have no newer tracker observations due as of 5 October.",
        "forecasts": "Original frozen scenario anchors and paths remain unchanged.",
    },
    "frozenFileSha256": hashlib.sha256((PUBLIC / "scenarios-v1.json").read_bytes()).hexdigest(),
    "policy": "Imported newly available September commodity actuals and the latest provisional RONI observation; recorded current World Bank palm-oil revisions. No scenario anchors or paths were changed.",
}
write_json(REPORT_PATH, report)

calendar = read_json(CALENDAR_PATH)
completed = []
for event in list(calendar["entries"]):
    if event.get("date") == "2026-10-02" and event.get("title") == "World Bank commodity prices":
        calendar["entries"].remove(event)
        event["checkedAt"] = DAY
        event["importedAt"] = DAY
        event["actualsAdded"] = [f"{metric}: 2026-09" for metric in ("rice", "maize", "sugar", "palm", "coffee")]
        palm_revisions = metric_updates["palm"]["revisedObservations"]
        event["revisionsIncluded"] = [f"palm: 2026-{month:02d}" for month in range(3, 9)] if palm_revisions else []
        event["note"] = "September workbook values appeared after the 2 October check; imported on 5 October."
        completed.append(event)
    elif event.get("title") == "NOAA Relative Oceanic Niño Index" and event.get("month") == "2026-10":
        calendar["entries"].remove(event)
        event["date"] = None
        event["checkedAt"] = DAY
        event["importedAt"] = DAY
        event["actualsAdded"] = ["enso: 2026-08 = 1.7°C"]
        event["revisionsIncluded"] = []
        event["note"] = "Available by NOAA's fifth-of-month update window; exact posting day is not specified."
        completed.append(event)

existing_completed = {
    (item.get("title"), item.get("date"), item.get("month"))
    for item in calendar.get("completedReleases", [])
}
calendar["completedReleases"] = calendar.get("completedReleases", []) + [
    event
    for event in completed
    if (event.get("title"), event.get("date"), event.get("month")) not in existing_completed
]
for event in calendar["completedReleases"]:
    if event.get("title") == "World Bank commodity prices" and event.get("date") == "2026-10-02":
        event["checkedAt"] = DAY
        event["importedAt"] = DAY
        event["actualsAdded"] = [f"{metric}: 2026-09" for metric in ("rice", "maize", "sugar", "palm", "coffee")]
        event["revisionsIncluded"] = [
            f"palm: {item['date']}" for item in metric_updates["palm"]["revisedObservations"]
        ]
        event["note"] = "September workbook values appeared after the 2 October check; imported on 5 October."
    elif event.get("title") == "NOAA Relative Oceanic Niño Index" and event.get("month") == "2026-10":
        event["checkedAt"] = DAY
        event["importedAt"] = DAY
        event["actualsAdded"] = ["enso: 2026-08 = 1.7°C"]
        event["note"] = "Available by NOAA's fifth-of-month update window; exact posting day is not specified."
calendar["completedReleases"].sort(key=lambda item: (item.get("date") or item.get("month") or "", item.get("title", "")))
for event in calendar["entries"]:
    event["checkedAt"] = DAY
calendar["checkedAt"] = DAY
calendar["lastReleaseReviewAt"] = DAY
write_json(CALENDAR_PATH, calendar)
write_json(CALENDAR_PUBLIC, calendar)

print(json.dumps({
    "metricsUpdated": {
        metric: {
            "latestObservation": update["latestObservation"],
            "observationsAdded": update["observationsAdded"],
            "revisedObservationCount": len(update["revisedObservations"]),
            "revisedObservations": update["revisedObservations"],
        }
        for metric, update in metric_updates.items()
    },
    "calendarCompleted": [event["title"] for event in completed],
}, ensure_ascii=False, indent=2))
