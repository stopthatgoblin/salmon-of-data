# A public-data proxy for NI power-station generation

The public dispatch feed supports a useful **last published instructed output**
proxy for the three main thermal stations. A two-day historical check is promising,
but the result should not be presented as measured live generation.

## Initial accuracy check

Evaluation: **28–29 October 2026**, 96 half-hour periods per station. The proxy used
only reports already published at each point in time. Actual metered output was
used later for scoring. This is an initial test, not a general accuracy guarantee.

| Station | Mean absolute error | 90th percentile error | Largest error |
|---|---:|---:|---:|
| Ballylumford | 14.9 MW | 44.8 MW | 71.2 MW |
| Kilroot | 13.5 MW | 47.4 MW | 116.2 MW |
| Three-station total | 23.3 MW | 64.6 MW | 118.1 MW |

Coolkeeragh was at zero output throughout both days. Its zero error provides no
evidence about accuracy when it is running. Both Ballylumford and Kilroot were
generating in every scored half-hour.

![Dispatch proxy compared with metered output](validation.png)

New instructions in the downloaded sample became public between
**15.1 and 74.5 minutes after issue**, with a median
delay of **45.3 minutes**. Scheduled future instructions can be
known before their effective time; the delay applies to disclosure after issue.

Publication lag matters. Reconstructing the same stepwise targets retrospectively,
after the hourly batches arrive, reduces mean error to
**10.2 MW for Ballylumford** and
**3.1 MW for Kilroot**. Those figures
are a diagnostic for a delayed instructed-output chart, not a live accuracy score.

## What the prototype calculates

1. Initialise each of 13 mapped thermal units from an earlier metered half-hour.
   The seed report covered 26 October and was public on 27 October, before the
   evaluation started. Non-zero seeds were superseded by dispatch commands before
   any evaluated minute used them.
2. Read hourly dispatch batches, retaining their original publication timestamps.
   There are 136 downloaded hourly reports and no
   missing issue-hour windows between the first and last report in this sample.
3. Pair MW targets with matching synchronisation/desynchronisation commands.
   A missing numeric field is unknown, rather than zero. Explicit desynchronisation
   or trip instructions set the target to zero.
4. Use a command only when both its publication time and effective time have
   passed. Carry the last published numeric target forward until a new command
   takes effect. Explicit expiry produces an unknown state.
5. Sum units into Ballylumford, Coolkeeragh and Kilroot. No scaling is applied to
   force the three stations to equal the grid's total other-generation estimate.
6. Compare one-minute samples, averaged over each nominal half-hour, with later
   metered readings. The guide defines the XML field `MeteredMW` as interval MWh:
   half-hour values are multiplied by two to compare average MW. Some XML end
   times end in `:29:59`; these remain nominal 30-minute settlement periods.

The implementation includes causality checks: an unpublished command cannot
alter an earlier estimate, an explicit unknown state remains unknown, and a
missing unit cannot silently contribute zero.

## Where the proxy is weakest

- **Start-ups:** a target is not confirmation that a unit has reached it. On
  28 October Ballylumford B10 had a 63 MW synchronisation target, but its metered
  early output was much lower. The prototype's instantaneous step is deliberately
  simple and overstates this part of the start-up.
- **Unpublished changes:** a new dispatch or trip can remain invisible until the
  next hourly batch. This caused much larger errors than the typical steady-output
  difference. Kilroot's largest observed half-hour error was
  116.2 MW.
- **Ramping and control response:** the prototype has no physical start-up curve,
  ramp-rate model or automatic frequency-control response. The inspected daily
  instruction records had zero ramp-rate fields, so these were not treated as
  usable physical ramp rates.
- **Instruction amendments:** this is not the full Trading and Settlement Code
  profile algorithm. Production use needs a fuller treatment of cancellations,
  competing future instructions and special operating modes.
- **Coverage:** this pilot covers the mapped thermal stations, not all NI plant.
  Wind/solar dispatch commands can be limits rather than achieved output. Their
  generation should continue to come from the aggregate generation feeds.
- **Clock changes:** the selected evaluation is outside the clock-change day.
  Production code must resolve offset-free market timestamps around DST changes.

## Recommended public display

Use the label **Estimated station output — latest published dispatch targets**,
with the latest batch publication time and the issue-hour coverage shown beside
the chart. Display start-up/shutdown instructions as status notes. Mark gaps and
stale feeds explicitly, and suppress a station total if any constituent unit's
state is unknown.

Keep the original seven-series grid overview. Add station targets as a separate
operational view and replace history with metered actuals when those arrive.
Keep generation outside these stations as a separate unallocated component.
Do not describe the observed errors as a guaranteed confidence interval.

## Reproduction and files

Run `python3 collect.py`, then `python3 analyse.py` from this directory (or invoke
them by path). Downloads are cached under `cache/`. `manifest.json` records the
source files, their publication times and the collection time. `validation.csv`
contains each scored station half-hour; `summary.json` contains metrics, initial
states and a last-known-target snapshot. The snapshot is a calculation from the
downloaded sample, not a continuously running service.

`report.py` recreates this report and chart; chart generation requires matplotlib.

## Public sources

- [SEMO report portal](https://www.sem-o.com/market-data/static-reports)
- [Current SEMO Data Publication Guide, issue 3.5](https://www.sem-o.com/market-messages/release-op-updated-its-and-dpug):
  BM-160 hourly accepted dispatch instructions and BM-086 metered generation.
- [Hourly dispatch report index](https://reports.sem-o.com/api/v1/documents/static-reports?name=PUB_HrlyDispatchInstr&sort_by=PublishTime&order_by=DESC&page_size=1)
- [Metered generation report index](https://reports.sem-o.com/api/v1/documents/static-reports?name=PUB_DailyMeterDataD1&sort_by=PublishTime&order_by=DESC&page_size=1)
- [SONI station/unit lookup published for 2025–26](https://www.sem-o.com/sites/semo/files/2025-09/2025%20-%2026%20NI%20CLAF%20Publication%20v1.pdf).
  These 13 identifiers were checked against the October 2026 unit and meter reports;
  the mapping must be maintained for new or changed units.
- [Open Data Licence](https://www.smartgriddashboard.com/all/open-data-license/).
  Supported by EirGrid Group Data.
