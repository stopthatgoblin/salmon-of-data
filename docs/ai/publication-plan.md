# Superseded recommendation

The newer local-only deployment and unattended-update guide recommends Cloudflare static hosting and automatic publication of validated data, following Peter’s preference for no routine manual work. A static export has now been verified. The earlier review-before-every-update and Netlify-adaptation sections below are retained as historical planning context, not the current recommendation.

# Publication and update plan

Prepared 6 September 2026. Recommendation only: no hosting, scheduler, notifications or domain purchase has been configured.

## Recommended pattern

Use a GitHub repository as the review and publication record. A scheduled GitHub Actions workflow checks sources, captures a dated vintage, validates inputs, rebuilds actuals under frozen v1 definitions, then opens or updates one data-update pull request. The pull request should show each new observation, historical revision, old/new latest dates, source retrieval times, validation results and a deploy preview. Peter reviews and merges; the hosting platform deploys the approved commit. After several reliable release cycles, clean validated updates can be auto-merged if desired.

Notify through GitHub pull-request/review notifications when data actually changes, plus workflow-failure notifications and a stale-data alert when a scheduled release remains missing after a grace period. Do not email for every unchanged polling run. Use a separate delivery service only if you later want a public subscriber list. Netlify's built-in email deploy notifications require Pro or Enterprise, so do not rely on them for a no-cost design.

Run a daily check away from the top of the hour, with extra retries after scheduled releases and a manual catch-up trigger. GitHub scheduled runs can be delayed or dropped, and public-repository schedules can be disabled after 60 days of inactivity; include monitoring for the scheduler itself. Provider release times and FRED availability are not identical. A release calendar should express local timezone, reference period, expected publication date, confirmation status and source link; update it from the official calendars rather than assuming fixed monthly days.

Keep each original forecast anchor, endpoint and definition immutable. Separate `freeze_date`, `retrieved_at`, `published_at` (when provided) and `observation_period`. Preserve first-release and revised vintages so next year's evaluation can report both. A new definition needs a new named version, never an overwrite. Archive large raw files outside normal Git history; keep compact normalized extracts, manifests and hashes with each release. Agree an archival destination before scheduling.

Quality gates: expected schema and series IDs; duplicate keys; numeric/quality flags; all required basket members; sensible units; chronological uniqueness; contiguous rolling windows; latest common pay/CPI period; large revisions flagged for review; no silent filling or zero substitution. A failed source must keep the last good public dataset and show its age. No source failure should remove a metric or publish partial calculations without a visible explanation.

## Hosting fit

The dashboard needs no server-side data API: its charts consume a build-time snapshot and the blog is authored content. A static build on Netlify is a good long-term fit. Netlify can connect to Git and build approved commits automatically. However, the current Vinext scaffold builds a Cloudflare Worker; its `dist/server` output is not a Netlify deploy artifact. Before publication, either produce a genuine static export/migrate the thin presentation shell, use standard Next.js with Netlify's supported integration, or retain the current worker target and host on Cloudflare. Do not simply upload the present build folder to Netlify.

The existing downloader only captures new inputs, and the builder still deliberately uses the September 2026 cutoff. Production work must parameterize the actuals input/vintage and cutoff, while keeping the forecast registry read-only. Build date must not replace the latest observation date. Blog text is edited separately in `content/posts.json`; pipeline updates should never generate or rewrite posts.

## Next expected releases as known on 6 September 2026

| Source | Metrics | Next release | Reference period / status |
| --- | --- | --- | --- |
| Indeed Hiring Lab | Recruitment | Check weekdays; repository generally updated weekly | No guaranteed next publication day identified |
| BLS CPI | Real pay | 11 September 2026, 08:30 America/New_York | August 2026; confirmed calendar |
| Statistics Canada detailed JVWS | Canada demand and pay | 15 September 2026 | Q2 2026; explicitly confirmed by latest release |
| BLS JOLTS | Actual hiring | 29 September 2026, 10:00 America/New_York | August 2026; confirmed calendar |
| BLS Employment Situation | Employment and nominal pay input | 2 October 2026, 08:30 America/New_York | September 2026; confirmed calendar |
| New York Fed graduate dashboard | Graduate gap and underemployment | Expected November 2026 | Quarterly update pattern; exact day unconfirmed |

September's newer nominal earnings still require September CPI before updating real pay. Canada's monthly vacancy releases are not substitutes for the detailed quarterly occupation table.

## Sources

- [GitHub scheduling behaviour](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub workflow notifications](https://docs.github.com/en/actions/concepts/workflows-and-actions/notifications-for-workflow-runs)
- [Netlify Git-connected deploys](https://docs.netlify.com/deploy/create-deploys/)
- [Netlify deploy notifications and plan restrictions](https://docs.netlify.com/deploy/deploy-notifications/)
- [BLS CPI calendar](https://www.bls.gov/schedule/news_release/cpi.htm)
- [BLS JOLTS calendar](https://www.bls.gov/schedule/news_release/jolts.htm)
- [BLS employment calendar](https://www.bls.gov/schedule/news_release/empsit.htm)
- [BLS calendar subscription](https://www.bls.gov/schedule/news_release/bls.ics)
- [Statistics Canada next detailed quarterly release](https://www150.statcan.gc.ca/n1/daily-quotidien/260827/dq260827b-eng.htm)
- [New York Fed graduate dashboard](https://www.newyorkfed.org/research/college-labor-market)
- [Indeed data repository](https://github.com/hiring-lab/job_postings_tracker)

## Domain shortlist

Verisign .com RDAP queries on 6 September 2026 returned HTTP 404 (no registry record) for `aidisplacementtracker.com` and `aijobdisplacementtracker.com`. The former is shorter; the latter exactly matches the site's title. Both appear unregistered, subject to registrar checkout, reserved-name rules and availability changing. No price or trademark clearance is implied. `aijobdisplacement.com` and `aijobshift.com` returned registered records.

Registry checks: https://rdap.verisign.com/com/v1/domain/aidisplacementtracker.com and https://rdap.verisign.com/com/v1/domain/aijobdisplacementtracker.com. No registration was attempted.
