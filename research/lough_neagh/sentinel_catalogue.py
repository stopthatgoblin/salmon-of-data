"""Archive a paginated, public Sentinel catalogue; does not retrieve turbidity.

Run from repository root: python3 research/lough_neagh/sentinel_catalogue.py
"""
import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]


def fetch(url):
    with tempfile.NamedTemporaryFile() as f:
        subprocess.run(["curl", "-L", "--fail", "--silent", "--show-error",
                        "--retry", "3", "--max-time", "90", url, "-o", f.name], check=True)
        return Path(f.name).read_bytes()


def acquire(start, end, destination, collection="sentinel-2-l2a"):
    destination.mkdir(parents=True, exist_ok=True)
    url = "https://earth-search.aws.element84.com/v1/search?" + urlencode({
        "collections": collection, "bbox": "-6.72,54.43,-6.18,54.80",
        "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z", "limit": 100})
    manifest, features, seen = [], {}, set()
    while url:
        if url in seen:
            raise ValueError("Catalogue returned a pagination loop")
        seen.add(url)
        body = fetch(url)
        page = json.loads(body)
        path = destination / f"page-{len(manifest) + 1:03d}.json.gz"
        path.write_bytes(gzip.compress(body, mtime=0))
        manifest.append({"url": url, "path": str(path.relative_to(ROOT)),
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                         "uncompressed_sha256": hashlib.sha256(body).hexdigest(),
                         "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                         "number_returned": len(page["features"])})
        for f in page["features"]:
            features[f["id"]] = f
        url = next((l["href"] for l in page["links"] if l["rel"] == "next"), None)
        print(f"Archived page {len(manifest)}; {len(features)} unique items", flush=True)
    records = sorted(features.values(), key=lambda x: x["properties"]["datetime"])
    times = sorted({r["properties"]["datetime"] for r in records})
    dates = sorted({t[:10] for t in times})
    summary = {
        "description": "Bounding-box catalogue inventory, NOT usable water observations or lake coverage",
        "collection": collection,
        "bbox_wgs84": [-6.72, 54.43, -6.18, 54.80], "requested_start": start, "requested_end": end,
        "items": len(records), "unique_acquisition_dates": len(dates),
        "first_datetime": min(times) if times else None, "last_datetime": max(times) if times else None,
        "items_by_platform": dict(collections.Counter(r["properties"]["platform"] for r in records)),
        "items_by_year": dict(collections.Counter(r["properties"]["datetime"][:4] for r in records)),
        "items_by_tile": dict(collections.Counter(r["properties"].get("grid:code") for r in records)),
        "manifest": manifest,
    }
    (destination / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "manifest"}, indent=2))


def read_items(directory):
    manifest = json.loads((directory / "manifest.json").read_text())
    items = {}
    for entry in manifest["manifest"]:
        path = ROOT / entry["path"]
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise ValueError(f"Archive checksum mismatch: {path}")
        for item in json.loads(gzip.decompress(data))["features"]:
            items[item["id"]] = item
    return sorted(items.values(), key=lambda i: i["properties"]["datetime"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2015-06-23")
    parser.add_argument("--end", required=True, help="Explicit inclusive UTC cutoff, YYYY-MM-DD")
    parser.add_argument("--output", default="data/lough-neagh/raw/sentinel/catalogue-2026-09-23")
    parser.add_argument("--collection", default="sentinel-2-l2a")
    args = parser.parse_args()
    acquire(args.start, args.end, ROOT / args.output, args.collection)
