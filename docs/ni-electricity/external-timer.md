# Cloudflare timer for the existing GitHub collectors

## Prepared, not armed

The timer-only `salmon-electricity-scheduler` Worker is deployed on the existing account. Its `workers.dev` and preview URLs are disabled, it has no HTTP handler, and `wrangler.electricity-scheduler.jsonc` deliberately has an empty cron list until the owner adds a restricted GitHub credential. No paid plan or product is required.

This addresses a different failure from a collector error: on 1 November 2026 production manual and push collections succeeded, but GitHub had not delivered any native scheduled events during the investigation. Refreshing the active workflow registration and republishing its schedule did not immediately produce a timer run. This does not establish that GitHub schedules will never recover. The local review was using a separate temporary preview watch, which explains why it kept updating independently.

Cloudflare's timer will dispatch the existing workflow on production `main`, with `automatic: true`. That retains the Python collectors, KV state, daily-success checks, retry limits, signed-flow rules and history validation. Recent overview collections suppress duplicates if GitHub's native schedule also fires. GitHub runner queue delays and upstream source delays can still occur; the extra timer removes reliance on GitHub's own cron delivery.

## One owner step: encrypted repository-scoped credential

1. Open [GitHub fine-grained personal access tokens](https://github.com/settings/personal-access-tokens), then **Generate new token**.
2. Name it `Salmon electricity timer`. Set an expiry you can maintain, for example 90 days, and keep a renewal reminder.
3. Use your own resource owner. Under **Repository access**, select **Only select repositories → salmon-of-data**.
4. Under **Repository permissions**, set **Actions → Read and write**. Metadata read is included automatically. No Contents write, Workflows write, organisation or account permissions are needed.
5. Generate the token and copy it once. Keep it out of chat, repository files and shell command history.
6. In [Cloudflare](https://dash.cloudflare.com/), open **Workers & Pages → salmon-electricity-scheduler → Settings → Variables and Secrets → Add**.
7. Select **Secret** (encrypted), name it exactly `GITHUB_ACTIONS_TOKEN`, paste the value and save/deploy it to production. It belongs to the scheduler Worker, not the public site's build variables or the KV namespace.
8. Tell Codex that the secret has been added; do not send its value. Secret-list metadata is sufficient to check that it exists.

GitHub requires Actions write permission for workflow dispatch. The existing Cloudflare collector token stored in GitHub authorises the reverse direction (GitHub → KV); it cannot be reused for Cloudflare → GitHub. The GitHub plugin does not provision a separate restricted deployment credential, and an existing broad local login should not be copied into the Worker.

## Activation and verification

After the secret exists, arm these three crons in the scheduler configuration and deploy that configuration:

```json
"triggers": { "crons": ["2,17,32,47 * * * *", "0 6,7 * * *", "5 7-12 * * *"] }
```

The handler filters the daily UTC candidates to **07:00 Europe/London** across GMT/BST, and catch-ups to 08:05–12:05 UK time. Successful history publication suppresses that day's catch-ups. It only reads the small existing public KV pointers, then sends an authenticated dispatch to a fixed GitHub API URL. Credentials never appear in URLs or log messages; redirects are rejected. There is no public trigger endpoint.

Verify a real scheduled Cloudflare invocation, its GitHub production run, updated `lastSuccess` in the public manifest, and an open browser's response to a changed version. A recent successful collection can legitimately suppress the first timer invocation. Cloudflare warns that changed cron triggers may take up to 15 minutes to propagate. Do not label the fallback active before these checks pass.

The timer adds roughly 100 small invocations and pointer reads/day; the existing collectors keep their bounded KV writes. Retain Workers **Free**. On that plan quota exhaustion fails rather than purchasing paid overages. Token expiry or revocation stops dispatch and requires renewal. This timer's code is deployed separately from the static site's existing Cloudflare build command.

References: [GitHub workflow dispatch permissions](https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event), [Cloudflare cron triggers](https://developers.cloudflare.com/workers/configuration/cron-triggers/), [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/).
