# Daily gas collector

`python -m gas.cloud` fetches GNI, ENTSOG, SEMO and EirGrid/SONI sources, validates a common gas day and publishes immutable snapshots before advancing a merged date index. The target defaults to yesterday in Europe/Dublin.

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
