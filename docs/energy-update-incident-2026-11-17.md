# Gas update investigation, 17 November 2026

Checked against production and fresh public source requests at approximately 21:25–21:30 GMT. The current blocker is the Smart Grid Dashboard demand API. SEMO has published the previously missing meter reports, and the gas scheduler is dispatching production collections.

## Production evidence

The [live gas manifest](https://salmonofdata.com/api/gas/manifest.json) returned HTTP 200 with:

- `latest`: `2026-11-11`
- `lastSuccess`: `2026-11-12T22:51:03Z`
- `lastAttempt`: `2026-11-17T21:21:30Z`
- `lastError`: `Daily update failed; retaining the last accepted data.`
- `waitingForSource`: `null`

Scheduled gas jobs ran every 20 minutes from 19:00 through 21:20. The [21:20 production run](https://github.com/stopthatgoblin/salmon-of-data/actions/runs/44178848814), on current `main` commit `c696326`, passed all 16 gas/model checks and then failed at 21:21:31 with `Gas collection failed: HTTP Error 400: Bad Request`. The retry change from 16 November is present in that commit's ancestry; the evening timer and collector invocation are working.

## SEMO meter recovery

A fresh `PUB_DailyMeterDataD1` index contained these newly published reports:

| Settlement date | Publication on 17 November | Report |
| --- | --- | --- |
| 12 November | 10:22:00 | `PUB_DailyMeterDataD1_202611171022.xml` |
| 13 November | 11:43:55 | `PUB_DailyMeterDataD1_202611171143.xml` |
| 14 November | 13:14:51 | `PUB_DailyMeterDataD1_202611171314.xml` |
| 15 November | 14:17:25 | `PUB_DailyMeterDataD1_202611171417.xml` |
| 16 November | 15:25:41 | `PUB_DailyMeterDataD1_202611171525.xml` |

The timestamps above reproduce SEMO's `PublishTime` values. A collection for gas day 16 November, using a fresh temporary response cache, downloaded and parsed these meter files successfully. It then failed while loading regional demand in `Collection.__init__`, before gas-day assembly or publication.

## Reproduced demand failure

`gas/sources.py:116` requests both regions from `https://www.smartgriddashboard.com/api/chart/` with `chartType=demand`, `areas=demandactual`, `dateRange=custom`, `dateFrom=10-Nov-2026` and `dateTo=17-Nov-2026`. Both requests, including the existing `Eirgrid-Content-Request: Nextjs` header, returned:

```text
HTTP 400
{"error":"Invalid request"}
```

Changing only the range selector to `week` made these date-range requests return HTTP 200, but with `{"Rows":[]}` for both regions. Daily requests for 16 and 17 November also returned empty demand rows. ISO dates with `dateRange=custom` still returned HTTP 400.

The public NI and ROI demand pages currently request `chartType=demand`, `dateRange=day`, `areas=demandactual,demandforecast` and `17-Nov-2026` for both dates. Matching those parameters and the site's fetch header also returned HTTP 200 with empty rows in both regions. The homepage's default chart returned wind and solar rows, so the entire chart service was not unavailable.

These comparisons establish that our custom-range requests are currently rejected and that the tested formats used by the source site do not currently supply demand data either. A change in upstream request validation is an inference; its deployment time and the reason for empty demand responses have not been established.

The [21:17 electricity production run](https://github.com/stopthatgoblin/salmon-of-data/actions/runs/44178208335) independently failed in both NI and ROI grid downloads with HTTP 400. This is consistent with the shared request-format dependency.

## Consequence and recovery

Gas publication requires complete quarter-hour demand for both regions to calculate the gas-fired generation shares. The failed source request stops collection, and publication retains the accepted archive through 11 November. The public API is serving that archive with a current failure timestamp.

Recovery requires a supported demand request that returns complete actual readings, followed by a successful collection and seven-day revision run. Merely replacing `custom` with `day` or `week` has not been demonstrated to recover the data. Keep coverage validation and last-good publication behavior intact. If source recovery takes the missing dates outside the rolling revision window, explicitly backfill those dates.

No collector, scheduler, deployment or production data was changed during this investigation. Diagnostic source files were written only under `/tmp`.

## Fix feasibility evaluation

Additional live checks at approximately 21:39–21:47 GMT establish two independent source gaps and a feasible partial-restoration path.

### Demand service and request compatibility

Both regions' public `DashboardService.svc/data?area=demandActual` endpoints returned HTTP 503, `Service Unavailable`. The official demand pages link to `DashboardService.svc/csv?area=demandActual`; those exports returned HTTP 503 too. This strengthens the evidence of a provider-side service failure behind the empty demand responses from `/api/chart/`.

The working NI wind series provides a useful request-format control. For the same 10–17 November date parameters, `dateRange=day` returned all 768 quarter-hours across eight calendar days. `week` returned 672 quarter-hours ending on 16 November, and `custom` returned HTTP 400. Therefore a blind change to `week` risks dropping the final calendar day needed by a gas-day window. `day` is accepted and preserves that explicit window on the tested working series, although demand recovery still needs verification when its backend returns data.

The [current EirGrid quarter-hourly workbook](https://cms.eirgrid.ie/sites/default/files/publications/System-Data-Qtr-Hourly-2026-V9.xlsx), last modified on 1 October, contains one `System Data` sheet with 26,205 rows. Its actual date range is 1 January through 30 September 2026; the final timestamp is in `A26205`. It cannot supply the missing November observations. No working equivalent current-demand replacement was established in the tested official API, export and workbook paths.

### Additional GNI publication gap

Fresh daily requests with `date=2026-11-17` returned physical flows, sector consumption and commercial allocations through **14 November**, with no 15 or 16 November values. With demand explicitly left empty in a local diagnostic, assembling 16 November failed on `Missing/invalid GNI daily value`. The three source URLs were:

- [Daily physical flows](https://www.gasnetworks.ie/api/v1/physicalflows?date=2026-11-17&frequency=daily)
- [Daily sector consumption](https://www.gasnetworks.ie/api/v1/gasconsumption?date=2026-11-17&frequency=daily)
- [Daily commercial allocations](https://www.gasnetworks.ie/api/v1/commercialentrypoint?date=2026-11-17&frequency=daily)

This GNI gap was hidden by the earlier demand failure. It prevents an otherwise unchanged collector from publishing its current 16 November target even if demand becomes available.

### Verified core calculations for 14 November

A local diagnostic reused fresh SEMO source captures, left demand mappings empty, and ran the existing assembler for 14 November. It completed NI heat-input/startup modelling, ROI unit output, GNI flows/allocations/consumption and ENTSOG interval checks, then stopped at the expected demand-coverage guard. No fabricated demand, modified publication rules or production writes were used.

| Quantity | GWh |
| --- | ---: |
| Moffat physical inflow | 199.914444 |
| Bellanaboy physical inflow | 19.621505 |
| NI commercial allocation | 49.491578 |
| ROI reported total use | 160.677515 |
| NI modelled power gas | 22.164814 |
| ROI reported power gas | 98.096946 |

Both gas residuals are non-negative. All 24 hourly timestamps match the gas-day window exactly. Moffat's hourly sum matches its daily value; Bellanaboy differs by only 0.000002 GWh. Electricity uses a fully metered day with zero dispatch-estimate hours. This is evidence for a partial-restoration design, not a published or fully validated production snapshot.

### Feasible implementation and limits

A software change can allow the dashboard to advance beyond 11 November while preserving source meaning:

1. Use an accepted request range, verify all required timestamps, and report demand-service failure explicitly.
2. Permit unavailable `demand` and `demandShare` together while continuing to require valid gas quantities, electricity output and gas-use shares. Mark only the affected demand figures unavailable; retain the existing data on other cards.
3. Try completed days within a bounded window and publish days whose core sources pass. Keep the intended newest target pending, so accepting an older or incomplete-demand day never disables retries for newer data or demand revisions.
4. Update Python validation, the TypeScript snapshot type, client validation, regional cards and calculation details to handle the explicit unavailable state. Revisit accepted days to add demand readings when service recovers.

This is a contained collector-and-client change, not a one-parameter repair. Regression checks should cover null demand versus zero, rejection of incomplete core sources, archive retention, and retries after accepting an older day. A full 16 November snapshot with all existing metrics still depends on GNI publishing the newer days and the demand service returning complete actual readings, or on a separately verified equivalent source. No recovery ETA has been established.

The evaluation changed only these investigation notes. All prototypes and downloaded source files remain temporary; production behavior is unchanged.
