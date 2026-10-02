# Reproduce the feasibility investigation

No website code consumes these outputs. `publication_allowed` is false in the matchup audit; no deployable model has been saved. Research and raw downloads are separate from the React application.

## Frozen, offline analysis

The versionable [input capsule](../../data/lough-neagh/snapshots/matchup-inputs-2026-09-23.tar.gz) contains 2,792 files: both archived STAC catalogues, original small station pixel windows/metadata, the normalized provisional DAERA snapshot, station/schema metadata, request manifests, and both lake geometries. Its [manifest](../../data/lough-neagh/snapshots/matchup-inputs-2026-09-23.json) hashes every member and the archive. It is about 12 MB compressed. This makes the matched analysis reproducible even if upstream probe records change.

The full original HTTP DAERA responses, large diagnostic TIFF, EOCIS sample and product documents are retained under `data/lough-neagh/raw/` locally and excluded from Git. They are not all in the compact capsule. Copernicus inspection results and source manifests are separately retained under `processed/` and `provenance/`. Do not describe the capsule as a complete archive of every research source.

Tested environment: Python 3.9.12, NumPy 1.26.4, rasterio 1.3.8, affine 2.4.0, pyproj 3.3.1, Shapely 2.0.6, matplotlib 3.9.4 and h5py 3.6.0. Versions are recorded in [requirements.txt](../../research/lough_neagh/requirements.txt). Use an isolated environment for a new installation; platform libraries may need compatible wheels. On the investigation machine, the working interpreter is `/Users/peterdonaghy/opt/anaconda3/bin/python3`; a bare `python3` resolved to a different environment on resumption.

From the repository root, using that environment:

```sh
python3 research/lough_neagh/capsule.py restore
python3 -m unittest discover -s research/lough_neagh -p 'test_*.py' -v
python3 research/lough_neagh/audit_radiometry.py
python3 research/lough_neagh/build_matchups.py
python3 research/lough_neagh/model_screening.py
python3 research/lough_neagh/figures.py
```

Restoration verifies hashes and refuses to overwrite different existing files. There is no network access in these analysis commands. Numerical output should reproduce under the recorded environment; figure fonts may differ across systems. Tests cover temporal ties/gaps/nulls/conflicting duplicates, source-ID preservation, common 10/20 m footprints, radiometric offset/nodata/negative handling, cloud masking, fit-only preprocessing, negative R² and whole-date/station/forward split isolation.

## What the scripts do

| Script | Responsibility |
|---|---|
| `sentinel_catalogue.py` | Paginated STAC acquisition, archived response hashes, catalogue inventory |
| `extract_screening.py` | Small COG range reads; raw pixel arrays plus source metadata and SCL diagnostics |
| `daera/fetch.py` | Content-addressed HTTP responses, exact ID-set checks, normalized records and data-quality audit |
| `daera/context.py` | Provider guidance, station views and older environmental-data discovery |
| `audit_radiometry.py` | Same-SAFE C1/legacy pixel encoding comparison, checksum and difference checks |
| `build_matchups.py` | All candidate rows, exact common footprints, nearest observed labels and explicit QC exclusions |
| `model_screening.py` | Eight fixed simple candidates, grouped holdouts, residuals, sensitivities and conditional bootstrap diagnostics |
| `figures.py` | Study-location figure and clearly labelled validation diagnostics |
| `copernicus_audit.py` | Offline EOCIS NetCDF inspection and CLMS metadata/access audit |
| `capsule.py` | Deterministic input packaging and safe, hash-verified restoration |

## Matching rules and their status

The analysis takes the nearest recorded probe time within 15 minutes, reflecting half the nominal 30-minute cadence. Ties go to the earlier reading. The closest null/conflicting record is flagged rather than silently replaced with a more distant valid one. Valid observations must bracket the overpass within 30 minutes each side; there is no interpolation. Original duplicates and all associated IDs remain in the source snapshot. Identical duplicates at the matched time retain their IDs; conflicting values are rejected. Exact zero or negative target values require review and are excluded from the exploratory fit, not deleted from the ledger.

The spectral footprint is 3 × 3 native SCL cells (60 m square) and exactly corresponding native spectral pixels, summarized by median and standard deviation/CV. The footprint must be inside the official polygon and at least 100 m from its boundary. Features with nonpositive/out-of-range pixels or nodata are flagged. The red-band CV limit is 0.2. Shore and homogeneity sensitivity results are retained. These thresholds are **declared research choices**, not established physical constants or tested production masks. SCL-only screening, unresolved surface scum/glint and two stations constrain the experiment.

The ledger also retains ±1-hour probe variability and alternative ±60-minute-clock values as diagnostics; these do not replace the official UTC interpretation. Source depth/coordinate history and row quality remain unresolved. The pipeline does not fabricate a matchup uncertainty value or regard source precision as field accuracy.

Regression candidates are fixed before examining their diagnostic scores: training median, station median, one annual sine/cosine baseline, ordinary least-squares red, NIR, red+NIR and two band ratios. No nonlinear learner, tuned hyperparameter or final winner is deployed. Forward folds train on the first 40%, 60% and 80% of dates and test on the next 20%; they never train on the future. Station folds remove all dates represented at the test station from training, as well as the station. Folds with fewer than eight training dates are skipped as a numerical diagnostic safeguard, not declared scientifically sufficient. Pooled and date-balanced errors are both recorded.

## Fresh acquisition is a new edition

The archived cutoff is explicit. To reproduce the original selection from public services, use:

```sh
python3 research/lough_neagh/sentinel_catalogue.py --end 2026-09-23
python3 research/lough_neagh/sentinel_catalogue.py --start 2025-01-06 --end 2026-09-16 --collection sentinel-2-c1-l2a --output data/lough-neagh/raw/sentinel/c1-catalogue-2026-09-23
python3 research/lough_neagh/extract_screening.py --catalogue data/lough-neagh/raw/sentinel/c1-catalogue-2026-09-23 --output data/lough-neagh/raw/sentinel/c1-station-windows --workers 4
python3 research/lough_neagh/daera/fetch.py
```

These may need network permission. STAC and COG access used here require no account. Catalogue queries can return revised/newly indexed products, so a new network run is not guaranteed to equal the frozen snapshot. Preserve the capsule. Use a new output directory for new Sentinel editions; do not repurpose a dated one. DAERA `--refresh` explicitly acquires new observations; the script aborts if IDs change during a paged retrieval. The current default command reuses hash-verified cached requests when available.

CLMS raster benchmarking additionally needs authorised CDSE access; it has not been performed. EOCIS inspection can be rerun with `python3 research/lough_neagh/copernicus_audit.py` while its original locally retained inputs exist. The saved Copernicus source manifest lists canonical URLs and sample checksums; some original HTTP request times were not retained and are explicitly unknown. PDF contents, not filenames, establish the inspected product-document versions.

No scheduled automation, deployment, email or data-provider request was sent. Changes to reference data, atmospheric correction or mask rules require a new validation edition and a new explicit publication decision.
