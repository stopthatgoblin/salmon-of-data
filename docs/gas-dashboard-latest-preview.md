# Second local gas preview

Created on 10 November 2026 from public sources fetched beginning at 20:31 UTC.

- New version: `http://localhost:3100/dashboards/ireland-gas/latest/`
- Original 8 November snapshot: `http://localhost:3100/dashboards/ireland-gas/`

The second version uses the newest completed gas day, **9 November 05:00 GMT to 10 November 05:00 GMT**. It is another static snapshot, not an unattended feed. No publication, Cloudflare configuration or scheduled collector was created.

## Values

| Quantity | GWh |
| --- | ---: |
| Moffat physical inflow | 228.741666 |
| Corrib / Bellanaboy physical inflow | 21.461531 |
| ROI Moffat commercial allocation | 160.598047 |
| NI commercial allocation | 68.572413 |
| North-South physical flow towards NI | 1.309444 |
| ROI reported total gas consumption | 177.705839 |
| ROI reported power gas | 115.361700 |
| ROI other gas, calculated difference | 62.344139 |
| NI modelled power gas | 40.513168 |
| NI other use and balancing, allocation residual | 28.059245 |
| NI gas-fired electrical output | 14.341447 |
| NI electricity demand | 23.232750 |
| ROI gas-fired electrical output | 51.216888 |
| ROI electricity demand | 109.058250 |

Gas-fired output equals approximately **61.73% of NI electricity demand** and **46.96% of ROI demand**. The cards state the regional denominators explicitly. These are generation-to-demand comparisons, not a tracing of where particular generated electricity was consumed.

The power-use summary changes from about two-thirds on 8 November to **about 63%** on 9 November. North-South changes from zero/no arrow to **1.3 GWh towards NI**, with a direction arrow. Reported commercial allocations are retained as reported; the separate physical North-South transfer is not added to the NI allocation without verification of that allocation's accounting boundary.

## Electricity timing

The new SEMO D+1 report is `PUB_DailyMeterDataD1_202611101500.xml`, with publication time 10 November 15:00:01. It covers the 9 November calendar day. The gas day therefore has **19 metered hours plus five hours estimated from dispatch instructions**, ending at 05:00 on 10 November. The previous calendar day's full report and retained NI meter history supply startup context. Actual gas firing of multi-fuel units is assumed.

NI uses the same six-unit heat-input/startup model and 1.11 gross/net conversion as the first preview. ROI electricity includes 42 gas/multi-fuel unit identifiers with meter coverage, excluding battery GU_404270. Gas use remains reported for ROI and modelled for NI. The original 8 November JSON was not overwritten.

## Capacity references

| Shown item | Daily numerator | Published reference | Ratio |
| --- | ---: | ---: | ---: |
| SNIP inlet / NI entry reference | Twynholm physical inflow 66.520556 GWh | Moffat (NI) firm technical entry capacity 89.280 GWh/day | 74.51% |
| ROI via Moffat | ROI Moffat allocation 160.598047 GWh | Moffat technical entry capacity 433.368 GWh/day | 37.06% |
| Corrib / Bellanaboy | Bellanaboy physical inflow 21.461531 GWh | Bellanaboy technical entry capacity 103.870 GWh/day | 20.66% |

