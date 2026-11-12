# First historical NI gas backtest

**The unit-based method closely reproduces the operator's published figures in
this first 21-day comparison.** This is a retrospective validation, not a fitted
model or a guarantee of future daily accuracy.

## Published reference

[GMO NI's September 2026 demand report](https://www.gmo-ni.com/site/wp-content/uploads/2026/10/Demand-Slide_Sep-26.pdf),
linked from its [operational data page](https://www.gmo-ni.com/operational-data/),
contains three daily charts: NI total gas demand, NI power gas demand and NI
distribution gas demand. The blue/teal series represent September; orange is
August. The original report was downloaded on 9 November 2026.

The PDF retains vector paths with one vertex per day. `backtest.py` extracts the
30 September points from each chart and converts their vertical coordinates to
GWh using that chart's own zero and upper labelled gridline. It checks the page
title, dimensions, colors, point counts, spacing and gridline counts. The rendered
page was inspected to verify the series and axes.

These are **chart-derived approximate reference values**, not the underlying
operator spreadsheet or exact gas-meter readings. PDF coordinate rounding is
material when interpreting sub-percent errors. Percentages below are deliberately
rounded; the saved JSON's additional digits support reproduction, not additional
measurement precision.

## Period and inputs

- Requested: gas days **9-30 September 2026**.
- Accepted: **10-30 September**, 21 complete days.
- Excluded: **9 September**, because the available earlier meter history cannot
  establish the startup temperature category for one start. No day was removed
  on the basis of its estimation error.
- Every accepted day has all 48 metered half-hours for all 13 mapped thermal
  units. Six gas units enter the gas calculation; seven distillate units are
  excluded.
- Gas days use **05:00 Europe/Dublin to 05:00 the following day**; in September
  this corresponds to 04:00-04:00 UTC. GNI chart timestamps for daily allocations
  are encoded at 05:00 UTC even in summer, so those records are matched by their
  gas-day date label, rather than interpreted as interval-start instants.
- Unit curves and startup fuel come from the March 2025 public SEM PLEXOS model.
  The 1.11 gross/net gas-energy conversion is the same assumption used for the
  November worked example. **No heat rate, conversion factor or scaling parameter
  was fitted to the September report.**
- GNI's historical Northern Ireland commercial entry allocations provide the
  daily quantity from which the power estimate is subtracted for the residual.

## Results

| Quantity being checked | Mean absolute daily error | Mean absolute daily percentage error | Bias over the full 21-day total | Largest absolute daily error |
| --- | ---: | ---: | ---: | ---: |
| Estimated power-sector gas input vs published power demand | **0.19 GWh** | **0.8%** | **+0.5%** | **0.66 GWh** |
| Allocation-minus-estimated-power residual vs published total-minus-power | **0.34 GWh** | **2.7%** | **-0.9%** | **1.04 GWh** |
| NI entry allocation vs published total NI gas demand | **0.30 GWh** | **0.8%** | **+0.02%** | **1.09 GWh** |

Across the accepted period:

| Gas quantity | Operator reference | Model / allocation-derived value |
| --- | ---: | ---: |
| Power-sector gas | 487.47 GWh | 489.88 GWh |
| Non-power gas, calculated as total minus power | 267.95 GWh | 265.66 GWh |
| Total NI gas | 755.42 GWh | 755.54 GWh allocated |

The non-power reference is computed as **GMO NI total demand minus GMO NI power
demand**. It is not simply the distribution chart. The report's total is above
power plus distribution by approximately 0.54 GWh/day on average across the
whole September chart. The publication does not identify the reason for that
difference. Distribution-only demand is therefore not assumed to cover every
non-power/network item.

Metrics are calculated over matching accepted days. Mean absolute percentage
error is the average of each day's absolute percentage error. Aggregate bias is
the difference in period sums divided by the reported period sum; it is not the
same as mean daily percentage error.

## Interpretation

This provides useful evidence for an **estimated daily NI power and non-power
dashboard**. It also shows why non-power error can exceed power error: the NI
entry allocation differs from the report's consumption total on individual days,
even though their period sums are very close.

Keep the estimate labels and retain negative residuals or missing-data gaps.
The test covers part of one autumn month; it does not establish winter accuracy,
performance during unusual fuel switching, or the quality of every current
derating/startup condition. It uses retrospectively available metered electricity
reports, not a simulation of what was known at each day's first publication.
It therefore does not test dispatch-proxy accuracy, source latency or revisions.

The appropriate next validation is a longer, independently reported period
covering different seasons and plant combinations. Obtaining GMO NI's underlying
daily numbers would remove the PDF chart precision limitation. Broader testing
should preserve the present fixed model as the baseline; any later calibration
needs a separate held-out evaluation period.

## Reproduce and inspect

Run with a Python environment containing `pdfplumber` (the Codex bundled Python
runtime used here supplies it):

```sh
python3 -m electricity.research.ni_gas.backtest \
  --reference outputs/gas-feasibility/backtest/Demand-Slide_Sep-26.pdf \
  --allocations \
    outputs/gas-feasibility/backtest/gni-commercial-entry-2026-09-14.json \
    outputs/gas-feasibility/backtest/gni-commercial-entry-2026-09-22.json \
    outputs/gas-feasibility/backtest/gni-commercial-entry-september.json \
  --meter-cache outputs/electricity-replay/reports \
  --model 'outputs/gas-feasibility/unit-model/PUBLIC Validation 2024-2032 Model 2025-03-14.xml' \
  --output-dir outputs/gas-feasibility/backtest

python3 -m unittest electricity.research.ni_gas.test_estimate -v
```

Ignored evidence under `outputs/gas-feasibility/backtest/` includes the original
PDF, its inspected PNG render, allocation responses, extracted chart vertices,
per-day estimates with source editions/model parameters, and `comparison.json`
containing all 21 comparisons, exclusions, metrics and input checksums.

Two routine fixes were needed when extending the November example into summer
history: match GNI daily records by gas-day date label, and accept a cold startup
when a sufficiently long contiguous observed shutdown establishes its category
without requiring the exact last running time. Short ambiguous startup histories
remain excluded. The November example's 29.096 GWh power estimate is unchanged.
