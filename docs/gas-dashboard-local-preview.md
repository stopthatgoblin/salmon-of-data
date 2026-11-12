# All-Ireland gas: local design preview

Open `http://localhost:3100/dashboards/ireland-gas/`.

This is a fixed design snapshot for the gas day **8 November 2026, 05:00 GMT to 9 November, 05:00 GMT**. The route is excluded from indexing and is not added to the public homepage. No gas collector, schedule, hosting registration or publication was created.

The page uses the existing site's cream paper, Georgia headings, teal accents, salmon electricity colour and fine rules. It includes a Natural Earth map with the NI/ROI border, approximate pipeline routes, selectable supply explanations, regional usage cards, hourly physical supply bars, source definitions and a downloadable JSON snapshot.

## Snapshot figures

| Quantity | GWh | Basis |
| --- | ---: | --- |
| Moffat physical entry | 228.637223 | GNI daily physical flows |
| Corrib / Bellanaboy physical entry | 21.078546 | GNI daily physical flows |
| ROI Moffat allocation | 173.358519 | GNI commercial allocation; IC1/IC2 combined |
| NI entry allocation | 55.317743 | GNI commercial allocation |
| ROI gas consumption | 187.196358 | GNI reported DM + NDM + ROI LDM |
| ROI power gas | 130.961389 | GNI reported power sector, already included in LDM |
| ROI other gas | 56.234969 | Consumption minus power |
| NI power gas | 30.216027 | Unit-specific research estimate |
| NI other use and balancing | 25.101716 | NI entry allocation minus estimated power gas |
| NI gas-fired electricity | 10.106722 | Metered output plus dispatch estimate |
| ROI gas-fired electricity | 59.587543 | Metered output plus dispatch estimate |
| NI electricity demand | 20.165750 | 96 EirGrid/SONI quarter-hours |
| ROI electricity demand | 101.451000 | 96 EirGrid quarter-hours |

Gas-fired output divided by regional demand is approximately **50.1% NI** and **58.7% ROI**. This is a generation-to-demand comparison, not a claim that all locally generated gas electricity was consumed in that region.

## Electricity timing and estimates

The latest available SEMO D+1 report covers the calendar day 8 November. The matching gas day therefore has **19 metered hours and five estimated hours**, with the latter covering 00:00-05:00 on 9 November. The static assembly integrates retrospectively available dispatch targets, seeded from the final meter half-hour, to estimate those five hours. All electricity output totals and shares are labelled as estimates.

NI power gas uses the existing six-unit research model: no-load heat input, incremental heat rates, inferred startup fuel and an assumed 1.11 gross/net conversion. Gas firing is assumed for gas/multi-fuel units. Oil-only NI units are excluded. ROI electricity uses gas/multi-fuel technical-offer generator identifiers with meter coverage, excluding battery GU_404270. Actual fuel switching and CHP on-site consumption are not observed.

The one-off offline assembly is retained at `electricity/research/ni_gas/build_static_snapshot.py`. Run it from the repository root only when the downloaded research inputs are present in `outputs/gas-feasibility/`; it makes no network calls. It validates complete unit half-hour and demand quarter-hour coverage and reconciles hourly physical flows to daily totals. Public source URLs, unit contributions and assumptions are saved in `public/data/ireland-gas/2026-11-08.json`.

## Boundaries

Moffat's physical total includes NI and ROI downstream, the Isle of Man and Scottish offtakes. NI/ROI allocation labels do not establish exact physical landfall quantities or a separate measured IC1/IC2 split. SNIP physical entry at Twynholm includes the Stranraer offtake in Scotland. Isle of Man's zero commercial allocation is not treated as evidence of zero physical consumption.

ROI non-power use is calculated from reported consumption, not supply. NI's residual retains linepack, own-use, allocation and other balancing differences. Headline all-island usage combines ROI consumption with NI allocation and is explicitly qualified. These boundaries are explained on the overview and in the sources view.

## Local serving

Use Node 22.13 or newer. `npm run build` creates the static site; `npm start` serves it on loopback port 3100. The local preview is a built static site, so edits require rebuilding and reloading. Existing electricity collectors and production services are not started by this workflow.

## Verification

The production build and TypeScript check pass, as do all 51 existing repository checks. The snapshot's regional gas totals and electricity demand shares reconcile, and the 24 hourly physical flow values sum to the daily source totals. Browser review covered desktop and phone layouts, pipeline selection, calculation dialogs, hourly readings and source disclosures. No console errors were observed. The revised desktop screenshot is retained at `outputs/gas-feasibility/static-2026-11-08/dashboard-preview-v2.jpg`.

## Design revision and supply difference

The revised map removes internal ROI network routes and city markers. Coastal terminal labels use leader lines, the supply boxes have more space, and the North-South link is drawn separately from the SNIP and IC1/IC2 terminal connections. The cached ENTSOG/GNI (UK) report explicitly gives **zero** at South North CSEP entry for this gas day, so the map shows 0.0 GWh without a direction arrow. Source, date, indicator, missing-data flag and interval are validated in the offline snapshot assembly.

