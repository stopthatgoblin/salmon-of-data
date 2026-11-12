"""Offline research estimate of NI power-sector gas input and an allocation residual.

Uses archived SEMO metered half-hours and the public SEM 2024-2032 PLEXOS XML.
Not a production collector or a gas-consumption meter. See README.md.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

UTC = timezone.utc
LOCAL = ZoneInfo('Europe/Dublin')
GAS_UNITS = {
    'GU_503720': 'B31', 'GU_503730': 'B32', 'GU_503740': 'B10',
    'GU_500040': 'CPS CCGT', 'GU_504110': 'KGT6', 'GU_504120': 'KGT7',
}
OIL_UNITS = {
    'GU_500283': 'BGT1', 'GU_500284': 'BGT2', 'GU_500041': 'CGT8',
    'GU_500820': 'KGT1', 'GU_500821': 'KGT2',
    'GU_500824': 'KGT3', 'GU_500825': 'KGT4',
}


def stamp(value):
    at = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)


def gas_window(day):
    # GNI's published gas-day convention is 05:00 local time.
    first = datetime.combine(day, time(5), LOCAL).astimezone(UTC)
    last = datetime.combine(day + timedelta(days=1), time(5), LOCAL).astimezone(UTC)
    return first, last


def model_parameters(path):
    tables = defaultdict(list)
    for element in ET.parse(path).getroot():
        kind = element.tag.split('}')[-1]
        if kind in {'t_object', 't_property', 't_membership', 't_data', 't_band', 't_tag'}:
            tables[kind].append({child.tag.split('}')[-1]: child.text for child in element})
    objects = {r['object_id']: r for r in tables['t_object']}
    props = {r['property_id']: r for r in tables['t_property']}
    memberships = {r['membership_id']: r for r in tables['t_membership']}
    bands = {r['data_id']: int(r['band_id']) for r in tables['t_band']}
    tags = defaultdict(list)
    for row in tables['t_tag']:
        tags[row['data_id']].append(objects[row['object_id']]['name'])
    wanted = set(GAS_UNITS.values())
    values = defaultdict(dict)
    for row in tables['t_data']:
        member = memberships[row['membership_id']]
        parent = objects[member['parent_object_id']]['name']
        child = objects[member['child_object_id']]['name']
        prop = props[row['property_id']]['name']
        band = bands.get(row['data_id'], 1)
        row_tags = tags[row['data_id']]
        if child in wanted and member['collection_id'] == '1':
            if prop in {'Heat Rate Base', 'Heat Rate Incr', 'Load Point', 'Min Stable Level'} and not row_tags:
                values[child][prop, band] = float(row['value'])
            elif prop == 'Start Cost Time' and row_tags == ['Three-State Start']:
                values[child][prop, band] = float(row['value'])
        elif parent in wanted and prop == 'Offtake at Start' and row_tags == ['Three-State Start']:
            values[parent][prop, band] = float(row['value'])
    result = {}
    for name in sorted(wanted):
        rows = values[name]
        curves = sorted((band, value) for (prop, band), value in rows.items() if prop == 'Load Point')
        if not curves:
            raise ValueError('No curve for ' + name)
        result[name] = {
            'baseGjPerHourLhv': rows['Heat Rate Base', 1],
            'segments': [[upper, rows['Heat Rate Incr', band]] for band, upper in curves],
            'minimumStableMw': rows['Min Stable Level', 1],
            'startupGjLhv': [value for (prop, band), value in sorted(rows.items()) if prop == 'Offtake at Start'],
            'startupCoolingHours': [value for (prop, band), value in sorted(rows.items()) if prop == 'Start Cost Time'],
        }
        if not result[name]['startupGjLhv']:
            raise ValueError('No startup fuel for ' + name)
    return result


def fuel_rate(power_mw, params):
    """Integrate marginal heat rates to obtain GJ/h LHV at a positive load.

    Extend the first segment below minimum stable output and the last above the
    final load point; the caller records those out-of-range observations.
    """
    if not math.isfinite(power_mw):
        raise ValueError('Non-finite electricity output')
    if power_mw <= 0:
        return 0.0
    fuel = params['baseGjPerHourLhv']
    previous = 0.0
    for upper, slope in params['segments']:
        fuel += max(0.0, min(power_mw, upper) - previous) * slope
        previous = upper
        if power_mw <= upper:
            return fuel
    return fuel + (power_mw - previous) * params['segments'][-1][1]


def read_meters(cache, first, last):
    accepted = {}
    for path in sorted(cache.glob('PUB_DailyMeterDataD1*.gz')):
        data = json.loads(gzip.decompress(path.read_bytes()))
        if data['kind'] != 'PUB_DailyMeterDataD1':
            continue
        for unit, at, mw in data['rows']:
            at = stamp(at)
            if unit not in GAS_UNITS | OIL_UNITS or not first - timedelta(days=8) <= at < last:
                continue
            if not isinstance(mw, (int, float)) or not math.isfinite(mw):
                raise ValueError('Invalid meter value')
            key = unit, at
            candidate = dict(mw=mw, published=data['published'], resource=data['resource'])
            prior = accepted.get(key)
            if prior and prior['published'] == candidate['published'] and prior['mw'] != mw:
                raise ValueError('Conflicting meter edition')
            if prior is None or candidate['published'] > prior['published']:
                accepted[key] = candidate
    return accepted


def startup_fuel(curve, offline_hours, exact_history=True):
    """Return startup GJ, allowing a proven cold start without exact downtime."""
    fuel = curve['startupGjLhv']
    boundaries = curve['startupCoolingHours']
    if len(fuel) == 1:
        return fuel[0]
    # Start Cost Time entries are incremental cooling durations.
    cold_boundary = sum(boundaries[:len(fuel) - 1])
    if not exact_history:
        if offline_hours > cold_boundary:
            return fuel[-1]
        raise ValueError('Insufficient offline history to classify startup')
    band = 0
    boundary = boundaries[0]
    while band < len(fuel) - 1 and offline_hours > boundary:
        band += 1
        boundary += boundaries[band] if band < len(boundaries) else 0
    return fuel[band]


def estimate(day, cache, model, allocations, hhv_lhv=1.11):
    if not math.isfinite(hhv_lhv) or hhv_lhv <= 1:
        raise ValueError('Expected a positive gross/net gas energy ratio above one')
    first, last = gas_window(day)
    params = model_parameters(model)
    meters = read_meters(cache, first, last)
    expected = [first + timedelta(minutes=30 * n) for n in range(int((last - first).total_seconds() / 1800))]
    missing = [(unit, at.isoformat()) for unit in GAS_UNITS | OIL_UNITS for at in expected if (unit, at) not in meters]
    if missing:
        raise ValueError(f'Incomplete gas day: {len(missing)} unit half-hours missing; first {missing[0]}')
    results = []
    for unit, name in GAS_UNITS.items():
        curve = params[name]
        running_gj = sum(fuel_rate(meters[unit, at]['mw'], curve) * 0.5 for at in expected)
        starts, startup_gj = [], 0.0
        for at in expected:
            # This threshold is only for detecting starts in half-hour meter data.
            previous_at = at - timedelta(minutes=30)
            current = meters[unit, at]['mw']
            previous = meters.get((unit, previous_at))
            if previous is None:
                raise ValueError('Missing preceding half-hour for ' + unit)
            if current <= 1 or previous['mw'] > 1:
                continue
            cursor = previous_at
            while (unit, cursor) in meters and meters[unit, cursor]['mw'] <= 1:
                cursor -= timedelta(minutes=30)
            offline = (previous_at - cursor).total_seconds() / 3600
            exact = (unit, cursor) in meters
            start_gj = startup_fuel(curve, offline, exact)
            startup_gj += start_gj
            starts.append(dict(firstPositiveHalfHour=at.isoformat(), offlineHours=offline,
                               offlineHoursIsLowerBound=not exact, startupGjLhv=start_gj))
        results.append(dict(
            unitId=unit, modelUnit=name, electricalMwh=sum(max(0, meters[unit, at]['mw']) * 0.5 for at in expected),
            runningGjLhv=running_gj, startupGjLhv=startup_gj,
            gasGwhHhv=(running_gj + startup_gj) * hhv_lhv / 3600,
            belowModelMinimumHalfHours=sum(0 < meters[unit, at]['mw'] < curve['minimumStableMw'] for at in expected),
            aboveModelCurveHalfHours=sum(meters[unit, at]['mw'] > curve['segments'][-1][0] for at in expected),
            starts=starts,
        ))
    series = next(s for s in json.loads(allocations.read_text()) if s['name'] == 'Northern Ireland')
    # GNI's chart encodes daily gas-day date labels at 05:00 UTC even in summer.
    # Match its date label, not that chart timestamp as an interval boundary.
    gas = [(datetime.fromtimestamp(epoch / 1000, UTC), value) for epoch, value in series['data']
           if datetime.fromtimestamp(epoch / 1000, UTC).date() == day]
    if len(gas) != 1 or not isinstance(gas[0][1], (int, float)) or not math.isfinite(gas[0][1]):
        raise ValueError('Missing unique NI allocation for this gas day')
    total = gas[0][1] / 1e6
    power = sum(row['gasGwhHhv'] for row in results)
    residual = total - power  # Preserve a negative residual; never hide it by clipping.
    return dict(
        gasDay=str(day), fromUtc=first.isoformat(), toUtc=last.isoformat(), expectedHalfHours=len(expected),
        basis='Research estimate: unit-specific running heat-input curves plus inferred startup fuel; assumed normal gas firing.',
        grossToNetGasEnergyRatio=hhv_lhv, modelFile=model.name,
        allocationDateLabelTimestamp=gas[0][0].isoformat(),
        allocationDateLabelTimestampMatchesIntervalStart=gas[0][0] == first,
        modelSha256=hashlib.sha256(model.read_bytes()).hexdigest(), modelParameters=params,
        electricitySources=sorted({v['resource'] for (u, at), v in meters.items() if first <= at < last}),
        offlineHistorySources=sorted({v['resource'] for (u, at), v in meters.items() if at < first}),
        units=results,
        excludedDistillateElectricalMwh={name: sum(max(0, meters[unit, at]['mw']) * 0.5 for at in expected) for unit, name in OIL_UNITS.items()},
        niReportedEntryAllocationGwh=total, estimatedPowerGasGwh=power,
        nonPowerAndBalancingResidualGwh=residual,
        sensitivityPowerPlusMinus10Percent={
            'description': 'Illustrative sensitivity, not an empirical confidence interval; excludes uncertainty in the allocation boundary.',
            'powerGwh': [power * .9, power * 1.1],
            'residualGwh': [total - power * 1.1, total - power * .9],
        },
        limitations=[
            'NI entry allocation is not independently established as total NI metered consumption; the residual retains stock, own-use and other boundary differences.',
            'Multi-fuel units assumed to burn gas; actual fuel switching is not observed by the electricity meter feed.',
            'Starts inferred from half-hour output; startup fuel is assigned to the first positive half-hour and may cross a gas-day boundary in reality.',
            'The model may differ from current degraded, derated or upgraded unit performance; below-minimum operation uses an extrapolation.',
            'The approximate 1.11 gross/net conversion must be refined before treating the estimate as calibrated.',
        ],
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gas-day', type=date.fromisoformat, required=True)
    parser.add_argument('--meter-cache', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--allocations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = estimate(args.gas_day, args.meter_cache, args.model, args.allocations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({key: result[key] for key in ['gasDay', 'niReportedEntryAllocationGwh', 'estimatedPowerGasGwh', 'nonPowerAndBalancingResidualGwh']}, indent=2))


if __name__ == '__main__':
    main()
