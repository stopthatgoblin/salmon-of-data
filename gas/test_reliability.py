from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from gas.cloud import LocalStore, MANIFEST, STATUS, collection_days, fingerprint, publish
from gas.collect import Collection, intervals, validate
from gas.sources import MeterDataPending, Sources, iso
from electricity.research.ni_gas.estimate import gas_window


def snapshot(day=date(2026,11,18), missing=()):
    data=json.loads((Path(__file__).resolve().parents[1]/'public/data/ireland-gas/2026-11-08.json').read_text())
    first,last=gas_window(day)
    data.update(schema=3,gasDay=day.isoformat(),fromUtc=iso(first),toUtc=iso(last),capturedAt='2026-11-19T19:00:00Z')
    for i,row in enumerate(data['hourly']):row['time']=iso(first+timedelta(hours=i))
    basis=dict(meteredHours=24,dispatchEstimateHours=0,estimateFromUtc=iso(last))
    data['electricityBasis'].update(basis,regional={region:deepcopy(basis) for region in ['ni','roi']})
    data['sourceChecks']={'pending':[]}
    for region in missing:
        row=data['regions'][region]
        row.update(electricity=None,demandShare=None)
        if region=='ni':row.update(powerGas=None,otherGas=None,powerShare=None)
        data['units'][region]=[]
        data['electricityBasis']['regional'][region]=None
        data['electricityBasis'].update(meteredHours=None,dispatchEstimateHours=None,estimateFromUtc=None)
        data['sourceChecks']['pending'].append(dict(source='SEMO meter data',gasDay=day.isoformat(),region=region,reason='Missing readings'))
    return data


