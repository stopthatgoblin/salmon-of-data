# Island of Ireland gas dashboard: data feasibility

Investigated on **9 November 2026** using operators' public websites, live JSON
responses, ENTSOG reporting-point metadata, and the existing electricity collectors.
This is a sourcing investigation, not a dashboard implementation.

## Historical validation now available

A [first backtest against GMO NI's published September report](../electricity/research/ni_gas/BACKTEST.md)
covers 21 complete gas days, 10-30 September 2026. Without fitting heat-rate or
conversion parameters to those reference values, power-sector gas estimates have
approximately **0.19 GWh / 0.8% mean absolute daily error**. The allocation-based
non-power residual has approximately **0.34 GWh / 2.7% mean absolute daily error**
against the report's total-minus-power reference. Reference values were extracted
from PDF vector charts and have limited precision. This supports feasibility of
the estimated NI split, while leaving longer-period and seasonal validation open.

## Worked NI unit-specific gas estimate

The requested unit-specific approach has now been tested against a complete
archived gas day. The [NI estimate research note](../electricity/research/ni_gas/README.md)
documents the model, unit mappings, calculation and reproduction commands.
Public 2024-2032 SEM PLEXOS heat-input curves and startup fuel values were matched
to six gas-fired SEMO units. Seven distillate units were excluded.

For gas day **4 November 2026, 05:00 GMT to 5 November, 05:00 GMT**, the calculation
gives **29.096 GWh estimated power-sector gas input**. GNI's NI entry allocation was
**58.591 GWh**, leaving **29.496 GWh non-power/system-balancing residual**. Both
derived quantities need estimate labels. The result uses actual metered electrical
output; fuel input remains modeled. Normal gas firing and an approximate 1.11
gross/net gas-energy conversion are assumptions. Some Ballylumford output falls
below the model's stable-load range, so this example demonstrates feasibility and
does not establish a calibrated accuracy bound.

## Clarification: daily all-island dashboard

A daily refreshed all-island dashboard is feasible with **operator-reported ROI
consumption and explicitly estimated NI power/non-power usage**. A fully
operator-reported daily consumption split for both jurisdictions has not been
verified. Moving the refresh to daily does not itself close the NI sourcing gap.

Further checks found:

- GMO NI's [September 2026 monthly demand report](https://www.gmo-ni.com/site/wp-content/uploads/2026/10/Demand-Slide_Sep-26.pdf)
  contains charts of NI total, power and distribution demand by day. This confirms
  the operator holds a daily split, but the checked public publication is monthly,
  not an automated previous-day data feed.
- Previous-day ENTSOG queries for PTL (`UK-TSO-0002`) and GNI (UK)
  (`IE-TSO-0001`), requesting daily Physical Flow and Allocation, returned the
  previously identified physical points. They did not provide a numeric daily
  power-station consumption series or complete NI sector consumption allocation.
- Legacy Belfast Gas and BGE (NI) point-inventory queries returned 404. This does
  not prove that no other public or operator-provided dataset exists.

The feasible initial specification is: daily physical supply/transfer figures for
Moffat, Corrib, Twynholm/SNIP and North-South; qualified ROI import attribution;
GNI's ROI power and non-power consumption; and estimated NI power demand and a
qualified NI non-power/system-balancing residual. If estimating NI power use,
prefer complete published metered electrical output for the matching gas day
where available, while retaining the uncertainty in fuel choice, heat rates,
startup fuel and CHP. Existing dispatch estimates alone do not measure gas use.

Supply entry quantities must not be described as NI consumption without boundary,
linepack and other adjustments. An all-island usage total combining reported ROI
data with estimated NI data also needs an estimate label.

Use the latest common complete gas day for the comparable daily view and show
each source's publication/collection time. Some checked daily ENTSOG queries also
returned the current gas day's partially accumulated flow, even with status
`Confirmed`; that status does not establish a completed daily total. Source
publication delays may make the latest usable common date older than yesterday.

## Clarification: combined ROI imports and previous-day consumption

The user's follow-up asks about **IC1+IC2 combined, excluding the Isle of Man**,
rather than requiring the two pipe flows separately. A useful hourly upstream
proxy is Moffat physical flow minus Twynholm physical flow. The sampled hour gives
10.577778 - 3.055833 = **7.521945 GWh**, before Isle of Man offtake, network own-use
and changes in the Scottish/subsea system's gas inventory. Because Twynholm is
upstream of Stranraer, subtracting Twynholm already removes the Stranraer supply;
do not subtract it again. An independently verified hourly Isle of Man physical
offtake and the relevant inventory changes are still missing, so this does not
establish exact hourly delivery at the two ROI landfalls. Gas delivered into ROI
through IC2 can subsequently move to NI through the North-South Pipeline; distinguish
gross landfall arrivals from net gas retained for the ROI market.

The daily commercial-entry feed separates Moffat, NI and Isle of Man allocations.
Its Moffat allocation is the useful ROI-attributed commercial quantity, rather than
a substitute for measured IC1+IC2 landfall flow. For gas day 8 November, it reports
Moffat 173.358519 GWh, NI 55.317743 GWh and Isle of Man zero. The zero Isle of Man
allocation has not been independently established as physical zero demand. Do not
assume a commercial allocation has the same boundary, timing or revision status
as the upstream physical series.

For the main **ROI consumption** display, prefer GNI's previous completed gas-day
sector consumption/allocations to converting electricity dispatch estimates back
to gas input. A fresh `gasconsumption?date=2026-11-09&frequency=daily` request
returned both forecasts and separate `Gas Consumption by Market Sector` series.
For gas day **8 November 2026, 05:00 to 9 November 2026, 05:00 GMT**:

- ROI total = DM + NDM + ROI LDM = **187.196358 GWh**.
- ROI Power Gen = **130.961389 GWh**.
- ROI non-power = total minus Power Gen = **56.234969 GWh**.

These are operator-reported daily figures, subject to the source's allocation
and revision process. They remove the electricity-to-gas efficiency assumptions
and avoid using supply-minus-power as a consumption residual.

This trades hourly detail for a stronger daily demand basis. Querying yesterday
with `frequency=hourly` returned 24 points but still only forecast end-of-day and
forecast cumulative throughput series. Waiting a day does not turn that endpoint
into independently measured hourly sector consumption. Refresh recent gas days
to pick up revisions and show the latest complete available day rather than
guaranteeing yesterday by a particular publication time.

This is **ROI**, not an established all-island power/non-power split. GNI's glossary
explicitly says Total LDM includes NI and Isle of Man LDM sites, while ROI LDM
excludes them. Consequently, Total LDM minus ROI LDM must not be called NI power
demand. The original all-island specification still needs a matching NI sector
source or a separately labelled NI estimate.

## Finding

An hourly dashboard is feasible with qualifications. Corrib, aggregate Moffat and
the SNIP inlet have public hourly physical measurements. **Separate IC1 and IC2
physical flows were not found** in the GNI portal or the relevant ENTSOG point
inventories. An hourly supply-minus-power residual cannot be described as measured
non-electricity consumption without accounting for linepack and other adjustments.

| Requirement | Finding | Appropriate interpretation |
| --- | --- | --- |
| Corrib | Verified hourly delivered energy at Bellanaboy | Physical entry to the transmission network; not offshore well production |
| Moffat | Verified hourly delivered energy from GNI; National Gas also reports hourly physical flow on ENTSOG | Upstream aggregate flow; avoid adding the downstream SNIP flow again |
| SNIP | Verified hourly physical flow at Twynholm from Premier Transmission on ENTSOG | SNIP inlet in Scotland, before the Stranraer offtake and pipeline inventory changes |
| IC1 and IC2 separately | No public hourly measurement found | Draw the two routes, but do not invent their flow split |
| North-South Pipeline | Verified hourly physical flow at the South North CSEP | Transfer within the all-island system, not additional external supply |
| Capacity utilisation | Published technical capacities exist for entry points | Match each denominator to its reporting boundary; entry capacity is not necessarily physical pipe capacity |
| Power generation gas use | Feasible estimate from existing electricity unit estimates and unit-specific fuel-consumption assumptions | Estimated gas input, with uncertainty in dispatch, fuel choice, efficiency, starts and CHP |
| ROI power-sector gas use | Verified hourly-updated forecasts/estimated cumulative throughput, plus daily allocations | Useful independent comparison; hourly publication does not make these metered hourly actuals |
| Non-power use | Estimated ROI sector breakdown is available; all-island residual needs adjustments | Initially label as a residual including linepack/balancing rather than measured consumption |

## Live responses verified

For **19:00-20:00 GMT on 9 November 2026**:

| Series | Source quantity | Energy/rate |
| --- | --- | --- |
| Bellanaboy hourly delivered quantity | 903,869 kWh over the hour | 0.903869 GWh; average 903.869 MW thermal |
| Moffat hourly delivered quantity | 10,577,778 kWh over the hour | 10.577778 GWh; average 10,577.778 MW thermal |
| Twynholm physical flow, PTL | 3,055,833 kWh/h | 3.055833 GW thermal |
| Stranraer exit, PTL | 20,989 kWh/h | 0.020989 GW thermal |
| South North CSEP entry, GNI (UK) | 0 kWh/h | An explicit measured zero in this sample |

The GNI map response identified `valid_from=19:00`, `valid_to=20:00` and
`updated_at=20:46:41 UTC`. The corresponding PTL record's `lastUpdateDateTime`
was 20:33:49 UTC. Across 39 numeric Twynholm hourly records in the 8-9 November
query, the median last-update delay from interval end was **35.48 minutes**, with
a range of **33.5-136.15 minutes**. Last-update times may reflect revisions;
this small sample is not a publication service-level guarantee or a measurement
of first availability. Polling every 10-15 minutes can discover new hours but
cannot eliminate upstream publication delays.

National Gas's ENTSOG record for the same latest hour was 10,467,300 kWh/h,
marked provisional. Keep operator provenance and revisions; do not mix the two
Moffat editions into a single supposedly exact series.

## Access methods

These unauthenticated read requests returned JSON successfully during the investigation.
The GNI endpoints were identified from its own Drupal settings and chart JavaScript.
They are working website endpoints, not a verified versioned developer contract.

### Gas Networks Ireland

Base: `https://www.gasnetworks.ie/api/v1/`

| Endpoint/query | Result |
| --- | --- |
| `map` | Latest entry quantities, pressures, calorific values and explicit observation/publication timestamps |
| `physicalflows?date=2026-11-09&frequency=hourly` | Hourly delivered quantities, cumulative gas-day throughput and separately labelled nominations |
| `physicalflows?date=2026-11-09&frequency=daily` | Daily physical quantities, including the previous completed gas day |
| `gasconsumption?date=2026-11-09&frequency=hourly` | DM, NDM, ROI LDM and ROI Power Gen: forecast end-of-day quantities and forecast cumulative throughput |
| `firmcapacity?date=2026-11-09&frequency=daily` | Technical, booked and available capacity by entry point |
| `commercialentrypoint?date=2026-11-09&frequency=daily` | Daily commercial allocations, including Northern Ireland and Isle of Man |
| `commercialexitpoint?date=2026-11-09&frequency=daily` | Daily sector allocations, including ROI Power Gen |

The chart data are arrays of series with `name`, `location`, `group`, and
`data: [[epoch_milliseconds, value], ...]`. Select the exact group: hourly delivered
quantity, cumulative throughput and nominations are different measures. The hourly
query returned 15 elapsed-hour points from 05:00 through 19:00 on the test day.
Passing `frequency=hourly` to the commercial allocation endpoints still returned
daily points: inspect actual timestamps and intervals rather than trusting the
requested frequency.

The GNI map's `powerStations` section contains plant capacities, not live gas
consumption. Its Loughshinny strategic point had pressure/CV but no gas quantity.
The zero Gormanston entry quantity must not be relabelled as zero flow through IC2.

### ENTSOG / GMO Northern Ireland

Base: `https://transparency.entsog.eu/api/v1/`

Working discovery request:

```text
operatorpointdirections?operatorKey=UK-TSO-0002&limit=1000
```

Query each operator separately for metadata: the comma-separated metadata filter
attempted in this investigation returned 404; single-operator requests succeeded.

Working physical-flow query:

```text
operationaldatas?operatorKey=UK-TSO-0002&pointKey=ITP-00077&directionKey=entry&indicator=Physical%20Flow&periodType=hour&from=2026-11-08&to=2026-11-10&limit=200
```

| Operator key | Point key | Point/direction | Verified hourly physical data |
| --- | --- | --- | --- |
| `UK-TSO-0002` | `ITP-00077` | Twynholm entry | Yes, confirmed numeric records |
| `UK-TSO-0002` | `DIS-00017` | Stranraer exit | Yes |
| `UK-TSO-0002` | `DIS-00015` | Greater Belfast exit | Yes |
| `UK-TSO-0002` | `ITP-00298` | Carrickfergus exit | Yes; same transfer is reported as entry by GNI (UK) |
| `IE-TSO-0001` | `ITP-00222` | South North CSEP entry | Yes |
| `IE-TSO-0001` | `FNC-00044` | Ten Towns exit | Yes |
| `UK-TSO-0001` | `ITP-00090` | Moffat exit | Yes, provisional |
| `IE-TSO-0002` | `ITP-00495` | Moffat (IE) entry | Daily physical data verified; native GNI portal supplies the hourly series |
| `UK-TSO-0002` | `ITP-00496` | Moffat (NI) entry | Hourly physical records were N/A; use the physical Twynholm series |

Read `isNA`, numeric `value`, `periodType`, `unit`, offsets and `flowStatus`.
N/A records may occupy future hours and must not become zeros. Capacity records
may span years, even when filtering a single day. The tested `timeZone=UTC`
request still returned CET metadata and offset-bearing timestamps: parse the
actual offsets and normalize to UTC internally.

GNI's and PTL's reporting-point inventories contain no separate IC1/IC2 physical
measurement points. Moffat (IE) and Moffat (NI) are pipe-in-pipe reporting constructs;
they do not identify the two subsea interconnectors.

### Capacity

GMO NI's January 2026 technical capacity register, version 1.5, lists:

- Moffat NI IP entry: **89.28 GWh/day**, including 0.94 GWh/day reserved for Stranraer.
- South North IP entry: **66.30 GWh/day**, including 6.60 GWh/day reserved for the ROI system exit.

The live PTL ENTSOG daily technical-capacity record also returned 89.28 GWh/day
at Moffat (NI). It explicitly marks technical capacity at Twynholm as not applicable
because capacity is not sold there. The register says technical capacity may differ
from physical capacity.

For context, the sampled Twynholm rate is equivalent to 82.15% of the published
Moffat NI daily entry capacity after multiplying the hourly rate by 24. This would
need an explicit **published NI entry-capacity reference** label; it is not a verified
instantaneous SNIP hydraulic utilisation measurement. Do not call daily cumulative
throughput divided by a full-day capacity the current flow-rate utilisation.

The GNI capacity response included Moffat 433.368 GWh/day and Bellanaboy
103.870 GWh/day. Confirm the physical/commercial boundary before using Moffat's
capacity against an aggregate physical flow. No current per-IC1/per-IC2 operational
capacity series was verified.

## Power demand and residual methodology

The existing NI and ROI electricity collectors publish unit-level **dispatch-target
estimates**, not live gas meters. Gas input can be estimated by integrating each
gas-fired unit's electrical output over the matching hour and dividing by its
efficiency, or applying a load-dependent heat-rate curve. Account for startup fuel,
dual-fuel operation, missing units and CHP. Use a consistent gross/net calorific
value basis when comparing fuel input with the gas operator's energy figures.

GNI's hourly-updated ROI power-sector throughput is a useful independent estimate.
Within a single response, adjacent cumulative values can produce an implied hourly
increment, retaining its forecast/estimate status. Revisions mean this is not
automatically an independently metered hourly series. Do not subtract cumulative
values from different retrieval editions without checking revisions.

**ROI LDM includes power generation.** For a first operator-based ROI estimate:

```text
ROI total demand = DM + NDM + ROI LDM
ROI non-power demand = DM + NDM + ROI LDM - ROI Power Gen
```

Do not add Power Gen to LDM again. Daily commercial allocations provide a later
comparison. No matching public hourly all-island power-sector meter total was
verified.

For an upstream-connected-system balance, in consistent hourly energy units:

```text
non-power consumption = Moffat + Corrib + other injections
                      - Isle of Man demand - Stranraer demand
                      - power-sector gas consumption
                      - network own-use/losses
                      - increase in gas held within the chosen network boundary
```

This is a balance identity, not a verified complete set of public input feeds.
Using Moffat creates a boundary that includes Scottish/subsea pipe inventory.
**Do not add SNIP to Moffat**, or count the North-South transfer as another import
to the island. Do not assume today's zero/missing Isle of Man allocation proves
zero physical demand. Include biomethane/other injections where material.

Without the linepack adjustment, the residual includes changes in stored gas,
losses and estimation error. An hourly Irish/all-island linepack stock series was
not verified. GNI's `stockgas` endpoint returned stock-gas purchase/sale transactions,
not hourly physical inventory; it does not solve this problem. The initial label
should therefore be **non-power and system-balancing residual**. Gas-day totals
reduce within-day effects but still require accounting for stock changes.

## Physical map

Use a schematic of the connected network, with measurements attached to their
actual locations and unquantified links distinguished from quantified links:

- Moffat → Beattock → the southwest Scotland onshore system.
- Twynholm offtake → SNIP → Ballylumford/Islandmagee → wider NI network.
- Brighouse Bay compression → IC1 → Loughshinny, County Dublin.
- Brighouse Bay area → IC2 → Gormanston, County Meath, with the Isle of Man spur.
- Gormanston → North-South Pipeline → NI network.
- Corrib → Bellanaboy → the Irish onshore network.

Twynholm flow is not Ballylumford power station's gas consumption. Also, Moffat
minus Twynholm is not a measured IC1+IC2 landfall flow: intermediate storage,
own-use and other offtakes matter.

## Build recommendation and remaining verification

Proceed with an hourly measured-supply view using Corrib, Moffat and SNIP, a
physical route map, estimated power demand, ROI sector estimates, and a clearly
qualified residual. Leave the IC1/IC2 individual flow values unavailable.

Before committing to the full original specification, request clarification from
GNI about public/exportable hourly IC1 and IC2 measurements at Brighouse Bay,
Loughshinny and Gormanston, each pipe's capacity basis, the portal's Gormanston
entry-point semantics, hourly linepack and Isle of Man flow availability, and a
supported access/cadence contract. No operator has been contacted in this task.
Run a bounded multi-day collection to establish completeness, actual publication
timing, revisions and gas-day/DST behavior before promising an operational cadence.

## Primary references

- [GNI physical flows](https://www.gasnetworks.ie/about/data-transparency/entry-flows/physical-flows)
- [GNI live map JSON](https://www.gasnetworks.ie/api/v1/map)
- [GNI gas consumption by market sector](https://www.gasnetworks.ie/about/data-transparency/exit-flows/gas-consumption-by-market-sector)
- [GNI commercial entry allocations](https://www.gasnetworks.ie/about/data-transparency/entry-flows/commercial-flows)
- [GNI commercial exit allocations](https://www.gasnetworks.ie/about/data-transparency/exit-flows/commercial-exit-point-energy-allocations)
- [GNI firm capacities](https://www.gasnetworks.ie/about/data-transparency/capacities/firm-capacity-entry-points)
- [GNI glossary, including LDM, delivered quantity and gas-day conventions](https://www.gasnetworks.ie/about/data-transparency/glossary-terms)
- [GMO NI operational information and ENTSOG publication route](https://www.gmo-ni.com/operational-data/)
- [GMO NI technical capacity register, v1.5](https://www.gmo-ni.com/site/wp-content/uploads/2026/06/NI-Network-Technical-Capacity-Register-v1.5.pdf)
- [ENTSOG API manual v3.0, October 2025](https://transparency.entsog.eu/api/archiveDirectories/8/api-manual/ENTSOG_TP_API_UserManual_v3.0.pdf)
- [GNI Natural Gas Emergency Plan, July 2025, network description](https://www.gasnetworks.ie/sites/default/files/2025-09/Natural-Gas-Emergency-Plan-2025.pdf)
- [UK offshore regulator: IC1 Loughshinny and IC2 Gormanston routes](https://assets.publishing.service.gov.uk/media/60f01f118fa8f50c76838722/Gas_Interconnector_Pipelines_Rock_Stabilisation_-_PL-2077-0_-_GNI__UK__Limited_-_Decision_Date_15-07-2021.pdf)
- [Mutual Energy connection policy, SNIP and Stranraer assets](https://www.mutual-energy.com/wp-content/uploads/2021/05/Connection-Policy-October-2020-2.pdf)
- [Gasunie operator explanation of hourly entry/exit differences and linepack](https://www.gasunietransportservices.nl/en/shipper-trader/balancing-regime/damping)

Local electricity evidence: `electricity/dashboard/refresh_snapshot.py`,
`electricity/roi/collect.py`, `electricity/research/dispatch_proxy/REPORT.md`.
Raw investigation responses are retained under ignored
`outputs/gas-feasibility/2026-11-09/` in this checkout.
