# All-Ireland gas dashboard

The gas dashboard now has an unattended collector, versioned daily snapshots and a date archive. It uses the existing Cloudflare website and GitHub repository.

## Daily operation

1. The private Cloudflare scheduler starts collection at **19:00 Europe/Dublin**.
2. GitHub Actions fetches and validates the latest completed gas day and revises the previous six days.
3. Accepted dated editions are stored in gas KV. Old dates and editions are retained without expiry.
4. The website reads the archive API. Data refreshes do not rebuild the website.

If SEMO has not published the target calendar-day meter report, the archive explicitly reports **Waiting for SEMO meter data** and keeps the accepted day visible. Evening retries continue; a pending report also receives catch-ups at **07:00, 10:00, 13:00 and 16:00 Europe/Dublin**. Catch-ups retain the original missing gas-day target across midnight and revise its preceding six days. A successful catch-up for an older day does not suppress that evening's newer target. Missing data is never replaced with zero and the existing six-hour dispatch-estimate limit remains.

The primary view remains 05:00 to 05:00 local time. The newest electricity totals can include dispatch estimates; later meter publications upgrade earlier days. NI power gas remains modelled. Missing sources preserve the last accepted view and expose a delayed-update message.

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

The evening gas expression is `0,20,40 18-22 * * *` in UTC. The handler permits 19:00 through 22:40 Ireland time and skips after the current target succeeds. The catch-up expression is `0 6,7,9,10,12,13,15,16 * * *`, filtered to the four Ireland-time hours above across GMT/BST. Daytime invocations skip unless a missing SEMO meter report is recorded. Existing electricity expressions are retained.

## Source and archive boundaries

GNI supplies daily physical flows, allocations and ROI sector consumption. ENTSOG supplies SNIP and North-South physical flows. SEMO unit meters and dispatch reports supply electrical output, with unit heat curves/startup fuel used for NI gas input. EirGrid/SONI supplies aligned regional demand.

The initial validated archive covers 5-11 November 2026. Older first editions of 8/9 November are retained as versions. Future accepted days extend the date picker. Older backfill is possible only where every required feed and startup context passes validation.

The specific licence coverage of GNI operational API series remains unconfirmed and is disclosed in the source notes. The live page retains attribution, reuse links, model assumptions and the distinction between physical flows and commercial allocations.
