# Cloudflare options for the electricity dashboard

Pricing checked against official documentation on **31 October 2026**. Implementation updated **1 November 2026**: the selected Workers Free + KV service is deployed to an isolated preview. No paid subscription or R2 bucket was enabled.

## Selected production service

**Selected option:** the user has now chosen **GitHub Actions + Workers Free + KV**, replacing the earlier R2 proposal below. The compressed existing cache measures about 9.2 MB, so the complete local collector state has a practical KV starting point. See [the concrete launch checklist](launch-checklist.md) for account setup, state preservation, parity checks and publication order. The [operating guide](README.md) records implementation, preview validation and publication status.

The production requirement is automatic collection: the overview every 15 minutes, and history once per UK calendar day at **07:00 Europe/London**. This supersedes the handover's suggested 07:10 history start. The static edition is the local review stage; publishing its bundled files alone does not meet the production requirement.

The selected implementation uses **GitHub Actions running the original Python collector, private compressed KV state, and a small read-only Cloudflare Worker on the Free plan**, retaining the existing website deployment. R2 is not used. The handover's native scheduled Cloudflare collector remains an alternative if tighter scheduling becomes necessary. The front end can remain statically hosted while it reads changing, versioned datasets through a read-only API. Data refreshes do not require a site rebuild or Git commit, and collection runs independently of visitors and the Mac.

- Overview: request a run every 15 minutes, e.g. `7,22,37,52 * * * *` to avoid the start of the hour. GitHub supports schedules as often as every five minutes. Preserve the source's actual observation time and mark delayed data; scheduled runs can be delayed or dropped.
- History: request the daily job at 07:00 Belfast time, including BST/GMT changes. GitHub's current schedule documentation supports an IANA timezone such as Europe/London. Persist the successful UK date and permit bounded catch-up attempts after failure. Publication follows successful validation; neither a scheduler nor this site can force an upstream feed to publish on time. If the native Cloudflare collector is used instead, its UTC cron needs an explicit Europe/London due-date check.
- Browser: check a small manifest every minute while visible and on return; load only changed datasets and preserve filters and open station details.
- Storage: retain the last validated version on upstream failure, store collector state privately, serialize writes, and seed the existing history once. Daily jobs refresh recent windows rather than replaying the whole archive.

GitHub's standard Linux runner can reuse the existing Python collection logic. Persistent caches must be restored/published to durable storage, publication must serialize competing writers, and source access must be tested from GitHub's runner network. Do not rely on an ephemeral runner disk as the only historical archive. A native Workers collector would require a runtime port and CPU/memory benchmarks instead. At 31 days, the normal schedule is 2,976 overview runs and 31 daily history runs, plus bounded retries. Public-repository schedules disable after 60 days without repository activity; this needs an operational reminder or independent freshness monitoring.

**Budget:** target $0 using free public-repository compute, Workers Free and standard KV. Normal collection uses about 388 KV writes/day, plus bounded health writes and catch-ups; state uses three slots per dataset. Free quotas stop operations instead of buying overages. This limit applies to the selected service; existing subscriptions or domain renewals are separate. The $5 Workers subscription is not required merely because collection runs every 15 minutes. Keep the Free plan until measured traffic/CPU or a different collector architecture justifies Paid. If an absolute dollar ceiling is required, prefer products that stop at free quotas, or verify a provider-enforced cap covering every enabled metered product. Do not treat CPU limits or budget alerts as a dollar cap.

## Static assets and bundled fallback

The existing `wrangler.static.jsonc` already serves `dist/client` as Worker Static Assets. The new dashboard, JSON data, map and explorer compile into that same directory. Charts, grouping and exports run in the browser.

[Cloudflare states](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/) that requests to static assets are free and unlimited and asset storage has no additional charge. The static assets themselves do **not** require Workers Paid or R2. The live data API uses the Free Worker and KV allowances separately. Keep assets served directly; invoking a dynamic Worker first or enabling the separate paid Workers Cache product changes the cost model. Existing account subscriptions, domain costs and any build allowances are separate from this dashboard's asset serving.

Manual dataset replacement and a normal site rebuild can remain free. A future deployment can use the site's existing GitHub → Cloudflare workflow without changing its hosting architecture.

## Alternative free approaches considered

