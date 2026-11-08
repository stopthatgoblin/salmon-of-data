"""Checks for historical alignment, missing-input exclusion and retention."""
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from electricity import replay


class ReplayTests(unittest.TestCase):
    def journal_fixture(self, root, region, *, output=10, collected='2026-11-08T12:02:00Z', version=None):
        version = version or ('1' * 24 if region == 'ni' else '2' * 24)
        snapshot = dict(time='2026-11-08T12:00:00Z', retrievedAt=collected,
                        demand=120, generation=100, wind=20, solar=5, moyle=10,
                        stations=[dict(id='test', units=[dict(id='GU_TEST', output=output, available=60, maximum=100)])])
        if region == 'roi':
            snapshot.update(ni=dict(time=snapshot['time'], demand=120, generation=100, moyle=10),
                            interconnectors=[dict(id='eastWest', value=30), dict(id='greenlink', value=20)])
        key = ('public/roi/snapshot/' if region == 'roi' else 'public/snapshot/') + version
        replay.save(root / key, replay.encode(snapshot))
        pointer_key = 'private/roi/snapshot/current' if region == 'roi' else 'public/snapshot/current'
        pointer = dict(records=[dict(key=key, version=version, time=snapshot['time'],
                                    collectedAt=collected, stateKey='private/SECRET-ARCHIVE')])
        replay.save(root / pointer_key, replay.encode(pointer))
        return snapshot, pointer_key

    def test_journal_reads_only_accepted_public_json_and_retains_history(self):
        mapping = {'test': ['GU_TEST']}
        with tempfile.TemporaryDirectory() as directory, patch.object(replay, 'station_mapping', return_value=mapping), \
                patch.object(replay, 'fetch', side_effect=AssertionError('Journaling must not access network')):
            root = Path(directory) / 'local'
            output = Path(directory) / 'public'
            self.journal_fixture(root, 'ni')
            self.journal_fixture(root, 'roi', output=77)
            replay.save(root / 'private/SECRET-ARCHIVE', b'PRIVATE SOURCE ARCHIVE MUST NEVER BE EXPORTED')
            at = replay.stamp('2026-11-01T00:00:00')
            grid, meter = self.inputs([at])
            days, _ = replay.assemble('ni', mapping, grid, meter, (lambda *_: None, lambda *_: None),
                                      date(2026, 11, 1), date(2026, 11, 1))
            replay.export_region('ni', mapping, days, output, '2026-11-08T00:00:00Z')
            result = replay.journal_local(root, output)
            self.assertEqual(len(result['regions']), 2)
            self.assertEqual(result['skipped'], [])
            ni_manifest = json.loads((output / 'ni/manifest.json').read_text())
            self.assertEqual([day['date'] for day in ni_manifest['days']], ['2026-11-01', '2026-11-08'])
            roi_day = json.loads((output / 'roi/2026-11-08.json').read_text())
            row = roi_day['rows'][0]
            self.assertEqual(row['stationBasis'], 'captured-dispatch-proxy')
            self.assertEqual(row['collectedAt'], '2026-11-08T12:02:00Z')
            self.assertEqual(row['outputs'], [77])
            self.assertEqual(row['grid'], [120, 100, 20, 5, 30, 20, 120, 100, 10])
            for path in output.rglob('*.json'):
                self.assertNotIn('PRIVATE SOURCE ARCHIVE', path.read_text())

    def test_meter_upgrade_wins_over_later_proxy_journaling(self):
        mapping = {'test': ['GU_TEST']}
        with tempfile.TemporaryDirectory() as directory, patch.object(replay, 'station_mapping', return_value=mapping):
            root, output = Path(directory) / 'local', Path(directory) / 'public'
            self.journal_fixture(root, 'ni', output=10)
            replay.journal_local(root, output)
            at = replay.stamp('2026-11-08T12:00:00')
            grid, meter = self.inputs([at])
            meter['GU_TEST', at] = (15, 'actual-meter.xml')
            days, _ = replay.assemble('ni', mapping, grid, meter, (lambda *_: None, lambda *_: None),
                                      date(2026, 11, 8), date(2026, 11, 8))
            replay.export_region('ni', mapping, days, output, '2026-11-10T00:00:00Z')
            self.journal_fixture(root, 'ni', output=99, collected='2026-11-08T12:10:00Z')
            replay.journal_local(root, output)
            row = json.loads((output / 'ni/2026-11-08.json').read_text())['rows'][0]
            self.assertEqual(row['outputs'], [15])
            self.assertEqual(row['stationBasis'], 'metered-half-hour')
            self.assertEqual(row['available'], [60])

    def test_journal_rejects_private_pointer_target_and_incomplete_units(self):
        mapping = {'test': ['GU_TEST']}
        with tempfile.TemporaryDirectory() as directory, patch.object(replay, 'station_mapping', return_value=mapping):
            root, output = Path(directory) / 'local', Path(directory) / 'public'
            _, pointer_key = self.journal_fixture(root, 'ni', output=None)
            self.journal_fixture(root, 'roi')
            pointer_path = root / 'private/roi/snapshot/current'
            pointer = json.loads(pointer_path.read_text())
            pointer['records'][0]['key'] = 'private/roi/snapshot/state-0'
            replay.save(pointer_path, replay.encode(pointer))
            result = replay.journal_local(root, output)
            self.assertEqual(result['regions'], [])
            self.assertEqual(len(result['skipped']), 2)
            self.assertIn('numeric mapped unit', result['skipped'][0]['reason'])
            self.assertIn('allowlisted public snapshot', result['skipped'][1]['reason'])
            self.assertFalse(output.exists())

    def test_successful_but_empty_grid_body_is_retried(self):
        response = dict(Rows=[dict(EffectiveTime='01-Nov-2026 00:00:00',
                                 FieldName='SYSTEM_DEMAND', Region='NI', Value=1234)])
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(replay, 'fetch', side_effect=[b'{"Rows":[]}', b'{"Rows":[]}', replay.encode(response)]) as fetch, \
                patch.object(replay.time, 'sleep'):
            data = replay.grid_month('ni', 'demand', date(2026, 11, 1), date(2026, 11, 1),
                                     Path(directory), True, [])
            self.assertEqual(fetch.call_count, 3)
            self.assertEqual(data['rows'], [['2026-11-01T00:00:00', 1234]])

    def test_meter_is_energy_per_half_hour_and_revisions_win(self):
        raw = b'''<REPORT DatasetName="PUB_DailyMeterDataD1" Date="2026-09-09" PublishTime="2026-09-10T15:00:00">
          <ROW ResourceName="GU_TEST" StartTime="2026-09-08T23:00:00" EndTime="2026-09-08T23:29:59" MeteredMW="21.25"/>
          <ROW ResourceName="GU_OTHER" StartTime="2026-09-08T23:00:00" EndTime="2026-09-08T23:30:00" MeteredMW="99"/>
        </REPORT>'''
        report = replay.parse_report(raw, 'meter.xml', {'GU_TEST'})
        self.assertEqual(report['rows'], [['GU_TEST', '2026-09-08T23:00:00Z', 42.5]])
        revision = dict(report, published='2026-09-11T15:00:00', resource='revision.xml',
                        rows=[['GU_TEST', '2026-09-08T23:00:00Z', 43]])
        meter = replay.merge_meter([revision, report])
        self.assertEqual(meter['GU_TEST', replay.stamp('2026-09-08T23:00:00')], (43, 'revision.xml'))

    def test_meter_missing_is_not_zero_and_bad_interval_rejected(self):
        raw = b'''<REPORT DatasetName="PUB_DailyMeterDataD1" Date="2026-11-01" PublishTime="2026-11-02T15:00:00">
          <ROW ResourceName="GU_TEST" StartTime="2026-11-01T00:00:00" EndTime="2026-11-01T00:29:59"/>
        </REPORT>'''
        self.assertEqual(replay.parse_report(raw, 'meter.xml', {'GU_TEST'})['rows'], [])
        with self.assertRaises(ValueError):
            replay.parse_report(raw.replace(b'00:29:59', b'00:15:00'), 'bad.xml', {'GU_TEST'})

    def inputs(self, instants):
        grid = {(region, key): {at: 100 for at in instants}
                for region, key in [('ni', key) for key in replay.GRID_KEYS['ni']]}
        meter = {('GU_TEST', at.replace(minute=at.minute // 30 * 30)): (0, 'meter.xml') for at in instants}
        return grid, meter

    def test_half_hour_applies_only_to_contained_quarters(self):
        start = replay.stamp('2026-11-01T00:00:00')
        instants = [start + timedelta(minutes=minute) for minute in [0, 15, 30]]
        grid, meter = self.inputs(instants)
        del meter['GU_TEST', instants[2]]
        days, missing = replay.assemble('ni', {'test': ['GU_TEST']}, grid, meter,
            (lambda *_: None, lambda *_: None), date(2026, 11, 1), date(2026, 11, 1))
        self.assertEqual([row['time'] for row in days['2026-11-01']],
                         ['2026-11-01T00:00:00+00:00', '2026-11-01T00:15:00+00:00'])
        self.assertEqual(missing['2026-11-01'], 1)
        self.assertEqual(days['2026-11-01'][0]['outputs'], [0])
        self.assertEqual(days['2026-11-01'][0]['available'], [None])

    def test_dst_repeated_local_times_are_different_instants(self):
        instants = [replay.stamp('2026-10-25T00:00:00'), replay.stamp('2026-10-25T01:00:00')]
        grid, meter = self.inputs(instants)
        mapping = {'test': ['GU_TEST']}
        days, _ = replay.assemble('ni', mapping, grid, meter,
            (lambda *_: None, lambda *_: None), date(2026, 10, 25), date(2026, 10, 25))
        self.assertEqual([row['time'] for row in days['2026-10-25']],
                         ['2026-10-25T01:00:00+01:00', '2026-10-25T01:00:00+00:00'])
        with tempfile.TemporaryDirectory() as directory:
            manifest = replay.export_region('ni', mapping, days, Path(directory), '2026-11-08T00:00:00Z')
            self.assertEqual(manifest['days'][0]['count'], 2)

    def test_grid_missing_input_excludes_timestamp(self):
        at = replay.stamp('2026-11-01T00:00:00')
        grid, meter = self.inputs([at])
        del grid['ni', 'solar'][at]
        days, _ = replay.assemble('ni', {'test': ['GU_TEST']}, grid, meter,
            (lambda *_: None, lambda *_: None), date(2026, 11, 1), date(2026, 11, 1))
        self.assertEqual(dict(days), {})

    def test_historical_availability_does_not_leak_across_absent_day(self):
        report = dict(kind='PUB_DlyGenUnitTechCharDataTrans', date='2026-09-09',
                      published='2026-09-10T14:00:00', resource='baseline.xml',
                      rows=[['GU_TEST', '2026-09-01T00:00:00Z', 0, '2026-09-01T00:00:00Z'],
                            ['GU_TEST', '2026-09-09T10:00:00Z', 100, '2026-09-09T09:59:00Z']])
        available, maximum = replay.declared_at([report], {'GU_TEST'})
        self.assertEqual(available('GU_TEST', replay.stamp('2026-09-08T23:00:00')), 0)
        self.assertEqual(available('GU_TEST', replay.stamp('2026-09-09T10:00:00')), 100)
        self.assertIsNone(available('GU_TEST', replay.stamp('2026-09-09T23:00:00')))
        self.assertIsNone(maximum('GU_TEST', replay.stamp('2026-09-09T10:00:00')))

    def test_prior_days_and_timestamps_survive_rolling_source_window(self):
        first = replay.stamp('2026-11-01T00:00:00')
        instants = [first, first + timedelta(minutes=15)]
        grid, meter = self.inputs(instants)
        mapping = {'test': ['GU_TEST']}
        days, _ = replay.assemble('ni', mapping, grid, meter,
            (lambda *_: None, lambda *_: None), date(2026, 11, 1), date(2026, 11, 1))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            replay.export_region('ni', mapping, days, output, '2026-11-08T00:00:00Z')
            replay.export_region('ni', mapping, {'2026-11-01': days['2026-11-01'][:1]}, output,
                                 '2026-11-08T01:00:00Z')
            manifest = replay.export_region('ni', mapping, {}, output, '2026-11-08T02:00:00Z')
            self.assertEqual(manifest['days'][0]['count'], 2)
            data = json.loads((output / 'ni/2026-11-01.json').read_text())
            data['rows'][0]['outputs'][0] = None
            with self.assertRaises(ValueError):
                replay.validate_day(data)

    def test_new_missing_declaration_retains_value_for_same_historical_instant(self):
        at = replay.stamp('2026-11-01T00:00:00')
        grid, meter = self.inputs([at])
        mapping = {'test': ['GU_TEST']}
        days, _ = replay.assemble('ni', mapping, grid, meter,
            (lambda *_: 50, lambda *_: 100), date(2026, 11, 1), date(2026, 11, 1))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            replay.export_region('ni', mapping, days, output, '2026-11-08T00:00:00Z')
            days['2026-11-01'][0]['available'] = [None]
            days['2026-11-01'][0]['maximum'] = [None]
            replay.export_region('ni', mapping, days, output, '2026-11-08T01:00:00Z')
            data = json.loads((output / 'ni/2026-11-01.json').read_text())
            self.assertEqual(data['rows'][0]['available'], [50])
            self.assertEqual(data['rows'][0]['maximum'], [100])


if __name__ == '__main__':
    unittest.main()
