"""Cache Sentinel L2A station windows for an exploratory feasibility screen.

Sen2Cor BOA is NOT aquatic water-leaving reflectance. This script cannot publish
turbidity and does not turn an SCL water label into scientific validation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from pyproj import Transformer

from sentinel_catalogue import read_items, ROOT

# Authoritative DAERA /FeatureServer/0 query, outSR=4326; positional accuracy unknown.
STATIONS = {
    "L1278": {"name": "Rea's Wood", "lon": -6.241996568375846, "lat": 54.712602169290584},
    "L1279": {"name": "Washing Bay", "lon": -6.569769770482481, "lat": 54.523188284062314},
    "L1284": {"name": "Toome", "lon": -6.466696920835618, "lat": 54.75354853784675},
}
BANDS = ["blue", "green", "red", "rededge1", "rededge2", "rededge3", "nir", "nir08", "swir16", "swir22"]
EXTRACTION_VERSION = 1


def select_items(items, start, end):
    selected = {}
    for item in items:
        p = item["properties"]
        if not start <= p["datetime"][:10] <= end:
            continue
        uri = p["s2:product_uri"].split("_")
        key = (uri[0], uri[2], uri[4], uri[5])  # spacecraft, sensing time, orbit, tile
        rank = (tuple(int(x) for x in p["s2:processing_baseline"].split(".")), p["s2:generation_time"], item["id"])
        if key not in selected or rank > selected[key][0]:
            selected[key] = (rank, item)
    return sorted([x[1] for x in selected.values()], key=lambda x: x["properties"]["datetime"])


def read_patch(src, station, width):
    x, y = Transformer.from_crs(4326, src.crs, always_xy=True).transform(station["lon"], station["lat"])
    row, col = src.index(x, y)
    half = width // 2
    win = Window(col - half, row - half, width, width)
    arr = src.read(1, window=win, boundless=True, fill_value=src.nodata)
    return arr, list(src.window_transform(win))[:6]


def screening_mask(scl):
    """Explicit research screen; not a validated cloud/adjacency/glint mask."""
    c = scl.shape[0] // 2
    core = scl[c-1:c+2, c-1:c+2]
    neighbourhood = scl[c-6:c+7, c-6:c+7]
    return {
        "scl_core_water_pixels": int(np.count_nonzero(core == 6)),
        "scl_core_pixels": int(core.size),
        "scl_cloud_shadow_snow_within_120m": bool(np.isin(neighbourhood, [3, 8, 9, 10, 11]).any()),
        "scl_land_within_120m": bool(np.isin(neighbourhood, [4, 5]).any()),
        "scl_centre_class": int(scl[c, c]),
    }


def process(item, output):
    path = output / (item["id"] + ".json")
    if path.exists():
        saved = json.loads(path.read_text())
        same_points = all(all(saved.get("stations", {}).get(s, {}).get(k) == v for k, v in point.items())
                          for s, point in STATIONS.items())
        same_assets = all(item["assets"].get(k) == asset for k, asset in saved.get("assets", {}).items())
        if (saved.get("complete") and saved.get("extraction_version") == EXTRACTION_VERSION
                and same_points and same_assets and saved.get("properties") == item["properties"]):
            # Reuse only intact cache; never silently accept edited arrays.
            for file in saved["arrays"].values():
                if hashlib.sha256((output / file["path"]).read_bytes()).hexdigest() != file["sha256"]:
                    raise ValueError("Cached array checksum mismatch")
            return saved
    metadata = {"item_id": item["id"], "properties": item["properties"], "extraction_version": EXTRACTION_VERSION,
                "collection": item["collection"], "purpose": "exploratory_Sen2Cor_screen_only",
                "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "assets": {}, "stations": {}, "arrays": {}, "complete": False}
    arrays = {station: {} for station in STATIONS}
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_MAX_RETRY="2",
                      GDAL_HTTP_RETRY_DELAY="1", GDAL_HTTP_TIMEOUT="45", VSI_CACHE=True,
                      CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif"):
        asset = item["assets"]["scl"]
        metadata["assets"]["scl"] = asset
        with rasterio.open(asset["href"]) as src:
            for station, point in STATIONS.items():
                patch, transform = read_patch(src, point, 51)
                arrays[station]["scl"] = patch
                metadata["stations"][station] = {**point, **screening_mask(patch),
                    "scl_transform": transform, "crs": str(src.crs), "band_transforms": {}}
        candidates = [s for s, v in metadata["stations"].items()
                      if v["scl_core_water_pixels"] == 9 and not v["scl_cloud_shadow_snow_within_120m"]]
        for band in BANDS if candidates else []:
            asset = item["assets"][band]
            metadata["assets"][band] = asset
            with rasterio.open(asset["href"]) as src:
                for station in candidates:
                    # 60m core: 6x6 10m or 3x3 20m; store 13/7 pixels for sensitivity.
                    width = 13 if abs(src.res[0]) == 10 else 7
                    patch, transform = read_patch(src, STATIONS[station], width)
                    arrays[station][band] = patch
                    metadata["stations"][station]["band_transforms"][band] = transform
        for station, data in arrays.items():
            filename = f"{item['id']}-{station}.npz"
            np.savez_compressed(output / filename, **data)
            metadata["arrays"][station] = {"path": filename, "sha256": hashlib.sha256((output / filename).read_bytes()).hexdigest()}
    metadata["complete"] = True
    path.write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-01-06")
    parser.add_argument("--end", default="2026-09-16")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--catalogue", default="data/lough-neagh/raw/sentinel/catalogue-2026-09-23")
    parser.add_argument("--output", default="data/lough-neagh/raw/sentinel/station-windows")
    args = parser.parse_args()
    folder = ROOT / args.output
    folder.mkdir(parents=True, exist_ok=True)
    items = select_items(read_items(ROOT / args.catalogue), args.start, args.end)
    if args.limit:
        items = items[:args.limit]
    failures = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(process, item, folder): item["id"] for item in items}
        for i, future in enumerate(as_completed(futures), 1):
            try:
                record = future.result()
                print(f"{i}/{len(items)} {record['item_id']}: {len(record['assets']) - 1} spectral bands", flush=True)
            except Exception as exc:
                failures.append({"item_id": futures[future], "error": str(exc)})
                print(f"FAILED {futures[future]}: {exc}", flush=True)
    (folder / "run.json").write_text(json.dumps({"requested_items": len(items), "failures": failures,
        "start": args.start, "end": args.end, "limited": args.limit is not None}, indent=2) + "\n")
    if failures:
        raise SystemExit(1)
