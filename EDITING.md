# Editing Salmon of Data

## Blog posts and their order

Put posts in `content/posts/` as `.md` files. Copy `content/post-template.md` to start.

```yaml
---
title: "What the new figures tell us"
date: "2026-09-08"
author: "Peter Donaghy"
excerpt: "A short introduction for the blog listing."
tag: "El Niño"
draft: false
---
```

The `date` field controls ordering: newest first. The filename does not control the publication date; it becomes the URL. Posts on the same date sort alphabetically by filename. Changing a post's text does not change its date or position. Drafts are hidden. Future-dated posts appear immediately unless marked `draft: true`; there is no scheduled publishing system.

Write the post below the second `---`. Rename files only if you want their URLs to change.

## Small wording changes

You can ask Codex to change the exact sentence, or edit the text in these files:

| Area | File |
| --- | --- |
| Landing-page headlines, introduction and tracker cards | `app/page.tsx` |
| Your biography, social links and disclosures | `components/about.tsx` |
| Shared navigation and footer | `app/layout.tsx` |
| El Niño title, hypothesis and methodology | `app/trackers/el-nino/page.tsx` |
| El Niño chart explanations, shared labels and freeze notes | `components/tracker.tsx` |
| AI title and hypothesis | `app/trackers/ai/page.tsx` |
| AI chart explanations and shared labels | `components/ai-tracker.tsx` |
| Shared calendar introduction and table | `components/release-calendar.tsx` |
| Calendar dates, trackers and release notes | `data/release-calendar.json` |
| Per-chart source licences and attribution | `components/chart-licence.tsx` |
| Blog listing introduction | `app/blog/page.tsx` |
| Individual blog articles | `content/posts/*.md` |

These `.tsx` files contain the page structure as well as text. Change the wording between the tags while preserving the surrounding tags, braces and quotes. Blog articles need only Markdown. For substantial edits, ask Codex to make and check them.

El Niño metric-specific descriptions live in `scripts/build-data.py` and are regenerated into `data/dashboard.json`. Change them in the source script then rebuild the data, rather than editing only the generated JSON. AI metric-specific descriptive copy is in `data/ai/dashboard.json`. Do not change numerical definitions, anchors or scenario endpoints as a wording edit.

## Seeing changes

The current localhost preview serves the built site. After editing, run:

```sh
npm run build
```

Then refresh http://127.0.0.1:3100/. The running static server serves the new build without restarting.

For a live editing session, stop `npm start` first and use `npm run dev`. Markdown files are watched and blog pages regenerated automatically. Use `npm run build` when finished to update the static site. Local editing does not publish to the internet.

## Future actuals and frozen forecasts

The solid dark line represents published actuals. As new observations are imported, the line extends into the shaded scenario region and is drawn **above** the dashed scenario lines. Missing source periods remain gaps. Exact actuals remain available in tooltips and CSVs; rounding the y-axis labels does not round the underlying observations.

Forecasts are loaded independently from:

- `public/data/scenarios-v1.json` for El Niño (frozen 7 September 2026).
- `public/data/ai/frozen-metrics-v1.json` for AI (frozen 6 September 2026).

Each chart states the original latest observation's date and value. The current latest reading is shown separately, so it can advance as data arrives. The dashed lines always use the **original** anchors, not the newest observation. If actuals continue beyond the forecast horizon, no new forecast is invented.

There is no automatic data importer running yet. A data refresh must append valid, consistently defined observations and update the public downloads/source manifest; it must preserve the original freeze files and source archives. The existing El Niño builder reproduces the September snapshot with an explicit cutoff, which must be advanced as part of a future import. Source revisions should be identified separately from new observations. Use a new, explicitly labelled forecast version if assumptions are ever changed.

## Shared data calendar

The main page at `/#calendar` is the calendar for all trackers. Edit `data/release-calendar.json` to add or revise releases. Each entry has a tracker (`ai` or `el-nino`), frequency, source link, covered period and either an exact `date` or a `month` with an expected-window status. Use an exact date only when confirmed by the source. Daily and weekly entries are excluded. The downloadable calendar is synchronised during the build. Keep checked dates current; the page currently covers the remainder of 2026.
