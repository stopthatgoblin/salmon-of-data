# Metric audit - 6 September 2026

All 3,168 displayed observations independently rebuilt from archived source files using pandas pivoting, calendar reindexing and rolling operations in `scripts/audit-metrics.py`. All dates agree. Maximum absolute difference is under 0.000001, entirely explained by dashboard export rounding. No calculation or frozen definition required alteration. Raw-file hashes and the immutable scenario registry are checked separately by `scripts/validate-data.py`.

| Metric | Observations | Latest value | Assessment |
| --- | ---: | ---: | --- |
| Recruitment | 2,401 | 86.704853 | Useful early signal. Six sector growth indices get equal weights, not weights proportional to jobs. This is relative demand, not a posting share or job-loss count. |
| Graduate gap | 138 | 2.839 pp | Clear entry-level outcome. Recent graduate rate minus all-graduate rate; the control includes the recent group. Covers all degrees, not only exposed occupations. |
| Underemployment | 138 | 41.950% | Useful corroboration of a difficult graduate transition. Denominator is employed recent graduates. It is qualification mismatch, not insufficient working hours. |
| Actual hiring | 139 | 99.044650 | Stronger evidence than advertisements, but the broad sector includes staffing and waste services. Ratio of three-month mean rates, not mean of monthly ratios. |
| Employment | 140 | 107.482312 | Best direct job-stock signal in this panel. NAICS 54 payroll-job share relative to 2019. A falling share may coexist with rising job numbers. Payroll jobs are not unique people. |
| Real pay | 138 | 104.073142 | Useful income context. Nominal hourly pay divided by CPI, then indexed. Uses July, the latest common month. Composition and inflation can dominate any AI effect. |
| Canada demand | 37 | 1.366280% | Useful occupation-specific cross-country corroboration. Ratio of four-quarter vacancy sums; not an annual count of unique vacancies. No rolling window bridges missing quarters. |
| Canada pay | 37 | 67.028200% | Useful bargaining-power context. Ratio of equally weighted four-quarter wage means minus one. Not mean quarterly premiums, vacancy-weighted wages, real pay or fixed-seniority pay. |

The three US 2019 indices divide each month's ratio by the arithmetic mean of the twelve 2019 ratios. They do not divide by the ratio of annual means. The source-smoothed graduate series is not smoothed again. Canadian quality flags are retained in the archived extract; suppressed/missing values are not zeros. October 2025 graduate estimates were supplied by the New York Fed, not invented by this dashboard.

## Interpretation

These eight metrics form a transparent pressure dashboard, not eight independent tests of AI causality. Several share data, populations and macroeconomic shocks. Interest rates, offshoring, migration, changing job mix and the post-pandemic hiring correction are plausible alternatives. The all-market controls themselves include AI-exposed work.

Use recruitment as an early signal, employment as the main job-stock outcome, and the other six as corroboration/context. Do not sum their readings or convert them directly into GDP lost. The employment high-path equivalent of 1.08423 million fewer sector jobs assumes total private employment stays at its anchor level; it is not a forecast of unemployment. A lower employment share could instead mean slower growth than other industries.

High/medium/low are judgement-based scenarios with fixed, explicit endpoints. Their direction is economically intelligible but their magnitudes are not empirically calibrated probabilities or confidence intervals. The September 2027 review rule compares first-published outcomes at their observation dates with each frozen line; revisions are reported separately. Four quarters of persistence provides discipline, not a statistical significance test. By 2029, widespread resilient outcomes would weaken the predicted broad net-displacement pattern; weak outcomes would support that pattern without proving AI caused it. Gross displacement within an otherwise growing economy can still occur.

Future stronger attribution needs adoption/exposure measures and credible comparisons between exposed and less-exposed workers, ideally within age and occupation groups. Add this as a separately versioned analysis, without changing the frozen v1 definitions after seeing results.

## Chart correction

Previously, timestamps containing only projections could interrupt future observed lines, while future observed timestamps could interrupt dashed paths. `lib/chart-data.ts` now evaluates all three original scenarios at every chart timestamp in their fixed window. The observed series is drawn last, so solid actuals overlay the paths where they coincide. Frozen forecasts remain visible for comparison rather than being erased. Explicit source gaps remain gaps. Regression tests use synthetic future observations only in the test file; no synthetic actuals were added to the dashboard.

See `public/data/recruitment-worked-example.md` and `recruitment-excel-inputs.csv` for an independently reproducible Excel example.
