"""Download a small, cached sample of public SEMO reports for proxy validation.

No credentials are used. Reruns reuse XML files and refresh the report indexes.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import json
import shutil
import tempfile
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"
BASE = "https://reports.sem-o.com"


def fetch(url):
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=25) as response:
                return response.read()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def index(name, start, end):
    query = dict(name=name, date_from=start, date_to=end, sort_by="PublishTime",
                 order_by="ASC", page_size=300, page=1)
    items = []
    while True:
        url = BASE + "/api/v1/documents/static-reports?" + urllib.parse.urlencode(query)
        page = json.loads(fetch(url))
        items.extend(page["items"])
        if query["page"] >= page["pagination"]["totalPages"]:
            break
        query["page"] += 1
    return items


def download(item):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / item["ResourceName"]
    if not path.exists():
        raw = fetch(BASE + "/documents/" + item["ResourceName"])
        # Readers must never see an unfinished XML file during concurrent jobs.
        with tempfile.NamedTemporaryFile(dir=CACHE, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw)
        temporary.replace(path)
        time.sleep(0.15)
    return path.name


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    specs = [
        ("PUB_HrlyDispatchInstr", "2026-10-26", "2026-10-31"),
        ("PUB_DailyMeterDataD1", "2026-10-26", "2026-10-29"),
        ("PUB_DailyDispatchInstrD1", "2026-10-28", "2026-10-29"),
    ]
    manifest = []
    for name, start, end in specs:
        rows = index(name, start, end)
        print(name, len(rows), "reports", flush=True)
        manifest.extend(rows)
    # Reuse the already inspected public files where possible.
    for item in manifest:
        prior = Path("/tmp") / ("ni-electricity-" + item["ResourceName"])
        destination = CACHE / item["ResourceName"]
        if prior.exists() and not destination.exists():
            shutil.copyfile(prior, destination)
    errors = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [(item, pool.submit(download, item)) for item in manifest]
        for number, (item, future) in enumerate(futures, 1):
            try:
                future.result()
            except Exception as exc:
                errors.append({"resource": item["ResourceName"], "error": str(exc)})
            if number % 24 == 0:
                print("Cached", number, "of", len(manifest), flush=True)
    result = {"retrieved_at_utc": datetime.utcnow().isoformat() + "Z",
              "source": BASE, "reports": manifest, "errors": errors}
    (ROOT / "manifest.json").write_text(json.dumps(result, indent=2))
    print("Finished:", len(manifest), "reports;", len(errors), "errors", flush=True)


if __name__ == "__main__":
    main()
