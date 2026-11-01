# Northern Ireland electricity: operation and publication

The native `/dashboards/ni-electricity/` route includes the overview map, 13 station units, historical explorer, seven public grid series and CSV / PNG / SVG downloads. The Irish Sea label stays visible on desktop and mobile.

## Architecture

- GitHub Actions runs the original Python collectors. Their calculation files were copied unchanged into `electricity/dashboard/` and `electricity/research/dispatch_proxy/`.
- Overview: `2,17,32,47 * * * *` in UTC. History: **07:00 Europe/London**, including British Summer Time, with hourly catch-up opportunities from 08:05 to 12:05 if needed. A successful daily run suppresses catch-ups. Schedules can be delayed or missed.
- `electricity/cloud.py` restores compressed source state from KV, runs the original code, validates the result and publishes complete data before advancing pointers. It rejects backwards grid times, broken balances, partial days and loss of previously accepted historical readings, including archived station history.
- Each dataset retains three state slots and three public versions. Raw dispatch XML is limited to 14 days; accepted historical caches are retained. Archives above 20 MiB fail safely for review. Readers retain an older valid version during KV propagation; a collector refuses to resume from an older archive while its newest state is unavailable.
- Normal publication takes four KV writes and, after the third version, one delete. The usual 96 overview runs plus one successful history run use **388 writes and about 97 deletes/day**. Failed runs use at most two health writes; bounded retries and morning catch-ups leave room within the standard Free quotas. Other apps share account allowances.
- The existing `salmon-of-data` Worker exposes only manifest, snapshot and history GET/HEAD reads at `/api/electricity/`. Private source archives have no public route. Static site assets use Cloudflare's asset service directly.
- The overview is optionally enriched with official current-day demand, wind and solar forecasts. Demand combines available actuals and the remaining forecast, allowing only a short publication boundary between them. Wind/solar takes the maximum of matching forecast sums across all 96 quarter-hours, rather than adding separate peaks. Forecast outages retain same-day accepted peaks or show unavailable; they do not block valid actual readings. Yesterday’s peaks are never labelled as today’s.
- The browser polls the manifest every minute while visible, and on focus/return. It downloads changed versions, keeps chart selections and open station details, shows delayed readings and respects reduced-motion preferences. Failed requests leave the displayed data intact.
- Bundled accepted JSON provides an explicitly dated fallback during API outages and for a plain local preview. `edition.json` describes these fallback files; `automaticUpdates: false` describes the files themselves, not the live service.

The original signed flows, aligned actual readings, station dispatch-target estimates, complete-day rules, missing-data gaps, 95% monthly/annual coverage threshold, day-weighted headline and source attribution remain. Station dispatch estimates differ from metered output. Moyle's 250 MW assumption and North–South's 300 MW reference remain collector assumptions, not live capacity feeds.

## Account setup and preview

[The owner setup guide](setup-guide.md) records the verified settings. No separate Node dashboard selector is required: Cloudflare reads `.node-version` (`24.19.0`). GitHub permits all actions, including the pinned official checkout and Python actions. The collector token remains a GitHub secret.

