"""ROI alignment, independent publication and retention on source failure."""
import copy
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import cloud
import roi_cloud
from roi import collect

ROOT = Path(__file__).resolve().parent.parent


def snapshot():
    data = json.loads((ROOT / 'public/data/roi-electricity/snapshot.json').read_text())
    data['ni']['version'] = 'a' * 24
    data['ni']['dataBasis'] = 'accepted-ni-snapshot'
    data['sources']['grid'] = {key: value for key, value in data['sources']['grid'].items() if key.startswith('ROI:')}
    return data


class ROITests(unittest.TestCase):
    def test_dispatch_gap_hides_estimates_and_complete_reports_restore_them(self):
        uid = 'GU_TEST'
        def xml(rows):
            root = ET.Element('Report')
            for row in rows:
                ET.SubElement(root, 'Row', row)
            return root
        reports = {
            'PUB_DailyRegisteredUnits': xml([dict(UnitID=uid,UnitName='Test',Status='Registered')]),
            'PUB_DailyTechnicalOfferData': xml([dict(ResourceName=uid,MaximumGeneration='100',StartTime='2026-11-12T00:00:00',FuelType='GAS')]),
            'PUB_DlyGenUnitTechCharDataTrans': xml([dict(ResourceName=uid,OutturnAvailability='100',EffectiveTime='2026-11-12T00:00:00',IssueTime='2026-11-12T00:00:00')]),
            'PUB_DailyMeterDataD1': xml([dict(ResourceName=uid,MeteredMW='20',StartTime='2026-11-12T13:00:00',EndTime='2026-11-12T13:30:00')]),
        }
        def report(name):
            return dict(ResourceName=name+'.xml',PublishTime='2026-11-12T13:50:00'), reports[name]
        with tempfile.TemporaryDirectory() as directory, patch.object(collect,'CACHE',Path(directory)), \
             patch.object(collect,'NOW',datetime(2026,11,12,16,30)), patch.object(collect,'UNITS',{uid}), \
             patch.object(collect,'report',side_effect=report):
            manifest = []
            for hour, value in [(13,50),(15,60)]:
                name=f'PUB_HrlyDispatchInstr_20261112{hour:02}00.xml'
                (Path(directory)/name).write_bytes(ET.tostring(xml([dict(ResourceName=uid,
                    InstructionTimeStamp=f'2026-11-12T{hour:02}:15:00',InstructionIssueTime=f'2026-11-12T{hour:02}:10:00',
                    InstructionCode='MWOF',DispatchInstruction=str(value))])))
                manifest.append(dict(ResourceName=name,PublishTime=f'2026-11-12T{hour+1:02}:15:00'))
            path=Path(directory)/'plant-report-manifest.json'
            path.write_text(json.dumps(manifest))
            units, provenance=collect.station_capture(datetime(2026,11,12,15,30))
            self.assertIsNone(units[uid]['output'])
            self.assertEqual(units[uid]['basis'],'dispatch_gap')
            self.assertEqual(provenance['missingDispatchHours'],['2026-11-12T14:00:00Z'])
            # A published empty hour is complete coverage, not a missing hour.
            name='PUB_HrlyDispatchInstr_202611121400.xml'
            (Path(directory)/name).write_bytes(ET.tostring(xml([])))
            manifest.append(dict(ResourceName=name,PublishTime='2026-11-12T15:15:00'))
            path.write_text(json.dumps(manifest))
            units, provenance=collect.station_capture(datetime(2026,11,12,15,30))
            self.assertEqual(units[uid]['output'],60)
            self.assertEqual(provenance['missingDispatchHours'],[])

    def test_current_grid_publishes_with_explicitly_unknown_station_outputs(self):
        data=snapshot()
        units={u['id']:{**u,'output':None,'basis':'dispatch_gap'} for s in data['stations'] for u in s['units']}
        plants={**data['sources']['plants'],'missingDispatchHours':['2026-11-04T14:00:00Z']}
        grid={tuple(key.split(':')):source['value'] for key,source in data['sources']['grid'].items()}
        at=datetime.fromisoformat(data['time'].removesuffix('Z'))
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'snapshot.json'
            output.write_bytes(cloud.encode(data))
            with patch.object(collect,'SNAPSHOT',output),patch.object(collect,'CACHE',Path(directory)), \
                 patch.object(collect,'grid_capture',return_value=(at,grid,data['sources']['grid'])), \
                 patch.object(collect,'station_capture',return_value=(units,plants)), \
                 patch.object(collect,'peaks',return_value=data['expectedPeaks']):
                rebuilt=collect.build(data['ni'])
        roi_cloud.validate(rebuilt,data)
        self.assertEqual(rebuilt['time'],data['time'])
        self.assertEqual(rebuilt['demand'],data['demand'])
        self.assertEqual(rebuilt['interconnectors'],data['interconnectors'])
        self.assertTrue(all(s['output'] is None for s in rebuilt['stations']))
        self.assertAlmostEqual(rebuilt['otherGeneration'],data['generation']-data['wind']-data['solar'])
        rebuilt['stations'][0]['units'][0]['output']=0
        with self.assertRaisesRegex(ValueError,'cannot cross'):
            roi_cloud.validate(rebuilt,data)

    def test_station_catalog_upgrades_old_archives_and_reallocates_output(self):
        data = snapshot()
        added = {'aughinish', 'tarbert-teg', 'north-wall-teg', 'shannonbridge-teg', 'ringsend-flexgen', 'corduff-flexgen'}
        legacy = copy.deepcopy(data)
        allocated = sum(s['output'] or 0 for s in legacy['stations'] if s['id'] in added)
        legacy['stations'] = [s for s in legacy['stations'] if s['id'] not in added]
        legacy['otherGeneration'] += allocated
        legacy['other'] += allocated
        for station in legacy['stations']:
            station['card'] = [0, 0]
        units = {unit['id']: unit for station in data['stations'] for unit in station['units']}
        grid = {tuple(key.split(':')): source['value'] for key, source in data['sources']['grid'].items()}
        at = datetime.fromisoformat(data['time'].removesuffix('Z'))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'snapshot.json'
            output.write_bytes(cloud.encode(legacy))
            with patch.object(collect, 'SNAPSHOT', output), patch.object(collect, 'CACHE', Path(directory)), \
                 patch.object(collect, 'grid_capture', return_value=(at, grid, data['sources']['grid'])), \
                 patch.object(collect, 'station_capture', return_value=(units, data['sources']['plants'])), \
                 patch.object(collect, 'peaks', return_value=data['expectedPeaks']):
                rebuilt = collect.build(data['ni'])
        roi_cloud.validate(rebuilt, legacy)
        self.assertEqual([s['id'] for s in rebuilt['stations']], [s['id'] for s in collect.STATIONS])
        self.assertEqual([s['card'] for s in rebuilt['stations']], [s['card'] for s in collect.STATIONS])
        self.assertEqual(rebuilt['generation'], legacy['generation'])
        self.assertAlmostEqual(rebuilt['other'], legacy['other'] - allocated)
        self.assertEqual(collect.MAPPING['aughinish'], ['GU_400120', 'GU_400121'])
        self.assertEqual(collect.MAPPING['tarbert-teg'], ['GU_406490'])

    def test_demand_peak_time_matches_actual_or_forecast_and_rejects_gaps(self):
        at = datetime(2026, 11, 4, 14)
        start = at.replace(hour=0)
        actual = {start + timedelta(minutes=i): 800 for i in range(0, 14*60-30, 15)}
        forecast = {start + timedelta(minutes=i): 1000 for i in range(14*60, 24*60, 30)}
        forecast.update({at.replace(hour=17, minute=30): 1500, at.replace(hour=18): 1500})
        def write(path, values, field):
            path.write_text(json.dumps({'url': 'https://example.test/' + path.name,
                'retrievedAt': '2026-11-04T14:00:00Z', 'data': {'Rows': [
                    {'Region': 'ROI', 'FieldName': field, 'Value': value,
                     'EffectiveTime': stamp.strftime('%d-%b-%Y %H:%M:%S')} for stamp,value in values.items()]}}))
        with tempfile.TemporaryDirectory() as directory, patch.object(collect, 'CACHE', Path(directory)), patch.object(collect, 'NOW', at):
            write(Path(directory)/'ROI-demand-forecast.json', forecast, 'DEMAND_FORECAST_VALUE')
            for observed, value, clock in [(1400, 1500, '17:30'), (1600, 1600, '08:15')]:
                with self.subTest(observed=observed):
                    actual[start + timedelta(hours=8, minutes=15)] = observed
                    write(Path(directory)/'ROI-demand.json', actual, 'SYSTEM_DEMAND')
                    peak = collect.peaks(at)
                    self.assertEqual((peak['demand'], peak['demandTime']), (value, clock))
            del actual[start + timedelta(hours=6)]
            write(Path(directory)/'ROI-demand.json', actual, 'SYSTEM_DEMAND')
            peak = collect.peaks(at)
            self.assertIsNone(peak['demand'])
            self.assertIsNone(peak['demandTime'])

    def test_signed_balances_unknown_output_and_alignment(self):
        data = snapshot()
        roi_cloud.validate(data)
        changed = copy.deepcopy(data)
        station = next(s for s in changed['stations'] if s['output'])
        previous = station['output']
        station['output'] = station['units'][0]['output'] = None
        changed['otherGeneration'] += previous
        changed['other'] += previous
        roi_cloud.validate(changed)
        for key in ['other', 'reconciliation']:
            changed = copy.deepcopy(data)
            changed[key] += 10
            with self.assertRaisesRegex(ValueError, 'balance'):
                roi_cloud.validate(changed)
        changed = copy.deepcopy(data)
        changed['ni']['time'] = '2026-11-04T10:00:00Z'
        with self.assertRaisesRegex(ValueError, 'aligned'):
            roi_cloud.validate(changed)
        changed = copy.deepcopy(data)
        changed['time'] = '2026-11-03T10:00:00Z'
        with self.assertRaisesRegex(ValueError, 'backwards'):
            roi_cloud.validate(changed, data)

    def test_roi_selects_exact_accepted_ni_time_without_refetching_ni(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(collect, 'CACHE', Path(directory)):
            rows = [dict(Region=region, FieldName=field, EffectiveTime='04-Nov-2026 19:00:00', Value=i)
                    for i, (region, field) in enumerate(collect.FIELDS)]
            rows += [dict(row, EffectiveTime='04-Nov-2026 19:15:00', Value=999) for row in rows]
            payload = dict(url='https://www.smartgriddashboard.com/api/chart/', retrievedAt='2026-11-04T19:30:00Z', data=dict(Rows=rows))
            (Path(directory) / 'ROI-demand.json').write_text(json.dumps(payload))
            at, values, provenance = collect.grid_capture({'time': '2026-11-04T19:00:00Z'})
            self.assertEqual(collect.iso(at), '2026-11-04T19:00:00Z')
            self.assertEqual(values[collect.FIELDS[0]], 0)
            self.assertEqual(len(provenance), 6)
            with self.assertRaisesRegex(ValueError, 'accepted NI'):
                collect.grid_capture({'time': '2026-11-04T18:45:00Z'})
            rows.append(dict(rows[0], Value=998))
            (Path(directory) / 'ROI-demand.json').write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, 'Conflicting'):
                collect.grid_capture({'time': '2026-11-04T19:00:00Z'})

    def test_regional_publication_restores_own_state_and_never_changes_ni(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kv = cloud.FileKV(root / 'kv')
            kv.put('public/snapshot/current', b'{"NI":"unchanged"}')
            work = root / 'work'
            output = work / 'dashboard/dist/assets/snapshot.json'
            output.parent.mkdir(parents=True)
            data = snapshot()
            output.write_bytes(cloud.encode(data))
            cloud.publish(kv, 'snapshot', work, data, prefix='roi/')
            self.assertEqual(kv.get('public/snapshot/current'), b'{"NI":"unchanged"}')
            _, restored = cloud.load_state(kv, 'snapshot', root / 'restored', require_latest=True, prefix='roi/')
            self.assertEqual(restored, data)
            pointer = kv.get_json('private/roi/snapshot/current')
            accepted = kv.get(pointer['records'][0]['key'])
            with patch.object(roi_cloud, 'accepted_ni', side_effect=RuntimeError('source failure')):
                with self.assertRaisesRegex(RuntimeError, 'source failure'):
                    roi_cloud.run(kv, force=True)
            after = kv.get_json('private/roi/snapshot/current')
            self.assertFalse(after['ok'])
            self.assertEqual(after['records'], pointer['records'])
            self.assertEqual(kv.get(after['records'][0]['key']), accepted)
            self.assertEqual(kv.get('public/snapshot/current'), b'{"NI":"unchanged"}')

    def test_missing_latest_ni_version_never_falls_back_to_different_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            kv = cloud.FileKV(directory)
            ni = (ROOT / 'public/data/ni-electricity/snapshot.json').read_bytes()
            version = hashlib.sha256(ni).hexdigest()[:24]
            kv.put('public/snapshot/' + version, ni)
            kv.put('public/snapshot/current', cloud.encode({'records': [{'version': 'b' * 24}, {'version': version}]}))
            with self.assertRaisesRegex(RuntimeError, 'propagating'):
                roi_cloud.accepted_ni(kv)
            kv.put('public/snapshot/current', cloud.encode({'records': [{'version': version}]}))
            self.assertEqual(roi_cloud.accepted_ni(kv)['version'], version)
            # A newer canonical publication must never fall back to the frozen
            # public pointer while its version is still propagating.
            kv.put('private/snapshot/current', cloud.encode({'records': [{'version': 'b' * 24}]}))
            with self.assertRaisesRegex(RuntimeError, 'propagating'):
                roi_cloud.accepted_ni(kv)


if __name__ == '__main__':
    unittest.main()
