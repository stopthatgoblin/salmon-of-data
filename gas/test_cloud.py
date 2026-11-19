from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from gas.cloud import LocalStore, MANIFEST, STATUS, collect_and_publish, failure, publish, source_wait
from gas.collect import Collection, daily, demand_total, intervals, physical, validate
from gas.sources import GasDataPending, MeterDataPending, Sources, iso
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
            if source != 'PUB_DailyMeterDataD1':
                raise TimeoutError('Unrelated report index is unavailable')
            return [dict(Date='2026-11-11', PublishTime='2026-11-12T15:58:55')]
        with patch('gas.collect.Sources.index', side_effect=index) as queried, patch('gas.collect.Sources.fetch') as fetch:
            with self.assertRaises(MeterDataPending) as caught:
                Collection(date(2026,11,12), Path(self.temp.name) / 'sources')
            self.assertEqual(caught.exception.latest_report_date, '2026-11-11')
            self.assertEqual(caught.exception.gas_day, '2026-11-12')
            self.assertEqual([call.args[0] for call in queried.call_args_list], ['PUB_DailyMeterDataD1'])
            fetch.assert_not_called()

    def test_available_primary_meters_do_not_hide_an_unrelated_source_failure(self):
        def index(source, first):
            if source == 'PUB_DailyMeterDataD1':
                return [dict(Date='2026-11-12', PublishTime='2026-11-13T15:00:00')]
            raise TimeoutError('Report index is unavailable')
        with patch('gas.collect.Sources.index', side_effect=index):
            with self.assertRaises(TimeoutError):
                Collection(date(2026,11,12), Path(self.temp.name) / 'sources')

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

    def test_gni_identical_duplicates_are_accepted_but_conflicts_remain_pending(self):
        day = date(2026,11,8)
        epoch = 1794096000000
        rows = [dict(name='DM',data=[[epoch,1000],[epoch,1000]])]
        self.assertEqual(daily(rows,day,name='DM'),.001)
        rows[0]['data'][1][1] = 1001
        with self.assertRaises(GasDataPending) as caught:
            daily(rows,day,name='DM')
        pending = source_wait(caught.exception)
        self.assertEqual(pending['source'],'GNI daily data')
        self.assertEqual(pending['reason'],'Conflicting daily values for DM')
        rows[0]['data'][1][1] = None
        with self.assertRaises(ValueError):daily(rows,day,name='DM')

    def meter_collection(self, day):
        collection = Collection.__new__(Collection)
        first,last = gas_window(day)
        collection.meters = {(uid,at):(100 if uid == 'ni' else 200,first)
                             for uid in ['ni','roi'] for at in intervals(first-timedelta(minutes=30),last,30)}
        return collection, first, last

    def test_regional_meter_tails_are_estimated_without_overwriting_available_readings(self):
        day = date(2026,11,17)
        collection,first,last = self.meter_collection(day)
        cut = last-timedelta(hours=5)
        for at in intervals(cut,last,30):del collection.meters['ni',at]
        events = {'ni':[(cut,cut,120)]}
        with patch.object(collection,'dispatch',return_value=(events,['dispatch.xml'])) as dispatch:
            meters,actual_cut,urls = collection.complete_meters(day,{'ni','roi'})
        self.assertEqual(actual_cut,cut)
        self.assertEqual(urls,['dispatch.xml'])
        dispatch.assert_called_once_with(cut-timedelta(minutes=30),last,{'ni'})
        self.assertTrue(all(meters['ni',at] == 120 for at in intervals(cut,last,30)))
        self.assertTrue(all(meters['roi',at] == 200 for at in intervals(first,last,30)))
        self.assertEqual(meters['ni',cut-timedelta(minutes=30)],100)
        self.assertNotIn(('ni',cut),collection.meters)

    def test_each_unit_uses_its_own_final_meter_as_dispatch_seed(self):
        day = date(2026,11,17)
        collection,first,last = self.meter_collection(day)
        for uid,hours in [('ni',6),('roi',2)]:
            for at in intervals(last-timedelta(hours=hours),last,30):del collection.meters[uid,at]
        # A dispatch instruction preceding ROI's later meter cutoff must not
        # replace that unit's more recent measured seed.
        events = {'ni':[], 'roi':[(last-timedelta(hours=4),first,999)]}
        with patch.object(collection,'dispatch',return_value=(events,[])):
            meters,cut,_ = collection.complete_meters(day,{'ni','roi'})
        self.assertEqual(cut,last-timedelta(hours=6))
        self.assertEqual(meters['ni',last-timedelta(minutes=30)],100)
        self.assertEqual(meters['roi',last-timedelta(minutes=30)],200)

    def test_full_day_internal_gaps_and_long_tails_still_wait_for_meters(self):
        day = date(2026,11,18)
        for kind in ['full','internal','long']:
            with self.subTest(kind=kind):
                collection,first,last = self.meter_collection(day)
                missing = intervals(first,last,30) if kind == 'full' else [first+timedelta(hours=1)] if kind == 'internal' else intervals(last-timedelta(hours=6,minutes=30),last,30)
                for at in missing:del collection.meters['ni',at]
                with patch.object(collection,'dispatch') as dispatch:
                    with self.assertRaises(MeterDataPending) as caught:
                        collection.complete_meters(day,{'ni','roi'})
                    dispatch.assert_not_called()
                self.assertEqual(source_wait(caught.exception)['source'],'SEMO meter data')
                self.assertTrue(source_wait(caught.exception)['reason'])

    def test_complete_meters_do_not_need_dispatch_reports(self):
        day = date(2026,11,17)
        collection,_,last = self.meter_collection(day)
        with patch.object(collection,'dispatch') as dispatch:
            _,cut,urls = collection.complete_meters(day,{'ni','roi'})
            dispatch.assert_not_called()
        self.assertEqual(cut,last)
        self.assertEqual(urls,[])

    def test_entsog_wrong_period_and_na_are_rejected(self):
        first,last=gas_window(date(2026,11,8))
        row=dict(pointKey='test',directionKey='entry',indicator='Physical Flow',periodFrom=first.isoformat(),periodTo=last.isoformat(),value=0,unit='kWh/d')
        self.assertEqual(physical([row],'test','entry',first,last),0)
        for changed in [dict(row,isNA=True),dict(row,periodTo=first.isoformat())]:
            with self.assertRaises(ValueError):physical([changed],'test','entry',first,last)

    def snapshot_for(self, day, missing=()):
        data = deepcopy(self.snapshot)
        data['schema'] = 2
        data['gasDay'] = day.isoformat()
        first, last = gas_window(day)
        data.update(fromUtc=iso(first), toUtc=iso(last))
        for index, row in enumerate(data['hourly']):
            row['time'] = iso(first + timedelta(hours=index))
        for region in missing:
            data['regions'][region].update(demand=None, demandShare=None)
        return data

    def test_only_explicit_paired_null_demand_is_optional(self):
        partial = self.snapshot_for(date(2026,11,8), ['ni'])
        validate(partial)
        for changes in [dict(demand=None, demandShare=0), dict(demand=0, demandShare=None),
                        dict(demand=-1, demandShare=0), dict(demand=float('nan'), demandShare=0)]:
            data = deepcopy(partial)
            data['regions']['ni'].update(changes)
            with self.assertRaises(ValueError):validate(data)
        for field in ['totalGas','powerGas','electricity','otherGas','powerShare']:
            data = deepcopy(partial)
            data['regions']['ni'][field] = None
            with self.assertRaises(ValueError):validate(data)
        partial['schema'] = 1
        with self.assertRaises(ValueError):validate(partial)

    def test_supported_demand_request_preserves_both_calendar_endpoints(self):
        with patch.object(Sources, 'json', return_value={'Rows': [dict(
                Region='NI', FieldName='SYSTEM_DEMAND', EffectiveTime='17-Nov-2026 04:45:00', Value=1000)]}) as fetch:
            readings, url = Sources(Path(self.temp.name)/'sources').demand('ni',date(2026,11,10),date(2026,11,17))
        self.assertIn('dateRange=day', url)
        self.assertIn('dateFrom=10-Nov-2026', url)
        self.assertIn('dateTo=17-Nov-2026', url)
        self.assertEqual(len(readings), 1)
        self.assertEqual(fetch.call_args.kwargs['headers']['Eirgrid-Content-Request'], 'Nextjs')

    def test_demand_source_failure_is_explicitly_unavailable(self):
        collection = Collection.__new__(Collection)
        collection.target, collection.first_day = date(2026,11,16), date(2026,11,10)
        collection.sources = Sources(Path(self.temp.name)/'sources')
        collection.demand_errors = {}
        with patch.object(collection.sources, 'demand', side_effect=TimeoutError('source timeout')):
            readings, url = collection.optional_demand('ni')
        self.assertEqual(readings, {})
        self.assertEqual(collection.demand_errors, {'ni':'TimeoutError'})
        self.assertIn('dateRange=day', url)

    def test_demand_needs_every_real_quarter_hour_including_clock_change_days(self):
        for day, hours in [(date(2026,3,28),23),(date(2026,10,24),25),(date(2026,11,14),24)]:
            first, last = gas_window(day)
            values = {at:1000 for at in intervals(first,last,15)}
            self.assertEqual(demand_total(values,first,last),hours)
            for unavailable in [None,0,float('nan')]:
                broken = {**values, first:unavailable}
                self.assertIsNone(demand_total(broken,first,last))
            del values[first]
            self.assertIsNone(demand_total(values,first,last))

    def test_missing_primary_meters_can_leave_older_days_eligible(self):
        def index(source, first):
            if source == 'PUB_DailyMeterDataD1':
                return [dict(Date='2026-11-11', PublishTime='2026-11-12T15:58:55')]
            raise TimeoutError('Fallback initialization reached remaining sources')
        with patch('gas.collect.Sources.index', side_effect=index):
            with self.assertRaisesRegex(TimeoutError, 'Fallback initialization'):
                Collection(date(2026,11,12), Path(self.temp.name)/'sources', allow_older=True)
        collection = Collection.__new__(Collection)
        collection.indices = {'PUB_DailyMeterDataD1': [dict(Date='2026-11-11')]}
        with self.assertRaises(MeterDataPending):collection.assemble(date(2026,11,12))

    def test_available_days_publish_while_newest_target_and_demand_keep_retrying(self):
        target = date(2026,11,16)
        now = datetime(2026,11,17,21,tzinfo=timezone.utc)
        partial = self.snapshot_for(date(2026,11,14), ['ni','roi'])
        def assemble(day):
            if day > date(2026,11,14):raise GasDataPending(day)
            return partial
        with patch('gas.cloud.Collection') as collection:
            collection.return_value.assemble.side_effect = assemble
            manifest = collect_and_publish(self.store,target,Path(self.temp.name)/'sources',3,now=now)
        self.assertEqual(manifest['latest'],'2026-11-14')
        self.assertTrue(manifest['pending'])
        self.assertEqual(manifest['days'][-1]['missingDemand'],['ni','roi'])
        status = self.store.get_json(STATUS)
        self.assertEqual(status['targetGasDay'],'2026-11-16')
        self.assertIsNone(status['successfulDate'])
        self.assertEqual(status['waitingForSource']['source'],'GNI daily data')
        partial_version = manifest['days'][-1]['version']
        with patch('gas.cloud.Collection') as collection:
            collection.return_value.assemble.side_effect = self.snapshot_for
            complete = collect_and_publish(self.store,target,Path(self.temp.name)/'sources',3,now=now)
        self.assertEqual(complete['latest'],'2026-11-16')
        self.assertFalse(complete['pending'])
        self.assertEqual(complete['incompleteDays'],[])
        self.assertIsNone(complete['waitingForSource'])
        self.assertEqual(self.store.get_json(STATUS)['successfulDate'],'2026-11-17')
        self.assertIn(partial_version,complete['days'][0]['versions'])
        self.assertIsNotNone(self.store.get_json('public/gas/day/2026-11-14/'+partial_version))

    def test_complete_newest_day_still_retries_missing_historical_demand(self):
        target = date(2026,11,16)
        with patch('gas.cloud.Collection') as collection:
            collection.return_value.assemble.side_effect = lambda day:self.snapshot_for(day,['roi'] if day < target else [])
            manifest = collect_and_publish(self.store,target,Path(self.temp.name)/'sources',2)
        self.assertTrue(manifest['pending'])
        self.assertEqual(manifest['incompleteDays'],[dict(date='2026-11-15',missingDemand=['roi'])])
        self.assertTrue(manifest['targetComplete'])
        self.assertIsNotNone(self.store.get_json(STATUS)['successfulDate'])

    def test_transient_missing_demand_cannot_downgrade_an_accepted_day(self):
        day = date(2026,11,8)
        complete = publish(self.store,[self.snapshot_for(day)],target=day)
        retained = publish(self.store,[self.snapshot_for(day,['ni'])],target=day)
        self.assertEqual(retained['days'],complete['days'])
        self.assertFalse(retained['pending'])

    def test_no_available_core_day_preserves_archive(self):
        accepted = publish(self.store,[self.snapshot])
        with patch('gas.cloud.Collection') as collection:
            collection.return_value.assemble.side_effect = GasDataPending(date(2026,11,16))
            with self.assertRaises(GasDataPending):
                collect_and_publish(self.store,date(2026,11,16),Path(self.temp.name)/'sources',2)
        self.assertEqual(self.store.get_json(MANIFEST),accepted)


if __name__ == '__main__':unittest.main()
