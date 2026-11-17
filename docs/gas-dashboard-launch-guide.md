# All-Ireland gas dashboard

The gas dashboard now has an unattended collector, versioned daily snapshots and a date archive. It uses the existing Cloudflare website and GitHub repository.

## Daily operation

1. The private Cloudflare scheduler starts collection at **19:00 Europe/Dublin**.
2. GitHub Actions tries the latest completed gas day and the previous six days. Each day whose core gas and electricity sources pass is published, even when a newer day is delayed.
3. Accepted dated editions are stored in gas KV. Old dates and editions are retained without expiry.
4. The website reads the archive API. Data refreshes do not rebuild the website.

If SEMO meters or GNI daily quantities are missing, the archive identifies the source wait and shows the latest accepted day. Unavailable EirGrid/SONI demand no longer prevents publication of valid gas data: only the affected regional demand totals and generation-to-demand percentages are marked unavailable. Complete quarter-hour coverage is still required before those metrics become numeric. The demand API uses `dateRange=day` with explicit endpoints; `custom` is rejected and `week` can truncate the required window.

Evening retries continue; failed or partial collections also receive catch-ups at **07:00, 10:00, 13:00 and 16:00 Europe/Dublin**. Catch-ups retain the original requested target across midnight. An accepted older day, or a day with missing demand, does not mark the requested window complete or suppress retries. Each run revisits the window so recovered source data upgrades accepted editions. Missing data never becomes zero, and the six-hour dispatch-estimate limit remains.

The manifest exposes `pending`, `pendingDays` and `incompleteDays`. The private status retains the requested `targetGasDay`; `successfulDate` advances only after all requested dates and demand metrics are complete. GitHub's run summary distinguishes a successful partial publication from complete source recovery. A run with no valid candidates fails and preserves the accepted archive. An accepted edition is retained when a candidate would lose demand coverage or require more dispatch estimates.

The primary view remains 05:00 to 05:00 local time. The newest electricity totals can include dispatch estimates; later meter publications upgrade earlier days. NI power gas remains modelled. Snapshot schema 2 permits paired `null` demand and demand-share values; the client also reads the original schema 1 archive. Core gas totals, electricity output, gas-use shares, balances and source intervals remain mandatory.

## Resources

| Component | Configuration |
| --- | --- |
| Website and gas API | `wrangler.static.jsonc`, Worker `salmon-of-data` |
| Isolated preview | `wrangler.electricity-preview.jsonc` |
| Private timer | `wrangler.electricity-scheduler.jsonc` |
| Collector | `.github/workflows/ireland-gas.yml` |
| Production gas KV | `ireland-gas-prod` |
| Preview gas KV | `ireland-gas-preview` |

The workflow reads gas namespace IDs directly from the tracked Wrangler configuration. It reuses the existing GitHub `CLOUDFLARE_ACCOUNT_ID` variable and `CLOUDFLARE_API_TOKEN` secret. The timer reuses its encrypted `GITHUB_ACTIONS_TOKEN`. No additional GitHub variables or copied credentials are required.

## Manual recovery

In GitHub **Actions → Ireland gas data → Run workflow**, select **production** on **main**. Normally leave the date empty and revision days at 7. A failed update retains the accepted archive. Fix the source or code problem, then rerun.

For local collection without credentials:

```sh
python3 -m gas.cloud --local-dir outputs/gas-live/kv --seed --export public/data/ireland-gas/latest.json
```

For local display, build then start with `GAS_LOCAL_KV_DIR` pointing to that local KV directory.

## Deployment

Reviewed changes merged to `main` use the existing Cloudflare Git build. Manual website deployment uses:

```sh
npm run build
npx wrangler deploy --config wrangler.static.jsonc
```

Scheduler changes are deployed separately:

```sh
npx wrangler deploy --config wrangler.electricity-scheduler.jsonc
```

For the schema 2 rollout, deploy the compatible website before the collector starts publishing nullable-demand snapshots. Deploy the timer separately; its cron expressions are unchanged. The existing `lastError` field also remains populated during a partial update, retaining compatibility with the prior timer while it is being replaced.

The evening gas expression is `0,20,40 18-22 * * *` in UTC. The handler permits 19:00 through 22:40 Ireland time and skips after the current target window is complete. The catch-up expression is `0 6,7,9,10,12,13,15,16 * * *`, filtered to the four Ireland-time hours above across GMT/BST. Daytime invocations run while source recovery remains pending or a collection failed. The existing 18-minute attempt throttle and electricity expressions are retained.

## Source and archive boundaries

GNI supplies daily physical flows, allocations and ROI sector consumption. ENTSOG supplies SNIP and North-South physical flows. SEMO unit meters and dispatch reports supply electrical output, with unit heat curves/startup fuel used for NI gas input. EirGrid/SONI supplies aligned regional demand.

The initial validated archive covers 5-11 November 2026. Older first editions of 8/9 November are retained as versions. Future accepted days extend the date picker. Older backfill is possible only where every required feed and startup context passes validation.

The specific licence coverage of GNI operational API series remains unconfirmed and is disclosed in the source notes. The live page retains attribution, reuse links, model assumptions and the distinction between physical flows and commercial allocations.
