# Workers Free + KV: automation and publication checklist

Selected architecture: GitHub Actions + Workers Free + KV. Updated 1 November 2026: owner setup is verified, the original collectors and durable storage adapter are implemented, the live API/browser polling are built, and the separate Cloudflare preview is deployed and collecting successfully. Production publication is pending. The [operating guide](README.md) records the current implementation and manual refresh/recovery steps.

## Existing setup identified locally

- Repository: `https://github.com/stopthatgoblin/salmon-of-data`.
- Documented production branch: `main`.
- Documented existing Cloudflare Worker: `salmon-of-data`, serving `dist/client` using `wrangler.static.jsonc`.
- Documented domain: `salmonofdata.com`; confirm these production settings in Cloudflare before changing them.
- Integration branch: `codex/ni-electricity`. This branch tests collectors against preview. Production schedules and website publication use `main`.
- Original collector: `/Volumes/External SSD/Projects/NI electricity/dashboard`, with helpers in `../research/dispatch_proxy/`.
- Active Mac working copy: `~/Library/Application Support/SalmonOfDataElectricity/`.

## What the owner needs to provide or enable

Follow the [click-by-click owner setup guide](setup-guide.md) for the dashboard menu paths and exact repository variable/secret names.

1. **GitHub access** to the public repository and its Actions/settings. Verified: the GitHub plugin is installed and enabled. An authenticated Git push dry run to stopthatgoblin/salmon-of-data succeeded, confirming repository write access. A subsequent remote-ref check confirmed that the test branch was not created; main remains at b84e0596938c44fa38acd63e527bb816878ee912. The repository API also confirms Actions is enabled with all actions allowed, and all three variables plus the collector secret are present.
2. **Cloudflare access** to the account already hosting the site. Confirm the account is on **Workers Free**; this is separate from the domain's Free/Pro plan. No Workers Paid upgrade is part of this setup.
3. **A standard Workers KV production namespace**, proposed name `ni-electricity-prod`, plus a separate preview namespace for testing. Use standard Workers KV, not the private-beta KV Instant product. Record their namespace IDs and the Cloudflare account ID; these IDs are not passwords.
4. **A collector API token** with Workers KV Storage edit access scoped to the hosting account. Put its value directly into the repository's GitHub Actions secret `CLOUDFLARE_API_TOKEN`; do not paste it into chat or commit it. Reuse the existing Cloudflare Git integration/build deployment credentials for website publication where possible. If code deployment is moved into Actions, it needs a separately scoped deployment token with Worker deployment permissions.
5. **Actions configuration:** enable the scheduled workflows on `main`, allow the pinned official actions needed by the workflow, and supply `CLOUDFLARE_ACCOUNT_ID` and `ELECTRICITY_KV_NAMESPACE_ID` as repository variables. Preview must have its own namespace configuration; preview jobs must not write production.
6. **Failure notifications:** enable GitHub's workflow-failure notifications and decide where an independent stale-data alert should go. Account for GitHub disabling public-repository schedules after 60 days without repository activity; successful scheduled runs alone should not be treated as resolving that rule.

Namespace names and variable names above are proposed conventions. Match them to the final code/configuration rather than creating duplicate resources.

## Feasibility measurement

The active local caches were read without changing them:

| Cache | Files | Original bytes | gzip tar archive bytes |
|---|---:|---:|---:|
| Historical source cache | 1,068 | 10,470,668 | 6,879,785 |
| Dispatch/technical source cache | 247 | 51,792,896 | 2,328,584 |

The two compressed archives total **9,208,369 bytes** (about 9.2 MB). The current published snapshot and history JSON total **602,657 bytes**. Each archive is below KV's 25 MiB value limit, and this starting state is comfortably below the 1 GB free storage allowance.

This measurement establishes a practical starting point, not unlimited future retention. Bound raw-cache retention, keep accepted historical data and provenance, monitor growth, and stop publishing safely if size limits are exceeded. Do not upload all 1,315 cache files as individual KV keys: the initial seed alone would exceed the free daily write allowance. Store compressed archives/chunks and a bounded number of versions, with a measured per-run operation budget. A bulk API request still counts writes per key.

