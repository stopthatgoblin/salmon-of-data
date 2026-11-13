from copy import deepcopy
from datetime import date, datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gas.cloud import LocalStore, MANIFEST, STATUS, failure, publish
from gas.collect import Collection, daily, physical, validate
from gas.sources import MeterDataPending
from electricity.research.ni_gas.estimate import gas_window


class GasRules(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((Path(__file__).resolve().parents[1] / 'public/data/ireland-gas/2026-11-08.json').read_text())
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = LocalStore(self.temp.name)

    def test_clock_change_windows_are_real_intervals(self):
        for day, hours in [(date(2026,3,28),23),(date(2026,10,24),25),(date(2026,11,8),24)]:
            first,last=gas_window(day)
            self.assertEqual((last-first).total_seconds()/3600,hours)

    def test_residual_and_denominator_errors_are_rejected(self):
        for field in ['otherGas','demandShare']:
            data=deepcopy(self.snapshot);data['regions']['ni'][field]+=1
            with self.assertRaises(ValueError):validate(data)

    def test_invalid_candidate_cannot_advance_public_archive(self):
        first=publish(self.store,[self.snapshot])
        data=deepcopy(self.snapshot);data['hourly'].pop()
        with self.assertRaises(ValueError):publish(self.store,[data])
        self.assertEqual(first,self.store.get_json(MANIFEST))

    def test_revisions_preserve_first_edition_and_old_dates(self):
        first=publish(self.store,[self.snapshot])
        data=deepcopy(self.snapshot);data['notes'].append('Later accepted edition')
        old=self.store.get_json(MANIFEST)
        old['days'].insert(0,dict(date='2026-09-10',version='a'*24,versions=['a'*24]))
        self.store.put_json(MANIFEST,old)
        updated=publish(self.store,[data])
        self.assertEqual(updated['days'][0]['date'],'2026-09-10')
        self.assertEqual(len(updated['days'][1]['versions']),2)
        version=first['days'][0]['version']
        self.assertIsNotNone(self.store.get_json('public/gas/day/2026-11-08/'+version))

    def test_failed_update_preserves_accepted_latest(self):
        accepted=publish(self.store,[self.snapshot],target=date(2026,11,8))
        failure(self.store,date(2026,11,9),datetime(2026,11,10,19,tzinfo=timezone.utc))
        failed=self.store.get_json(MANIFEST)
        self.assertEqual(failed['days'],accepted['days'])
        self.assertEqual(failed['latest'],accepted['latest'])
        self.assertTrue(failed['lastError'])

    def test_missing_primary_meter_report_is_reported_before_other_sources_are_fetched(self):
        def index(source, first):
            return [dict(Date='2026-11-11', PublishTime='2026-11-12T15:58:55')] if source == 'PUB_DailyMeterDataD1' else []
        with patch('gas.collect.Sources.index', side_effect=index), patch('gas.collect.Sources.fetch') as fetch:
            with self.assertRaises(MeterDataPending) as caught:
                Collection(date(2026,11,12), Path(self.temp.name) / 'sources')
            self.assertEqual(caught.exception.latest_report_date, '2026-11-11')
            self.assertEqual(caught.exception.gas_day, '2026-11-12')
            fetch.assert_not_called()

    def test_source_wait_preserves_archive_and_clears_after_successful_backfill(self):
        accepted = publish(self.store, [self.snapshot], target=date(2026,11,8))
        failure(self.store, date(2026,11,9), datetime(2026,11,10,19,tzinfo=timezone.utc),
                MeterDataPending(date(2026,11,9), '2026-11-08'))
        pending = self.store.get_json(MANIFEST)
        self.assertEqual(pending['days'], accepted['days'])
        self.assertEqual(pending['lastSuccess'], accepted['lastSuccess'])
        self.assertEqual(pending['waitingForSource']['gasDay'], '2026-11-09')
        self.assertIn('Waiting for SEMO meter data', pending['lastError'])
        self.assertEqual(self.store.get_json(STATUS)['targetGasDay'], '2026-11-09')
        updated = publish(self.store, [self.snapshot], target=date(2026,11,8))
        self.assertIsNone(updated['waitingForSource'])
        self.assertIsNone(updated['lastError'])
        self.assertIsNone(self.store.get_json(STATUS)['waitingForSource'])

    def test_zero_is_a_value_and_missing_is_not_zero(self):
        rows=[dict(name='Moffat',data=[[1794096000000,0]])] # 8 November UTC midnight
        self.assertEqual(daily(rows,date(2026,11,8),name='Moffat'),0)
        with self.assertRaises(ValueError):daily(rows,date(2026,11,9),name='Moffat')

    def test_entsog_wrong_period_and_na_are_rejected(self):
        first,last=gas_window(date(2026,11,8))
        row=dict(pointKey='test',directionKey='entry',indicator='Physical Flow',periodFrom=first.isoformat(),periodTo=last.isoformat(),value=0,unit='kWh/d')
        self.assertEqual(physical([row],'test','entry',first,last),0)
        for changed in [dict(row,isNA=True),dict(row,periodTo=first.isoformat())]:
            with self.assertRaises(ValueError):physical([changed],'test','entry',first,last)


if __name__ == '__main__':unittest.main()
