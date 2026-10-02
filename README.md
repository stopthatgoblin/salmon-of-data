# Salmon of Data

A local, editorial-style website with a tracker directory, About section, Markdown blog and eight-tab El Niño impact tracker and the fully integrated eight-tab AI displacement tracker, including its release calendar.

## Local preview

Use Node 22.13 or newer (tested with the bundled Node 24 runtime).

```sh
npm install
npm run build
npm start
```

Open http://127.0.0.1:3100/. The finished static site is in `dist/client`. No public deployment or domain change has been made.

For editing with live updates, stop the static preview first, then run:

```sh
npm run dev
```

This uses the same port. Markdown additions, edits and removals are watched automatically by the development server. After editing, `npm run build` refreshes the static version served by `npm start`. Refresh the browser after rebuilding the static site.

If the system Node is older, first select the bundled runtime:

```sh
export PATH="/Users/peterdonaghy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH"
```

## Add a blog post

1. Copy `content/post-template.md` into `content/posts/`, for example `content/posts/what-the-september-data-shows.md`.
2. Set the quoted `title`, `date` (YYYY-MM-DD), `author`, `excerpt` and optional `tag`.
3. Write Markdown below the closing `---`. Headings, paragraphs, links, lists, quotes, tables, images and code blocks are supported. Put local images under `public/images/` and refer to them as `/images/name.jpg`.
4. Remove `draft: true` (or set it to `false`) to include it in the blog. The filename becomes the URL slug; posts sort newest first by the frontmatter date (equal dates sort alphabetically by filename). Dates label posts; they do not schedule publication.
5. The development preview picks up the change automatically. For the static preview, run `npm run build` and refresh the page.

The existing “Why I built this tracker” article was copied verbatim from the AI tracker's human-authored post. No new blog article has been written on Peter's behalf. `content/post-template.md` is outside the published posts directory and is never shown as a post. Raw HTML is escaped by the Markdown renderer.

## Tracker data and scenarios

- `data/raw/`: original public downloads retained for reproducibility.
- `scripts/build-data.py`: source parsing and chart-data generation (Python with openpyxl).
- `data/dashboard.json`: chart-ready snapshot.
- `public/data/*.csv`: full downloaded history for each metric plus labelled scenario checkpoints.
- `public/data/scenarios-v1.json`: original frozen anchors and checkpoint values, dated 7 September 2026. The builder reuses this file and does not overwrite it.
- `public/data/sources.json`: source URLs, download URLs, retrieval date and SHA-256 hashes.

The September edition uses downloaded public observations, never simulated history. Nominal world commodity benchmarks are monthly averages. RONI points are three-month seasons labelled by their middle month. The retired South African maize data is retained in the frozen source archive but is no longer displayed.

High/Medium/Low lines are **judgement-based conditional scenarios**, not fitted forecasts, probability bands or identified causal estimates. Prices show total changes, including non-El Niño influences. Monthly scenarios interpolate linearly between saved checkpoints. In the harvest panel, high impact means a *lower* yield. Climate projections stop in July 2027; prices allow recovery through August 2029. The El Niño charts show 2023 history and the full projection horizon, with no Focus toggle. El Niño is the first tab. The maize harvest panel has been retired; its original frozen data remains archived. Dollar axes use whole-dollar ticks; sugar uses whole US cents/kg so small price differences remain readable.

This is a dated snapshot, not an activated live-import pipeline. To reproduce it:

```sh
/Users/peterdonaghy/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/build-data.py
```

The builder's source cutoff is intentionally explicit. Future data updates should archive new source files, advance the cutoff and retrieval date, and preserve `scenarios-v1.json` and the original raw archive. New observations can cross the original forecast date without rebasing scenario paths. If scenario definitions change, publish a new version and explain it rather than overwriting v1.

## Validation

```sh
npm run check
npm run build
node scripts/check-site.mjs
```

`check` verifies TypeScript and the meaningful chart invariants: stable original anchors after future observations, missing-data gaps, annual harvest treatment, scenario ordering and finite horizons. `check-site` checks the exported routes, referenced local assets, downloadable data and the copied blog post. The retained source files make the data transformation reproducible.

## Integrated AI tracker

- `/trackers/ai/`: all eight original metrics, definitions, scenario explanations, checkpoints and source notes.
- `/#calendar`: shared main-page release calendar for both trackers; confirmed dates and expected windows are distinguished. The old `/trackers/ai/calendar/` address links here.
- `data/ai/dashboard.json`: observed AI metric series.
- `public/data/ai/`: all original public downloads, frozen definitions, worked example and CSVs.
- `data/ai/raw/`: full original source archive.
- `docs/ai/`: original metric audit and publication notes.
- `archive/ai-original/`: original README and scripts retained as archival references; their original relative paths refer to the old project and are not this site's active build commands.

Both trackers read their forecast anchors and paths directly from their immutable freeze files, separately from their current observations. Appending actuals extends the solid line; it does not recalculate the dashed forecasts. Each panel displays the original data period and value available when the forecast was frozen. AI's original freeze is 6 September 2026; El Niño's is 7 September 2026.

See `EDITING.md` for page wording, blog ordering and data-update guidance.
