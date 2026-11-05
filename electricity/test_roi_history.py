"""Complete-day ROI history, shared NI inputs, retention and private archives."""
import copy
from datetime import date
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cloud
import roi_cloud
from roi import history


def dataset():
    grid = {key:{'2026-11-01':[(f'{minute//60:02}:{minute%60:02}:00',value) for minute in range(0,1440,15)]}
        for key,value in dict(demand=4000,generation=3500,wind=500,solar=100,eastWest=-100,greenlink=200).items()}
    ni = dict(version='a'*24,generatedAt='2026-11-02T07:00:00Z',first='2026-11-01',last='2026-11-01',
        series=[dict(key='northSouth',expected=96)],days=[dict(date='2026-11-01',v=[-150],n=[96])])
    rows=history.assemble(grid,ni,2026,date(2026,11,1))
    # Leading empty dates are trimmed; source-labelled NI flow is part of the cohort.
    result=dict(schema=1,dataBasis='public-source-history',generatedAt='2026-11-02T08:00:00Z',first=rows[0]['date'],last=rows[-1]['date'],series=copy.deepcopy(history.SERIES),days=rows,requestFailures=0,
        niSource={key:ni[key] for key in ['version','generatedAt','first','last']})
    history.refresh_coverage(result)
    return result,grid,ni


class HistoryTests(unittest.TestCase):
    def test_complete_days_shared_signed_flow_and_missing_solar(self):
        data,grid,ni=dataset()
        history.validate(data)
        columns={s['key']:i for i,s in enumerate(data['series'])}
        self.assertEqual(data['days'][0]['v'][columns['northSouth']],150)
        self.assertEqual(data['days'][0]['v'][columns['eastWest']],-100)
        self.assertEqual(data['days'][0]['v'][columns['otherROI']],2900)
        grid['solar']['2026-11-01'].pop()
        row=history.assemble(grid,ni,2026,date(2026,11,1))[0]
        self.assertIsNone(row['v'][columns['solar']])
        self.assertIsNone(row['v'][columns['otherROI']])
        self.assertEqual(row['n'][columns['solar']],95)
        self.assertEqual(row['v'][columns['generation']],3500)

    def test_partial_refresh_retains_the_entire_accepted_regional_cohort(self):
        old,_,_=dataset()
        new=copy.deepcopy(old)
        columns={s['key']:i for i,s in enumerate(new['series'])}
        new['generatedAt']='2026-11-03T08:00:00Z'
        new['days'][0]['v'][columns['solar']]=None
        new['days'][0]['n'][columns['solar']]=95
        new['days'][0]['v'][columns['otherROI']]=None
        new['days'][0]['v'][columns['demand']]=9999
        new['days'][0]['v'][columns['northSouth']]=-999
        history.retain_complete(new,old)
        self.assertEqual(new['days'],old['days'])
        self.assertEqual(new['retainedCompleteDays']['dates'],['2026-11-01'])
        history.validate(new,old)
        broken=copy.deepcopy(old)
        broken['days'][0]['v'][0]=None
        with self.assertRaisesRegex(ValueError,'would be lost'):
            history.validate(broken,old)

    def test_incomplete_day_and_missing_history_version_rejected(self):
        data,_,_=dataset()
        data['days'][0]['n'][0]=95
        with self.assertRaisesRegex(ValueError,'Partial'):
            history.validate(data)
        data,_,_=dataset()
        data['niSource']['version']='bad'
        with self.assertRaisesRegex(ValueError,'NI source version'):
            history.validate(data)

    def test_history_state_round_trip_and_source_failure_do_not_touch_overview(self):
        data,_,ni=dataset()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);work=root/'work';kv=cloud.FileKV(root/'kv')
            output=work/'dashboard/dist/assets/history.json';output.parent.mkdir(parents=True);output.write_bytes(cloud.encode(data))
            cache=work/'dashboard/history-cache';cache.mkdir();(cache/'inputs.json.gz').write_bytes(gzip.compress(b'{"raw":"retained"}'))
            (work/'dashboard/history-audit.json').write_text('{}')
            kv.put('public/roi/snapshot/current',b'{"unchanged":true}')
            cloud.publish(kv,'history',work,data,prefix='roi/')
            pointer=kv.get_json('private/roi/history/current')
            _,restored=cloud.load_state(kv,'history',root/'restored',require_latest=True,prefix='roi/')
            self.assertEqual(restored,data)
            with patch.object(roi_cloud,'accepted_ni',return_value=ni), patch.object(history,'collect',side_effect=RuntimeError('source failure')):
                with self.assertRaisesRegex(RuntimeError,'source failure'):
                    roi_cloud.run_history(kv,force=True)
            after=kv.get_json('private/roi/history/current')
            self.assertEqual(after['records'],pointer['records'])
            self.assertFalse(after['ok'])
            self.assertEqual(kv.get('public/roi/snapshot/current'),b'{"unchanged":true}')


if __name__=='__main__':
    unittest.main()
