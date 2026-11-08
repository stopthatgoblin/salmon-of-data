"""Public replay publication, retention and failure checks using FileKV only."""
from copy import deepcopy
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from electricity import replay, replay_cloud


MAPPING = {'test': ['GU_TEST']}


def row(at, output=10, basis='metered-half-hour'):
    data = dict(time=at, grid=[120, 100, 20, 5, 10], outputs=[output],
                available=[60], maximum=[100], moyleAvailable=None, stationBasis=basis)
    if basis == 'captured-dispatch-proxy':
        data['collectedAt'] = replay.iso(replay.stamp(at) + timedelta(minutes=2))
    return data


def prepare(root, region, days):
    days = deepcopy(days)
    if region == 'roi':
        for rows in days.values():
            for item in rows:
                item['grid'] = [120, 100, 20, 5, 30, 20, 120, 100, 10]
    replay.export_region(region, MAPPING, days, root, '2026-11-08T00:00:00Z')


class TrackedKV(replay_cloud.cloud.FileKV):
    def __init__(self, directory):
        super().__init__(directory)
        self.reads, self.puts = [], []
        self.fail_key = None

    def get(self, key):
        self.reads.append(key)
        return super().get(key)

    def put(self, key, value):
        self.puts.append(key)
        if key == self.fail_key or self.fail_key and key.startswith(self.fail_key):
            raise RuntimeError('Simulated staging failure')
        return super().put(key, value)