The capacity panel and its dedicated definitions section were removed from both local previews on 12 November at the user's request. The following capacity research is retained as historical evidence and is not displayed in the dashboard. [ENTSOG's PTL data](https://transparency.entsog.eu/api/v1/operationaldatas?operatorKey=UK-TSO-0002&pointKey=ITP-00496&directionKey=entry&indicator=Firm%20Technical&periodType=day&from=2026-11-09&to=2026-11-10&limit=20) gives the NI reference. Its validity period covers the selected gas day. Twynholm firm capacity is explicitly marked not applicable because PTL does not sell capacity there; the SNIP number is consequently labelled as a **NI entry reference**, not a verified hydraulic maximum for SNIP. The inlet numerator also includes the Stranraer offtake.

[GNI's firm-capacity portal](https://www.gasnetworks.ie/about/data-transparency/capacities/firm-capacity-entry-points) supplies the Moffat and Bellanaboy references, selected by the gas-day date. The Moffat ratio uses the ROI commercial allocation, rather than dividing aggregate Scotland physical flow by ROI entry capacity. It does not establish separate IC1 or IC2 utilisation. No measured individual flow split and corresponding operational per-pipe limit have been verified. Gormanston's separate entry-point capacity is not relabelled as IC2 pipe capacity.

These percentages describe daily quantities relative to published entry references, not hourly peaks, capacity bookings or remaining spare hydraulic capability. Individual source URLs, numerator definitions, capacity values, percentages and caveats are retained in the downloadable snapshot's `capacityReferences` array.

## Design and implementation

Both versions share the dashboard component with a typed snapshot/context rather than separate copies of the presentation. There are comparison links between them. Date, totals, summary, arrow direction, sources and attribution extraction date derive from their respective snapshot.

Dark mode reuses the electricity dashboards' toggle, palette and saved `electricity-theme` preference. Gas-specific map, cards, charts and dialogs have matching dark styles. IC1 and IC2 have labels using the SNIP label treatment, positioned alongside their corresponding routes. The NI label remains inside western NI, without a leader line. All gas text uses ordinary hyphens, including North-South.

## Reproduction and checks

Source captures and their URL manifest are retained locally under `outputs/gas-feasibility/static-2026-11-09/`. They are ignored research evidence, not public source assets. The initial NI demand response was empty; a retry using the electricity collector's `Eirgrid-Content-Request: Nextjs` header returned both calendar days. Both regions have all 96 required quarter-hours over the selected gas day.

Rebuild the snapshot offline with:

```sh
python3 -m electricity.research.ni_gas.build_static_snapshot \
  --gas-day 2026-11-09 \
  --source-dir outputs/gas-feasibility/static-2026-11-09 \
  --capacity-references
```

The assembler checks meter coverage, a contiguous estimated tail, hourly physical-flow agreement, unique dated actual gas values, and source intervals/missing flags. It preserves the NI residual and uses no fitted adjustment to make the balance close. The production frontend build, TypeScript check, 51 repository tests and NI heat-model tests pass. Desktop and 390px phone review cover light/dark themes, theme persistence, the original/new comparison, calculation dialogs and capacity source explanations. No horizontal overflow or browser errors were observed.

Screenshots are retained in the source-capture directory as `dashboard-latest-dark-overview.jpg`, `dashboard-latest-dark.jpg`, `dashboard-latest-light.jpg` and `dashboard-mobile-dark.jpg`. The latest browser tab is left on the new preview in dark mode.

## 12 November local revision

Removed the published capacity-percentage panel and its dedicated source explanation from the shared dashboard, including unused styles. IC1, IC2 and SNIP map labels, regional electricity-demand shares and the frozen 9 November data are retained. The source snapshot still contains its original capacity research metadata. No production collector, deployment or schedule was added.

Rebuilt the production frontend and passed TypeScript plus all 51 existing repository tests. Restarted the retained localhost server on port 3100 and verified both routes return HTTP 200. Browser review confirmed the removed sections are absent from the overview and definitions, with light/dark switching intact. Evidence: `dashboard-no-capacity-dark.png` (full page) and `dashboard-no-capacity-proof.png` (map and usage transition). A detailed, undeployed implementation and Cloudflare launch plan is in `docs/gas-dashboard-launch-guide.md`.

## 12 November network verification

Checked the physical connections against [GNI's interconnector description and map, page 20](https://www.gasnetworks.ie/sites/default/files/2025-11/Action-17-SGER-Detailed-Proposal-April-2024-Strategic-Case.pdf#page=20), [the GNI survey contractor's named landfalls, page 2](https://www.awjmarine.co.uk/wp-content/uploads/2021/06/CS0600_GNI_PipelineInspection_NtM_TitanDiscovery.pdf#page=2) and [Mutual Energy's SNIP description](https://www.mutual-energy.com/gas/).

The original single Scottish trunk was a simplification: Beattock and Brighouse Bay have two onshore pipelines. SNIP takes off at Twynholm towards Ballylumford. IC1 leaves Brighouse Bay for Loughshinny, Co. Dublin; IC2 leaves for Gormanston, Co. Meath, and supplies the Isle of Man through a spur to Glen Mooar.

The local map now depicts the two Scottish pipes and Beattock, names the offshore routes explicitly in its geometry, and shows the Isle of Man spur in a darker colour in both themes. IC2 passes on the Isle of Man side of IC1 near the spur and then crosses to the Gormanston route, following the rough layout in GNI's map. A background casing distinguishes the drawing's crossing from the actual marked spur tee. The geometry remains schematic and is not an engineering or surveyed route. No separate IC1/IC2 or Isle of Man flow is inferred. Snapshot numbers are unchanged.

Source evidence is retained locally under `outputs/gas-feasibility/network-check/`. The dashboard's calculation/source details now link the network references as well as the flow sources.

Validation: the production build, TypeScript and 51 existing tests pass. Desktop light/dark review confirmed the two onshore pipes, correct IC1/IC2 landing labels and darker spur, and the pipeline-layout source explanation opens correctly. Screenshots are `dashboard-network-light.png` and `dashboard-network-dark.png` in the network-check directory.

## 12 November follow-up: Scottish inlet detail and light-theme spur

Lightened the Isle of Man spur in the light theme to a muted blue-grey; its label retains the normal readable muted text colour. Dark-theme colours are unchanged.

The previous drawing's short single Moffat-to-Beattock segment was schematic and did not establish the actual inlet pipe count. The public sources reviewed confirm the two pipes downstream of Beattock, not the complete internal inlet configuration. The map now groups Moffat entry and nearby Beattock compressor as one schematic point, omitting unverified inlet pipework.

Added Kirkcudbright as a geographic landmark beside the easterly onshore route, without a terminal dot. It is not labelled as a separate IC2 terminal or independent route: [GNI's current Scottish-system description](https://www.gasnetworks.ie/about/projects/south-west-scotland-onshore-system-security-upgrade) explicitly identifies an interconnection at Cluden. [GNI's July 2025 emergency plan, section 3](https://www.gasnetworks.ie/sites/default/files/2025-09/Natural-Gas-Emergency-Plan-2025.pdf) confirms the pair of Beattock-to-Brighouse pipes, the Brighouse compressors and Twynholm offtake. [The original second-interconnector environmental statement, section 1.10](https://www.eib.org/attachments/registers/76879216.pdf) places the NTS connection adjacent to Beattock and distinguishes the nearby Moffat town from the entry infrastructure. It is historical design evidence, not a current inlet inventory.

Snapshot quantities and offshore landing points are unchanged. The map description, Scottish flow note and source explanation now state what is grouped and what pipework is omitted.

The production build and browser check pass. Verified the lighter light-theme spur against the main pipe colour, the combined entry/compressor point, two outgoing Scottish pipes and Kirkcudbright label. Evidence: `outputs/gas-feasibility/network-check/dashboard-lighter-spur.png`.

## 12 November source-map correction

The user's crop of GNI's published map makes the paired Scottish routes from Moffat clear. The local map now follows that overview instead of grouping Moffat and Beattock. Moffat is the common entry point, Beattock and Brighouse Bay are labelled separately as compressor-station locations, SNIP takes off at Twynholm and the two offshore interconnectors retain their existing landing points. Kirkcudbright remains a geographic label.

The Scottish pair and the continuation to IC1/IC2 are a faithful schematic representation of the published overview. This does not imply that the drawing resolves individual station inlet pipes or valves, or that the two onshore routes are operationally independent; GNI identifies their interconnection at Cluden. The previous combined-node presentation is superseded. The lighter Isle of Man spur in the light theme is retained.

The production build and TypeScript check pass. Desktop browser review confirms separate Moffat/Beattock labels, the paired routes and retained spur styling. Evidence: `outputs/gas-feasibility/network-check/dashboard-source-map-aligned.png`.
