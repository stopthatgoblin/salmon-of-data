# Copernicus and EOCIS product audit

Audit date: 23 September 2026. **Decision: retain CLMS as a candidate benchmark, but do not publish its NTU values as locally validated observations.** The available evidence does not establish whether the current CLMS raster has valid Lough Neagh coverage or acceptable local turbidity accuracy. The independently accessible EOCIS archive contains real Neagh imagery, but cannot supply the 2025–2026 probe comparison and its inspected sample lacks essential masks. These are distinct access, provenance and validation limitations; none proves that Sentinel retrieval is physically impossible.

## Products and versions

| Product | Resolution and time support | Archive and current version | Role in this project |
|---|---|---|---|
| CLMS Lake Water Quality 100 m | Nominal 100 m, 10-day composites, Sentinel-2 MSI | v1: 2019–2024; v2: 2024–present. Saved catalogue's latest product is **v2.2.2**, 1–10 September 2026, published 16 September | Candidate operational benchmark; not a single-overpass map |
| CLMS Lake Water Quality 300 m | Nominal 300 m, 10-day composites, Sentinel-3 OLCI for recent products | 2016–present, with separate earlier 2002–2012 reprocessing | Secondary offshore cross-sensor consistency check; insufficient for fine shoreline detail |
| EOCIS Lake Catchment Change Indicators | 100 m British National Grid; dated Sentinel-2 products | Catalogue V1.0; actual Neagh files **fv1.5.0**, 26 May 2016–29 December 2023 | Accessible historical research input, subject to new QC and validation |

