"""Compare archived raw C1/legacy pixels for EXACTLY the same SAFE product.

This diagnoses encoding differences; it does not validate Sen2Cor for water.
"""
import collections
import hashlib
import json

import numpy as np

from sentinel_catalogue import ROOT


def verify_differences(counts):
    if not counts or set(counts) != {1000}:
        raise ValueError("Radiometry unresolved: expected only +1000 C1-minus-legacy DN differences")


def main():
    root = ROOT / "data/lough-neagh/raw/sentinel"
    legacy = {}
    for path in (root / "station-windows").glob("S*.json"):
        item = json.loads(path.read_text())
        legacy[item["properties"]["s2:product_uri"]] = item
    checks = []
    for path in sorted((root / "c1-station-windows").glob("S*.json")):
        current = json.loads(path.read_text())
        previous = legacy.get(current["properties"]["s2:product_uri"])
        if previous is None:
            continue
        for station in current["arrays"]:
            for folder, metadata in [("c1-station-windows", current), ("station-windows", previous)]:
                entry = metadata["arrays"][station]
                if hashlib.sha256((root / folder / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
                    raise ValueError("Pixel cache hash mismatch")
            with np.load(root / "c1-station-windows" / current["arrays"][station]["path"]) as a, np.load(root / "station-windows" / previous["arrays"][station]["path"]) as b:
                for band in a.files:
                    if band == "scl" or band not in b.files:
                        continue
                    if current["stations"][station]["band_transforms"][band] != previous["stations"][station]["band_transforms"][band]:
                        raise ValueError("Comparison footprints differ")
                    good = (a[band] > 1000) & (b[band] > 1)
                    diff = a[band].astype(int)-b[band].astype(int)
                    checks.append({"safe_product": current["properties"]["s2:product_uri"], "c1": current["item_id"],
                        "legacy": previous["item_id"], "station": station, "band": band,
                        "unclamped_pixels": int(good.sum()), "difference_counts": dict(collections.Counter(diff[good].ravel().tolist())),
                        "c1_pixels_at_or_below_1000": int(((a[band] > 0) & (a[band] <= 1000)).sum()),
                        "legacy_pixels_one": int((b[band] == 1).sum())})
    differences = dict(sum((collections.Counter(r["difference_counts"]) for r in checks), collections.Counter()))
    verify_differences(differences)
    report = {"purpose": "Raw DN parity diagnostic for exact same SAFE product and geospatial windows. Does not validate atmospheric correction.",
        "comparisons": len(checks), "unique_safe_products": len({r["safe_product"] for r in checks}),
        "all_unclamped_pixel_differences": differences,
        "c1_pixels_at_or_below_1000": sum(r["c1_pixels_at_or_below_1000"] for r in checks),
        "legacy_pixels_one": sum(r["legacy_pixels_one"] for r in checks),
        "decision": "Use C1 collection explicit scale .0001 and offset -.1. Legacy metadata contradictory and quarantined. Full checks retained.",
        "checks": checks}
    output = ROOT / "data/lough-neagh/derived/radiometry-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, indent=2))


if __name__ == "__main__":
    main()
