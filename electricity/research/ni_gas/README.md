# NI daily power-sector gas estimate

A working, offline research calculation now combines **unit-specific metered
electricity output and public heat-input curves**. It supports the proposed
estimated NI power/non-power split. A [first 21-day historical comparison](BACKTEST.md)
against GMO NI's published charts gives about 0.8% mean absolute daily error for
power gas and 2.7% for the non-power residual. No parameters were fitted to those
reference data. The method is not connected to a production dashboard.

## Worked example

Gas day **4 November 2026, 05:00 GMT to 5 November, 05:00 GMT**. All 13 mapped NI
thermal units have 48 distinct metered half-hours in the archived source reports.
Use the source reports directly rather than assuming an electricity dashboard
calendar day matches a gas day.

| Unit | SEMO resource | Electrical output (GWh) | Estimated gas input (GWh gross) |
| --- | --- | ---: | ---: |
| Ballylumford B31 | GU_503720 | 2.268 | 6.499 |
| Ballylumford B32 | GU_503730 | 1.217 | 3.902 |
| Ballylumford B10 | GU_503740 | 2.209 | 4.862 |
| Coolkeeragh C30 | GU_500040 | 0 | 0 |
| Kilroot GT6 | GU_504110 | 4.123 | 13.833 |
| Kilroot GT7 | GU_504120 | 0 | 0 |
| **Total** | | **9.817** | **29.096** |

GNI's **Northern Ireland daily entry allocation** for the same gas day was
**58.591 GWh**. Subtracting the modeled power-sector gas input produces a
**29.496 GWh non-power and system-balancing residual**. That is a worked estimate,
not a separately metered NI consumption split. Do not relabel the entry allocation
as measured total NI end-user consumption.

The seven distillate units are excluded. The sample includes **0.079 GWh of
distillate-unit electricity**, demonstrating why summing all thermal station
generation would overstate gas-fired generation. Source market-unit names and
IDs are retained independently of a plant manufacturer's turbine labels.

## Unit-specific model

Source: the SEM Committee's public
[2024-2032 SEM PLEXOS model, published March 2025](https://www.semcommittee.com/publications/sem-25-010-sem-plexos-model-validation-2024-2032-and-backcast-report).
The public ZIP contains `PUBLIC Validation 2024-2032 Model 2025-03-14.xml`.
Its fuel-curve properties define a no-load base in GJ/h and incremental heat
rates in GJ/MWh at load breakpoints. The fuel rate at an observed MW output is
the base plus the integral of the marginal rates up to that output; it is zero
when output is non-positive. Apply the rate to each metered half-hour separately.

Selected source parameters (net/lower heating value basis):

| Model unit | No-load fuel (GJ/h) | Load breakpoint : marginal rate (MW : GJ/MWh) |
| --- | ---: | --- |
| B31, B32 | 336.7 | 113 : 5.73; 247 : 5.73 |
| B10 | 103 | 63 : 6.02; 101 : 6.02 |
| CPS CCGT / C30 | 635.4 | 211 : 4.21; 260 : 5.23; 310 : 5.25; 350 : 5.43; 404 : 5.49 |
| KGT6, KGT7 | 703 | 326 : 6.79; 345 : 10.9 |

For example, at 335 MW, a Kilroot unit's running fuel input is
703 + (326 × 6.79) + (9 × 10.9) = **3,014.64 GJ/h LHV**.
Using the full-load average efficiency at every load would lose this behavior.

The model also supplies fuel offtake at start. The B32 meter series shows an
inferred start at 08:00 on the sample day after nine hours offline; the model's
warm-start fuel is **1,134 GJ LHV**, included in its 3.902 GWh gross estimate.
There are no inferred starts for the other five gas units within this gas day.
The code uses the model's Three-State Start fuel values and cooling times.

The [model report](https://www.semcommittee.com/files/semcommittee/2025-03/SEM-25-010%20SEM%20PLEXOS%20Model%20Validation%202024-2032%20Backcast%20Report.pdf),
page 63 / PDF page 70, says generator heat rates are expressed on an LHV basis
and describes HHV energy as approximately 11% greater. This prototype multiplies
LHV fuel energy by **1.11**, then divides GJ by **3,600** to obtain GWh gross,
for comparison with the gas supply figures. This is an approximate conversion,
not a measured gas-composition conversion for each day. The [CSO's GNI-based gas
statistics](https://www.cso.ie/en/releasesandpublications/ep/p-ngdsd/networkedgasdailysupplyanddemandjanuary-march2026/backgroundnotes/)
use gross calorific values.

## Limitations that affect the residual

- Normal gas firing is assumed for the multi-fuel gas units. Their electricity
  meters alone cannot establish whether backup liquid fuel was used.
- Current derating and plant condition can differ from the 2025 model. In the
  sample, B31 has 41 and B32 has 20 half-hours below the model's minimum stable
  load. The affine fuel curves are extrapolated there and those counts are
  exposed in the JSON. This is a material reason to calibrate the estimate.
- Startup timing and offline duration are inferred from half-hour output. Actual
  startup fuel may begin earlier and may cross the gas-day boundary. The startup
  assignment is a research approximation, not a full PLEXOS operational replay.
- An entry allocation minus modeled gas use still contains changes in linepack,
  own-use and any differences in geographic/accounting boundaries. It is not a
  direct measure of households and industry.
- Missing unit half-hours or startup history stop the calculation; they do not
  become zero generation. A negative residual is preserved as a diagnostic.

An illustrative ±10% change in modeled power-sector gas use moves it to
**26.19-32.01 GWh**, and the residual to **26.59-32.41 GWh**. This is a sensitivity
scenario, not a measured confidence interval or a full assessment of error.

Before production, broaden the initial backtest across seasons and plant
conditions, refine the gross/net conversion and fuel assumptions, and establish
how the NI allocation boundary relates to consumption on individual days.
Keep the labels **Estimated gas used for electricity** and **Estimated non-power /
balancing residual** until those issues are resolved.

## Reproduction

The downloaded public model, intermediate parameters and sample output are under
ignored `outputs/gas-feasibility/unit-model/`. Retained public electricity report
derivatives are under `outputs/electricity-replay/reports/`; each records its SEMO
resource name and publication time. The misleading `MeteredMW` source field is
interval MWh: the existing parser converts it to half-hour average MW before
writing these derivatives. This script multiplies those averages by 0.5 hours,
so energy is not doubled.

From the repository root:

```sh
python3 electricity/research/ni_gas/estimate.py \
  --gas-day 2026-11-04 \
  --meter-cache outputs/electricity-replay/reports \
  --model 'outputs/gas-feasibility/unit-model/PUBLIC Validation 2024-2032 Model 2025-03-14.xml' \
  --allocations outputs/gas-feasibility/2026-11-09/gni-commercial-entry.json \
  --output outputs/gas-feasibility/unit-model/sample-2026-11-04.json

python3 -m unittest electricity.research.ni_gas.test_estimate -v
```

The output retains model parameters and checksum, unit estimates, startup events,
source editions, below-minimum/extrapolation counts and limitations. It uses the
local 05:00 gas-day boundary, including 23/25-hour gas days around clock changes.
It performs no network requests and does not change any live dashboard or schedule.