| Option | Cost position | Tradeoff |
|---|---|---|
| Existing Mac Python collector plus publication of validated static snapshots | Collector runs on existing hardware; static serving remains free | Requires the Mac to be awake, signed in and online. A publication step still needs implementing. |
| Python collector on standard GitHub-hosted runners in a public repository | [GitHub says these runners are free](https://docs.github.com/en/billing/concepts/product-billing/github-actions) | Scheduled runs can be delayed or dropped. Durable collector state and publication need designing; it is not guaranteed quarter-hour operation. |
| External Python collection plus a small Workers Free/KV data service | Can stay within free Workers and KV quotas, avoiding the CPU-heavy collector on Workers | Needs a secure write boundary, bounded reads/writes and durable source-state storage. At free limits, service can fail rather than continue. Must validate this design before promising it. |
| Entire collector on Workers Free | Potentially free only after a measured fit | Free CPU is 10 ms per invocation. The current desktop collector cannot simply be deployed unchanged; this is not an assumed fit. |

Workers Free currently includes 100,000 requests/day. KV includes 100,000 reads/day, 1,000 writes/day and 1 GB storage; free operations fail after limits. See [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/). Private-repository Actions uses included compute and can incur charges beyond it; GitHub supports [budgets](https://docs.github.com/en/billing/how-tos/set-up-budgets) that stop relevant usage. Avoid rebuilding the whole site every 15 minutes without checking CI/build quotas. GitHub also [documents schedule delays and public-repository inactivity disabling](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

The Mac option depends on the Mac staying online. GitHub Actions is an approximate schedule, suitable for the user's accepted tolerance; it is the preferred initial approach. Consider the native Cloudflare collector if observed schedule delays become unacceptable.

## Selected KV service: illustrative free capacity

Production uses three writes per accepted dataset publication. NI and ROI at 15-minute overview cadence plus one history publication each need about **582 writes/day**, with one additional health write for a failed attempt. The 1,000-write daily allowance is account-wide, including previews and manual runs. A 50% email is expected once usage crosses 500 writes; it does not by itself mean the Free allowance will be exhausted. Check the separate read/write/delete/list totals before attributing a notice to visitors. [KV metrics](https://developers.cloudflare.com/kv/observability/metrics-analytics/).

The live API now caches successful responses at the edge: 60 seconds for manifests/current JSON and one day for immutable versioned JSON. This reduces repeated KV reads from visitors at the same edge location; it does not remove API Worker invocations. Static assets still bypass the Worker. Local review bypasses the cache. The capacity examples below are conservative uncached scenarios; cache effectiveness depends on traffic distribution. No traffic-based collection or paid-plan upgrade is enabled. These changes create headroom but cannot guarantee service under arbitrary traffic or unrelated account workloads.

Assume one five-minute visit per user per month, about 10 API requests and 18 KV reads per visit, with traffic spread evenly. Static asset requests are separate and free. The manifest uses two KV reads per check; longer sessions and repeat visits increase usage. Normal writes are below the daily free allowance, and retained state is tens of MB. Other Workers/KV workloads share account allowances.

| Monthly visits | API requests/month | Average KV reads/day | Workers Free + KV charge | Expected capacity |
|---:|---:|---:|---:|---|
| 1,000 | 10,000 | 600 | $0 | Within free allowances |
| 10,000 | 100,000 | 6,000 | $0 | Within free allowances |
| 100,000 | 1,000,000 | 60,000 | $0 | Within free allowances if traffic is spread |
| 1,000,000 | 10,000,000 | 600,000 | $0 | Exceeds free daily capacity; requests fail |

These are capacity scenarios, not a promise based on unique-user count. At roughly 18 KV reads per visit, around 5,500 five-minute visits in one day can consume the read allowance. A tab left open for an hour makes about 60 manifest checks. Staying on Free caps spend for this service by limiting availability.

## Earlier R2 comparison: not the selected deployment

These are planning scenarios, not a measured bill. Both columns use free standard GitHub-hosted Linux collection in the public repository; only the Cloudflare serving plan differs. They include the Workers plan fee and modeled R2 reads, before taxes. Ordinary static website assets are served directly at no per-request charge.

Assume a 30-day month, one five-minute visit per user, a budget of **10 API requests per visit** (initial data, one-minute manifest checks and some version fetches), **2 ms CPU per API request**, and a conservative **two R2 reads per API request without cache hits**. Reserve another 100,000 R2 reads/month for collector state. Assume total storage below 10 GB-month, Class A writes below 1 million/month, logs within included allowances, and no other account workload consuming the shared allowances. Actual collector operations, CPU and cache hit rates must be measured.

| Monthly users / visits | API requests | Workers Free + R2 | Workers Paid + R2 |
|---:|---:|---:|---:|
| 1,000 | 10,000 | $0 | about $5 |
| 10,000 | 100,000 | $0 | about $5 |
| 100,000 | 1 million | $0 | about $5 |
| 1 million | 10 million | exceeds daily free capacity | about $9 |
| 5 million | 50 million | exceeds daily free capacity | about $51 |

Free estimates assume traffic sufficiently spread across days. Workers Free has a **daily**, account-wide 100,000-request limit; it is not a pool of 3 million requests usable on any day. At 10 requests/visit, 10,000 visits in one day would use the whole daily allowance. Further requests fail rather than automatically buying Paid capacity. Long open sessions, repeat visits, bots and other Workers count too.

Calculation using published rates:

- Worker Paid: `$5 + max(API_requests - 10,000,000, 0) / 1,000,000 * $0.30 + max(CPU_ms - 30,000,000, 0) / 1,000,000 * $0.02`.
- R2 Standard Class B: `$0.36 * max(ceil((2 * API_requests + 100,000) / 1,000,000) - 10, 0)`, reflecting whole-million operation rounding and the included 10 million reads.
- One million visits: Workers $5, R2 modeled reads $3.96, total $8.96.
- Five million visits: Workers $18.40, R2 modeled reads $32.76, total $51.16.

Caching can reduce R2 reads; it does not necessarily remove the API Worker invocation charge. No collection is triggered by visitor traffic. A visitor leaving a tab open for an hour makes roughly 60 manifest checks, so monthly unique-user count alone does not determine the bill.

For a stronger $0 ceiling, consider **Workers Free + KV** for the small published datasets and compact retained state instead of R2. KV Free has 100,000 reads/day, 1,000 writes/day and 1 GB storage, and operations fail at free limits. The present published JSON is under 1 MB and 15-minute snapshot publishing is only 96 runs/day, so this is plausible. The full collector cache/archive must be measured and bounded before promising that the complete service fits. If R2 is retained for raw archives, its possible charges remain separate. [KV pricing](https://developers.cloudflare.com/kv/platform/pricing/).

## If Workers Paid is chosen: $5 is a minimum, not a cap

[Workers Standard pricing](https://developers.cloudflare.com/workers/platform/pricing/) has a $5/month subscription, with 10 million Worker requests and 30 million CPU milliseconds included, then metered overages. These are account allowances, shared with other Workers. Taxes or other account products can add to the invoice.

[R2 Standard's free allowance](https://developers.cloudflare.com/r2/pricing/) is 10 GB-month storage, 1 million Class A operations and 10 million Class B operations/month, with free egress. Exceeding the storage or operation allowance can still create a bill; this is not a hard cap.

Before enabling paid collection:

1. Inspect whether the account has the new hard spending-cap feature, and exactly which products and overages it covers. Cloudflare's [October update](https://blog.cloudflare.com/enterprise-for-all-update/) says hard caps are being prototyped with early availability in Q4 2026. Do not assume availability, or R2 coverage, for this account. Budget alerts notify; they do not themselves stop charges.
2. Keep expensive collection schedule-only; public visitors must never trigger collection, backfills or retries. Bound schedules, retries, source requests and execution time. Use per-invocation CPU limits and budget the maximum invocation count against the included account CPU allowance.
3. Serve published snapshots directly as static assets where practical. If a dynamic read API is necessary, bound and cache its traffic and account for its request/CPU cost. Workers Cache hits are still billable requests under current pricing.
4. Retain only a bounded number of published snapshots and raw archives, set storage lifecycle policies, and limit writes. Reduce log volume and check its pricing separately.
5. Alert before allowances are exhausted and implement a conservative stop-collection rule that leaves the last valid snapshot online. A custom stop rule reduces risk but is not a provider-guaranteed dollar cap.

For a strict bill that must never exceed $5, prefer the static/free approach or verify a provider-enforced cap covering every enabled metered product before enabling Paid. CPU limits and alerts alone cannot guarantee that ceiling.
