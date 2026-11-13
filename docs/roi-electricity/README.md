# Republic of Ireland electricity: operation and deployment order

The native ROI route is `/dashboards/roi-electricity/`. It shares the site shell, icon artwork, API, namespaces and scheduler with NI. The standalone source in `Projects/ROI electricity` remains unchanged. This work is local until you commit/push it; the following steps do not imply a production deployment has already happened.

## Data now implemented

The overview collects EirGrid ROI demand, reported generation, wind, solar, East–West and Greenlink actuals at the exact accepted NI snapshot time. SEMO supplies estimates of station targets, availability and technical maxima. Unknown station outputs remain unknown. ROI North–South is the sign-reversed NI balance, with the accepted NI version retained in provenance.

Missing hourly dispatch reports no longer freeze valid regional grid readings. The collector publishes aligned actuals and flows, marks station output estimates unavailable, and leaves their generation in Other/Unallocated. A visible notice and source metadata explain the partial station coverage. Published availability and technical maxima retain their separate provenance. Complete dispatch coverage restores estimates automatically; missing grid inputs, invalid balances and backwards times still block publication. This policy applies only to the overview, not historical completeness or gas calculations.

Real historical collection scans monthly source windows from 2010 through yesterday and trims leading periods with no complete readings. Its eight public series are wind, solar, non-wind/solar generation, total ROI generation, demand, East–West, Greenlink and North–South. The first complete date differs by series. It never fills missing early solar or interconnector values with zero. All eight series use 96 source-labelled quarter-hours per accepted day. North–South uses the exact accepted NI historical edition, sign reversed, over matching complete daily intervals. The source NI version is recorded. The current unfinished day is excluded.

Non-wind/solar history is generation minus wind and solar; it differs from the overview's Other/Unallocated, which includes station estimates and demand reconciliation. Historical station targets are not presented as metered history. Monthly/annual charts require 95% coverage of elapsed days; sparse available means and counts remain in CSV. A later partial refresh retains the entire accepted regional day together, including its flow vintage, and records retained dates and source edition.

The East–West display endpoint is schematic near Holyhead on the Irish Sea coast. Greenlink retains its Pembrokeshire endpoint. These map paths are a presentation, not surveyed cable routes or exact terminal locations. Generation and pylon icons are shared from `components/electricity/` by both ROI and NI.

## The exact deployment sequence

The current local branch is **`codex/ni-electricity`**. The production branch is **`main`**. The automatic push workflow on the feature branch targets preview. Production is gated by `ELECTRICITY_ROI_ENABLED`; keep that flag false until both datasets have been initialized and checked.

### 1. Finish local historical collection and review

The initial real backfill has been collected and validated locally: **17 May 2013 to 3 November 2026**, with 4,919 source-date rows and gaps retained by series. All 912 available daily North–South values were checked against the exact accepted NI history edition with the sign reversed. The accepted compressed state is 6.8 MB, below the 20 MiB bound. Trends loaded the new history into the already-open page without a reload. To repeat it or resume a failed initial download, use Node 24.22.1 and Python, from the repository root:

```sh
python3 electricity/roi_cloud.py history --force \
  --local-dir outputs/electricity-local \
  --work-dir outputs/roi-history-backfill
npm run electricity:fallback
```

The `history` command reads the accepted NI history already mirrored by `npm run start:live`. It requires NI history through yesterday. If this is a new machine or empty local store, first run `npm run start:live` and wait for its first NI mirror/ROI overview success, then run the history command in a second terminal. Do not run two history collectors against the same local store at once. `--work-dir` retains successful month downloads if an initial source request fails, so rerunning resumes from cache. It does not seed fictional data or write to Cloudflare.

`electricity:fallback` copies only accepted public ROI JSON into `public/data/roi-electricity/`, with checksums in `edition.json`. Raw reports, source caches, KV archives and local logs remain under ignored `outputs/`.

After code/fallback changes, stop the local server with Ctrl+C, then:

```sh
npm run check
python3 -m unittest discover -s electricity -p 'test_*.py'
python3 -m unittest discover -s electricity/dashboard -p 'test_*.py'
npm run build
node scripts/check-site.mjs
npm run start:live
```

Use Python 3.11 for the unchanged NI calculation suite in production; the ROI standard-library collector also runs with the bundled Python 3.12. The Mac's built-in Python 3.9 supports these collector commands, but selecting the bundled runtime avoids environment differences. If needed:

```sh
export PATH="/Users/peterdonaghy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
export ELECTRICITY_PYTHON="/Users/peterdonaghy/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"
"$ELECTRICITY_PYTHON" electricity/roi_cloud.py history --force \
  --local-dir outputs/electricity-local --work-dir outputs/roi-history-backfill
```

