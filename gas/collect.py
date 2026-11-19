"""Assemble aligned gas-day snapshots from reported flows and unit electricity."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import math
from pathlib import Path

from electricity.research.ni_gas.estimate import gas_window, fuel_rate, startup_fuel, OIL_UNITS
from gas.sources import GasDataPending, MeterDataPending, Sources, demand_url, iso, newest, parallel, stamp

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
    if not values or all(value is None for value in values):
        raise GasDataPending(day)
    require(all(finite(value) and value >= 0 for value in values), 'Invalid GNI daily value')
    if any(value != values[0] for value in values[1:]):
        raise GasDataPending(day, 'Conflicting daily values for ' + series[0]['name'])
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


def demand_total(values, first, last):
    times = intervals(first, last, 15)
    if not all(at in values and finite(values[at]) and values[at] > 0 for at in times):
        return None
    return sum(values[at] * .25 / 1000 for at in times)


class Collection:
    def __init__(self, target, cache, revision_days=7, offline=False, *, allow_older=False, gas_first=False):
        require(1 <= revision_days <= 14, 'Invalid revision window')
        self.target = target
        self.first_day = target - timedelta(days=revision_days - 1)
        require(self.first_day.isoformat() >= MODEL['validFrom'], 'Model not validated for this historical fleet')
        self.sources = Sources(cache, offline)
        # Enough observation to prove a cold start even on an empty new runner.
        cooling = max(sum(p['startupCoolingHours'][:len(p['startupGjLhv']) - 1]) for p in NI_UNITS.values())
        context = math.ceil(cooling / 24) + 2
        self.context_first = self.first_day - timedelta(days=context)
        self.gas_first = gas_first
        self._electricity_loaded = False
        self._electricity_error = None
        self.meters, self.meter_sources, self.indices = {}, [], {}
        self.demand_errors, self.demands = {}, {}
        if not gas_first:
            self._load_electricity(allow_older)

    def _load_electricity(self, allow_older=True):
        target = self.target
        names = ['PUB_DailyMeterDataD1', 'PUB_DailyTechnicalOfferData', 'PUB_DailyRegisteredUnits']
        # Prove that the primary day's meters exist before loading unrelated
        # indexes. A slow registry must not hide a known missing meter report.
        meter_index = self.sources.index(names[0], self.context_first)
        if newest(meter_index, target) is None and (not allow_older or not any(
                self.first_day.isoformat() <= row['Date'] <= target.isoformat() for row in meter_index)):
            latest = max((r['Date'] for r in meter_index if r['Date'] <= target.isoformat()), default=None)
            raise MeterDataPending(target, latest)
        indices = parallel([lambda name=name: self.sources.index(name, self.context_first) for name in names[1:]])
        self.indices = {names[0]: meter_index, **dict(zip(names[1:], indices))}
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
        self.demand_errors = {}
        self.demands = dict(zip(['ni', 'roi'], parallel([
            lambda region=region: self.optional_demand(region)
            for region in ['ni', 'roi']])))
        self.dispatch_items = None
        self._electricity_loaded = True

    def optional_demand(self, region):
        last = self.target + timedelta(days=1)
        try:
            return self.sources.demand(region, self.first_day, last)
        except Exception as error:
            self.demand_errors[region] = type(error).__name__
            print(f'Gas: {region.upper()} demand unavailable ({type(error).__name__}); gas collection continues.', flush=True)
            return {}, demand_url(region, self.first_day, last)

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

    def electricity(self, day, region):
        if self._electricity_error is not None:
            raise self._electricity_error
        if not self._electricity_loaded:
            try:
                self._load_electricity()
            except Exception as error:
                self._electricity_error = error
                raise
        if newest(self.indices['PUB_DailyMeterDataD1'], day) is None:
            latest = max((r['Date'] for r in self.indices['PUB_DailyMeterDataD1'] if r['Date'] <= day.isoformat()), default=None)
            raise MeterDataPending(day, latest)
        first, last = gas_window(day)
        expected = intervals(first, last, 30)
        tech, tech_url = self.dated_report('PUB_DailyTechnicalOfferData', day)
        register, register_url = self.dated_report('PUB_DailyRegisteredUnits', day)
        names = {r.get('UnitID'): r.get('UnitName') for r in register}
        candidates = {r.get('ResourceName') for r in tech if r.get('Jurisdiction') == 'ROI'
                      and r.get('FuelType') in ('GAS', 'MULTI_FUEL') and r.get('ResourceName') != 'GU_404270'}
        roi = {uid for uid in candidates if any((uid, at) in self.meters for at in expected)}
        if region == 'roi':
            require(len(roi) >= 20, 'Incomplete ROI gas/multi-fuel unit roster')
        unknown_ni = {r.get('ResourceName') for r in tech if r.get('Jurisdiction') == 'NI' and r.get('FuelType') in ('GAS', 'MULTI_FUEL') and r.get('ResourceName') not in NI_UNITS and r.get('ResourceName') not in OIL_UNITS and any((r.get('ResourceName'), at) in self.meters for at in expected)}
        if region == 'ni':
            require(not unknown_ni, 'Unmodelled NI gas/multi-fuel unit; model review required')
        units = set(NI_UNITS) if region == 'ni' else roi
        meters, cut, dispatch_urls = self.complete_meters(day, units)
        estimated = (last - cut).total_seconds() / 3600
        ni_units = []
        for uid, curve in (NI_UNITS.items() if region == 'ni' else []):
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
        roi_units = [dict(id=uid, name=names.get(uid, uid), electricityGwh=sum(max(0, meters[uid, at]) * .5 / 1000 for at in expected)) for uid in (sorted(roi) if region == 'roi' else [])]
        return dict(units=ni_units if region == 'ni' else roi_units,
                    basis=dict(meteredHours=(cut-first).total_seconds()/3600, dispatchEstimateHours=estimated,
                               estimateFromUtc=iso(cut)),
                    sources={'meter.xml': next(r['url'] for r in self.meter_sources if r['date'] == day.isoformat()),
                             'technical': tech_url, 'register': register_url}, dispatch=dispatch_urls)

    def assemble(self, day):
        # Preserve the strict research entry point; the cloud collector explicitly
        # opts into publishing reported gas independently of electricity inputs.
        if not getattr(self, 'gas_first', False) and newest(self.indices['PUB_DailyMeterDataD1'], day) is None:
            raise MeterDataPending(day)
        first, last = gas_window(day)
        fetched = parallel([
            lambda: self.sources.gni('physicalflows', day), lambda: self.sources.gni('gasconsumption', day),
            lambda: self.sources.gni('commercialentrypoint', day), lambda: self.optional_hourly(day),
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
        electricity, pending = {}, []
        for region in ['ni', 'roi']:
            try:
                available = self.electricity(day, region)
                if region == 'ni':
                    model_gas = sum(row['gasGwh'] for row in available['units'])
                    require(finite(model_gas) and 0 <= model_gas <= flows['niAllocated'], 'NI model gas is outside the reported allocation; model review required')
                electricity[region] = available
            except Exception as error:
                if not self.gas_first:
                    raise
                pending.append(dict(source='SEMO meter data' if isinstance(error, MeterDataPending) else 'Electricity sources',
                                    gasDay=day.isoformat(), region=region, reason=str(error)))
        regions = {}
        for region, total in [('ni', flows['niAllocated']), ('roi', roi_total)]:
            available = electricity.get(region)
            members = available['units'] if available else []
            power = sum(r['gasGwh'] for r in members) if region == 'ni' and available else roi_power if region == 'roi' else None
            output = sum(r['electricityGwh'] for r in members) if available else None
            values, _ = self.demands.get(region, ({}, ''))
            demand = demand_total(values, first, last)
            require(total > 0 and (power is None or 0 <= power <= total), 'Invalid regional gas use/residual')
            regions[region] = dict(totalGas=total, powerGas=power, otherGas=total-power if power is not None else None,
                                   electricity=output, demand=demand,
                                   demandShare=output/demand*100 if output is not None and demand is not None else None,
                                   powerShare=power/total*100 if power is not None else None)
        try:
            hours = []
            for at in intervals(first, last, 60):
                row = dict(time=iso(at))
                for location, key in [('Moffat', 'scotland'), ('Bellanaboy', 'corrib')]:
                    series = [r for r in hourly if r.get('location') == location and r.get('group') == 'Hourly Delivered Quantity of Gas']
                    require(len(series) == 1, 'Missing hourly physical-flow series')
                    values = [v for epoch, v in series[0]['data'] if datetime.fromtimestamp(epoch/1000, UTC) == at]
                    require(values and all(finite(value) and value >= 0 and value == values[0] for value in values), 'Missing or conflicting hourly physical flow at '+iso(at))
                    row[key] = values[0] / 1e6
                hours.append(row)
            differences = {key: sum(r[key] for r in hours) - flows[key] for key in ['scotland', 'corrib']}
            require(all(abs(value) <= max(.1, flows[key] * .005) for key, value in differences.items()), 'Hourly/daily source totals disagree beyond tolerance')
        except Exception as error:
            hours, differences = [], {}
            pending.append(dict(source='GNI hourly flows', gasDay=day.isoformat(), reason=str(error)))
        captured = iso(datetime.now(UTC))
        complete = len(electricity) == 2
        bases = {region: electricity[region]['basis'] if region in electricity else None for region in ['ni', 'roi']}
        metered = min(row['meteredHours'] for row in bases.values()) if complete else None
        estimated = max(row['dispatchEstimateHours'] for row in bases.values()) if complete else None
        source_urls = {'gniDailyPhysical': gas_url, 'gniConsumption': consumption_url, 'gniAllocations': allocation_url,
                       'gniHourlyPhysical': hourly_url, 'snip': snip_url, 'northSouth': north_url, 'model': MODEL['source']}
        for row in electricity.values():
            source_urls.update(row['sources'])
        for region in ['ni', 'roi']:
            source_urls[region + 'Demand'] = self.demands.get(region, ({}, demand_url(region, self.first_day, self.target+timedelta(days=1))))[1]
        result = dict(schema=3, gasDay=day.isoformat(), fromUtc=iso(first), toUtc=iso(last), snapshotAsOf=captured[:10], capturedAt=captured,
                      flows=flows, regions=regions, hourly=hours,
                      units={region: electricity[region]['units'] if region in electricity else [] for region in ['ni', 'roi']},
                      electricityBasis=dict(meteredHours=metered, dispatchEstimateHours=estimated,
                          estimateFromUtc=min(row['estimateFromUtc'] for row in bases.values()) if complete else None,
                          regional=bases, description='Regional meter coverage is reported separately. Missing electricity inputs do not delay reported gas. Dispatch estimates are limited to six hours per unit; published meters are retained.'),
                      niGasBasis=dict(grossNetFactor=MODEL['grossNetFactor'], modelVersion=MODEL['version'], unitCount=len(NI_UNITS), description='Public unit heat-input curves and startup fuel; NI residual includes balancing.'),
                      sourceChecks=dict(hourlyDailyDifferenceGwh=differences, demandErrors=self.demand_errors, pending=pending),
                      sources=source_urls,
                      sourceReports=dict(meters=self.meter_sources,
                          dispatch=sorted({url for row in electricity.values() for url in row['dispatch']}), modelSha256=MODEL['sourceSha256']),
                      reuse=dict(gniPolicy='https://www.gasnetworks.ie/about/open-data', gniOperationalApiLicenceCoverageConfirmed=False,
                                 entsogTerms='https://transparency.entsog.eu/pdf/TRA0394_20161115_ENTSOG_TP_TC_of_Use_Rev_2_KNS_LG_KNS.pdf',
                                 entsogExtractionDate=captured[:10], electricityLicence='https://www.smartgriddashboard.com/ni/open-data-license/'), notes=[])
        validate(result)
        return result

    def optional_hourly(self, day):
        try:
            return self.sources.gni('physicalflows', day, 'hourly')
        except Exception:
            return [], 'https://www.gasnetworks.ie/api/v1/physicalflows?date='+day.isoformat()+'&frequency=hourly'

    def complete_meters(self, day, units):
        first, last = gas_window(day)
        expected = intervals(first, last, 30)
        meters = {key: value[0] for key, value in self.meters.items() if key[0] in units}
        cuts = {}
        for uid in sorted(units):
            cut = next((at for at in expected if (uid, at) not in meters), last)
            if cut == last:
                continue
            if cut == first:
                raise MeterDataPending(day, reason='No metered prefix for unit ' + uid)
            if any((uid, at) in meters for at in expected if at >= cut):
                raise MeterDataPending(day, reason='Non-contiguous meter coverage for unit ' + uid)
            if (last - cut).total_seconds() > 6 * 3600:
                raise MeterDataPending(day, reason='More than six hours of meters missing for unit ' + uid)
            cuts[uid] = cut
        cut = min(cuts.values(), default=last)
        dispatch_urls = []
        if cuts:
            events, dispatch_urls = self.dispatch(cut - timedelta(minutes=30), last, set(cuts))
            for uid, unit_cut in cuts.items():
                seed = unit_cut - timedelta(minutes=30)
                def target(at):
                    eligible = [e for e in events[uid] if seed <= e[0] <= at and e[1] <= at]
                    if not eligible:
                        return max(0, meters[uid, seed])
                    value = eligible[-1][2]
                    require(value is not None and finite(value), 'Unknown dispatch state')
                    return max(0, value)
                for at in intervals(unit_cut, last, 30):
                    meters[uid, at] = sum(target(at + timedelta(minutes=m, seconds=30)) for m in range(30)) / 30
        return meters, cut, dispatch_urls


def validate(data):
    require(data.get('schema') in (1, 2, 3), 'Unknown snapshot schema')
    day = date.fromisoformat(data['gasDay'])
    first, last = gas_window(day)
    require(stamp(data['fromUtc']) == first and stamp(data['toUtc']) == last, 'Gas-day boundary mismatch')
    if data['schema'] == 3 and data['hourly'] == []:
        require(any(row.get('source') == 'GNI hourly flows' for row in data['sourceChecks']['pending']), 'Missing hourly data needs a source reason')
    else:
        require([stamp(r['time']) for r in data['hourly']] == intervals(first, last, 60), 'Incomplete hourly timeline')
    for region in ['ni', 'roi']:
        row = data['regions'][region]
        require(finite(row.get('totalGas')) and row['totalGas'] > 0, 'Invalid regional gas total')
        optional = data['schema'] == 3
        if optional and row.get('powerGas') is None:
            require(region == 'ni' and all(key in row and row[key] is None for key in ['powerGas','otherGas','powerShare']), 'Unavailable power gas must have unavailable derived values')
        else:
            require(all(finite(row.get(k)) for k in ['powerGas','otherGas','powerShare']), 'Invalid regional number')
            require(min(row['powerGas'],row['otherGas']) >= 0, 'Invalid regional totals')
            require(abs(row['totalGas']-row['powerGas']-row['otherGas']) < 1e-6, 'Residual does not reconcile')
            require(abs(row['powerShare']-row['powerGas']/row['totalGas']*100) < 1e-6, 'Gas use share mismatch')
        if not (optional and 'electricity' in row and row['electricity'] is None):
            require(finite(row.get('electricity')) and row['electricity'] >= 0, 'Invalid electricity')
        if not (data['schema'] >= 2 and 'demand' in row and row['demand'] is None):
            require(finite(row.get('demand')) and row['demand'] > 0, 'Invalid demand')
        if row['demand'] is None or row['electricity'] is None:
            require('demandShare' in row and row['demandShare'] is None, 'Unavailable inputs must have an unavailable share')
        else:
            require(finite(row.get('demandShare')) and abs(row['demandShare']-row['electricity']/row['demand']*100) < 1e-6, 'Electricity demand share mismatch')
        if optional:
            basis = data['electricityBasis']['regional'][region]
            if row['electricity'] is None:
                require(basis is None and data['units'][region] == [], 'Unavailable electricity must have no meter coverage or units')
                require(any(item.get('region') == region for item in data['sourceChecks']['pending']), 'Unavailable electricity needs a source reason')
                if region == 'ni':require(row['powerGas'] is None, 'NI model requires electricity')
            else:
                require(basis is not None and data['units'][region], 'Available electricity needs meter coverage and units')
                require(finite(basis['dispatchEstimateHours']) and 0 <= basis['dispatchEstimateHours'] <= 6, 'Invalid estimate coverage')
                require(basis['meteredHours'] > 0 and basis['meteredHours']+basis['dispatchEstimateHours'] == (last-first).total_seconds()/3600, 'Electricity coverage mismatch')
    basis = data['electricityBasis']
    if data['schema'] < 3 or all(row['electricity'] is not None for row in data['regions'].values()):
        require(basis['meteredHours']+basis['dispatchEstimateHours'] == (last-first).total_seconds()/3600, 'Electricity coverage mismatch')
    else:
        require(all(basis.get(key) is None for key in ['meteredHours','dispatchEstimateHours','estimateFromUtc']), 'Partial coverage cannot claim a complete meter basis')
    require(all(finite(v) for v in data['flows'].values()), 'Invalid gas flow')
    return data