Collection periods and access routes are documented in the [CDSE CLMS catalogue](https://documentation.dataspace.copernicus.eu/Data/CopernicusServices/CLMS.html). The [100 m product page](https://land.copernicus.eu/en/products/water-bodies/lake-water-quality-v2-0-100m) marks the collection “Validated”, but has selected Europe/Africa coverage. A collection label is not independent validation at every lake. The saved product's global bounding polygon is not evidence of valid pixels at Neagh.

Version control matters. The downloaded **PUM is v2.2.0, issue I1.00, 16 July 2026**, although its URL and local filename still say 2.1. The downloaded [ATBD](https://land.copernicus.eu/en/technical-library/algorithm-theoretical-basis-document-lake-water-quality-100m-version-2.1) is also **v2.2.0, issue I1.00, 16 July 2026**. The publicly located **QAR is v2.0.0, issue I1.02, 24 July 2024**. The PUM refers to a v2.2.0 QAR; this audit did not obtain that report. It would be incorrect to represent the older QAR as a quantitative evaluation of v2.2.2. PDF hashes are retained because URL names are insufficient version identifiers.

## Retrieval and temporal interpretation

The current [PUM](https://land.copernicus.eu/en/technical-library/product-user-manual-lake-water-quality-100m-version-2.1/@@download/file), pp. 14–16 and 24, describes MSI L1C resampling, IdePix screening and Polymer 4.17 atmospheric correction. Version 2.2 changes meteorological inputs to ECMWF while retaining earlier retrieval parameterisation. Optical water type membership blends Nechad-based algorithms using 665, 705, 783 or 865 nm; unsupported classes become missing. Turbidity is temporally averaged, whereas reflectance uses a representative spectrum. First/last observation bands include acquisitions irrespective of pixel validity. Thus a composite cannot be matched as though it were one overpass. The nominal grid is 0.1/112 degrees, not equal-area square 100 m cells. Its stated uncertainty target is a requirement, not demonstrated Neagh performance.

**Project implications:** validate a composite against equivalent temporal support, preferably using its valid contributing acquisition times. A 10-day mean of all probe readings is not necessarily equivalent to a cloud-selected satellite mean. If contribution times cannot be recovered, this benchmark must be labelled a period comparison with a temporal-support limitation. Do not put a single-date “latest satellite estimate” label on a composite. For area-based summaries, calculate actual cell areas or reproject with an explicitly documented conservative method.

## What the quality evidence supports

The [v2.0 QAR](https://land.copernicus.eu/en/technical-library/quality-assessment-report-lake-water-quality-v2.0/@@download/file), pp. 31–32 and 75, reports optical-type-dependent inconsistencies and very high turbidity artefacts. It identifies nearshore and shallow-water areas without corresponding flags, and limited in-situ validation. These findings motivate explicit local tests; they do not establish that every newer product or Neagh scene is invalid. No Neagh-specific turbidity validation was identified in the documents inspected.

Required benchmark checks therefore include spatial artefacts, shore-distance sensitivity, shallow/bottom influence, bloom conditions, missingness, and out-of-sample agreement with comparable probes. Cross-sensor agreement alone cannot establish accuracy when methods share assumptions. No MAE, RMSE, bias or uncertainty coverage is reported for CLMS here because no locally matched CLMS dataset has been measured.

## Authentic access test

Public OData metadata and product-node lists were acquired. The newest saved NetCDF product has ID `57036110-e83d-4e6a-94b1-5a56e8d10fab`; its actual file is **1,641,461,601 bytes**. The corresponding product metadata includes package overhead. The COG catalogue provides an alternative large global bundle. Neither should be downloaded by the public website.

An unauthenticated **GET with Range: bytes=0-0** to the exact file-node `$value` URL returned **HTTP 401 Unauthorized** on 23 September 2026. The request URL and response headers are retained in the audit. An initial HEAD request returned 405 (unsupported method), so it was not used as authentication evidence. The bounded GET confirms the earlier saved 401 result. [CDSE OData documentation](https://documentation.dataspace.copernicus.eu/APIs/OData.html#product-download) describes token-authenticated downloading; [S3 access](https://documentation.dataspace.copernicus.eu/APIs/S3.html) uses generated credentials. Metadata discovery succeeding does not imply anonymous binary access. No sign-in, account creation or credentials were attempted. An authenticated backend can later extract Neagh subsets or range-read COGs; this is an access requirement, not evidence of scientific failure.

The latest saved catalogue product ends 10 September, despite the audit date being 23 September. A tracker must use the actual observation interval and publication date rather than assume delivery cadence or equate the nominal filename date with current conditions.

## EOCIS archive: inspected data, not a catalogue assumption

The [CEDA dataset record](https://catalogue.ceda.ac.uk/uuid/6e329e32570d4d4f818b8f8aa18e7a85/) describes completed, openly accessible expert-use data, with no planned updates. It warns that data have not been quality masked. Its catalogue publication in April 2025 does **not** imply observations beginning in 2025. The actual saved Neagh listing contains **1,435 distinct dates, 26 May 2016–29 December 2023**: 59/157/215/218/195/215/183/193 files respectively in 2016–2023. This is a file inventory, not a count of usable cloud-free lake observations. There is no overlap with the project's 2025–2026 high-frequency probe record.

The 14 June 2023 sample was downloaded from its CEDA listing link and checked against CEDA's MD5 (`7ca7b23a22f3e6488eb21dfae11da928`). Programmatic inspection found:

- Observation time **11:43:49 UTC**, encoded in global attributes and the numeric time coordinate.
- A **1061 × 1209** catchment grid with 100 m spacing, water-leaving reflectance at 13 bands, derived chlorophyll-a, turbidity, and four land/water indices.
- **No quality flag arrays and no water-mask array**, despite the catalogue's general description that flag sets are included. This is an observed discrepancy in this sample, not a claim about every archive file.
- A global warning that the product has not been quality controlled. Turbidity's long description identifies NTU, but `units` is `1`; the units metadata require reconciliation before automated display.
- A generic platform value listing both Sentinel-2A and Sentinel-2B, rather than an individual source scene ID. Source lineage must be recovered separately if each displayed observation is to be traceable.

The inspection JSON includes finite/non-fill counts and extrema for the **whole unmasked catchment container**. They are diagnostic checks, not Lough Neagh turbidity statistics. No map or scientifically interpreted lake summary is generated. An unmasked red/NIR anomaly would still require cloud, shore, bottom, bloom and temporal-consistency testing; a relative label does not remove those requirements.

## Reproduction and continuation

Run `python research/lough_neagh/copernicus_audit.py` with Python 3.9+, NumPy and h5py. It verifies the downloaded sample checksum and regenerates:

- `data/lough-neagh/processed/copernicus/audit.json`: source metadata, variable attributes, actual dates, access/validation state and sample diagnostics.
- `data/lough-neagh/raw/copernicus/manifest.json`: byte sizes, SHA-256 hashes and source references for saved evidence. Filesystem modification times are distinguished from unrecorded HTTP acquisition times.

Raw evidence is retained locally. The script has no network calls and does not estimate or publish turbidity. This run completed successfully; the CEDA checksum matched and the no-flags result was reproduced.

To continue the CLMS benchmark, obtain authorised CDSE access and extract one current Neagh raster with quality bands first; confirm actual spatial coverage, units and composite contribution metadata before archive acquisition. To use EOCIS quantitatively, obtain or reconstruct the absent masks and scene lineage, resolve units metadata, and find comparable historical in-situ data or reprocess overlapping contemporary scenes consistently. Both approaches still require independent local validation and a separate publication decision.
