# Gas dashboard: collectors, refresh and historical coverage

Investigated on 9 November 2026. This is an implementation proposal, not a deployment. The local dashboard still imports the fixed 8 November snapshot. No gas collector, cloud resources or schedule has been created.

## Required collection

| Feed | What to retain | What it supplies |
| --- | --- | --- |
| GNI operational API | Daily physical entry, hourly delivered quantities, daily commercial entry allocations and actual gas consumption by market sector | Moffat, Corrib/Bellanaboy, NI and ROI allocations, reported ROI total and power gas; ROI other gas is total less power |
| ENTSOG TP | Point/operator/direction-specific physical flows, their intervals, missing flags and revisions | North-South flow and direction, SNIP and the Stranraer boundary check |
| SEMO | Half-hour unit meters for both calendar dates touched by a gas day, registered units and technical offers; dispatch instructions if a provisional morning view is wanted | NI gas input estimate, gas-fired electrical output in NI and ROI, fuel/unit classification |
| EirGrid/SONI | Both regions' quarter-hour actual demand over the gas day | Electricity output as a percentage of regional demand |

The SEM PLEXOS heat-input curves and startup fuel are versioned model inputs, not another daily feed. Retain the current six-unit NI model, its gross/net conversion, plant identity and validity dates. Revisit parameters and mappings when plant changes or new model editions require it. Older fleet configurations need historical mappings rather than applying today's six units indiscriminately.

Much of the SEMO and demand fetching can share the existing electricity infrastructure. Its exported station cards alone are insufficient: the gas calculation needs the underlying unit observations, the full gas/multi-fuel roster and a gas-day window, including startup history before that window. The existing replay cache may contain a narrower unit selection than the complete report.

A daily assembler would validate the feeds, align the gas day, run the NI model, calculate residuals and shares, and produce a small dated JSON snapshot. Missing or incomplete source data must stay unavailable or explicitly provisional. A failed run should preserve the last accepted snapshot and expose its age. Keep the physical-supply/allocated-use discrepancy separate from the NI non-power residual; do not assign it to the Isle of Man.

For future capacity percentages, add date-valid technical capacity from GNI/ENTSOG or the NI technical register. No independently measured IC1/IC2 flow split has been established, so it should not be invented by dividing the combined allocation.

## Cloudflare and 7am

Yes, a daily collection can be scheduled for 07:00 Ireland time. [Cloudflare Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/) run in UTC. Schedule `0 6,7 * * *` and let the handler run only when the Europe/Dublin local hour is 7, with an idempotent date guard. This gives 06:00 UTC in summer and 07:00 UTC in winter. The existing electricity scheduler already implements that approach using Europe/London, which currently has the same clock changes.

The smallest change follows the existing electricity architecture:

1. A private Cloudflare scheduled Worker starts a Python collector in GitHub Actions.
2. The collector fetches, checks and assembles the gas snapshot, reusing the existing Python model.
3. Store source material and dated snapshot revisions durably, for example private R2 source objects and public derived snapshots. KV can hold the accepted latest pointer and history manifest.
4. Serve the dashboard and a dated/latest JSON API from Cloudflare. Replace the fixed build-time snapshot import with that feed, so collecting a new day does not require rebuilding the whole website.