Review [ROI](http://127.0.0.1:3100/dashboards/roi-electricity/) and [NI](http://127.0.0.1:3100/dashboards/ni-electricity/). Check the map, station drawers, Trends grouping/year selection and CSV/image downloads. Keep the terminal running and the Mac awake for local refresh. Local overview collection runs every 15 minutes; the browser checks once per minute while visible and on focus. After the initial history backfill is seeded, the local process checks for the daily history job after 07:00 UK time and retries failures at hourly intervals. It uses a separate history process so history does not block quarter-hour overview collection. Plain `npm start` and `npm run dev` do not start collectors.

### 2. Commit and push the feature branch

Review `git status`. Include the ROI integration, shared icons, collectors, tests, accepted fallback files and this guide. Leave the unrelated local `electricity/research/commitment_backtest/` research out of this release. Commit the reviewed dashboard changes, then:

```sh
git push origin codex/ni-electricity
```

This makes the new collector code available to GitHub. It does not merge the production branch. Wait for the automatic preview collection, if triggered, to finish before starting the manual run below; runs sharing a namespace are serialized.

### 3. Build and deploy the preview Worker

From that same checkout, after `npm run build` has passed:

```sh
npx wrangler deploy --config wrangler.electricity-preview.jsonc
```

This deploys only **salmon-electricity-preview**, using **ni-electricity-preview**. It must include the updated API so `/api/electricity/roi/` is available. It is separate from the private timer and production website.

### 4. Initialize both preview datasets

Use the GitHub CLI, logged into the repository, to run the branch version of the workflow with the new ROI input:

```sh
gh workflow run ni-electricity.yml \
  --repo stopthatgoblin/salmon-of-data \
  --ref codex/ni-electricity \
  -f dataset=both -f target=preview -f include_roi=true \
  -f preview_watch=false -f automatic=false
gh run watch --repo stopthatgoblin/salmon-of-data
```

Select the newly dispatched **Electricity data** run in `gh run watch`, or follow it in [GitHub Actions](https://github.com/stopthatgoblin/salmon-of-data/actions/workflows/ni-electricity.yml). The existing workflow already supports manual dispatch on the default branch; `--ref` selects the new branch implementation. [GitHub's manual-run instructions](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

Wait for these four collection steps to succeed, in this order:

1. **Refresh overview** — NI overview.
2. **Refresh ROI overview** — uses the accepted NI overview.
3. **Refresh historical explorer** — NI history.
4. **Refresh ROI historical explorer** — full initial ROI historical collection, using the accepted NI history.

The initial ROI history run downloads all required source months and can take tens of minutes; the explicit manual ROI history/both run has a 90-minute job limit. Scheduled incremental jobs retain the 45-minute limit. Do not enable recurring production collection or treat a green overview step as completion of history. If the initial history fetch fails, rerun `dataset=history`, `target=preview`, `include_roi=true`, `automatic=false`; accepted data stays intact. Cloud first-run caches are temporary until a complete valid archive is published; the local `--work-dir` retry cache is separate.

Check the [preview ROI page](https://salmon-electricity-preview.peterdonaghy.workers.dev/dashboards/roi-electricity/) and [preview manifest](https://salmon-electricity-preview.peterdonaghy.workers.dev/api/electricity/roi/manifest.json). **Both** `snapshot` and `history` must have a version and `ok: true`. History's `last` should be yesterday; individual series can legitimately have missing days. Inspect Trends and download CSV. For a temporary two-hour overview refresh test, dispatch another preview run with `dataset=snapshot`, `preview_watch=true`; this does not create a permanent preview schedule.

If you do not use the GitHub CLI, merge/push the release to `main` first, then use the web UI in steps 6–7 with target **preview** before running target **production**. The updated **include_roi** field becomes visible once the new workflow definition is on `main`. This alternative publishes the accepted bundled fallback page while cloud collection is being initialized.

### 5. Merge/push the reviewed release to main

Merge the reviewed feature branch/PR into **main** through your usual GitHub process. Do not change the scheduler's ROI flag yet.

Cloudflare's existing **salmon-of-data** Git build should run automatically with:

```text
Production branch: main
Build command: npm run build
Deploy command: npx wrangler deploy --config wrangler.static.jsonc
```

Wait for the Cloudflare deployment to succeed. The updated public page/API can serve accepted fallback data while the initial production datasets are collected. Existing NI production operation continues. A local build or a feature-branch push alone does not publish the production website.

### 6. Initialize both production datasets

In [GitHub Actions → Electricity data](https://github.com/stopthatgoblin/salmon-of-data/actions/workflows/ni-electricity.yml), select **Run workflow** with these exact settings:

| Field | Value |
|---|---|
| Branch | **main** |
| dataset | **both** |
| target | **production** |
| preview_watch | **false / unchecked** |
| include_roi | **true / checked** |
| automatic | **false / unchecked** |

Click **Run workflow** once. Wait for the same four collection steps listed above to succeed. This fresh cloud collection creates ROI overview and history state in the existing production namespace. Do not upload design fixtures or replace NI state.

The CLI equivalent is:

```sh
gh workflow run ni-electricity.yml \
  --repo stopthatgoblin/salmon-of-data --ref main \
  -f dataset=both -f target=production -f include_roi=true \
  -f preview_watch=false -f automatic=false
```

### 7. Verify production data before enabling schedules

Open [the production ROI manifest](https://salmonofdata.com/api/electricity/roi/manifest.json). Check:

- `mode` is `live`.
- `snapshot.ok` and `history.ok` are both `true`.
- Both datasets have a `version`, `lastAttempt` and recent `lastSuccess`.
- `history.records[0].time` is yesterday's date. Overview observation time reflects available upstream readings, not simply when the job ran.

Open [the public ROI dashboard](https://salmonofdata.com/dashboards/roi-electricity/), review Overview and Trends, and download a CSV. The [snapshot](https://salmonofdata.com/api/electricity/roi/snapshot.json) records its accepted `ni.version`; the [history](https://salmonofdata.com/api/electricity/roi/history.json) records `niSource.version`. Compare each with its corresponding NI manifest entry. Versions can briefly differ while KV propagates or NI advances first; the version retained in ROI identifies the exact source cohort used.

If only ROI history failed, rerun **dataset=history**, **target=production**, **include_roi=true**, **automatic=false**, with preview_watch off. This retries NI history first, then ROI history, without recollecting overview. An upstream outage can still prevent a fresh collection; accepted editions remain readable and failed health remains visible.

### 8. Enable the GitHub collection gate

Open the repository's **Settings → Secrets and variables → Actions → Variables**. Add or edit the **repository variable**:

```text
Name: ELECTRICITY_ROI_ENABLED
Value: true
```

Use **Variables**, not **Secrets**. This enables ROI in the existing quarter-hour overview job, daily history job and temporary preview watch. The collector API token and account/namespace variables are already in place for NI and are reused. No new credential or namespace is required.

### 9. Enable and redeploy the private timer

Only after both production ROI datasets exist, edit `wrangler.electricity-scheduler.jsonc`:

```json
"vars": { "ELECTRICITY_ROI_ENABLED": "true" }
```

Then deploy that timer explicitly:

```sh
npx wrangler deploy --config wrangler.electricity-scheduler.jsonc
```

Commit the flag change to `main` (or through your usual PR) so future timer deployments retain it. This command targets **salmon-electricity-scheduler**, not the website or preview. Keep its existing encrypted `GITHUB_ACTIONS_TOKEN` and `ELECTRICITY_DATA` binding. A website push does **not** deploy this separate timer.

The timer now dispatches when either region is due for the selected dataset. A recent NI success cannot suppress an ROI retry. Enabling it before both initial ROI publications yields an explicit missing-state error. Overview remains on **:02, :17, :32 and :47 UTC**. History runs at **07:00 Europe/London**, with morning catch-ups from 08:05 to 12:05. Successful daily runs suppress catch-ups separately for each region. Changed Cloudflare cron configuration can take up to 15 minutes to propagate. [Cloudflare Cron Triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/).

### 10. Confirm unattended operation

At the next quarter-hour, observe the timer invocation, GitHub production run and advancing ROI overview `lastSuccess`. Leave the page open to confirm the changed version appears without reload. Check the next 07:00 UK history run and confirm both regions' history `lastSuccess` advances. GitHub queues, source publication delays and KV propagation can delay visible readings.

After activation, production collection runs in GitHub/Cloudflare with the Mac off. No website rebuild is needed every 15 minutes or every day. The local process is only for local review.

## Publication and operational bounds

API endpoints are unchanged. ROI uses versioned public JSON and separately scoped private archives/state pointers. The accepted `private/roi/{snapshot,history}/current` pointer is also the API's commit record; the API emits only allowlisted public fields and never exposes archive keys, checksums or slot numbers. Readers retain a fallback for old public pointers and public-only local NI mirrors, but collectors no longer write duplicate public pointers. The API allows only manifest/snapshot/history JSON routes; raw inputs and archives have no public route. Publications validate complete data before advancing pointers, keep three accepted versions, reject backwards/range-shrinking updates, and limit compressed state to 20 MiB. Failure of either ROI dataset does not roll back NI or the other ROI dataset.

A normal day uses about **582 KV writes**: three writes for each of 96 NI + 96 ROI overview collections and two daily history collections. This is 25% below the previous 776-write design. Manual runs, preview watches, failures and other account workloads share the remaining 418 writes under the 1,000-write Free allowance. A 50% usage email can still arrive late in a normal day; it is a threshold notice rather than evidence the quota has been exceeded. The read allowance is separate. The API's edge response cache reduces repeated visitor reads without changing the collection cadence. Keep the existing Free plan and avoid unnecessary forced runs. [KV pricing and daily limits](https://developers.cloudflare.com/kv/platform/pricing/).

For this publication change, deploy the compatible API Worker and timer **before** pushing the collector change to `main`. Existing four-write collectors work with the updated readers. Afterward, the three-write collectors advance only the private commit pointer. Old public pointers can remain frozen and must not be used for health checks. Use the public API manifests. For a rollback to older readers, first restore the previous collector and republish both private and sanitized public pointers from the accepted current state; do not blindly deploy an old API against frozen pointers.

To disable ROI collection, set the repository variable and the scheduler flag to false, and redeploy the scheduler. Accepted data stays readable and its age remains visible; NI continues its original schedules.
