"""Build an auditable, exploratory Sentinel/probe matchup ledger, not ground truth.

All candidates, rejected rows and quality reasons are retained. No values are
interpolated. The two in-lake stations cannot establish whole-lake validity.
"""
import bisect
import collections
import csv
import datetime as dt
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from affine import Affine
from pyproj import Transformer
from shapely.geometry import Point, box, shape
from shapely.ops import transform as project

from sentinel_catalogue import ROOT
from extract_screening import STATIONS, BANDS, select_items
from sentinel_catalogue import read_items

OUTPUT = ROOT / "data/lough-neagh/derived"
WINDOWS = ROOT / "data/lough-neagh/raw/sentinel/c1-station-windows"


def epoch(value):
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def group_measurements(rows):
    grouped = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in rows:
        grouped[(r["Probe_Ref_No"], r["Metric_Type"])][int(r["Date"]) / 1000].append(r)
    return {key: (sorted(values), values) for key, values in grouped.items()}


def nearest_measurement(index, instant, tolerance_seconds=900):
    """Nearest observed time; deterministic earlier tie; never interpolate."""
    if index is None:
        return None
    times, values = index
    i = bisect.bisect_left(times, instant)
    candidates = times[max(0, i-1):min(len(times), i+1)]
    if not candidates:
        return None
    closest = min(candidates, key=lambda t: (abs(t-instant), t))
    if abs(closest-instant) > tolerance_seconds:
        return None
    records = values[closest]
    def finite_value(r):
        try:
            value = float(r["Metric_Value"])
            return value if np.isfinite(value) else None
        except (ValueError, TypeError):
            return None
    numbers = {finite_value(r) for r in records}
    missing = None in numbers
    numbers.discard(None)
    before = times[i-1] if i else None
    after = times[i] if i < len(times) else None
    if closest == instant:
        before = after = closest
    neighbours = [r for t in times[bisect.bisect_left(times, instant-3600):bisect.bisect_right(times, instant+3600)] for r in values[t]]
    sample = [finite_value(r) for r in neighbours if finite_value(r) is not None]
    brackets = (before is not None and after is not None and instant-before <= 1800 and after-instant <= 1800)
    if brackets:
        brackets = all(len({finite_value(r) for r in values[t]}) == 1 and finite_value(values[t][0]) is not None for t in [before, after])
    return {"value": next(iter(numbers)) if len(numbers) == 1 and not missing else None, "missing": missing,
            "conflicting": len(numbers) > 1, "objectids": ";".join(sorted(r["OBJECTID"] for r in records)),
            "timestamp": records[0]["timestamp_utc"], "delta_minutes": (closest-instant)/60,
            "bracketed_30min": brackets,
            "local_2h_n": len(sample), "local_2h_missing_n": len(neighbours)-len(sample),
            "local_2h_min": min(sample) if sample else None, "local_2h_max": max(sample) if sample else None,
            "local_2h_median": float(np.median(sample)) if sample else None, "duplicates": len(records)}


def common_footprint(scl_transform):
    # 51x51 archived SCL patch, central native 20m cell at row25 col25.
    a = Affine(*scl_transform)
    left, top = a * (24, 24)
    right, bottom = a * (27, 27)
    return left, bottom, right, top


def aligned_core(array, band_transform, bounds):
    """Select identical map bounds, not independent centres at different scales."""
    inverse = ~Affine(*band_transform)
    left, bottom, right, top = bounds
    c0, r0 = inverse * (left, top)
    c1, r1 = inverse * (right, bottom)
    coords = [c0, r0, c1, r1]
    if not all(abs(x-round(x)) < 1e-6 for x in coords):
        raise ValueError("Band grid not aligned with native SCL footprint")
    c0, r0, c1, r1 = map(lambda x: int(round(x)), coords)
    if not (0 <= r0 < r1 <= array.shape[0] and 0 <= c0 < c1 <= array.shape[1]):
        raise ValueError("Common footprint outside cached band array")
    return array[r0:r1, c0:c1]


def decode_reflectance(raw, asset):
    band = asset["raster:bands"][0]
    if "scale" not in band or "offset" not in band or "nodata" not in band:
        raise ValueError("Explicit radiometric metadata required")
    mask = raw != band["nodata"]
    result = raw.astype(float) * band["scale"] + band["offset"]
    return np.where(mask, result, np.nan)


def write_csv(path, records):
    columns = list(dict.fromkeys(k for row in records for k in row))
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)


