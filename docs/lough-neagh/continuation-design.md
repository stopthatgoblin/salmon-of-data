# Conditional continuation design — not an operational tracker

The current publication decision is **no-go**. This document records implementation choices to revisit only after the scientific blockers in the main report are resolved. No updater, scheduled task, website route or publishing workflow is active.

## Scientific restart

Resolve the reference-feed screening/QA and deployment history first. Obtain radiometric and spatial validation spanning the lake's intended application domain. Start a new immutable analysis version; do not silently replace the present negative result. Include ACOLITE dark-spectrum fitting and another suitable aquatic processor, a generic L2A comparator, published spectrally appropriate algorithms, simple local regressions and the existing CLMS product. Save all exclusions. Separate pixel contamination, atmospheric error, probe error and algorithm error where the field data permit it.

Hold out whole dates and geographic areas. Reserve final tests before tuning atmospheric settings, spatial footprints, thresholds or features. Assess interval coverage, rank/change accuracy and application-relevant absolute errors, including high-turbidity and bloom conditions. Record an explicit domain of validity and unsupported conditions. A good result at two shoreline points is insufficient for a lake-wide product.

## Geographic sectors

Start with the authoritative lake polygon, explicitly excluding islands and the Lower Bann channel. Project to UTM29N for metre-based operations. Obtain authoritative settlement/shore-access coordinates for Toome, Antrim/Rea's Wood, Ballyronan, Ardboe, Washing Bay, Maghery, Oxford Island/Kinnego and eastern-shore reference locations. These names are editorial geography, not hydrographic compartments.

A reproducible option is water-clipped Voronoi assignment to a documented set of shoreline anchor points, with a separately defined central-lake region and an inward shore exclusion. Fix and version coordinates, central-region definition, adjacency treatment and buffer only after development evidence supports them; do not pick a buffer solely to maximise a final test score. Review polygons for disconnected slivers, inappropriate river-mouth assignments, overlap and total covered area. Retain unassigned/buffered water explicitly. No such polygons have been produced or validated in this no-go edition.

Calculate statistics from all valid, area-weighted cells in each sector, never one shoreline pixel. Publish valid area/eligible area, observed median/IQR, and separately estimated predictive uncertainty. Changes between dates should use their common valid footprint or flag changed spatial support. Seasonal percentiles describe the distribution of usable satellite observations and require adequate historic/seasonal coverage; cloud sampling can bias them. Do not call an observed-subset median a whole-lake estimate when coverage is insufficient.

## Storage and presentation, conditional on a positive release decision

Keep acquisition, correction, retrieval, validation and aggregation in the research/backend pipeline. Store versioned COGs or chunked scientific rasters with value, uncertainty, quality mask, coordinates, source IDs and per-pixel/composite time support. Cache compact JSON/Parquet sector summaries separately. A web map should load only viewport/zoom tiles and lightweight metadata; never raw SAFE imagery or a global NetCDF. Preserve actual missing pixels and no-data reasons. Mobile zoom level must not imply finer resolution than the retrieval supports.

Integrate into the existing static Salmon of Data design only then. The principal page would identify the latest **observation date** or composite interval prominently, distinguish estimated NTU from DAERA in-situ measurements, and report stale/partial coverage. History would retain gaps, station identity, units and time support. Methodology would expose full held-out performance, limitations, source manifests and versions. A relative-only product would need different, explicitly validated language and scales. No synthetic visual mockup should be mistaken for observations.

## Inexpensive automated operation

An eventual updater should:

1. Discover newly available catalogue items with a bounded look-back for revisions; deduplicate acquisition/processing versions and record immutable source IDs.
2. Fetch the lake subset, validate hashes and radiometric conventions, apply pinned aquatic processing and independently tested pixel/shore/cloud/glint/bloom rules.
3. Reject unsupported platforms, baselines, geometry or optical domains; preserve reasons and raw inputs. A processing-version change triggers overlap revalidation.
4. Run the approved retrieval only inside its validated range, store uncertainty and quality separately, and leave cloud/unsupported cells empty.
5. Generate sector statistics and comparable-support changes. Flag unexpected spectra, discontinuities, spatial artefacts, insufficient coverage and implausible jumps for review. Review thresholds are operational QA, not ecological safety limits.
6. Verify provenance completeness, finite values, uncertainty coverage assumptions, spatial/temporal consistency, source freshness and schema compatibility. Archive every derived release.
7. Atomically promote a checked manifest to the static website. A failed check retains the previous release with its original date; it must not label it newly observed. Keep a rollback manifest.

Run processing in a backend job with cached intermediates and incremental scene selection. Credentials belong in server-side secrets, never client JavaScript or research manifests. Scientific approval, code tests and a concrete reviewable release should precede activation. This design is intentionally not a claim that these steps are implemented, priced or scientifically validated.