## Implementation work

### Collector and durable state

- Bring the existing Python collectors, required research helpers, their tests and source documentation into this repository. Preserve the calculation functions; adapt execution paths and storage boundaries for Linux Actions runners.
- Seed from the latest accepted Mac history and cache so the service retains already collected history rather than attempting a fresh multi-year scrape.
- Restore compressed state from KV before each job and persist accepted state afterward. GitHub runner disks and Actions caches must not be the only copy of irreplaceable history.
- Serialize publication. Write complete versioned data/state first, validate it, then advance pointers. Keep live and history publication independent. KV is eventually consistent, so a pointer becoming visible before its referenced data must leave readers on their last valid version, not break the dashboard.
- Preserve actual-only aligned timestamps, signed flows, station dispatch-target estimates, availability/provenance, complete-day criteria, clock-change gaps, 95% monthly/annual coverage, and attribution.
- Use bounded retries and execution times. Failed/empty/backwards or invalid source data must not replace the last accepted dataset. Preserve daily station-meter history retained internally by the original collector as well as the seven displayed grid series.

### GitHub schedules

- Overview: request a run every 15 minutes, away from the start of the hour, e.g. `7,22,37,52 * * * *`.
- History: request a run at **07:00 Europe/London** each day, with bounded catch-up attempts after failure. This is the user's requested start time, replacing the local prototype's 07:10. Use a persisted successful UK date to prevent duplicate successful daily jobs.
- Include a manual-run facility for seeding, testing and recovery. Scheduled runs are approximate, not a promise of source freshness or an exact completion time.
- Use standard GitHub-hosted Linux runners in the public repository; avoid paid larger runners and unnecessary artifact storage. Secrets are available only to trusted publication workflows, not untrusted pull-request runs.

### Website and read API

- Bind KV to the website Worker or a separate data Worker, preserving the existing static site and domain. A same-origin `/api/electricity/*` boundary avoids a new public domain/CORS setup.
- Expose only approved manifest/snapshot/history reads. Collector state, raw reports and writes must not be public API endpoints.
- Keep ordinary website assets served directly as static assets. Visitors must never trigger collection or historical backfills.
- Restore the prototype's one-minute visible-page polling, focus/return checks, changed-version loading, filter/dialog preservation, delayed-data labels and reduced-motion-aware 900 ms update wipe.
- Retain Overview, Trends and Definitions, all seven explorer series, all grouping/year controls, station dialogs and CSV/PNG/SVG downloads. Keep the corrected Irish Sea label.

## Publication order

1. Confirm the existing account, Free plan, Worker, domain and repository settings.
2. Prepare and test the Worker/API, workflows, cloud storage adapter, original collectors and frontend update behaviour locally and against the preview namespace.
3. Configure repository variables/secrets and seed production KV with accepted data/state.
4. Run a manual cloud collection and compare accepted output with the local collector at matching source timestamps. Test failure retention, delayed-source labels, version propagation, complete days and time-zone handling.
5. Review the complete site build and regression checks, including the saved-vintage and isolated-observation tracker regression tests. The earlier stale assertions were corrected without changing source observations or frozen forecasts.
6. Commit the complete site and pipeline changes; merge/push to **main**, which the existing Cloudflare integration is documented to build and deploy. Keep `npm run build` and the explicitly selected Wrangler configuration, updating that configuration for the KV binding/API entrypoint.
7. Verify the public dashboard/API, station details, historical grouping, downloads and credits, plus the site's existing tracker/blog routes. Verify both scheduled workflows and freshness monitoring.
8. After cloud collection has been verified, disable the old Mac update agents if desired; keep the working copy and last-good seed for recovery. Website publication does not disable Mac jobs.

## References

- [Workers KV limits](https://developers.cloudflare.com/kv/platform/limits/)
- [Workers KV pricing and quota behaviour](https://developers.cloudflare.com/kv/platform/pricing/)
- [Cloudflare CI credentials](https://developers.cloudflare.com/workers/ci-cd/external-cicd/github-actions/)
- [GitHub schedule behaviour and timezone support](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)

The public repository also exposes source files; keep API tokens, environment files and private drafts out of commits.