class ReplayCloudTests(unittest.TestCase):
    def test_seed_is_public_only_and_unchanged_run_has_zero_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source = base / 'source'
            for region in ['ni', 'roi']:
                prepare(source, region, {'2026-11-01': [row('2026-11-01T00:00:00+00:00')]})
                path = source / region / '2026-11-01.json'
                data = json.loads(path.read_text())
                data['privateArchive'] = 'PRIVATE-SECRET-MUST-NOT-APPEAR'
                data['rows'][0]['credentials'] = 'PRIVATE-SECRET-MUST-NOT-APPEAR'
                data['basis']['private'] = 'PRIVATE-SECRET-MUST-NOT-APPEAR'
                replay.save(path, replay.encode(data))
            kv = TrackedKV(base / 'kv')
            result = replay_cloud.publish(kv, source)
            self.assertEqual(result['writes'], 4)
            self.assertTrue(all(replay_cloud.PUBLIC_KEY.fullmatch(key) for key in kv.puts))
            manifest_raw = kv.get('public/replay/ni/manifest')
            manifest = json.loads(manifest_raw)
            record = manifest['days'][0]
            self.assertEqual(record['url'], f'/api/electricity/replay/ni/2026-11-01.json?v={record["version"]}')
            for path in (base / 'kv').rglob('*'):
                if path.is_file():
                    self.assertNotIn(b'PRIVATE-SECRET', path.read_bytes())
            before = kv.writes
            result = replay_cloud.publish(kv, source, now=datetime(2026, 11, 9, tzinfo=replay.UTC))
            self.assertEqual(result['writes'], 0)
            self.assertEqual(kv.writes, before)
            self.assertEqual(kv.get('public/replay/ni/manifest'), manifest_raw)

    def test_partial_new_day_merges_timestamps_and_meter_overrides_proxy(self):
        with tempfile.TemporaryDirectory() as directory:
            base, old, recent = Path(directory), Path(directory) / 'old', Path(directory) / 'recent'
            prepare(old, 'ni', {
                '2026-11-01': [row('2026-11-01T00:00:00+00:00')],
                '2026-11-02': [row('2026-11-02T12:00:00+00:00', basis='captured-dispatch-proxy'),
                               row('2026-11-02T12:15:00+00:00', output=11)],
            })
            kv = TrackedKV(base / 'kv')
            replay_cloud.publish(kv, old)
            old_manifest = json.loads(kv.get('public/replay/ni/manifest'))
            old_first = old_manifest['days'][0]
            upgrade = row('2026-11-02T12:00:00+00:00', output=15)
            upgrade['available'] = [None]
            prepare(recent, 'ni', {'2026-11-02': [upgrade, row('2026-11-02T12:30:00+00:00', output=16)]})
            kv.reads.clear()
            result = replay_cloud.publish(kv, recent)
            self.assertEqual(result['writes'], 2)
            self.assertFalse(any(key.startswith('public/replay/ni/2026-11-01/') for key in kv.reads))
            manifest = json.loads(kv.get('public/replay/ni/manifest'))
            self.assertEqual(manifest['days'][0], old_first)
            entry = manifest['days'][1]
            data = json.loads(kv.get(f'public/replay/ni/2026-11-02/{entry["version"]}'))
            self.assertEqual([item['outputs'][0] for item in data['rows']], [15, 11, 16])
            self.assertEqual(data['rows'][0]['stationBasis'], 'metered-half-hour')
            self.assertEqual(data['rows'][0]['available'], [60])
            proxy = base / 'proxy'
            prepare(proxy, 'ni', {'2026-11-02': [row('2026-11-02T12:00:00+00:00', output=99,
                                                        basis='captured-dispatch-proxy')]})
            self.assertEqual(replay_cloud.publish(kv, proxy)['writes'], 0)

    def test_failed_day_staging_does_not_advance_either_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            base, old, recent = Path(directory), Path(directory) / 'old', Path(directory) / 'recent'
            for region in ['ni', 'roi']:
                prepare(old, region, {'2026-11-01': [row('2026-11-01T00:00:00+00:00')]})
                prepare(recent, region, {'2026-11-02': [row('2026-11-02T00:00:00+00:00')]})
            kv = TrackedKV(base / 'kv')
            replay_cloud.publish(kv, old)
            before = {region: kv.get(f'public/replay/{region}/manifest') for region in ['ni', 'roi']}
            kv.fail_key = 'public/replay/roi/2026-11-02/'
            kv.puts.clear()
            with self.assertRaisesRegex(RuntimeError, 'staging failure'):
                replay_cloud.publish(kv, recent)
            self.assertFalse(any(key.endswith('/manifest') for key in kv.puts))
            self.assertEqual({region: kv.get(f'public/replay/{region}/manifest') for region in ['ni', 'roi']}, before)
            kv.fail_key = None
            replay_cloud.publish(kv, recent)
            for region in ['ni', 'roi']:
                self.assertEqual(len(json.loads(kv.get(f'public/replay/{region}/manifest'))['days']), 2)

    def test_missing_or_corrupt_prior_day_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            base, old, recent = Path(directory), Path(directory) / 'old', Path(directory) / 'recent'
            prepare(old, 'ni', {'2026-11-01': [row('2026-11-01T00:00:00+00:00')]})
            prepare(recent, 'ni', {'2026-11-01': [row('2026-11-01T00:15:00+00:00')]})
            kv = TrackedKV(base / 'kv')
            replay_cloud.publish(kv, old)
            before = kv.get('public/replay/ni/manifest')
            version = json.loads(before)['days'][0]['version']
            replay.save(base / 'kv' / f'public/replay/ni/2026-11-01/{version}', b'corrupt')
            writes = kv.writes
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                replay_cloud.publish(kv, recent)
            self.assertEqual(kv.writes, writes)
            self.assertEqual(kv.get('public/replay/ni/manifest'), before)

    def test_mapping_change_and_write_budget_fail_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = Path(directory), Path(directory) / 'source'
            for region in ['ni', 'roi']:
                prepare(source, region, {'2026-11-01': [row('2026-11-01T00:00:00+00:00')]})
            kv = TrackedKV(base / 'kv')
            with self.assertRaisesRegex(ValueError, 'write budget'):
                replay_cloud.publish(kv, source, max_writes=3)
            self.assertEqual(kv.writes, 0)
            replay_cloud.publish(kv, source)
            path = source / 'ni/manifest.json'
            data = json.loads(path.read_text())
            data['stationUnits'] = {'other': ['GU_TEST']}
            data['stationIds'] = ['other']
            replay.save(path, replay.encode(data))
            before = kv.writes
            with self.assertRaisesRegex(ValueError, 'mapping changed'):
                replay_cloud.publish(kv, source)
            self.assertEqual(kv.writes, before)

    def test_seed_cli_local_store_needs_neither_cloudflare_nor_source_network(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = Path(directory), Path(directory) / 'source'
            prepare(source, 'ni', {'2026-11-01': [row('2026-11-01T00:00:00+00:00')]})
            with patch.object(replay_cloud.sys, 'argv', ['replay_cloud', '--seed', '--source', str(source),
                                                        '--local-dir', str(base / 'kv')]), \
                    patch.object(replay_cloud, 'ReplayKV', side_effect=AssertionError('No Cloudflare calls permitted')), \
                    patch.object(replay, 'fetch', side_effect=AssertionError('No source calls needed for seed')), \
                    patch('builtins.print'):
                replay_cloud.main()
            self.assertTrue((base / 'kv/public/replay/ni/manifest').exists())

    def test_normal_cli_collects_only_recent_window_and_preserves_older_manifest(self):
        class Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 8, 12, tzinfo=replay.UTC)

        with tempfile.TemporaryDirectory() as directory:
            base, source = Path(directory), Path(directory) / 'source'
            prepare(source, 'ni', {'2026-09-01': [row('2026-09-01T00:00:00+01:00')]})
            replay_cloud.publish(TrackedKV(base / 'kv'), source)

            def collect(options):
                self.assertEqual(options.start.isoformat(), '2026-11-01')
                self.assertEqual(options.end.isoformat(), '2026-11-07')
                self.assertFalse((options.output / 'ni/2026-09-01.json').exists())
                prepare(options.output, 'ni', {'2026-11-05': [row('2026-11-05T00:00:00+00:00')]})
                return dict(failures=[])

            with patch.object(replay_cloud.sys, 'argv', ['replay_cloud', '--local-dir', str(base / 'kv')]), \
                    patch.object(replay_cloud, 'datetime', Frozen), patch.object(replay, 'collect', side_effect=collect), \
                    patch.object(replay_cloud, 'ReplayKV', side_effect=AssertionError('No Cloudflare calls permitted')), \
                    patch('builtins.print'):
                replay_cloud.main()
            manifest = json.loads((base / 'kv/public/replay/ni/manifest').read_text())
            self.assertEqual([item['date'] for item in manifest['days']], ['2026-09-01', '2026-11-05'])

    def test_recent_collection_failure_retains_published_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            base, source = Path(directory), Path(directory) / 'source'
            prepare(source, 'ni', {'2026-11-01': [row('2026-11-01T00:00:00+00:00')]})
            kv = TrackedKV(base / 'kv')
            replay_cloud.publish(kv, source)
            before = kv.get('public/replay/ni/manifest')
            with patch.object(replay_cloud.sys, 'argv', ['replay_cloud', '--local-dir', str(base / 'kv')]), \
                    patch.object(replay, 'collect', return_value={'failures': [{'source': 'grid'}]}), \
                    self.assertRaisesRegex(RuntimeError, 'source collection failed'):
                replay_cloud.main()
            self.assertEqual(kv.get('public/replay/ni/manifest'), before)

    def test_cloud_client_rejects_private_keys_without_network_or_credentials(self):
        client = object.__new__(replay_cloud.ReplayKV)
        with self.assertRaisesRegex(ValueError, 'allowlisted public replay'):
            client.request('GET', 'private/replay/current')
        with self.assertRaisesRegex(ValueError, 'allowlisted public replay'):
            client.request('DELETE', 'public/replay/ni/manifest')
        client.writes, client.max_writes = 0, 0
        with self.assertRaisesRegex(RuntimeError, 'write budget'):
            client.request('PUT', 'public/replay/ni/manifest', b'{}')


if __name__ == '__main__':
    unittest.main()
