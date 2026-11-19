# Daily gas collector

`python -m gas.cloud` fetches GNI, ENTSOG, SEMO and EirGrid/SONI sources, validates common gas days and publishes immutable snapshots before advancing a merged date index. The requested target defaults to yesterday in Europe/Dublin. Valid older days in the revision window can publish while the newest target remains pending.

- `sources.py`: bounded network retries, compressed response cache, dated report selection and upstream URLs. Mutable indices and gas/demand series are refetched. Cached immutable report names identify publication editions.
- `collect.py`: unit electricity, NI heat-input/startup model, reported ROI gas sectors, regional demand shares and physical flows. Missing values never become zero. Source interval coverage, gas residuals, model validity and hourly/daily agreement are checked.
- `ni-model.json`: six-unit parameters extracted from the public March 2025 SEM PLEXOS model, with source SHA and gross/net conversion. No large local model file is needed by a runner.
- `cloud.py`: local/Cloudflare adapters, accepted revisions, daily success guard and last-good failure status. Public endpoints cannot read private run state.

An empty new runner obtains enough preceding meter history to classify starts, rather than relying on a Mac folder or an optional GitHub cache. Active unmodelled NI gas/multi-fuel units stop publication pending review. ROI gas/multi-fuel units follow dated technical reports; the known misclassified battery is excluded. Fuel switching and CHP own-use remain unobserved.

The original heat-rate/startup functions are reused from `electricity/research/ni_gas/estimate.py`; their historical backtest and assumptions are retained beside them.

```sh
python -m unittest discover -s gas -p 'test_*.py'
python -m unittest discover -s electricity/research/ni_gas -p 'test_*.py'
python -m gas.cloud --local-dir outputs/gas-live/kv --seed
```

Normal collection revises seven days. No older date or edition is deleted. Source URLs/publication times and model identity accompany accepted snapshots; full raw response files are a local cache, not a durable public raw-data archive.

Schema 2 allows explicit paired `null` values for regional electricity demand and its generation-to-demand percentage when complete actual demand is unavailable. Core gas quantities and electrical output still pass all existing source/model/coverage checks. The client continues to accept schema 1. New candidates cannot replace accepted editions with poorer demand or meter coverage.

Partial publication returns successfully but records `pending: true`; it does not advance the daily completion guard. The timer continues bounded evening and daytime retries for the original target, and later runs revisit the window to fill missing dates and demand metrics. GitHub run summaries list the requested day, accepted latest day and outstanding sources. See `docs/gas-dashboard-launch-guide.md` for operation and deployment order.

Meter coverage is checked per unit. A missing contiguous tail of at most six hours can use reconstructed dispatch targets, seeded from that unit's final meter interval, while other units retain their published readings. The snapshot's metered/estimated hours describe the minimum metered prefix and maximum estimated tail across units. Missing prefixes, internal gaps and longer tails remain pending for SEMO recovery. Identical GNI daily duplicates are accepted once; conflicting values remain pending for GNI correction. Pending-source records and run summaries retain the specific reason.

Schema 3 separates regional electricity availability from validated reported gas. The production collector opts into `gas_first=True`; the strict research entry point remains available. Missing electricity never supplies a zero, and missing NI power gas also removes its residual and shares. Optional hourly charts can wait for source repair without suppressing daily readings. Publication fingerprints exclude collection timestamps, and unresolved dates remain queued beyond the rolling window. See `python -m gas.verify --help` for the preview-only date-advance and recovery check.
