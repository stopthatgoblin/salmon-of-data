# Historical electricity data: sourcing and decisions

Each build collects public sources, computes daily averages and publishes matching JavaScript and JSON datasets. The Mac installation schedules these builds daily. Visitors do not call upstream APIs. A daily scheduled Python job and ordinary static hosting are sufficient for deployment; Databricks is optional and is not needed to serve this tab.

## Grid series

Primary source: [EirGrid / SONI Smart Grid Dashboard](https://www.smartgriddashboard.com/ni/). EirGrid explicitly describes CSV exports and the public API in its [CleanerGrid information document](https://cms.eirgrid.ie/sites/default/files/2024-11/CleanerGrid-Extra-Information-Document-November-2024.pdf). Broader published spreadsheets are listed under [System and Renewable Data Reports](https://www.eirgrid.ie/grid/system-and-renewable-data-reports), but have not been merged into this prototype's interval-level feed.

The currently functioning chart endpoint is:

```text
https://www.smartgriddashboard.com/api/chart/?region=NI&chartType=demand&dateRange=custom&dateFrom=01-Jan-2026&dateTo=31-Jan-2026&areas=demandactual
```

Requests use `Eirgrid-Content-Request: Nextjs`. `refresh_history.py` requests at most one calendar month at a time. A full-year `dateRange=year` or large custom window returned an empty Rows array during testing. Some calendar-month queries also returned empty despite valid single-day readings, particularly 31-day wind / solar requests. Empty month responses are therefore rechecked in subwindows of at most 28 days, with every request recorded in the audit; cached empty responses from the original strategy are rechecked too. The standard `month` shortcut selected a rolling 30-day window, excluding the first day of a 31-day calendar month. The collector uses explicit calendar dates and `custom`, trims returned dates to the requested month, and caches provenance. This public website interface is not a versioned API contract and should be monitored if the upstream website changes.

| Series | chartType / areas | Field / calculation |
|---|---|---|
| Demand | demand / demandactual | SYSTEM_DEMAND |
| NI generation | generation / generationactual | GEN_EXP |
| Wind | wind / windactual | WIND_ACTUAL |
| Solar | solar / solaractual | SOLAR_ACTUAL |
| Moyle | interconnection / interconnection | INTER_MOYLE |
| North-South estimate | matched demand, generation and Moyle | demand − generation − Moyle |
| Non-renewables and other | matched generation, wind and solar | generation − wind − solar |

All are MW. Only actual fields are used. Missing values are not zero, including solar before its reporting history begins. The `INTER_NET_NI` field currently repeats Moyle and is not used as a North-South reading. Moyle and the derived North-South series remain signed: positive imports to NI, negative exports. Solar coverage is the dashboard's reporting portfolio, not all rooftop solar. Non-renewables and other includes the main power stations and any generation outside wind / solar, including other renewable sources; it is not a purely fossil-fuel category and cannot be compared directly with the smaller live balancing Other. The internal and CSV series key remains `otherNI`.

The collector probes every month back to January 2010. The resulting first / last complete dates and complete-day counts are recorded in `history-audit.json` and the website's Definitions & sources coverage table. The first result found in this one API is not proof that no earlier data exists elsewhere. Internal gaps can be substantial. A chart should not describe sparse available-day means as complete annual statistics.

## Power stations (retained archive; excluded from the Trends interface)

Primary source: [SEMO public reports](https://www.sem-o.com/market-data/static-reports). The [SEMO Data Publication Guide, Issue 3.5](https://www.sem-o.com/market-messages/release-op-updated-its-and-dpug) defines BM-086 Daily Meter Data and its units. The public index is queried for `PUB_DailyMeterDataD1`, then the latest indexed revision for each settlement date is downloaded from `https://reports.sem-o.com/documents/{ResourceName}`.

For past daily averages, published meter data is preferable to replaying a live target proxy. The `MeteredMW` XML field is **interval MWh**, despite its name: divide half-hour MWh by 0.5 hours to get average MW. The collector sums all units of a station at each interval, then requires all 48 half-hour slots in the calendar date of StartTime. It does not group by the report Date: the guide says the settlement day begins at 23:00 GMT. The initial D+1 data can be revised; this is not final settlement energy.

The current index at the initial investigation exposed D+1 meter files beginning with settlement date **1 September 2026**, rather than a continuous many-year archive. The D+5 index was checked too and had the same first settlement date, so later meter revisions do not by themselves unlock earlier years in the current index. The prototype uses D+1 consistently. Dispatch report searches also included isolated older files, which do not establish a continuous archive. Cache the extracted meter rows indefinitely and use them after the rolling index has expired. The collector retains previous cached station reports on subsequent builds. A production scheduler must preserve that cache or a durable equivalent.

The same 13 current units are used as the overview. Do not extend that mapping into earlier years without checking unit registration, commissioning and retirement: Kilroot's former coal units are not its current gas units. A long-term station backfill would need a verified archived meter source, historical registration mapping, or a separate reconstruction project with complete dispatch archives and initial states. The present dataset does not fabricate an older station history or equate missing output with zero.

## Dates and completeness

- Grid dates use the API's calendar labels; only days with all 96 distinct quarter-hour clock slots are averaged. Conflicting duplicates reject the day. Identical duplicate rows are deduplicated. Values are not interpolated.
- Meter dates use the XML StartTime labels; all units must appear at all 48 half-hour slots. Missing / ambiguous clock-change days are omitted rather than guessed. No cross-source balancing Other is derived from these meter series until the clock conventions and metering basis have been independently reconciled.
- The current day is excluded. Monthly and annual points average available complete daily values. To avoid making a few days stand in for a whole month or year, the chart requires at least **95% of elapsed days**. This is an explicit prototype display rule. An elapsed current year can qualify without pretending December has happened.
- The headline uses available daily values directly, so it is not an equally weighted average of monthly means. Dates, day counts, method and partial-period status remain available in the UI / CSV.
- CSV includes the seven displayed grid series (four generation categories, demand and two interconnectors), including values withheld from the chart for coverage. Individual station series remain in the collector archive but are omitted from the interface, coverage table and CSV. Missing means are empty. Columns include the full grouping's start / end, partial-period flag, elapsed expected days, per-series complete days, available observations and chart-eligibility flags. Inspect coverage before treating these as representative period means.

## Before publishing as a maintained service

Keep the data job independent of the frontend. Run it daily after meter publication, retain the cache, and deploy the generated static fixture only after its quality checks pass. Record build and source freshness and alert on failed / empty feeds. Periodically refetch older grid months and later meter revisions if a final-data archive is added. Preserve the required `Supported by EirGrid Group Data` attribution.

The Mac installation now refreshes this historical dataset daily at 07:10 Europe/London, with catch-up checks after waking and hourly retries on failure. No cloud service is scheduled. The website API remains an unversioned source interface, not a guaranteed archival service. See SCHEDULING.md for the active working copy, runtime health and controls.

## A route to longer Moyle history

NESO's [Historic Demand Data](https://www.neso.energy/data-portal/historic-demand-data) publishes annual CSVs, including a [2010 resource with MOYLE_FLOW](https://www.neso.energy/data-portal/historic-demand-data/historic_demand_data_2010). Its documented sign is opposite to the NI convention: positive is import **into GB**, so a NI-oriented series would negate it. It is half-hour settlement data and the historical dataset is published with a lag. This is a credible candidate for extending Moyle, and therefore the derived North-South balance, beyond the NI dashboard's currently loaded coverage. It has not been merged into this prototype: first validate the overlap, calendar / daylight-saving alignment, meter boundary and coverage, and then retain source provenance for each day. Do not silently splice it into the quarter-hour series or treat missing half hours as zero. This alternative does not supply NI station output or all NI rooftop solar.

## Chart images

The download section exports the selected chart as a self-contained SVG or a 2× PNG (2,400 × 1,420 pixels). Both include the source, daily-average basis, selected period, range-wide average and coverage. The export uses a fixed desktop-sized chart layout even on mobile, omits hover / keyboard targets and makes no external requests. Both image formats include the required EirGrid Group attribution and an Open Data Licence reference; SVG includes a clickable licence link. No image is offered for ranges with no eligible chart points.
