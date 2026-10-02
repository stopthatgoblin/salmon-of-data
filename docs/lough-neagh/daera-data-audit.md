# DAERA observations: acquisition and fitness for satellite validation

Audit date: 23 September 2026. This is an audit of downloaded records, not a claim that DAERA has validated them. The archived normalized snapshot contains **57,904 turbidity records and 65,413 phycocyanin fluorescence records**. All records, including nulls and duplicates, are preserved.

## What was acquired

The public [DAERA master ArcGIS service](https://services-eu1.arcgis.com/kswen6BYexuc1SUk/arcgis/rest/services/DAERA_Probes_and_Metrics_Master_Layers_View/FeatureServer) provides station features in layer 0 and observations in table 1. It is queryable without credentials. The acquisition script first captures all object IDs by metric, downloads bounded ID windows, verifies exact ID equality, rejects truncation, then writes a deterministic compressed CSV. A live source update was detected during the initial download; a refreshed snapshot passed the checks. Counts below therefore differ from earlier exploratory queries.

Files:

- `research/lough_neagh/daera/fetch.py`: reproducible acquisition and audit; standard library plus curl.
- `data/lough-neagh/raw/daera/observations.csv.gz`: 123,317 records; uncompressed SHA-256 `4e04da8425f95934b9e46f79432e37ebc7ef759decc4085025e03beae14a4f4b`.
- `data/lough-neagh/raw/daera/audit.json`: exact statistics and gap examples.
- `data/lough-neagh/raw/daera/manifest-4e04da8425f9.json`: request URLs, retrieval times, raw-response hashes and files underlying this snapshot.
- `data/lough-neagh/raw/daera/stations.json`: original attributes and WGS84 geometries.
- `research/lough_neagh/daera/context.py` and `data/lough-neagh/raw/daera/context/`: station-specific views, official guidance and older-archive discovery with hashed source responses.

CSV fields are `OBJECTID`, `Probe_Ref_No`, `Location`, `Metric_Value`, `Metric_Unit`, `Metric_Type`, `Date`, `timestamp_utc`, `GlobalID`, `source_quality_status`. `Date` retains source epoch milliseconds. `timestamp_utc` is its ISO-8601 conversion; the service explicitly specifies UTC with no daylight-saving adjustment. This metadata does **not** independently verify the original logger clock. Do not reinterpret these epochs as local British Summer Time.

## Stations and actual observation periods

The periods are calculated from observations, not release dates or commissioning fields.

| Station | Coordinates (latitude, longitude) | Model | First turbidity record (UTC) | Last turbidity record (UTC) | Turbidity rows |
|---|---|---|---|---|---:|
| L1278 Rea's Wood, Antrim | 54.712602, −6.241997 | AquaTROLL 600 | 2025-01-06 12:01 | 2026-09-16 20:00 | 27,036 |
| L1279 Washing Bay | 54.523188, −6.569770 | AquaTROLL 800 | 2025-07-03 07:44 | 2026-09-16 20:00 | 14,312 |
| L1284 Toome | 54.753549, −6.466697 | AquaTROLL 800 | 2025-07-10 09:16 | 2026-09-16 18:00 | 16,556 |

The service lists commissioning dates in January/February 2026, later than these actual records. Those fields must not be used to discard all 2025 data or assumed to describe each deployment. The station-specific descriptions also repeat Rea's Wood wording for Washing Bay and Toome; use station attributes/geometry and seek deployment history rather than treating copied prose as precise location evidence.

The [official dashboard FAQ](https://www.daera-ni.gov.uk/articles/lough-neagh-water-quality-dashboard-faq) describes observations approximately 50 cm below the surface, 30-minute buoy updates and a seven-day publication delay. It describes monthly maintenance, non-validated data for indicative trends, and removal of identified faults. These are three lake/outlet points, not a representative sample of the entire water body. The six inflowing-river probes provide temperature and oxygen, not turbidity. Missing intervals must remain missing.

The station [ArcGIS metadata](https://www.arcgis.com/sharing/rest/content/items/f4ab731e16e844609717ff1e50e94cfa?f=json) specify turbidity in NTU, nominal range 0–4,000 NTU and accuracy ±2% or ±0.5 NTU, whichever is greater; maintenance every four to six weeks. Treat this as published instrument specification, not total field uncertainty or proof of successful calibration. RFU has no supplied measurement-error range. Nominal NTU values are not automatically interchangeable with satellite algorithms calibrated in FNU; optical wavelength, geometry and calibration method must be confirmed.

## Critical screening and data-quality findings

**The public observations are an already-filtered view.** [Table metadata](https://services-eu1.arcgis.com/kswen6BYexuc1SUk/arcgis/rest/services/DAERA_Probes_and_Metrics_Master_Layers_View/FeatureServer/1?f=json) declare:

```sql
(threshold_exceeded = 'N') AND (Published = 'Y') AND (reviewed = 'Y')
```

The three downloadable station views have the same screening, plus location restrictions. They do not expose the threshold, review or publication flags as observation fields. `reviewed = 'Y'` does not override DAERA's explicit non-validated status. There is no row-level calibration, fouling, deployment or uncertainty field.

All three maximum turbidity values fall immediately below 40 NTU: 39.9548, 39.9842 and 39.9960. Together with the view predicate, this strongly suggests upper-range selection around 40 NTU, but **the exact threshold rule and reasons for removing records are not disclosed**. It is not evidence that actual Lough turbidity never exceeds 40 NTU. Missingness cannot be assumed random, and a fitted model cannot be validated for extremes using this view alone.

| Turbidity quality finding | Rea's Wood | Washing Bay | Toome |
|---|---:|---:|---:|
| Null values | 62 | 9 | 0 |
| Extra rows at duplicate timestamps | 33 | 10 | 7 |
| Timestamps with conflicting values | 28 | 8 | 2 |
| Exact-zero values | 5,650 | 1,938 | 3,614 |
| Longest continuous zero run, first to last (hours) | 255.5 | 52 | 119 |
| Gaps longer than 30 minutes | 992 | 1,570 | 2,274 |
| Longest gap (hours) | 384 | 1,202 | 245 |
| Median NTU among available non-null records | 1.38 | 6.25 | 4.00 |

These medians are descriptive statistics of the screened snapshot, not lake-wide or unbiased seasonal means. Median sampling interval is 30 minutes at every station. Many 60-minute intervals and longer gaps occur. In Washing Bay, turbidity is absent from 30 September to 20 November 2025 while fluorescence has much better coverage. RFU is therefore useful contextual information but cannot be substituted for missing NTU. The audit retains zeros: repeated zeros could reflect instrument floor handling, fouling, removed/calibrated offsets or real low signal, and are **not established to be valid clear-water observations**.

## Consequences for matchups

1. Preserve every source row and its ID; handle duplicate timestamps explicitly. Identical duplicates may be collapsed with all provenance IDs retained. Conflicting values require review or exclusion from calibration until their origin is explained.
2. Flag zero runs and periods around suspected maintenance. Do not silently change zero to a positive value for log regression or treat repeated zeros as 10 days of independent clear-water truth.
3. Keep near-satellite time variability and the number of available observations. A 30-minute sampling cadence supports close matching, but it does not justify a ±3-hour window in rapidly changing water. Determine sensitivity empirically without using test scenes to tune exclusions.
4. Approximately 0.5 m probe depth is much closer to optical sensing than a deep sample, yet the satellite sees a wavelength-dependent upper layer and surface scum can differ sharply from a subsurface probe. Spatial offsets to obtain clean pixels must be tested, not assumed representative of the probe.
5. Three stations and repeated times do not equal spatially independent lake-wide validation. Split whole overpasses/dates, test station transfer, and do not count neighbouring pixels as independent in-situ samples.
6. Provisional reference data and hidden source screening prevent an unconditional public NTU product even if a regression has a high apparent fit. A model restricted to an independently checked subset may still be research-useful; deployment needs validation, not just label availability.

## Older and complementary sources investigated

The public DAERA organisation catalogue exposes [River Water Quality Monitoring 1990 to 2024 — All Parameters](https://services-eu1.arcgis.com/kswen6BYexuc1SUk/arcgis/rest/services/River_Water_Quality_Monitoring_1990_to_2024_All_Parameters/FeatureServer/0). Its actual schema and a 1995 observation were acquired, rather than relying on the dataset publication date. It contains date, time, depth, station identity, chemical measurements and qualifier fields, including suspended solids in mg/L; it has **no turbidity NTU field**. This archive is useful for catchment context, but suspended solids and NTU are not interchangeable. The full chemical archive was not downloaded because it cannot add NTU labels.

The official [Freshwater Monitoring and Assessment page](https://www.daera-ni.gov.uk/articles/freshwater-monitoring-and-assessment) identifies a nine-site Lough Neagh programme collecting chemistry, phytoplankton and in-situ observations. Its existence does not establish that a complete historical NTU series is publicly available. The [2026 inter-agency protocol](https://www.daera-ni.gov.uk/sites/default/files/2026-04/Appendix%203.PDF) also lists AFBI's mid-lough continuous buoy and biweekly White Horse Flats long-term chemistry/phytoplankton/Secchi monitoring. These are promising independent offshore and long-term sources; their availability, turbidity content and QA need confirmation. Neither Secchi depth nor chlorophyll should be converted into invented turbidity labels.

The targeted official/catalogue searches did not identify a downloadable older lake-wide NTU dataset. This is a discovery limitation, not proof that DAERA/AFBI hold no such data.

## Information needed from the data provider

A technically useful request would seek the complete turbidity series including excluded records and flags; threshold rules; review/calibration/fouling/deployment logs; duplicate-resolution policy; logger timezone and any timestamp changes; station movement and exact depth history; turbidity sensor optical standard and calibration reference; and coincident offshore/boat/laboratory observations. Confirm whether data before the recorded 2026 commissioning dates use these same coordinates and sensors. No email was sent as part of this audit.

## Reproduction

```sh
python3 research/lough_neagh/daera/fetch.py
python3 research/lough_neagh/daera/context.py
```

The default reuses hash-verified cached responses. Add `--refresh` to acquire a new snapshot; this requires internet access. Source observations can be revised and old content-addressed raw responses should be retained. Refreshes must trigger revalidation and provenance changes, not quietly overwrite a published model's reference data.
