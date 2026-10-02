#!/usr/bin/env python3
"""Inspect saved Copernicus/EOCIS evidence; never create a publishable product.

Run from any directory with Python 3.9+, numpy and h5py. No network access,
credentials or netCDF4/xarray engine is needed. The EOCIS netCDF4 container is
read as HDF5, with fill values handled explicitly. No model is fitted here.
"""
from collections import Counter
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/lough-neagh/raw/copernicus"
OUT = ROOT / "data/lough-neagh/processed/copernicus"
CATALOGUE = "https://catalogue.ceda.ac.uk/uuid/6e329e32570d4d4f818b8f8aa18e7a85/"
DIRECTORY = "https://data.ceda.ac.uk/neodc/eocis/data/CHUK/lake_catchment_indicators/neagh"
TECHNICAL = "https://land.copernicus.eu/en/technical-library/"
CDSE = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"


def digest(path, algorithm="sha256"):
    result = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(part)
    return result.hexdigest()


def serialise(value):
    if isinstance(value, bytes):
        return value.decode("utf8")
    if isinstance(value, np.ndarray):
        return [serialise(x) for x in value.tolist()]
    if isinstance(value, np.generic):
        return serialise(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return str(value)
    return value


def attributes(obj):
    # HDF5 dimension references cannot be usefully serialised as source metadata.
    internal = {"DIMENSION_LIST", "REFERENCE_LIST", "_Netcdf4Coordinates"}
    return {k: serialise(v) for k, v in obj.attrs.items() if k not in internal}


def main():
    listing = json.loads((RAW / "eocis_neagh_listing.json").read_text())
    files = [item for item in listing["items"] if item.get("ext") == ".nc"]
    dates = sorted(item["regex_date"] for item in files)
    summary = {
        "audit_date": "2026-09-23",
        "publication_eligible": False,
        "purpose": "Product/access audit only; not local turbidity validation",
        "eocis": {
            "catalogue": CATALOGUE,
            "directory": DIRECTORY,
            "listed_netcdf_files": len(files),
            "unique_dates": len(set(dates)),
            "first_date": dates[0], "last_date": dates[-1],
            "files_by_year": dict(sorted(Counter(x[:4] for x in dates).items())),
            "overlap_with_2025_2026_observations": any(x >= "2025-01-01" for x in dates),
            "samples": [],
        },
    }
    for path in sorted(RAW.glob("*.nc")):
        entry = next(x for x in files if x["name"] == path.name)
        assert digest(path, "md5") == entry["md5"], "Downloaded sample differs from CEDA checksum"
        with h5py.File(path, "r") as dataset:
            variables = {
                k: {"shape": list(v.shape), "dtype": str(v.dtype), "attributes": attributes(v)}
                for k, v in dataset.items()
            }
            turbidity = dataset["turbidity"][()]
            fill = dataset["turbidity"].attrs["_FillValue"][0]
            keep = np.isfinite(turbidity) & (turbidity != fill)
            # These counts/ranges describe the entire unmasked catchment container.
            # They must not be interpreted as lake observations or validation data.
            sample = {
                "file": path.name, "download_url": entry["download"],
                "sha256": digest(path), "ceda_md5_verified": True,
                "global_attributes": attributes(dataset), "variables": variables,
                "time_coordinate_utc": (
                    datetime(1970, 1, 1, tzinfo=timezone.utc)
                    + timedelta(days=float(dataset["time"][0]))
                ).isoformat(),
                "grid_spacing_x_m": sorted(set(np.diff(dataset["x"][()]).tolist())),
                "grid_spacing_y_m": sorted(set(np.diff(dataset["y"][()]).tolist())),
                "quality_or_flag_variables": [k for k in dataset if "flag" in k.lower() or "quality" in k.lower()],
                "water_mask_variable_present": "water" in dataset,
                "unmasked_catchment_container_diagnostics": {
                    "total_cells": int(turbidity.size),
                    "finite_nonfill_turbidity_cells": int(keep.sum()),
                    "negative_turbidity_cells": int((turbidity[keep] < 0).sum()),
                    "minimum": float(turbidity[keep].min()),
                    "maximum": float(turbidity[keep].max()),
                    "warning": "Not Lough Neagh statistics; land/cloud/shore/bloom QC has not been applied.",
                },
            }
        summary["eocis"]["samples"].append(sample)
    clms = json.loads((RAW / "clms_lwq100_latest_catalogue.json").read_text())
    product = clms["value"][0]
    base = "https://download.dataspace.copernicus.eu/odata/v1/Products(" + product["Id"] + ")"
    filename = product["Name"].removesuffix("_nc") + ".nc"
    binary_url = base + "/Nodes(" + product["Name"] + ")/Nodes(" + filename + ")/$value"
    with (RAW / "clms_lwq100_cog_catalogue.csv").open() as stream:
        cogs = list(csv.DictReader(stream, delimiter=";"))
    latest_cog = max(cogs, key=lambda row: row["content_date_start"])
    summary["clms"] = {
        "dataset": "lwq-nrt_global_100m_10daily_v2",
        "catalogue_record": product,
        "latest_saved_cog_catalogue_record": latest_cog,
        "access_status": "Public catalogue metadata; saved unauthenticated download response is HTTP 401",
        "raster_downloaded": False,
        "neagh_pixel_coverage_confirmed": False,
        "local_validation_performed": False,
        "note": "Global product footprint alone does not prove valid Neagh pixels. The catalogue count may include multiple formats.",
        "access_probe": {
            "request_url": binary_url,
            "method": "GET", "range": "bytes=0-0", "authentication": "none",
            "max_response_bytes": 1024,
            "response_status": 401,
            "saved_response_headers": "clms_access_get_probe_headers.txt",
            "note": "A preceding HEAD request received HTTP 405 (unsupported method); the bounded GET reproduced HTTP 401.",
        },
    }
    sources = {
        "eocis_neagh_listing.json": DIRECTORY,
        "eocis_guide_v1.2.pdf": "https://eocis.org/wp-content/uploads/2025/03/UK_EOCIS_LakeCatchment_Quick-Start-Guide-V1.2.pdf",
        "lwq100_v2_pum.pdf": TECHNICAL + "product-user-manual-lake-water-quality-100m-version-2.0/@@download/file",
        "lwq100_v2_qar.pdf": TECHNICAL + "quality-assessment-report-lake-water-quality-v2.0/@@download/file",
        "lwq100_v2.1_pum.pdf": TECHNICAL + "product-user-manual-lake-water-quality-100m-version-2.1/@@download/file",
        "lwq100_v2.2_atbd.pdf": TECHNICAL + "algorithm-theoretical-basis-document-lake-water-quality-100m-version-2.1/@@download/file",
        "clms_lwq100_cog_catalogue.csv": "https://s3.waw3-1.cloudferro.com/swift/v1/CatalogueCSV/bio-geophysical/lake_water_quality/lwq-nrt_global_100m_10daily_v2/lwq-nrt_global_100m_10daily_v2_cog.csv",
        "clms_lwq100_catalogue_index.html": "https://csv.dataspace.copernicus.eu/bio-geophysical/lake_water_quality/lwq-nrt_global_100m_10daily_v2/",
        "clms_lwq100_latest_catalogue.json": CDSE,
    }
    for sample in summary["eocis"]["samples"]:
        sources[sample["file"]] = sample["download_url"]
    sources["clms_lwq100_latest_nodes.json"] = base + "/Nodes"
    sources["clms_lwq100_latest_file_nodes.json"] = base + "/Nodes(" + product["Name"] + ")/Nodes"
    sources["clms_access_probe_headers.txt"] = binary_url
    sources["clms_access_get_probe_headers.txt"] = binary_url
    # Earlier acquisition did not preserve the exact download request. Keep the
    # saved headers as evidence without inventing that part of its provenance.
    sources["clms_unauthenticated_download_headers.txt"] = None
    manifest = {
        "version": 1,
        "audit_date": "2026-09-23",
        "note": "Sources are canonical source references, not a complete HTTP request log. Pre-existing acquisition request timestamps were not retained; file mtime is recorded separately. Text files are local PDF extractions. PUM/ATBD URLs retain 2.1 in their path but their downloaded contents are 2.2.0.",
        "files": [],
    }
    for path in sorted(RAW.iterdir()):
        if not path.is_file() or path.name == "manifest.json":
            continue
        source = sources.get(path.name)
        derived_from = None
        if path.suffix == ".txt" and (path.with_suffix(".pdf")).exists():
            derived_from = path.with_suffix(".pdf").name
            source = sources.get(derived_from)
        manifest["files"].append({
            "path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
            "sha256": digest(path), "source_reference": source,
            "derived_from": derived_from,
            "filesystem_mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "audit.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    (RAW / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n")
    print(json.dumps({
        "eocis_files": len(files), "eocis_range": [dates[0], dates[-1]],
        "sample_quality_flags": summary["eocis"]["samples"][0]["quality_or_flag_variables"],
        "latest_clms": product["Name"], "publication_eligible": False,
    }, indent=2))


if __name__ == "__main__":
    main()