def build():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    observations_path = ROOT / "data/lough-neagh/raw/daera/observations.csv.gz"
    with gzip.open(observations_path, "rt") as f:
        observations = list(csv.DictReader(f))
    expected_units = {"Turbidity": "Nephelometric Turbidity Unit (NTU)",
                      "BGA_PC_Fluorescence": "Relative Fluorescence Units (RFU)"}
    if any(r["Metric_Type"] not in expected_units or r["Metric_Unit"].strip() != expected_units[r["Metric_Type"]] for r in observations):
        raise ValueError("Unexpected probe variable/units; do not silently convert measurement types")
    indexes = group_measurements(observations)
    station_metadata = json.loads((ROOT / "data/lough-neagh/raw/daera/stations.json").read_text())
    commissioned = {f["attributes"]["Probe_Ref_No"]: f["attributes"]["Commissioned_Date"] for f in station_metadata["features"]}
    geometry_path = ROOT / "data/lough-neagh/raw/geography/daera-lough-neagh.geojson"
    feature = json.loads(geometry_path.read_text())["features"][0]
    if feature["properties"]["localId"] != "UKGBNI3NB0032":
        raise ValueError("Wrong lake polygon")
    to_utm = Transformer.from_crs(4326, 32629, always_xy=True).transform
    lake = project(to_utm, shape(feature["geometry"]))
    if not lake.is_valid:
        raise ValueError("Invalid lake geometry")
    catalogue = ROOT / "data/lough-neagh/raw/sentinel/c1-catalogue-2026-09-23"
    items = select_items(read_items(catalogue), "2025-01-06", "2026-09-16")
    records, source_hashes = [], []
    for item in items:
        path = WINDOWS / (item["id"] + ".json")
        meta = json.loads(path.read_text()) if path.exists() else None
        if meta is not None and (meta["collection"] != "sentinel-2-c1-l2a" or not meta["complete"]):
            raise ValueError("Only complete C1 caches accepted; legacy radiometry is quarantined")
        if meta is not None and (meta["properties"] != item["properties"] or meta.get("extraction_version") != 1):
            raise ValueError("Cached scene metadata or extraction version changed")
        if meta:
            source_hashes.append({"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        props = item["properties"]
        instant = epoch(props["datetime"])
        for station, point in STATIONS.items():
            p = Point(to_utm(point["lon"], point["lat"]))
            row = {"scene_id": item["id"], "overpass_group": props["datetime"][:10],
                   "datetime_utc": props["datetime"], "platform": props["platform"],
                   "source_product": props["s2:product_uri"], "collection": item["collection"],
                   "processing_baseline": props["s2:processing_baseline"], "station": station,
                   "station_name": point["name"], "lon": point["lon"], "lat": point["lat"],
                   "inside_lake": lake.contains(p), "shore_distance_m": lake.boundary.distance(p),
                   "before_current_commissioned_date": props["datetime"][:10] < commissioned[station],
                   "probe_quality": "provisional_filtered_view_no_row_flags",
                   "tile_cloud_percent": props["eo:cloud_cover"],
                   "sun_elevation": props.get("view:sun_elevation"), "view_angle": props.get("view:incidence_angle"),
                   "reflectance_type": "Sen2Cor_BOA_not_aquatic_Rw", "publication_eligible": False}
            reasons = []
            if not row["inside_lake"]:
                reasons.append("outside_lake_polygon")
            m = nearest_measurement(indexes.get((station, "Turbidity")), instant)
            if m is None:
                reasons.append("no_probe_within_15min")
            else:
                for k, v in m.items():
                    row["probe_"+k] = v
                if m["conflicting"]:
                    reasons.append("conflicting_probe_values")
                if m["missing"] or m["value"] is None:
                    reasons.append("missing_or_invalid_probe_value")
                if m["value"] is not None and m["value"] <= 0:
                    reasons.append("zero_or_negative_probe_requires_review")
                if not m["bracketed_30min"]:
                    reasons.append("probe_gap_or_unbracketed")
            for shift in [-3600, 3600]:
                alternate = nearest_measurement(indexes.get((station, "Turbidity")), instant+shift)
                row[f"probe_ntu_shift_{shift//60:+d}min"] = alternate["value"] if alternate else None
            pc = nearest_measurement(indexes.get((station, "BGA_PC_Fluorescence")), instant)
            row["phycocyanin_rfu"] = pc["value"] if pc else None
            if meta is None:
                reasons.append("satellite_download_unavailable")
            else:
                s = meta["stations"][station]
                if s["crs"] != "EPSG:32629":
                    raise ValueError("Cached footprint CRS differs from projected lake CRS")
                if any(s[k] != point[k] for k in ["lon", "lat"]):
                    raise ValueError("Station coordinate changed")
                for k in ["scl_core_water_pixels", "scl_cloud_shadow_snow_within_120m", "scl_land_within_120m"]:
                    row[k] = s[k]
                footprint = box(*common_footprint(s["scl_transform"]))
                row["footprint_shore_distance_m"] = footprint.distance(lake.boundary)
                row["footprint_inside_lake"] = lake.contains(footprint)
                if not row["footprint_inside_lake"] or row["footprint_shore_distance_m"] < 100:
                    reasons.append("footprint_shore_buffer_100m")
                if s["scl_core_water_pixels"] != 9:
                    reasons.append("scl_core_not_all_water")
                if s["scl_cloud_shadow_snow_within_120m"]:
                    reasons.append("scl_cloud_shadow_snow_nearby")
                cache = WINDOWS / meta["arrays"][station]["path"]
                if hashlib.sha256(cache.read_bytes()).hexdigest() != meta["arrays"][station]["sha256"]:
                    raise ValueError("Array checksum mismatch")
                with np.load(cache) as arrays:
                    for band in BANDS:
                        if band not in arrays:
                            continue
                        if meta["assets"][band] != item["assets"][band]:
                            raise ValueError("Asset metadata changed")
                        core = aligned_core(arrays[band], s["band_transforms"][band], common_footprint(s["scl_transform"]))
                        values = decode_reflectance(core, meta["assets"][band])
                        row[band+"_median"] = float(np.nanmedian(values))
                        row[band+"_sd"] = float(np.nanstd(values))
                        row[band+"_n"] = int(np.isfinite(values).sum())
                        row[band+"_raw_min"] = int(core.min())
                        row[band+"_nonpositive_pixels"] = int(np.count_nonzero(values <= 0))
                        row[band+"_gte_one_pixels"] = int(np.count_nonzero(values >= 1))
                        row[band+"_cv"] = float(np.nanstd(values)/np.nanmean(values)) if np.nanmean(values) > 0 else None
                        if not np.isfinite(values).all():
                            reasons.append("band_nodata:"+band)
                        if band in ["green", "red", "nir", "rededge1"] and ((values <= 0) | (values >= 1)).any():
                            reasons.append("nonphysical_feature_pixels:"+band)
                if "red_median" not in row:
                    reasons.append("spectra_not_sampled_after_scl_rejection")
                elif any(row[b+"_median"] <= 0 or row[b+"_median"] >= 1 for b in ["green", "red", "nir", "rededge1"]):
                    reasons.append("nonphysical_or_nonpositive_feature_reflectance")
                elif row["red_cv"] is None or row["red_cv"] > .2:
                    reasons.append("heterogeneous_red_cv_above_0.2")
            row["exclusion_reasons"] = ";".join(sorted(set(reasons)))
            row["exploratory_eligible"] = not reasons
            records.append(row)
    write_csv(OUTPUT / "candidate-matchups.csv", records)
    accepted = [r for r in records if r["exploratory_eligible"]]
    write_csv(OUTPUT / "exploratory-matchups.csv", accepted)
    summary = {"pipeline_version": "feasibility-1", "publication_allowed": False,
               "description": "Diagnostic matchups of provisional threshold-filtered DAERA data and Sen2Cor BOA. NOT validated turbidity.",
               "candidate_rows": len(records), "scene_count": len(items), "date_count": len(set(r["overpass_group"] for r in records)),
               "accepted_rows": len(accepted), "accepted_dates": len(set(r["overpass_group"] for r in accepted)),
               "accepted_by_station": dict(collections.Counter(r["station"] for r in accepted)),
               "rejection_counts_nonexclusive": dict(collections.Counter(reason for r in records for reason in r["exclusion_reasons"].split(";") if reason)),
               "station_geography": [{k: r[k] for k in ["station", "station_name", "lon", "lat", "inside_lake", "shore_distance_m"]} for r in records[:3]],
               "rules": {"nearest_probe_minutes": 15, "bracket_each_side_minutes": 30,
                         "footprint": "native SCL 3x3 20m pixels; identical 60m square for all spectral bands",
                         "shore_buffer_m_research_choice": 100, "max_red_cv_research_choice": .2,
                         "cloud_screen": "SCL 3,8,9,10,11 absent from 13x13 neighbourhood; not a complete cloud/glint mask"},
               "inputs": [{"path": str(p.relative_to(ROOT)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                          for p in [observations_path, geometry_path, catalogue / "manifest.json"]] + source_hashes}
    (OUTPUT / "matchup-audit.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "inputs"}, indent=2))


if __name__ == "__main__":
    build()
