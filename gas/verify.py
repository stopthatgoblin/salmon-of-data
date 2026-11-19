"""Exercise date advance, outage recovery and no-op publication in isolated preview keys.

Reported values come from real upstream days. Only the NI availability mask is
replayed. This never publishes simulated data to the public dashboard archive.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re

from gas.cloud import CloudStore, LocalStore, ROOT, publish
from gas.collect import Collection
from gas.sources import iso
from zoneinfo import ZoneInfo


class VerificationStore:
    def __init__(self, store, run):
        if not re.fullmatch(r'[a-zA-Z0-9-]{1,40}',run):raise ValueError('Invalid verification run')
        self.store,self.prefix=store,'private/gas/verification/'+run+'/'
    def get_json(self,key):return self.store.get_json(self.prefix+key)
    def put_json(self,key,value):self.store.put_json(self.prefix+key,value)


def verify(store, previous, complete, *, now=None):
    now=now or datetime.now(timezone.utc)
    day=datetime.fromisoformat(complete['gasDay']).date()
    first=publish(store,[previous],target=datetime.fromisoformat(previous['gasDay']).date(),now=now)
    partial=deepcopy(complete)
    partial['regions']['ni'].update(electricity=None,powerGas=None,otherGas=None,powerShare=None,demandShare=None)
    partial['units']['ni']=[]
    partial['electricityBasis'].update(meteredHours=None,dispatchEstimateHours=None,estimateFromUtc=None)
    partial['electricityBasis']['regional']['ni']=None
    partial['sourceChecks']['pending']=[dict(source='SEMO meter data',gasDay=day.isoformat(),region='ni',reason='Recorded meter-outage replay')]
    second=publish(store,[partial],target=day,now=now+timedelta(seconds=1))
    if not (second['latest']>first['latest'] and not second['targetComplete']):raise RuntimeError('Partial gas publication did not advance its date')
    first_version=second['days'][-1]['version']
    recovered=publish(store,[complete],target=day,now=now+timedelta(seconds=2))
    if not recovered['targetComplete'] or recovered['pending']:raise RuntimeError('Source recovery did not complete the requested day')
    if first_version not in recovered['days'][-1]['versions']:raise RuntimeError('Recovery lost the accepted first edition')
    repeated=deepcopy(complete)
    repeated['capturedAt']=iso(now+timedelta(seconds=3))
    unchanged=publish(store,[repeated],target=day,now=now+timedelta(seconds=3))
    if unchanged['changedDays'] or unchanged['days']!=recovered['days']:raise RuntimeError('Timestamp-only retry created a revision')
    return dict(dateAdvance=True,recovery=True,unchangedRetry=True,firstEditionRetained=True,
                previousDay=previous['gasDay'],recoveredDay=complete['gasDay'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-dir',type=Path)
    parser.add_argument('--cache',type=Path,default=ROOT/'outputs/gas-live/sources')
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    if args.local_dir:
        store=LocalStore(args.local_dir)
    else:
        config=json.loads((ROOT/'wrangler.electricity-preview.jsonc').read_text())
        preview=next(row['id'] for row in config['kv_namespaces'] if row['binding']=='GAS_DATA')
        if os.environ.get('GAS_TARGET')!='preview' or os.environ.get('GAS_KV_NAMESPACE_ID')!=preview:
            raise ValueError('Recovery verification is restricted to the preview namespace')
        store=CloudStore()
    today=datetime.now(ZoneInfo('Europe/Dublin')).date()
    target=today-timedelta(days=2)
    collection=Collection(target,args.cache,2,args.offline,allow_older=True,gas_first=True)
    previous,complete=[collection.assemble(day) for day in [target-timedelta(days=1),target]]
    if any(value is None for row in complete['regions'].values() for value in [row['electricity'],row['demand'],row['powerGas']]) or complete['sourceChecks']['pending']:
        raise RuntimeError('Real source coverage is insufficient for the recovery verification')
    result=verify(VerificationStore(store,os.environ.get('GITHUB_RUN_ID','local')),previous,complete)
    output=ROOT/'outputs/gas-live/verification.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result),flush=True)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as summary:
            summary.write('## Preview publication verification\n\nReal source reports, isolated private preview keys; NI availability outage replay.\n\n')
            summary.write(f"Date advanced from {result['previousDay']} to {result['recoveredDay']}; recovery, retained first edition and unchanged retry all passed.\n\n")


if __name__=='__main__':main()
