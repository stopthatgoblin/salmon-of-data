# Moffat hourly flow check: 11 November 2026

Checked against fresh GNI responses on 12 November 2026. The sharp change appears in the published source; the dashboard has not introduced it.

| Bar label (Ireland time, GMT) | Moffat hourly delivery, GWh | Change in GNI cumulative throughput, GWh |
| --- | ---: | ---: |
| 16:00 | 16.028888 | 16.028888 |
| 17:00 | 15.898890 | 15.898890 |
| 18:00 | 10.064444 | 10.064444 |
| 19:00 | 10.259445 | 10.259445 |

The decrease between the bars labelled 17:00 and 18:00 is 5.834446 GWh, or 36.70%. Corrib remains close to 0.897 GWh in these hours. GNI describes its hour labels as the start of the corresponding hour, so these are hourly quantities, not instantaneous readings.

All 24 Moffat hourly quantities sum to **240.599445 GWh**, exactly matching GNI's separately published daily quantity. The hourly and cumulative series agree on the size of the step. The preceding day has no comparable 18:00 step, so this is not a recurring date-axis boundary created by the dashboard.

This corroborates the published data, rather than independently verifying the underlying meter. No operational notice identifying the cause of this particular change has been established. GNI documents that within-day flow profiles can vary with physical constraints and nomination changes; that does not establish the cause on this date. No smoothing, substitution or date-specific explanation has been added to the live chart.

Sources:

- [GNI hourly physical flows for 11 November](https://www.gasnetworks.ie/api/v1/physicalflows?date=2026-11-11&frequency=hourly)
- [GNI daily physical flows, containing 11 November](https://www.gasnetworks.ie/api/v1/physicalflows?date=2026-11-12&frequency=daily)
- [GNI hourly physical flows for the preceding day](https://www.gasnetworks.ie/api/v1/physicalflows?date=2026-11-10&frequency=hourly)
- [GNI physical-flow definitions](https://www.gasnetworks.ie/about/data-transparency/entry-flows/physical-flows)
- [GNI Winter Outlook 2025, section on Moffat flow profiles](https://www.gasnetworks.ie/sites/default/files/2025-11/Winter-Outlook-2025.pdf)

Fresh response copies are retained locally in `outputs/gas-live/flow-check/`.
