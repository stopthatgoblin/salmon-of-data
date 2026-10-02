"""Create/restore a deterministic portable snapshot of the matchup inputs.

Restoration refuses path traversal, symlinks and overwriting different content.
Large full-scene diagnostic downloads are not needed by the matchup pipeline.
"""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

from sentinel_catalogue import ROOT

FOLDER = ROOT / "data/lough-neagh/snapshots"
ARCHIVE = FOLDER / "matchup-inputs-2026-09-23.tar.gz"
MANIFEST = FOLDER / "matchup-inputs-2026-09-23.json"


def inputs():
    base = ROOT / "data/lough-neagh/raw"
    paths = []
    for folder in [base / "sentinel/catalogue-2026-09-23", base / "sentinel/c1-catalogue-2026-09-23",
                   base / "sentinel/station-windows", base / "sentinel/c1-station-windows"]:
        paths.extend(p for p in folder.iterdir() if p.is_file())
    for name in ["observations.csv.gz", "stations.json", "audit.json", "manifest.json", "manifest-4e04da8425f9.json"]:
        paths.append(base / "daera" / name)
    paths.extend((base / "daera").glob("*-schema-*.json.gz"))
    paths.extend([base / "geography/daera-lough-neagh.geojson", base / "geography/wfd-lakes.geojson"])
    return sorted(set(paths))


def create():
    FOLDER.mkdir(exist_ok=True, parents=True)
    records = []
    with ARCHIVE.open("wb") as target, gzip.GzipFile(fileobj=target, mode="wb", filename="", mtime=0) as compressed, tarfile.open(fileobj=compressed, mode="w|") as tar:
        for path in inputs():
            body = path.read_bytes()
            name = str(path.relative_to(ROOT))
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(body), 0o644, 0
            tar.addfile(info, io.BytesIO(body))
            records.append({"path": name, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})
    result = {"description": "Frozen research input snapshot. Provisional threshold-filtered DAERA records and satellite pixels; NOT a public turbidity product.",
              "edition": "2026-09-23", "archive": ARCHIVE.name, "bytes": ARCHIVE.stat().st_size,
              "sha256": hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(), "files": records}
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Archived {len(records)} files, {result['bytes']} bytes; SHA256 {result['sha256']}")


def restore():
    manifest = json.loads(MANIFEST.read_text())
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Snapshot archive hash mismatch")
    expected = {r["path"]: r for r in manifest["files"]}
    seen = set()
    with tarfile.open(ARCHIVE, "r:gz") as tar:
        for member in tar:
            path = (ROOT / member.name).resolve()
            if not member.isfile() or not path.is_relative_to(ROOT) or member.name not in expected or member.name in seen:
                raise ValueError("Unsafe or unexpected archive member")
            body = tar.extractfile(member).read()
            if hashlib.sha256(body).hexdigest() != expected[member.name]["sha256"]:
                raise ValueError("Snapshot member hash mismatch")
            if path.exists() and path.read_bytes() != body:
                raise ValueError(f"Existing file differs; preserve it before restoring: {path}")
            if not path.exists():
                path.parent.mkdir(exist_ok=True, parents=True)
                path.write_bytes(body)
            seen.add(member.name)
    if seen != set(expected):
        raise ValueError("Incomplete archive")
    print(f"Verified/restored {len(seen)} files; existing identical files preserved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["create", "restore"])
    args = parser.parse_args()
    create() if args.mode == "create" else restore()