This uses Cloudflare for scheduling, storage and delivery, with GitHub Actions for computation, as the electricity system already does. Running everything inside Cloudflare is also feasible but requires porting the Python parsing/model assembly to a Worker or Workflow and testing its resource use. [Worker execution limits](https://developers.cloudflare.com/workers/platform/limits/) apply; the current Python research script cannot simply be uploaded as an unchanged JavaScript Worker.

07:00 is a collection time, not a promise that all of yesterday's final data exists. The 8 November calendar-day meter report used by the preview was [published on 9 November at 15:48](https://reports.sem-o.com/documents/PUB_DailyMeterDataD1_202611091548.xml). It was unavailable at 07:00 that morning. The 8 November gas day also includes 00:00-05:00 on 9 November, requiring the following calendar day's meter report for full meter coverage. The preview currently contains 19 metered hours and five dispatch-estimated hours, assembled later on 9 November, not a reproduction of what was available at 07:00.

Recommended publication policy: refresh at 07:00 with the latest sufficiently complete reported gas data, clearly label any dispatch-based electricity and NI gas estimates as provisional, and check again after meter publication and on subsequent days. Refresh a trailing window to capture revisions. If the product must update only once a day, it can revise older dates on the next morning's run. A fully metered gas-day view will lag further than a calendar-day meter view. Actual source availability should choose the latest complete date; do not hard-code a one-day lag or assume a source publication SLA.

The existing NI backtest validates retrospective meter-based estimates. It does not establish the accuracy of an all-dispatch 07:00 estimate. Morning estimates need a separate comparison against later meters, and the dispatch feed must also be archived before its own public index rolls forward.

## 19:00 update and calendar-day option

A 19:00 Ireland-time update is feasible and would capture more electricity meter publications than a 07:00 run. A Cloudflare schedule of `0 18,19 * * *`, guarded by Europe/Dublin local hour 19 and an idempotent date key, handles summer and winter. This is a proposed schedule only; none has been created.

For example, at 19:00 on 9 November the 8 November calendar-day meter report is available. The 8 November gas day, however, runs from 8 November 05:00 to 9 November 05:00. Its first 19 hours can use that report, while its last five hours still need dispatch estimates until the 9 November calendar-day meter report is published. Thus a 19:00 update improves the latest gas-day estimate but does not remove the remaining five-hour meter gap. A view requiring complete electricity meters would use the latest older gas day for which both calendar-day reports exist. NI gas input remains a model estimate even once all electricity inputs are metered.

Midnight-to-midnight in Europe/Dublin is possible for the hourly physical supply and unit electricity/demand data, subject to full interval coverage and clock-change handling. On DST changes it is a 23- or 25-hour calendar day, not always 24 hours. At 19:00 the following day, the preceding calendar day's meter report may already be available, as it was in this worked example; source availability still needs checking.

The constraint is regional gas use. [GNI's market-sector page](https://www.gasnetworks.ie/about/data-transparency/exit-flows/gas-consumption-by-market-sector) defines its day as 05:00 to 05:00 local time. The verified hourly measures are forecast EOD and forecast throughput, while reported market-sector consumption and NI commercial allocations are daily gas-day quantities. They cannot be exactly regrouped into calendar days from those daily totals alone.

For 8 November midnight-to-midnight we would need 00:00-05:00 from the 7 November gas day plus 05:00-24:00 from the 8 November gas day. Allocating the gas-day totals between those intervals requires actual hourly consumption/allocation data not yet verified, or a clearly labelled estimation method. Pro-rating by hours would assume uniform demand and should not be presented as reported calendar-day use. Using the forecast throughput profile to distribute a later reported daily total is another possible estimate, which needs its own validation.

Recommendation for the current design: use a 19:00 refresh while retaining a consistent 05:00-05:00 gas day across all headline quantities. A calendar-day version is an option if estimated ROI gas consumption and estimated regional allocations are an acceptable tradeoff. Avoid placing calendar-day electricity and gas-day consumption in the same ratio or residual. The static preview's underlying period has therefore not been relabelled or changed in response to this feasibility question.

## Time machine

**Initial target: gas day 10 September 2026 onwards, with explicit gaps wherever full coverage is not verified.** This is a realistic candidate boundary, not a claim that the full dashboard archive has already been built or every intervening day is complete.

Evidence retained locally:

- The NI method has already been backtested for 21 complete gas days, 10-30 September 2026. The 9 September day was excluded because earlier meter history could not establish one startup category. See [the NI backtest](../electricity/research/ni_gas/BACKTEST.md).
- On 9 November the current public SEMO D+1 index's earliest data date was **10 September 2026**, published 11 September at 12:51. Yesterday's saved index started on 9 September. Thus the public index moves; retaining source reports is necessary. The earlier 9 September report is already cached locally for model startup history.
- Fresh GNI requests returned September daily consumption, commercial allocations and 24 hourly Moffat/Bellanaboy records. ENTSOG returned a dated, confirmed North-South physical-flow record for 10 September. This supports attempting a September backfill but is not a complete multi-feed coverage audit.
- GNI September Moffat hourly quantities sum to approximately 151.520 GWh versus 151.467 GWh in the separate daily series. Daily headlines should retain the daily source; hourly display checks must allow documented source precision/revisions or flag disagreement. Historical gas-day timestamps also need explicit convention checks: GNI daily labels and ENTSOG interval timestamps are not interchangeable in summer.
- [GNI's published daily demand archive](https://data.gov.ie/dataset/dailygasdemandireland/resource/0c920aa1-8cf3-4864-b279-3e7904ab35ec) starts on **1 January 2018** and is updated quarterly. [Daily supply](https://data.gov.ie/dataset/dailygassupply/resource/d3d6df1e-35a1-4360-8f2b-3c2f5f282e30) also starts in 2018. These can support an older ROI gas-only view; they do not establish complete NI unit gas estimates or hourly supply history. A fresh GNI hourly physical-flow request for 1 January 2018 returned an empty list.

Start with the September candidate boundary, enumerate every date and validate all required unit, demand and flow intervals before enabling dates in the picker. Extending the complete all-island view earlier requires additional SEMO/unit archives or another verified NI power-gas source, historical plant parameters and a wider flow audit. No fixed multi-year full-view promise is justified yet.

Archive every accepted day from launch and retain source/model/extraction metadata and revisions. A reconstruction using later meter revisions is different from an archive of the exact provisional figures visitors saw at 07:00. Keeping both is possible if editions are versioned from the start.

Raw research responses from this check are retained under `outputs/gas-feasibility/production-review/` (ignored local evidence). No credentials are included.

## Reuse and variable text

The two-thirds sentence is calculated from the selected snapshot's power gas divided by total gas use. It changes to another familiar fraction or a rounded percentage as the data changes. Corrib's share uses Corrib physical inflow divided by displayed island use, not total supply; for 8 November it is about 8.7%.

All three licence/policy URLs now come from snapshot reuse metadata. ENTSOG's attribution extraction date also comes from that metadata. A collector must record the real extraction date and applicable terms for each edition rather than substituting the selected gas day. Links are metadata, not a guarantee that an upstream provider's terms can be discovered automatically.

GNI's general open-data policy does not explicitly identify the operational API series used here. Its specific reuse coverage remains unconfirmed, as already disclosed in the preview. This question remains to be resolved before publication.
