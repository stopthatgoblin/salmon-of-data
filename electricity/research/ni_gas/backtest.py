"""Retrospective September 2026 validation against GMO NI's vector PDF charts.

Run with a Python environment containing pdfplumber. No network requests.
The extraction is intentionally specific to this verified report layout.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import statistics

from electricity.research.ni_gas.estimate import estimate


def reference_series(path):
    import pdfplumber

    configs = [
        ('total', (0.267, 0.447, 0.769), 80, 166, 60, 7),
        ('power', (0.267, 0.447, 0.769), 246, 304, 60, 4),
        ('distribution', (0.0824, 0.376, 0.51), 388, 446, 20, 5),
    ]
    result = {}
    with pdfplumber.open(path) as pdf:
        if len(pdf.pages) != 1:
            raise ValueError('Unexpected reference report page count')
        page = pdf.pages[0]
        if (page.width, page.height) != (960, 540) or 'NI Network September 26 Gas Demand' not in page.extract_text():
            raise ValueError('Reference is not the inspected September 2026 report')
        for kind, color, top, bottom, maximum_gwh, tick_count in configs:
            curves = [c for c in page.curves if c.get('stroking_color') == color
                      and len(c['pts']) == 30 and top <= c['top'] < bottom]
            if len(curves) != 1:
                raise ValueError('Cannot uniquely identify September series: ' + kind)
            grid = sorted(set(line['top'] for line in page.lines
                              if line.get('stroking_color') == .851 and top <= line['top'] < bottom
                              and line['x1'] - line['x0'] > 200))
            if len(grid) != tick_count:
                raise ValueError('Unexpected axis ticks: ' + kind)
            zero, high = max(grid), min(grid)
            points = curves[0]['pts']
            gaps = [b[0] - a[0] for a, b in zip(points, points[1:])]
            if min(gaps) <= 0 or max(gaps) / min(gaps) > 1.03:
                raise ValueError('Unexpected daily point spacing: ' + kind)
            result[kind] = {
                'zeroTop': zero, 'maximumTop': high, 'maximumGwh': maximum_gwh,
                'points': [dict(date=f'2026-09-{i + 1:02}', gwh=(zero - y) * maximum_gwh / (zero - high),
                                x=x, top=y) for i, (x, y) in enumerate(points)],
            }
    return result


def metrics(rows, actual_key, estimate_key):
    actual = [r[actual_key] for r in rows]
    predicted = [r[estimate_key] for r in rows]
    differences = [p - a for a, p in zip(actual, predicted)]
    return dict(
        count=len(rows), reportedSumGwh=sum(actual), estimatedSumGwh=sum(predicted),
        aggregateBiasPercent=100 * sum(differences) / sum(actual),
        meanAbsoluteErrorGwh=statistics.mean(abs(d) for d in differences),
        meanAbsolutePercentageError=statistics.mean(abs(d) / a for d, a in zip(differences, actual)) * 100,
        maximumAbsoluteErrorGwh=max(abs(d) for d in differences),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--allocations', type=Path, nargs='+', required=True)
    parser.add_argument('--meter-cache', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--first', type=date.fromisoformat, default=date(2026, 9, 9))
    parser.add_argument('--last', type=date.fromisoformat, default=date(2026, 9, 30))
    args = parser.parse_args()
    if not date(2026, 9, 1) <= args.first <= args.last <= date(2026, 9, 30):
        raise ValueError('Dates must be within the reference month')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reference = reference_series(args.reference)
    (args.output_dir / 'published-september-extracted.json').write_text(json.dumps(reference, indent=2) + '\n')
    published = {kind: {p['date']: p['gwh'] for p in series['points']} for kind, series in reference.items()}
    merged = {}
    for path in args.allocations:
        series = next(s for s in json.loads(path.read_text()) if s['name'] == 'Northern Ireland')
        for epoch, value in series['data']:
            if epoch in merged and merged[epoch] != value:
                raise ValueError('Conflicting NI allocation editions')
            merged[epoch] = value
    allocation_path = args.output_dir / 'merged-ni-allocations.json'
    allocation_path.write_text(json.dumps([dict(name='Northern Ireland', data=sorted(merged.items()))]) + '\n')
    rows, excluded = [], []
    day = args.first
    while day <= args.last:
        try:
            result = estimate(day, args.meter_cache, args.model, allocation_path)
        except ValueError as exc:
            excluded.append(dict(date=str(day), reason=str(exc)))
            print(day, 'excluded:', exc, flush=True)
            day += timedelta(days=1)
            continue
        (args.output_dir / f'estimate-{day}.json').write_text(json.dumps(result, indent=2) + '\n')
        key = str(day)
        rows.append(dict(
            date=key, reportedPowerGwh=published['power'][key], estimatedPowerGwh=result['estimatedPowerGasGwh'],
            reportedTotalGwh=published['total'][key], reportedDistributionGwh=published['distribution'][key],
            reportedNonPowerGwh=published['total'][key] - published['power'][key],
            entryAllocationGwh=result['niReportedEntryAllocationGwh'],
            estimatedNonPowerResidualGwh=result['nonPowerAndBalancingResidualGwh'],
            belowModelMinimumHalfHours=sum(u['belowModelMinimumHalfHours'] for u in result['units']),
            startupCount=sum(len(u['starts']) for u in result['units']),
        ))
        print(day, 'complete', flush=True)
        day += timedelta(days=1)
    if not rows:
        raise ValueError('No complete comparable days')
    output = dict(
        referenceUrl='https://www.gmo-ni.com/site/wp-content/uploads/2026/10/Demand-Slide_Sep-26.pdf',
        referenceSha256=hashlib.sha256(args.reference.read_bytes()).hexdigest(),
        modelSha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
        interpretation='Retrospective comparison against operator-published daily chart values; no heat-rate calibration or parameter fitting.',
        referencePrecision='Approximate chart-derived GWh; coordinate rounding is material relative to small power errors.',
        requestedFirst=str(args.first), requestedLast=str(args.last), acceptedFirst=rows[0]['date'], acceptedLast=rows[-1]['date'],
        days=len(rows), excluded=excluded,
        power=metrics(rows, 'reportedPowerGwh', 'estimatedPowerGwh'),
        nonPowerResidual=metrics(rows, 'reportedNonPowerGwh', 'estimatedNonPowerResidualGwh'),
        entryAllocation=metrics(rows, 'reportedTotalGwh', 'entryAllocationGwh'),
        rows=rows,
    )
    (args.output_dir / 'comparison.json').write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    print(json.dumps({k: output[k] for k in ['days', 'excluded', 'power', 'nonPowerResidual', 'entryAllocation']}, indent=2))


if __name__ == '__main__':
    main()