The separate preview Worker is [salmon-electricity-preview](https://salmon-electricity-preview.peterdonaghy.workers.dev/dashboards/ni-electricity/), bound only to `ni-electricity-preview`. Production uses `ni-electricity-prod`. Both namespace IDs were checked against the hosting account. Source-state seeding and fresh collections restored from preview KV succeeded on 1 November 2026.

The preview manifest explicitly reports preview mode. Its collectors run on demand; production schedules run from `main`. The optional `preview_watch` workflow-dispatch input performs seven further overview collections at 15-minute intervals after the initial collection, giving eight collections across a two-hour review window. It is restricted to preview, stops automatically and uses the same collector and GitHub secret as production. An upstream failure retains accepted readings and later intervals retry. This temporary test is not a permanent preview schedule.

Initial browser checks show a neutral connecting state, and a single transient status failure does not announce an outage. Requests support browsers without `AbortSignal.any`/`timeout`. Overview → Data freshness & connection shows connection-check and collection times, an HTTP/network failure reason where available, and a manual retry button. Definitions & sources contains durable methodology, source links and series start dates; it excludes live summary metrics, current coverage counts, end dates, collection status and fault reporting. Announced versions that have not loaded yet are identified separately from service connectivity.

Production is published at [salmonofdata.com](https://salmonofdata.com/dashboards/ni-electricity/), with the workflow on `main` activating the collection schedules. Pushes that change `electricity/**` or the workflow run both collectors: `main` writes to production and `codex/ni-electricity` writes to preview. Other site edits do not trigger collection. Each namespace has its own concurrency group, so a temporary preview watch cannot block production. Publication and production collection were authorised on 1 November 2026. Production refreshes use the separate production namespace.

## Local review

Use Node 24 and Python 3.11 (the adapter and original collectors use only Python's standard library). Python 3.11 preserves the local collector's floating-point summation behaviour; Python 3.12 can differ by 0.0001 MW in rounded internal station history:

```sh
npm run check
python3 -m unittest discover -s electricity/dashboard -p 'test_*.py'
python3 -m unittest discover -s electricity -p 'test_*.py'
npm run build
node scripts/check-site.mjs
npm start
```

[Local dashboard](http://127.0.0.1:3100/dashboards/ni-electricity/). The build is independent of the original project and Mac working copy. A plain `npm start` uses the bundled fallback.

For a separate local live-API store, seed once from an accepted copy containing `dashboard/` and `research/`, then refresh and start the preview:

```sh
python3 electricity/cloud.py seed --source "/path/to/accepted-copy" --local-dir outputs/ni-electricity/kv-preview
python3 electricity/cloud.py snapshot --force --local-dir outputs/ni-electricity/kv-preview
python3 electricity/cloud.py history --force --local-dir outputs/ni-electricity/kv-preview
ELECTRICITY_LOCAL_KV_DIR=outputs/ni-electricity/kv-preview npm start
```

To review the hosted preview's actual updates on localhost instead, use:

```sh
ELECTRICITY_PREVIEW_API=https://salmon-electricity-preview.peterdonaghy.workers.dev npm start
```

The current localhost preview uses this opt-in public API mirror. A standalone local store only changes when its collector runs. The existing Mac LaunchAgents were not changed.

Map context includes Ireland, Scotland, England, Wales and the Isle of Man from Natural Earth in the original shared projection. Overview, unit details, chart labels/tooltips and image exports display whole MW and calculated whole percentages. Calculations, source JSON and CSV retain precision.

## Manual cloud refresh and failures

After publication:

1. Open [repository Actions](https://github.com/stopthatgoblin/salmon-of-data/actions).
2. Select **NI electricity data → Run workflow**.
3. Use branch **main**, choose **snapshot**, **history**, or **both**.
4. Select **preview** for a test or **production** for the public service, then **Run workflow**.
5. Open the run and confirm both collection steps succeeded. Inspect the observation date on the dashboard; successful collection does not guarantee the upstream feed has published newer observations.
6. Check [the production manifest](https://salmonofdata.com/api/electricity/manifest.json) for each dataset's `ok`, `lastSuccess`, `lastAttempt`, source `time` and version.

Enable GitHub workflow-failure notifications in your personal notification settings. Public-repository schedules are disabled after 60 days without repository activity; successful scheduled jobs alone do not keep them enabled. Check the Actions page periodically and re-enable if needed. A separate external stale-data alert has not been configured; the dashboard labels stale readings and retained failures.

Keep Workers on **Free** for a $0 platform-spend limit for this design: daily allowance exhaustion makes operations fail instead of buying overages. No Workers Paid upgrade or R2 is used. Traffic can exhaust free reads/requests; this is an availability limit. Do not enable paid products as an automatic response. [Cloudflare limits and costs](cloudflare-options.md).

## Rollback and recovery

A code rollback in Cloudflare does not delete KV history. Revert the site commit or choose the previous Worker version in Cloudflare. A failed collector leaves accepted data/state pointers intact and marks health as failed. Run the affected dataset manually after the source recovers.

Each dataset keeps three accepted versions, with a checksum tying every archive to its pointer. Do not delete the private state to fix a failed fetch: a cold historical rebuild is deliberately refused. Keep the original Mac copy as an independent recovery source. Seeding refuses to replace an already initialized dataset; recovery of a damaged namespace requires reviewing and restoring an accepted archive first.

## Verification

The full TypeScript/JavaScript suite and Python rule/publication tests pass. The production build, exported routes/assets and Wrangler deployment dry runs pass. Both collectors completed fresh network runs locally and from restored Cloudflare preview state, with zero history source-request failures. Unit checks cover signed balances, backwards updates, historical retention, DST scheduling, failure retention, bounded versions, unsafe archives, private API paths, propagation misses and independent browser retries.

Two older tracker tests were corrected to replay the saved September vintage and use an isolated observation fixture; later provider revisions had made their old assertions invalid. No tracker observations or frozen forecasts were changed.

Browser verification includes desktop/mobile overview, Irish Sea label, station details, history grouping and downloads. The [original publication handover](../../NI_ELECTRICITY_HANDOFF.md) describes the earlier paid/R2 proposal; the selected implementation here uses GitHub Actions + Workers Free + KV.
