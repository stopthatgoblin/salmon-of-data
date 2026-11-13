"""Assemble aligned gas-day snapshots from reported flows and unit electricity."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path

from electricity.research.ni_gas.estimate import gas_window, fuel_rate, startup_fuel, OIL_UNITS
from gas.sources import MeterDataPending, Sources, iso, newest, parallel, stamp

UTC = timezone.utc
MODEL = json.loads((Path(__file__).parent / 'ni-model.json').read_text())
NI_UNITS = MODEL['units']


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def require(value, message):
    if not value:
        raise ValueError(message)


def daily(rows, day, *, name=None, location=None, group=None):
    series = [r for r in rows if (name is None or r.get('name') == name)
              and (location is None or r.get('location') == location)
              and (group is None or r.get('group') == group)]
    require(len(series) == 1, 'Missing or duplicate GNI series')
    values = [v for epoch, v in series[0]['data'] if datetime.fromtimestamp(epoch / 1000, UTC).date() == day]
    require(len(values) == 1 and finite(values[0]) and values[0] >= 0, 'Missing/invalid GNI daily value')
    return values[0] / 1e6


def physical(rows, point, direction, first, last):
    values = [r for r in rows if r['pointKey'] == point and r['directionKey'] == direction
              and r['indicator'] == 'Physical Flow' and stamp(r['periodFrom']) == first]
    require(len(values) == 1, 'Missing or duplicate ENTSOG physical flow: ' + point)
    row = values[0]
    require(not row.get('isNA') and finite(row.get('value')) and row['unit'] == 'kWh/d'
            and stamp(row['periodTo']) == last, 'Invalid ENTSOG value/period: ' + point)
    return row['value'] / 1e6


def intervals(first, last, minutes):
    count = int((last - first).total_seconds() / (60 * minutes))
    return [first + timedelta(minutes=minutes * n) for n in range(count)]


class Collection:
    def __init__(self, target, cache, revision_days=7, offline=False):
        require(1 <= revision_days <= 14, 'Invalid revision window')
        self.target = target
        self.first_day = target - timedelta(days=revision_days - 1)
        require(self.first_day.isoformat() >= MODEL['validFrom'], 'Model not validated for this historical fleet')
        self.sources = Sources(cache, offline)
        # Enough observation to prove a cold start even on an empty new runner.
        cooling = max(sum(p['startupCoolingHours'][:len(p['startupGjLhv']) - 1]) for p in NI_UNITS.values())
        context = math.ceil(cooling / 24) + 2
        self.context_first = self.first_day - timedelta(days=context)
        names = ['PUB_DailyMeterDataD1', 'PUB_DailyTechnicalOfferData', 'PUB_DailyRegisteredUnits']
        indices = parallel([lambda name=name: self.sources.index(name, self.context_first) for name in names])
        self.indices = dict(zip(names, indices))
        meter_index = self.indices[names[0]]
        if newest(meter_index, target) is None:
            latest = max((r['Date'] for r in meter_index if r['Date'] <= target.isoformat()), default=None)
            raise MeterDataPending(target, latest)
        self.meters, self.meter_sources = {}, []
        jobs = []
        cursor = self.context_first
        while cursor <= target + timedelta(days=1):
            item = newest(self.indices[names[0]], cursor)
            if item:
                jobs.append(lambda item=item: self.sources.report(item))
            cursor += timedelta(days=1)
        require(jobs, 'No SEMO meter reports')
        for root, url in parallel(jobs):
            require(root.get('DatasetName') == names[0], 'Unexpected meter dataset')
            self.meter_sources.append(dict(url=url, date=root.get('Date'), published=root.get('PublishTime')))
            published = stamp(root.get('PublishTime'))
            for row in root:
                uid = row.get('ResourceName')
                at = stamp(row.get('StartTime'))
                if uid not in NI_UNITS and at < gas_window(self.first_day)[0]:
                    continue
                if row.get('MeteredMW') in (None, ''):
                    continue
                require((stamp(row.get('EndTime')) - at).total_seconds() in (1799, 1800), 'Unexpected meter duration')
                mw = float(row.get('MeteredMW')) * 2  # SEMO field is half-hour MWh.
                require(finite(mw), 'Non-finite meter value')
                key = uid, at
                previous = self.meters.get(key)
                if previous and previous[1] == published:
                    require(previous[0] == mw, 'Conflicting meter values')
                if previous is None or published >= previous[1]:
                    self.meters[key] = mw, published
        self.demands = dict(zip(['ni', 'roi'], parallel([
            lambda region=region: self.sources.demand(region, self.first_day, target + timedelta(days=1))
            for region in ['ni', 'roi']])))
        self.dispatch_items = None

    def dated_report(self, name, day):
        eligible = [r for r in self.indices[name] if r['Date'] <= day.isoformat()]
        require(eligible, 'No dated SEMO ' + name)
        chosen = max(eligible, key=lambda r: (r['Date'], r['PublishTime']))
        require((day - date.fromisoformat(chosen['Date'])).days <= 3, 'Stale SEMO registry/technical report')
        return self.sources.report(chosen)

    def dispatch(self, first, last, units):
        if self.dispatch_items is None:
            self.dispatch_items = self.sources.index('PUB_HrlyDispatchInstr', self.first_day)
        # Select by report timestamp, not a fixed latest-N list. Revised reports
        # with the same hour use the newest publication.
        selected = {}
        for item in self.dispatch_items:
            resource = item['ResourceName']
            try:
                hour = datetime.strptime(resource[len('PUB_HrlyDispatchInstr_'):][:10], '%Y%m%d%H').replace(tzinfo=UTC)
            except ValueError:
                continue
            if first.replace(minute=0) - timedelta(hours=1) <= hour <= last + timedelta(hours=1):
                if hour not in selected or item['PublishTime'] > selected[hour]['PublishTime']:
                    selected[hour] = item
        needed = intervals(first.replace(minute=0), last, 60)
        require(all(at in selected for at in needed), 'Missing dispatch report in estimated period')
        grouped, urls = defaultdict(list), []
        for root, url in parallel([lambda item=item: self.sources.report(item) for item in selected.values()]):
            urls.append(url)
            for row in root:
                uid = row.get('ResourceName')
                if uid in units:
                    grouped[uid, stamp(row.get('InstructionTimeStamp')), stamp(row.get('InstructionIssueTime'))].append(row.attrib)
        events = defaultdict(list)
        for (uid, at, issued), rows in grouped.items():
            codes = {r['InstructionCode'] for r in rows}
            values = [float(r['DispatchInstruction']) for r in rows if r['InstructionCode'] == 'MWOF' and r.get('DispatchInstruction') is not None]
            value = 0 if 'TRIP' in codes else max(values) if values else 0 if 'DESY' in codes else None
            events[uid].append((at, issued, value))
        for rows in events.values():
            rows.sort()
        return events, urls

    def assemble(self, day):
        first, last = gas_window(day)
        expected = intervals(first, last, 30)
        tech, tech_url = self.dated_report('PUB_DailyTechnicalOfferData', day)
        register, register_url = self.dated_report('PUB_DailyRegisteredUnits', day)
        names = {r.get('UnitID'): r.get('UnitName') for r in register}
        candidates = {r.get('ResourceName') for r in tech if r.get('Jurisdiction') == 'ROI'
                      and r.get('FuelType') in ('GAS', 'MULTI_FUEL') and r.get('ResourceName') != 'GU_404270'}
        roi = {uid for uid in candidates if any((uid, at) in self.meters for at in expected)}
        require(len(roi) >= 20, 'Incomplete ROI gas/multi-fuel unit roster')
        unknown_ni = {r.get('ResourceName') for r in tech if r.get('Jurisdiction') == 'NI' and r.get('FuelType') in ('GAS', 'MULTI_FUEL') and r.get('ResourceName') not in NI_UNITS and r.get('ResourceName') not in OIL_UNITS and any((r.get('ResourceName'), at) in self.meters for at in expected)}
        require(not unknown_ni, 'Unmodelled NI gas/multi-fuel unit; model review required')
        units = set(NI_UNITS) | roi
        meters = {key: value[0] for key, value in self.meters.items() if key[0] in units}
        cut = next((at for at in expected if any((uid, at) not in meters for uid in units)), last)
        require(cut > first, 'No complete metered prefix for the gas day')
        require(all((uid, at) not in meters for uid in units for at in expected if at >= cut), 'Non-contiguous or uneven meter coverage')
        estimated = (last - cut).total_seconds() / 3600
        require(estimated <= 6, 'More than six hours of dispatch estimates would be required')
        dispatch_urls = []
        if estimated:
            events, dispatch_urls = self.dispatch(cut - timedelta(minutes=30), last, units)
            seed = cut - timedelta(minutes=30)
            def target(uid, at):
                eligible = [e for e in events[uid] if seed <= e[0] <= at and e[1] <= at]
                if not eligible:
                    return max(0, meters[uid, seed])
                value = eligible[-1][2]
                require(value is not None and finite(value), 'Unknown dispatch state')
                return max(0, value)
            for uid in units:
                for at in intervals(cut, last, 30):
                    meters[uid, at] = sum(target(uid, at + timedelta(minutes=m, seconds=30)) for m in range(30)) / 30
        ni_units = []
        for uid, curve in NI_UNITS.items():
            running = sum(fuel_rate(meters[uid, at], curve) * .5 for at in expected)
            starts = []
            for at in expected:
                require((uid, at - timedelta(minutes=30)) in meters, 'Missing NI startup context')
                if meters[uid, at] <= 1 or meters[uid, at - timedelta(minutes=30)] > 1:
                    continue
                cursor = at - timedelta(minutes=30)
                while (uid, cursor) in meters and meters[uid, cursor] <= 1:
                    cursor -= timedelta(minutes=30)
                offline = (at - timedelta(minutes=30) - cursor).total_seconds() / 3600
                fuel = startup_fuel(curve, offline, (uid, cursor) in meters)
                starts.append(dict(time=iso(at), gjLhv=fuel))
            ni_units.append(dict(id=uid, name=curve['name'], electricityGwh=sum(max(0, meters[uid, at]) * .5 / 1000 for at in expected),
                                 gasGwh=(running + sum(r['gjLhv'] for r in starts)) * MODEL['grossNetFactor'] / 3600, starts=starts))
        roi_units = [dict(id=uid, name=names.get(uid, uid), electricityGwh=sum(max(0, meters[uid, at]) * .5 / 1000 for at in expected)) for uid in sorted(roi)]
        fetched = parallel([
            lambda: self.sources.gni('physicalflows', day), lambda: self.sources.gni('gasconsumption', day),
            lambda: self.sources.gni('commercialentrypoint', day), lambda: self.sources.gni('physicalflows', day, 'hourly'),
            lambda: self.sources.entsog('UK-TSO-0002', day),
            lambda: self.sources.entsog('IE-TSO-0001', day, pointKey='ITP-00222', directionKey='entry'),
        ])
        (gas, gas_url), (consumption, consumption_url), (allocation, allocation_url), (hourly, hourly_url), (snip, snip_url), (north, north_url) = fetched
        flows = dict(scotland=daily(gas, day, location='Moffat', group='Daily Delivered Quantity of Gas'),
                     corrib=daily(gas, day, location='Bellanaboy', group='Daily Delivered Quantity of Gas'),
                     roiAllocated=daily(allocation, day, name='Moffat'), niAllocated=daily(allocation, day, name='Northern Ireland'),
                     snipPhysical=physical(snip, 'ITP-00077', 'entry', first, last),
                     stranraer=physical(snip, 'DIS-00017', 'exit', first, last),
                     southNorth=physical(north, 'ITP-00222', 'entry', first, last))
        roi_total = sum(daily(consumption, day, location=k, group='Gas Consumption') for k in ['DM', 'NDM', 'ROI LDM'])
        roi_power = daily(consumption, day, location='ROI Power Gen', group='Gas Consumption')
        ni_power = sum(r['gasGwh'] for r in ni_units)
        regions = {}
        for region, total, power, members in [('ni', flows['niAllocated'], ni_power, ni_units), ('roi', roi_total, roi_power, roi_units)]:
            values, _ = self.demands[region]
            times = intervals(first, last, 15)
            require(all(at in values and finite(values[at]) and values[at] > 0 for at in times), 'Incomplete ' + region + ' demand over the gas day')
            demand = sum(values[at] * .25 / 1000 for at in times)
            electricity = sum(r['electricityGwh'] for r in members)
            require(total > 0 and 0 <= power <= total, 'Invalid regional gas use/residual')
            regions[region] = dict(totalGas=total, powerGas=power, otherGas=total-power, electricity=electricity,
                                   demand=demand, demandShare=electricity/demand*100, powerShare=power/total*100)
        hours = []
        for at in intervals(first, last, 60):
            row = dict(time=iso(at))
            for location, key in [('Moffat', 'scotland'), ('Bellanaboy', 'corrib')]:
                series = [r for r in hourly if r.get('location') == location and r.get('group') == 'Hourly Delivered Quantity of Gas']
                require(len(series) == 1, 'Missing hourly physical-flow series')
                values = [v for epoch, v in series[0]['data'] if datetime.fromtimestamp(epoch/1000, UTC) == at]
                require(len(values) == 1 and finite(values[0]) and values[0] >= 0, 'Missing/invalid hourly physical flow')
                row[key] = values[0] / 1e6
            hours.append(row)
        differences = {key: sum(r[key] for r in hours) - flows[key] for key in ['scotland', 'corrib']}
        require(all(abs(value) <= max(.1, flows[key] * .005) for key, value in differences.items()), 'Hourly/daily source totals disagree beyond tolerance')
        captured = iso(datetime.now(UTC))
        metered = (cut-first).total_seconds()/3600
        result = dict(schema=1, gasDay=day.isoformat(), fromUtc=iso(first), toUtc=iso(last), snapshotAsOf=captured[:10], capturedAt=captured,
                      flows=flows, regions=regions, hourly=hours, units=dict(ni=ni_units, roi=roi_units),
                      electricityBasis=dict(meteredHours=metered, dispatchEstimateHours=estimated, estimateFromUtc=iso(cut),
                          description=f'{metered:g} hours metered; {estimated:g} hours reconstructed dispatch targets. Gas firing is assumed.'),
                      niGasBasis=dict(grossNetFactor=MODEL['grossNetFactor'], modelVersion=MODEL['version'], description='Public unit heat-input curves and startup fuel; NI residual includes balancing.'),
                      sourceChecks=dict(hourlyDailyDifferenceGwh=differences),
                      sources={'gniDailyPhysical': gas_url, 'gniConsumption': consumption_url, 'gniAllocations': allocation_url, 'gniHourlyPhysical': hourly_url,
                               'snip': snip_url, 'northSouth': north_url, 'meter.xml': next(r['url'] for r in self.meter_sources if r['date'] == day.isoformat()),
                               'technical': tech_url, 'register': register_url, 'model': MODEL['source'], 'niDemand': self.demands['ni'][1], 'roiDemand': self.demands['roi'][1]},
                      sourceReports=dict(meters=self.meter_sources, dispatch=dispatch_urls, modelSha256=MODEL['sourceSha256']),
                      reuse=dict(gniPolicy='https://www.gasnetworks.ie/about/open-data', gniOperationalApiLicenceCoverageConfirmed=False,
                                 entsogTerms='https://transparency.entsog.eu/pdf/TRA0394_20161115_ENTSOG_TP_TC_of_Use_Rev_2_KNS_LG_KNS.pdf',
                                 entsogExtractionDate=captured[:10], electricityLicence='https://www.smartgriddashboard.com/ni/open-data-license/'), notes=[])
        validate(result)
        return result


def validate(data):
    require(data.get('schema') == 1, 'Unknown snapshot schema')
    day = date.fromisoformat(data['gasDay'])
    first, last = gas_window(day)
    require(stamp(data['fromUtc']) == first and stamp(data['toUtc']) == last, 'Gas-day boundary mismatch')
    require([stamp(r['time']) for r in data['hourly']] == intervals(first, last, 60), 'Incomplete hourly timeline')
    for region in ['ni', 'roi']:
        row = data['regions'][region]
        require(all(finite(row.get(k)) for k in ['totalGas', 'powerGas', 'otherGas', 'electricity', 'demand', 'demandShare', 'powerShare']), 'Invalid regional number')
        require(row['totalGas'] > 0 and row['demand'] > 0 and min(row['powerGas'], row['otherGas'], row['electricity']) >= 0, 'Invalid regional totals')
        require(abs(row['totalGas'] - row['powerGas'] - row['otherGas']) < 1e-6, 'Residual does not reconcile')
        require(abs(row['demandShare'] - row['electricity']/row['demand']*100) < 1e-6, 'Electricity demand share mismatch')
    basis = data['electricityBasis']
    require(basis['meteredHours'] + basis['dispatchEstimateHours'] == (last-first).total_seconds()/3600, 'Electricity coverage mismatch')
    require(all(finite(v) for v in data['flows'].values()), 'Invalid gas flow')
    return data