class Reliability(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=LocalStore(self.temp.name)

    def test_partial_gas_day_advances_then_recovers_without_losing_first_edition(self):
        old=publish(self.store,[snapshot(date(2026,11,17))],target=date(2026,11,17))
        now=datetime(2026,11,19,20,tzinfo=timezone.utc)
        partial=publish(self.store,[snapshot(missing=['ni'])],target=date(2026,11,18),now=now)
        self.assertEqual(partial['latest'],'2026-11-18')
        self.assertFalse(partial['targetComplete'])
        self.assertEqual(partial['lastSuccess'],old['lastSuccess'])
        self.assertEqual(partial['waitingForSource']['source'],'SEMO meter data')
        first_version=partial['days'][-1]['version']
        recovered=publish(self.store,[snapshot()],target=date(2026,11,18),now=now+timedelta(hours=1))
        self.assertTrue(recovered['targetComplete'])
        self.assertFalse(recovered['pending'])
        self.assertIn(first_version,recovered['days'][-1]['versions'])
        self.assertIsNotNone(self.store.get_json('public/gas/day/2026-11-18/'+first_version))
        retained=publish(self.store,[snapshot(missing=['ni'])],target=date(2026,11,18))
        self.assertEqual(retained['days'],recovered['days'])
        self.assertEqual(retained['changedDays'],[])

    def test_timestamp_only_retry_has_no_immutable_write_or_data_change(self):
        now=datetime(2026,11,19,20,tzinfo=timezone.utc)
        data=snapshot()
        original=publish(self.store,[data],target=date(2026,11,18),now=now)
        data['capturedAt']='2026-11-20T10:00:00Z'
        data['snapshotAsOf']='2026-11-20'
        data['reuse']['entsogExtractionDate']='2026-11-20'
        with patch.object(self.store,'put_json',wraps=self.store.put_json) as put:
            unchanged=publish(self.store,[data],target=date(2026,11,18),now=now+timedelta(minutes=20))
        self.assertEqual(unchanged['changedDays'],[])
        self.assertEqual(unchanged['days'],original['days'])
        self.assertEqual(unchanged['lastDataChange'],original['lastDataChange'])
        self.assertNotEqual(unchanged['lastChecked'],original['lastChecked'])
        self.assertFalse(any(call.args[0].startswith('public/gas/day/') for call in put.call_args_list))
        data['notes'].append('Changed source evidence')
        self.assertNotEqual(fingerprint(data),original['days'][0]['version'])

    def test_a_return_to_an_earlier_value_reuses_its_original_immutable_edition(self):
        data=snapshot()
        original=publish(self.store,[data],target=date(2026,11,18))
        version=original['days'][0]['version']
        key='public/gas/day/2026-11-18/'+version
        first_edition=self.store.get_json(key)
        changed=deepcopy(data);changed['notes'].append('Revised source evidence')
        publish(self.store,[changed],target=date(2026,11,18))
        data['capturedAt']='2026-11-20T00:00:00Z'
        reverted=publish(self.store,[data],target=date(2026,11,18))
        self.assertEqual(reverted['days'][0]['version'],version)
        self.assertEqual(len(reverted['days'][0]['versions']),2)
        self.assertEqual(self.store.get_json(key),first_edition)

    def test_old_unresolved_days_survive_and_rotate_outside_revision_window(self):
        old=['2026-11-08','2026-11-09','2026-11-10']
        self.store.put_json(STATUS,dict(pendingDays=[dict(gasDay=day,source='GNI daily data') for day in old],backlogCursor='2026-11-08'))
        planned=collection_days(self.store,date(2026,11,24),7)
        self.assertEqual([day.isoformat() for day in planned[-2:]],old[1:])
        result=publish(self.store,[snapshot()],target=date(2026,11,18),checked_days=['2026-11-18'])
        self.assertTrue(result['targetComplete'])
        self.assertEqual({row['gasDay'] for row in result['pendingDays']},set(old))
        self.assertTrue(result['pending'])

    def test_partial_schema_never_turns_missing_power_into_a_zero_or_share(self):
        data=snapshot(missing=['ni'])
        validate(data)
        for key,value in [('powerGas',0),('otherGas',0),('powerShare',0),('demandShare',0),('electricity',0)]:
            with self.subTest(key=key):
                invalid=deepcopy(data);invalid['regions']['ni'][key]=value
                with self.assertRaises(ValueError):validate(invalid)
        invalid=deepcopy(data);invalid['sourceChecks']['pending']=[]
        with self.assertRaises(ValueError):validate(invalid)

    def test_gas_assembly_survives_ni_meter_failure_and_retains_roi_output(self):
        data=snapshot()
        day=date.fromisoformat(data['gasDay']);first,last=gas_window(day)
        epoch=first.timestamp()*1000
        gas=[dict(name=location,location=location,group='Daily Delivered Quantity of Gas',data=[[epoch,data['flows'][key]*1e6]]) for location,key in [('Moffat','scotland'),('Bellanaboy','corrib')]]
        consumption=[dict(name=location,location=location,group='Gas Consumption',data=[[epoch,value*1e6]]) for location,value in [('DM',10),('NDM',10),('ROI LDM',data['regions']['roi']['totalGas']-20),('ROI Power Gen',data['regions']['roi']['powerGas'])]]
        allocations=[dict(name=name,data=[[epoch,data['flows'][key]*1e6]]) for name,key in [('Moffat','roiAllocated'),('Northern Ireland','niAllocated')]]
        hourly=[dict(location=location,group='Hourly Delivered Quantity of Gas',data=[[datetime.fromisoformat(row['time'].replace('Z','+00:00')).timestamp()*1000,row[key]*1e6] for row in data['hourly']]) for location,key in [('Moffat','scotland'),('Bellanaboy','corrib')]]
        def entsog(point,direction,key):
            return dict(pointKey=point,directionKey=direction,indicator='Physical Flow',periodFrom=iso(first),periodTo=iso(last),unit='kWh/d',value=data['flows'][key]*1e6)
        collection=Collection.__new__(Collection)
        collection.gas_first=True;collection.first_day=day;collection.target=day
        collection.demands={};collection.demand_errors={};collection.meter_sources=[]
        collection.sources=Mock()
        collection.sources.gni.side_effect=lambda series,day,frequency='daily':({'physicalflows':gas if frequency=='daily' else hourly,'commercialentrypoint':allocations,'gasconsumption':consumption}[series],'https://example.com/'+series)
        collection.sources.entsog.side_effect=lambda operator,day,**kw:([entsog('ITP-00077','entry','snipPhysical'),entsog('DIS-00017','exit','stranraer')] if operator=='UK-TSO-0002' else [entsog('ITP-00222','entry','southNorth')],'https://example.com/entsog')
        def electricity(day,region):
            if region=='ni':raise MeterDataPending(day,reason='No NI meter prefix')
            return dict(units=data['units']['roi'],basis=data['electricityBasis']['regional']['roi'],sources={},dispatch=[])
        collection.electricity=electricity
        assembled=collection.assemble(day)
        self.assertEqual(assembled['flows'],data['flows'])
        self.assertIsNone(assembled['regions']['ni']['powerGas'])
        self.assertGreater(assembled['regions']['roi']['electricity'],0)
        self.assertEqual(assembled['regions']['roi']['powerGas'],data['regions']['roi']['powerGas'])
        self.assertEqual(assembled['sourceChecks']['pending'][0]['region'],'ni')
        hourly[0]['data'].append(hourly[0]['data'][0][:])
        self.assertEqual(len(collection.assemble(day)['hourly']),24)
        hourly[0]['data'].append([epoch,1])
        waiting=collection.assemble(day)
        self.assertEqual(waiting['hourly'],[])
        self.assertTrue(any(row['source']=='GNI hourly flows' for row in waiting['sourceChecks']['pending']))
        collection.electricity=lambda day,region: dict(units=[dict(gasGwh=data['flows']['niAllocated']+1)],
            basis=data['electricityBasis']['regional']['ni'],sources={},dispatch=[]) if region=='ni' else electricity(day,region)
        invalid_model=collection.assemble(day)
        self.assertEqual(invalid_model['flows'],data['flows'])
        self.assertIsNone(invalid_model['regions']['ni']['powerGas'])
        self.assertTrue(any('model review required' in row['reason'] for row in invalid_model['sourceChecks']['pending']))

    def test_catalog_keeps_reports_after_the_live_index_rolls_forward(self):
        source=Sources(Path(self.temp.name)/'sources')
        old=dict(ResourceName='PUB_DailyMeterDataD1_202611171500.xml',Date='2026-11-16',PublishTime='2026-11-17T15:00:00')
        new=dict(ResourceName='PUB_DailyMeterDataD1_202611191500.xml',Date='2026-11-18',PublishTime='2026-11-19T15:00:00')
        with patch.object(source,'json',return_value=dict(items=[old],pagination=dict(totalPages=1))):source.index('PUB_DailyMeterDataD1',date(2026,11,10))
        with patch.object(source,'json',return_value=dict(items=[new],pagination=dict(totalPages=1))):rows=source.index('PUB_DailyMeterDataD1',date(2026,11,10))
        self.assertEqual({row['ResourceName'] for row in rows},{old['ResourceName'],new['ResourceName']})
