# Recreate the recruitment metric in Excel

Prepared 6 September 2026. Definition and scenarios remain frozen at version 1.0.

## Original sources

Indeed Hiring Lab publishes these CSVs under CC BY 4.0:

- Sector indices: https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/job_postings_by_sector_US.csv
- All-US indices: https://raw.githubusercontent.com/hiring-lab/job_postings_tracker/master/US/aggregate_job_postings_US.csv
- Documentation and licence: https://github.com/hiring-lab/job_postings_tracker

The source repository can revise history. To reproduce this edition exactly, use the archived `data/raw/indeed-us-sectors.csv` and `data/raw/indeed-us-all.csv`. Their hashes are in the frozen registry. The downloadable `recruitment-excel-inputs.csv` is a pivot of those original input values, not the calculated dashboard metric.

## Worked example: 28 August 2026

| Input | Source index |
| --- | ---: |
| Software Development | 74.61 |
| Accounting | 96.65 |
| Marketing | 76.79 |
| Administrative Assistance | 95.03 |
| Customer Service | 88.01 |
| Banking & Finance | 100.22 |
| All US postings, seasonally adjusted | 102.13 |

Basket mean = (74.61 + 96.65 + 76.79 + 95.03 + 88.01 + 100.22) / 6 = 88.5516667.

Relative recruitment = 88.5516667 / 102.13 × 100 = **86.7048533**, displayed as **86.7**.

All input indices equal 100 on 1 February 2020, so the derived ratio also starts at 100. The reading means the equally weighted basket's growth factor is 13.3% below the all-market growth factor since that baseline. It does NOT mean 13.3% of white-collar jobs disappeared, or that this basket accounts for 86.7% of postings. These are indices already centred on 100: do not add 100 to the source values.

## Quick Excel recreation of the entire history

1. Download `recruitment-excel-inputs.csv`. In Excel use Data → From Text/CSV. Import the date as Date and the seven numeric columns as decimal numbers (English/US locale if needed). Load into a worksheet.
2. Columns A–H are date, Software Development, Accounting, Marketing, Administrative Assistance, Customer Service, Banking & Finance, All US postings.
3. In I1 enter `Basket mean`; in I2 enter `=IF(COUNT(B2:G2)=6,AVERAGE(B2:G2),NA())`.
4. In J1 enter `Relative recruitment`; in J2 enter `=IF(AND(COUNT(H2)=1,H2>0),I2/H2*100,NA())`.
5. Fill I2:J2 down all 2,401 observations. Plot A against J as a line chart. Keep all daily rows; do not smooth again. The sources are already seasonally adjusted seven-day trailing indices.
6. Check 1 February 2020 gives 100, and 28 August 2026 gives 86.7048533. Compare J to `recruitment.csv`, allowing 0.000001 for six-decimal export rounding.

## Rebuild the inputs yourself from the original CSVs

Use Excel Power Query to import both original CSVs. For sectors, filter `variable` to exactly `total postings` and `display_name` to the six names above. Keep `date`, `display_name` and `indeed_job_postings_index`; pivot `display_name` into six columns with “Don't aggregate”. There should be exactly one source value per date and sector. A duplicate should be investigated, not summed.

For the all-US file, filter `variable` to `total postings`, and retain `date` and `indeed_job_postings_index_SA`. Merge with the sector pivot on date, keeping dates with all seven numeric inputs. Order columns as above and dates ascending. For this frozen edition retain dates through 6 September 2026. Apply the same Excel formulas. Do not substitute new-posting indices or the non-seasonally-adjusted all-US column.

## Recreate the scenario lines

The original anchor is 28 August 2026 at 86.704853; the horizon is 31 December 2029. Frozen endpoints are low 95.375338, medium 78.034368, high 60.693397. For a date in A2 on or after the anchor and on or before the horizon, use:

`=86.704853+(95.375338-86.704853)*(A2-DATE(2026,8,28))/(DATE(2029,12,31)-DATE(2026,8,28))`

Replace 95.375338 with the medium or high endpoint for the other lines. Use NA() outside that interval. These are straight conditional paths, not statistical forecasts. Future actuals add a solid line alongside the same dashed paths: never replace their anchor with the latest reading.