The displayed physical supply is **249.715769 GWh**; displayed usage/allocation is **242.514101 GWh**. The difference is **7.201668 GWh**. It cannot be presented as Isle of Man consumption. In addition to the differing boundaries of physical flows, commercial allocations and consumption, reconciliation needs Scottish offtakes, inventory changes, system use and revisions. The source separately reports **0.331826 GWh** for the Stranraer offtake. A standalone physical Isle of Man amount for this day has not been verified. Its zero commercial allocation does not establish zero actual demand. The difference is recorded as unreconciled in the downloadable snapshot.

The overview now links to GNI's data transparency portal and open-data/reuse policy, ENTSOG's platform terms and the EirGrid Group Open Data Licence. ENTSOG is attributed with the 9 November 2026 extraction date. EirGrid's licence covers the group and subsidiary bodies including SEMO, with the required attribution retained. GNI's open-data policy describes CC BY 4.0 for covered datasets but does not explicitly identify these operational API series; that specific coverage remains unconfirmed and is disclosed in the sources view. No provider approval or endorsement is claimed.

## Data-driven presentation and conversion ratios

The preview still imports the fixed 8 November JSON at build time. Publishing this build would not activate live updates. A daily collector plus a runtime snapshot feed or automated rebuild is still required.

Quantitative presentation now derives from that snapshot: dates and gas-day duration, the natural-language power-use summary, flow descriptions and accessibility labels, source extraction dates, metered/estimated hour counts, hourly axis labels and chart scale. The summary uses a familiar fraction only when the computed share is close enough; otherwise it shows a rounded percentage. Manual checks at 50%, 66.5% and 80% produce different appropriate summaries. Geography, explanatory methodology and the explicit static-preview status remain fixed by design.

Bellanaboy now includes Co. Mayo. The Isle of Man spur is removed. The revised IC1/IC2 curves run west of its coastline, with a minimum centre-line clearance of approximately 14 and 28 SVG map units respectively before stroke width; their hit targets follow the same curves. The latest desktop screenshot is `outputs/gas-feasibility/static-2026-11-08/dashboard-preview-v3.jpg`.

The implied electricity-output / power-gas-input ratios are **33.45% NI** and **45.50% ROI**, on the displayed gross gas energy basis. They differ from the cards' **50% / 59%** shares of regional electricity demand. Plant technology, loading, starts and gas/electricity accounting coverage affect the input/output ratio. On this snapshot Coolkeeragh is at zero and Kilroot contributes about 3.71 GWh of NI's 10.11 GWh gas-fired output; the ROI estimate is led by Aghada AD2, Great Island, Huntstown and Tynagh. NI gas is modelled and ROI gas is reported; CHP export coverage can also differ, so these ratios are not directly measured, audited regional fleet efficiencies.

The revised build passes all 51 existing checks and the static production build. Desktop and phone review confirmed the Mayo label, removal of the spur and no horizontal overflow. A fresh reload hydrates without new browser errors; UTC display labels are normalised to `GMT` consistently between server and client.

Technology references: [Kilroot operator: open-cycle gas turbines](https://www.epuki.co.uk/about/our-power-stations/kilroot/), [US Department of Energy: recovery of turbine exhaust heat](https://www.energy.gov/hgeo/how-gas-turbine-power-plants-work), [SEAI calorific-value conventions](https://www.seai.ie/data-and-insights/seai-statistics/conversion-factors).

## Latest layout and production review

The country labels are repositioned, with the Northern Ireland label entirely inside western NI and no leader line. The NI flow box is moved right and slightly up to leave space. The Republic allocation box is nearer the Dublin landfalls. The regional cards omit duplicate NI/ROI labels. Corrib shows its calculated share of displayed island gas use in the headline and map callout. Dashboard branding now uses the same 12px base size as the other charts. Gas dashboard text and research notes use ordinary hyphens, including North-South.

Reuse URLs now come from the snapshot's metadata alongside the existing ENTSOG extraction date. The power-use summary remains calculated from the snapshot; it is not fixed to two-thirds. This preview still requires a future collector and runtime feed to update dates automatically.

The collector design, 07:00 source-latency limits and initial September time-machine boundary are documented in [production options](gas-dashboard-production-options.md). No production setup or publication was performed.

The latest production build and all 51 repository checks pass. Desktop and 390px phone review confirmed clear label placement, the calculated Corrib percentage, larger branding and no horizontal overflow. Both overview and sources show no en/em dashes, and the reviewed tab reports no browser errors. Screenshots are saved as `outputs/gas-feasibility/static-2026-11-08/dashboard-preview-v4.jpg` and `dashboard-mobile-v4.jpg`.

The latest map revision was checked against the rendered text bounds: all 3,321 sampled points in its bounding rectangle lie within the Northern Ireland polygon. Desktop and 390px phone review show no label or flow-box overlap and no horizontal overflow. The production build passes. The latest images are `outputs/gas-feasibility/static-2026-11-08/dashboard-map-v5.jpg` and `dashboard-preview-v5.jpg`. The 19:00 refresh and calendar-day tradeoffs are recorded in the production options note; the preview retains its reported 05:00-05:00 period.
