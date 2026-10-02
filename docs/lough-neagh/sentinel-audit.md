# Sentinel inputs, actual archive coverage and radiometry

Source audit: 23–24 September 2026. All numerical inventories below refer to saved catalogue responses, not presumed global coverage.

## Mission and native information

The [official mission description](https://sentiwiki.copernicus.eu/web/s2-mission) specifies a nominal 10-day single-satellite repeat and five-day two-satellite constellation repeat. Overlapping swaths improve opportunities at this latitude, but clouds determine useful water observations. S2A launched in 2015, S2B in 2017 and S2C in 2024. B/C form the nominal operational pair; A's extension adds opportunities. Do not assume every historical period has the same sampling frequency.

| MSI band(s) | Native resolution | Relevant purpose |
|---|---:|---|
| B2, B3, B4 | 10 m | Blue/green/red reflectance; water colour, red sensitivity and ratios |
| B8 | 10 m | Broad NIR; research predictor, bloom/land interference |
| B5, B6, B7 | 20 m | Red edge; diagnostic water-type/algal information and published retrieval candidates |
| B8A | 20 m | Narrow NIR; distinct response from B8 |
| B11, B12 | 20 m | SWIR; screening and aquatic/glint correction inputs |
| B1, B9, B10 | 60 m | Atmospheric/aerosol/water-vapour/cirrus information; B10 absent from L2A |

Native resolutions and platform-specific spectral responses are described in the mission documentation. Upsampling a 20 m red-edge band cannot create independent 10 m information. A/B/C identifiers and processing baselines remain in every analysis row. This audit retains results stratified by platform; it does not infer interchangeable aquatic accuracy or fit unjustified platform corrections.

[Official product documentation](https://sentiwiki.copernicus.eu/web/s2-products) describes L1C as the input to L2A surface-reflectance processing, including SCL, AOT and water-vapour outputs. It now reports Collection 1 reprocessing back to the 2015 mission start. The initially released L2A archive was more limited. Our mirror's earliest returned item in November 2016 therefore does not define the mission's earliest available imagery. L1C plus an aquatic processor remains the appropriate route to test aquatic correction; applying that correction again to L2A would be incorrect. [Processing documentation](https://sentiwiki.copernicus.eu/web/s2-processing) identifies Sen2Cor and evolving baseline/mask behaviour.

## Downloaded catalogues and windows

The public [Earth Search API](https://element84.com/earth-search) and [provider documentation](https://github.com/Element84/earth-search) allow STAC discovery and small HTTP range reads from COG assets without user credentials. The acquisition script follows every `next` link, checks for pagination loops and archives compressed responses with exact URLs, timestamps and checksums. It preserves original item assets and SAFE identifiers.

AOI search envelope: longitude −6.72 to −6.18, latitude 54.43 to 54.80. Returned tiles are MGRS **29UPA**; metric calculations use **EPSG:32629**. The envelope is for discovery, not a lake mask.

| Inventory | Requested period | Items | Acquisition dates | Interpretation |
|---|---|---:|---:|---|
| Legacy `sentinel-2-l2a` | 2015-06-23–2026-09-23 | 1,871 | 1,331 | Earliest returned 2016-11-09; mirror inventory only |
| `sentinel-2-c1-l2a` | 2025-01-06–2026-09-16 | 355 | 295 | Concurrent with public probe era |
| C1 after same-acquisition processing deduplication | Same period | 345 | 295 | Every selected scene sampled at all three coordinates |

Deduplication keys are spacecraft, product sensing time, relative orbit and tile. Prefer the highest processing baseline, then latest generation time, then stable item ID. Different spacecraft on one date are retained but grouped together in validation. Collection gaps and catalogue updates can occur; use official CDSE as a completeness cross-check before any archive publication.

SCL windows are 51 × 51 native 20 m cells. Spectral windows are retained only when the 3 × 3 central SCL cells are all water and no SCL cloud/shadow/snow classes occur in a surrounding 13 × 13 square. This provides 68 initial Rea's Wood and 79 Washing Bay scene–station candidates; Toome has none. These counts precede temporal/reference/homogeneity checks and do not measure whole-lake coverage. A tile cloud percentage is retained as metadata, not used as a lake usability threshold.

The final analysis uses the exact same 60 × 60 m footprint for each band: nine 20 m cells or 36 native 10 m cells. Independent floor-based centring of the 10 m and 20 m arrays would produce different footprints; affine-coordinate checks prevent that error. Source pixel arrays and metadata are checksum-verified. The SCL rule remains an exploratory screen: it can miss haze/glint and exclude genuinely very turbid or blooming water. Production would need independently assessed masks and spectral/visual QA.

## A consequential scale/offset conflict, detected and corrected

Legacy COGs advertise a reflectance scale of 0.0001 and offset −0.1 while some already have the offset removed from their digital numbers. Our 11 September 2025 example would yield strongly negative water reflectances if that offset were applied twice. The [provider discussion](https://github.com/Element84/earth-search/discussions/26), [issue 66](https://github.com/Element84/earth-search/issues/66) and [issue 71](https://github.com/Element84/earth-search/issues/71) document related offset/metadata/clipping problems. Plausibility alone is not a safe correction rule.

We acquired the alternate C1 collection and compared **1,470 paired band/station windows from 103 identical SAFE products**, requiring identical spatial transforms. Across **141,626 non-clamped comparable pixels**, C1 minus legacy digital number was always **1,000**. Thus `C1_DN × 0.0001 − 0.1` agrees with the already-adjusted legacy signal in these checked pixels. C1 also preserves low/negative reflectance values that the older conversion may clip. We retained these as flags; no negative spectrum was clamped to look plausible.

All model inputs now use C1's explicit asset scale/offset; legacy reflectance is quarantined. The radiometry audit fails if there are no comparisons, a checksum mismatch or any unexpected unclamped difference. This resolves the tested encoding issue; it does **not** establish aquatic atmospheric accuracy, future metadata correctness or platform invariance. The [full audit](../../data/lough-neagh/derived/radiometry-audit.json) records every comparison.

## Boundaries and provenance

The [DAERA Lake Water Bodies 2016 service](https://services-eu1.arcgis.com/kswen6BYexuc1SUk/arcgis/rest/services/Lake_Water_Bodies_2016/FeatureServer/0) supplies the polygon identified as `UKGBNI3NB0032`. An [EEA WFD boundary](https://water.discomap.eea.europa.eu/arcgis/rest/services/WISE_WFD/WFD2016_SurfaceWaterBody_WM/MapServer/4) independently reproduces the station distances to within millimetres numerically; that agreement reflects their shared source lineage, not independent ground surveying. The boundary is historical, and actual waterline/positional uncertainty remains. Exact geometries, query URLs and hashes are retained.

Every retained matchup records acquisition time, platform, SAFE product, processing baseline, station identity/coordinates, original probe IDs, quality reasons, scaled band statistics and source collection. Cache reuse checks extraction version, coordinates, properties, assets and array hashes. Frozen-input restoration is checksum-verified; a different existing file causes refusal rather than silent replacement.
