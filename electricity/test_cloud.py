"""Publication, retention and UK schedule checks around the original collector."""
from datetime import datetime, timezone
import copy
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import cloud

DATA = Path(__file__).resolve().parents[1] / 'public/data/ni-electricity'
NOW = datetime(2026, 11, 1, 8, tzinfo=timezone.utc)


class CloudTests(unittest.TestCase):
    def data(self, name):
        return json.loads((DATA / f'{name}.json').read_bytes())

    def test_signed_balances_and_backward_updates_fail_closed(self):
        original = self.data('snapshot')
        cloud.validate('snapshot', original, now=datetime(2026, 11, 2, tzinfo=timezone.utc))
        invalid = {**original, 'northSouth': -original['northSouth']}
        with self.assertRaises(ValueError):
            cloud.validate('snapshot', invalid, original, NOW)
        with self.assertRaises(ValueError):
            cloud.validate('snapshot', {**original, 'time': '2026-10-01T00:00:00Z'}, original, NOW)

    def test_previously_collected_meter_history_cannot_disappear(self):
        original = self.data('history')
        cloud.validate('history', original, now=NOW)
        changed = copy.deepcopy(original)
        index = next(i for i, s in enumerate(original['series']) if s['key'] == 'ballylumford')
        row = next(row for row in changed['days'] if row['v'][index] is not None)
        row['v'][index] = None
        with self.assertRaisesRegex(ValueError, 'would be lost'):
            cloud.validate('history', changed, original, NOW)

    def test_schedule_keeps_0700_belfast_across_both_clock_changes(self):
        for text, expected in [('2026-03-28T06:59:00+00:00', False), ('2026-03-28T07:00:00+00:00', True),
                               ('2026-03-29T05:59:00+00:00', False), ('2026-03-29T06:00:00+00:00', True),
                               ('2026-10-25T06:59:00+00:00', False), ('2026-10-25T07:00:00+00:00', True)]:
            self.assertEqual(cloud.history_due(None, datetime.fromisoformat(text)), expected)
        self.assertFalse(cloud.history_due({'successfulDate': '2026-11-01'}, NOW))
        self.assertFalse(cloud.history_due({'lastAttempt': '2026-11-01T07:30:00Z'}, NOW))
        self.assertTrue(cloud.history_due({'lastAttempt': '2026-11-01T07:00:00Z'}, NOW))

    def test_native_and_external_overview_jobs_share_one_utc_quarter_hour(self):
        pointer = {'lastSuccess': '2026-11-01T07:02:00Z'}
        self.assertTrue(cloud.snapshot_recent(pointer, datetime.fromisoformat('2026-11-01T07:14:59+00:00')))
        self.assertFalse(cloud.snapshot_recent(pointer, datetime.fromisoformat('2026-11-01T07:15:00+00:00')))
        self.assertFalse(cloud.snapshot_recent(None, NOW))

    def test_incomplete_source_refresh_retains_a_coherent_accepted_grid_day(self):
        original = self.data('history')
        changed = copy.deepcopy(original)
        columns = {series['key']: i for i, series in enumerate(original['series'])}
        row = next(row for row in changed['days'] if all(value is not None for value in row['v']))
        prior = next(old for old in original['days'] if old['date'] == row['date'])
        for key in ['generation', 'otherNI', 'northSouth']:
            row['v'][columns[key]], row['n'][columns[key]] = None, 95
        row['v'][columns['demand']] += 100
        row['v'][columns['ballylumford']] += 3
        cloud.preserve_complete_history(changed, original)
        for key in cloud.PUBLIC_SERIES:
            self.assertEqual(row['v'][columns[key]], prior['v'][columns[key]])
            self.assertEqual(row['n'][columns[key]], prior['n'][columns[key]])
        self.assertEqual(row['v'][columns['ballylumford']], prior['v'][columns['ballylumford']] + 3)
        self.assertIn(row['date'], changed['retainedCompleteDays']['series']['generation'])
        cloud.validate('history', changed, original, NOW)

    def test_complete_revisions_and_real_zero_replace_archive_while_new_gaps_remain(self):
        original = self.data('history')
        changed = copy.deepcopy(original)
        columns = {series['key']: i for i, series in enumerate(original['series'])}
        row = next(row for row in changed['days'] if all(value is not None for value in row['v']))
        row['v'][columns['wind']] = 0
        row['v'][columns['otherNI']] = round(row['v'][columns['generation']] - row['v'][columns['solar']], 4)
        gap = next(row for row in changed['days'] if row['v'][columns['solar']] is None)
        cloud.preserve_complete_history(changed, original)
        self.assertEqual(row['v'][columns['wind']], 0)
        self.assertIsNone(gap['v'][columns['solar']])
        self.assertNotIn('retainedCompleteDays', changed)
        cloud.validate('history', changed, original, NOW)

    def test_missing_station_day_is_retained_without_discarding_complete_grid_revision(self):
        original = self.data('history')
        changed = copy.deepcopy(original)
        columns = {series['key']: i for i, series in enumerate(original['series'])}
        row = next(row for row in changed['days'] if all(value is not None for value in row['v']))
        prior = next(old for old in original['days'] if old['date'] == row['date'])
        row['v'][columns['ballylumford']], row['n'][columns['ballylumford']] = None, 47
        row['v'][columns['demand']] += 100
        row['v'][columns['northSouth']] += 100
        cloud.preserve_complete_history(changed, original)
        self.assertEqual(row['v'][columns['ballylumford']], prior['v'][columns['ballylumford']])
        self.assertEqual(row['n'][columns['ballylumford']], 48)
        self.assertEqual(row['v'][columns['demand']], prior['v'][columns['demand']] + 100)
        self.assertEqual(set(changed['retainedCompleteDays']['series']), {'ballylumford'})
        cloud.validate('history', changed, original, NOW)

    def test_archive_preservation_does_not_mask_shrinking_ranges(self):
        original = self.data('history')
        changed = copy.deepcopy(original)
        changed['days'].pop()
        changed['last'] = changed['days'][-1]['date']
        cloud.preserve_complete_history(changed, original)
        with self.assertRaisesRegex(ValueError, 'range shrank'):
            cloud.validate('history', changed, original, NOW)

    def test_retained_grid_cohort_cannot_hide_invalid_fresh_readings(self):
        original = self.data('history')
        changed = copy.deepcopy(original)
        columns = {series['key']: i for i, series in enumerate(original['series'])}
        row = next(row for row in changed['days'] if all(value is not None for value in row['v']))
        row['v'][columns['generation']] = None
        row['v'][columns['demand']] = float('nan')
        with self.assertRaises(ValueError):
            cloud.preserve_complete_history(changed, original)

    def test_bounded_publication_and_fallback_when_state_arrives_late(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kv = cloud.FileKV(root / 'kv')
            work = root / 'work'
            cloud.make_work(work)
            data = self.data('snapshot')
            pointer = None
            for minute in range(5):
                data = {**data, 'retrievedAt': f'2026-11-01T07:{minute:02}:00Z'}
                (work / 'dashboard/dist/assets/snapshot.json').write_bytes(cloud.encode(data))
                cloud.publish(kv, 'snapshot', work, data, pointer, NOW)
                pointer = kv.get_json('private/snapshot/current')
            self.assertEqual(len(pointer['records']), 3)
            self.assertEqual(len(list((root / 'kv/public/snapshot').iterdir())), 3)  # Only the three immutable public datasets
            self.assertEqual(len(list((root / 'kv/private/snapshot').glob('state-*'))), 3)
            self.assertEqual(kv.writes, 3 * 5 + 2)  # 3 puts/run and two retention deletes
            self.assertEqual(kv.operations['put'], 15)
            self.assertEqual(kv.operations['delete'], 2)
            self.assertIsNone(kv.get('public/snapshot/current'))
            # Current state not visible yet at this location: restore the previous
            # accepted archive rather than start an empty backfill.
            kv.delete(pointer['records'][0]['stateKey'])
            restored = root / 'restored'
            _, previous = cloud.load_state(kv, 'snapshot', restored)
            self.assertEqual(previous['retrievedAt'], '2026-11-01T07:03:00Z')

    def test_failed_collection_leaves_public_data_and_archives_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kv = cloud.FileKV(root / 'kv')
            work = root / 'work'
            cloud.make_work(work)
            data = self.data('snapshot')
            (work / 'dashboard/dist/assets/snapshot.json').write_bytes(cloud.encode(data))
            cloud.publish(kv, 'snapshot', work, data, now=NOW)
            before = {p.name: p.read_bytes() for p in (root / 'kv/private/snapshot').glob('state-*')}
            records = kv.get_json('private/snapshot/current')['records']
            before_writes = kv.writes
            with patch.object(cloud.subprocess, 'run', side_effect=RuntimeError('upstream unavailable')):
                with self.assertRaises(RuntimeError):
                    cloud.run(kv, 'snapshot', force=True)
            self.assertEqual(kv.get_json('private/snapshot/current')['records'], records)
            self.assertFalse(kv.get_json('private/snapshot/current')['ok'])
            self.assertEqual(kv.writes - before_writes, 1)
            self.assertEqual(before, {p.name: p.read_bytes() for p in (root / 'kv/private/snapshot').glob('state-*')})

    def test_cold_start_and_unsafe_archive_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            with self.assertRaisesRegex(RuntimeError, 'has not been seeded'):
                cloud.load_state(cloud.FileKV(work / 'kv'), 'history', work)
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode='w:gz') as tar:
                info = tarfile.TarInfo('state.json')
                payload = cloud.encode({'schema': 1, 'version': 'x', 'dataset': 'history'})
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))
                tar.addfile(tarfile.TarInfo('../escape'))
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                cloud.restore(raw.getvalue(), work, 'history', 'x')


if __name__ == '__main__':
    unittest.main()
