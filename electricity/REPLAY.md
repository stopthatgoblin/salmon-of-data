# Electricity time machine

The NI and ROI Overview tabs share the compact Time machine control. Historical
mode replaces regional readings, mapped unit outputs, available capacity and the
station drawer together. Live polling continues in the background; Return to live
restores the newest accepted snapshot.

## Available history

The initial archive contains NI readings from **1 September 2026** and ROI
readings from **9 September 2026**. A selectable timestamp requires all regional
inputs and numeric outputs for every mapped unit (13 NI units; 33 ROI units).
Missing dates or quarters are omitted. The initial source scan found no complete
27 October day, and the latest meter reports can lag by several days.

Regional inputs are 15-minute observations. Historical station output is the
containing half-hour's SEMO metered energy multiplied by two, labelled **avg.**.
Recent locally captured snapshots are labelled **est.** until a later meter
report replaces them. Missing historical capacity is shown as unarchived rather
than borrowing today's availability. Forecasts and current dispatch provenance
are cleared in historical mode. Times use Europe/Dublin, including distinct
offsets for the repeated autumn clock-change hour.

NI's additional early coverage comes from its retained meter cache. ROI has no
equivalent earlier complete cache. Public exports contain selected numeric
readings and unit mappings; downloaded XML, report caches and private collector
state remain under ignored runtime/output directories.

## Local review

Use Node 24 and Python 3.11 or newer:

```sh
npm run build
npm run start:live
```

Set `ELECTRICITY_PYTHON` if the Python executable has a nonstandard location.
The live server collects locally every 15 minutes, journals complete accepted
snapshots and updates its local replay API. A daily meter backfill runs after
07:00 Europe/London, with hourly retries after failure. Keep this process running
to accumulate local history. Source errors preserve accepted data.

The full initial source scan is `python -m electricity.replay`. Use
`--retained-root PATH` to include an existing NI history cache, or `--offline`
to rebuild from already downloaded reports. Generated public files live in
`public/data/electricity-replay`; collection evidence is in
`outputs/electricity-replay/audit.json`.

## Production release

The prepared Electricity data workflow seeds the checked-in archive on a push
that matches its electricity paths. On its daily history runs it retrieves the
last seven UTC days and merges new complete readings into the existing archive.
Older published days are retained. This uses the existing Cloudflare account,
namespace and token settings; ROI must be enabled as for the existing collector.

`python -m electricity.replay_cloud --seed` prepares the initial public KV
archive, with a 160-write ceiling. A normal daily
`python -m electricity.replay_cloud` has a 16-write ceiling and typically writes
two new day files plus two manifests. Identical content causes no writes.
All immutable day files are staged before either manifest advances; source
failure, invalid readings or an exceeded write budget retain accepted manifests.
Use `--local-dir PATH` to exercise publication against filesystem KV without
contacting Cloudflare.

The Worker exposes only `/api/electricity/replay/{ni|roi}/manifest.json` and
version-pinned public day URLs. Manifests have short edge caching; immutable days
have one-day edge caching. Static bundled history remains a fallback. Production
history expands daily after meter data arrives; this does not add a Cloudflare
write for every 15-minute reading.

## Generator and connector metadata

ROI now maps 17 stations, adding North Wall TEG, Shannonbridge TEG, Ringsend
Flexgen and Corduff Flexgen to the prior 13. Their estimates enter the mapped
station total, reducing the residual by the same amount. Reported EirGrid
generation remains unchanged in source data; only the Generated in ROI headline
includes the signed reconciliation. Other/Unallocated already includes that
residual, so it is not added twice.

`electricity/asset-status.json` contains sourced programme/return expectations
checked on 8 November 2026. Return notes are specific to the affected units and
appear only after publication, during the relevant event window. An expired
estimate does not prove the asset returned; refresh the metadata from its linked
operator notice when a new expectation is published. Zero output alone does not
create an outage note. Celtic is a planned 700 MW connector, expected Q4 2028,
drawn schematically from Claycastle and excluded from operating import totals.
