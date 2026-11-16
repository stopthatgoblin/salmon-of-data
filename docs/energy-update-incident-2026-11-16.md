# Energy update investigation, 16 November 2026

## Production and source evidence

At 18:07 GMT, the live ROI manifest had accepted 16 November 17:30 grid readings. Its history was current through 15 November. A browser check displayed the same live readings and the station-output warning. Gas and both time-machine archives still ended on 11 November.

The public SEMO `PUB_DailyMeterDataD1` index still ended at settlement date 11 November, published on 12 November at 15:58:55. Other SEMO report families were publishing 16 November editions, including hourly dispatch instructions, registered units and availability. ROI's production collector continued to report one missing dispatch hour: `2026-11-12T14:00:00Z`. The missing dispatch interval prevents reliable station estimates under the current reconstruction rule; it does not block the independent grid totals or flows.

[SEMO's Indicative Settlement notice](https://www.sem-o.com/market-messages/indicative-settlement-418), updated on 16 November at 16:11, explicitly extends the delay from 12 November to 13–15 November and attributes it to late MDP data. This corroborates an upstream meter-data delay. It does not prove the cause of the missing hourly dispatch report.

[SEMO's release notice](https://www.sem-o.com/market-messages/release-op1) says its O/P.1 release was deployed around 15:00 on 12 November, encountered technical issues, and became effective at 13:10 on 13 November. The missing hourly report normally follows the affected deployment period. That timing is consistent with an upstream interruption, but a causal connection is not established. The gas dashboard commit `7f92bb2` was created on 12 November at 22:47 GMT.

The 16 November 07:00 electricity history job succeeded. Its time-machine step collected sources without request failures, then omitted 12–15 November because unit meters were missing. Neither archive was overwritten with incomplete days. The job is [43820773314](https://github.com/stopthatgoblin/salmon-of-data/actions/runs/43820773314).

Cloudflare's reported daily namespace storage maxima totalled approximately 120 MB on 15 and 16 November across production and preview. Reported writes were 577 for 15 November and 382 so far on 16 November, below the Free plan's 1,000/day write allowance. Source and collector logs did not report a quota failure. Gas uses its own KV namespace and workflow concurrency group; its shared scheduler only enters the gas branch on gas cron expressions.

## Internal retry fault and correction

The 16 November 07:00 gas catch-up job [43820685406](https://github.com/stopthatgoblin/salmon-of-data/actions/runs/43820685406) failed with a source read timeout. Its target was 14 November. The failure handler correctly replaced a specific source-wait notice with a generic failure, but the scheduler only retried daytime jobs carrying the specific source-wait flag. This disabled the remaining 10:00, 13:00 and 16:00 retries until the evening window. It did not stop electricity dispatch or explain why SEMO's meter report was absent.

Daytime catch-ups now retry any recorded unsuccessful collection with a valid completed target day, under the existing four-hour schedule and attempt throttle. Successful collections still clear failure state and suppress catch-ups. The collector checks the primary meter index before loading technical and registry indexes, so those unrelated requests cannot obscure a known missing meter report.

Regression coverage exercises the actual timeout state, retry throttling, success clearing, preservation of the original target, electricity dispatch despite a gas failure, and primary-meter checks before unrelated sources. Publication, gas calculations and the existing six-hour estimate limit are unchanged.

All 59 JavaScript tests and 16 gas/model Python tests passed. A fresh collection for 15 November against live sources, using a local test store, stopped specifically with `Waiting for SEMO meter data for 2026-11-15`.

## Operational limits

This correction restores retry behaviour; it does not supply missing station meters or dispatch instructions. ROI station outputs remain unavailable until source coverage supports reconstruction. Gas and the time machine retain accepted days while required source data is missing. The time-machine collector revisits the preceding seven days; a longer outage can require explicit backfill after source recovery.
