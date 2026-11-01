// Original aggregation semantics from the standalone dashboard.
  const DAY = 86400000;
  const utc = value => new Date(`${value}T00:00:00Z`);
  const iso = value => value.toISOString().slice(0, 10);
  const countDays = (start, end) => Math.max(0, Math.round((utc(end) - utc(start)) / DAY) + 1);

  function aggregate(history, resolution, startYear, endYear) {
    if (!['daily', 'monthly', 'annual'].includes(resolution)) throw new Error('Unknown grouping');
    if (!Number.isInteger(startYear) || !Number.isInteger(endYear) || startYear > endYear) throw new Error('Invalid year range');
    const first = `${startYear}-01-01`;
    const last = `${endYear}-12-31`;
    const groups = new Map();
    history.days.forEach(row => {
      if (row.date < first || row.date > last) return;
      const key = resolution === 'annual' ? row.date.slice(0, 4) : resolution === 'monthly' ? row.date.slice(0, 7) : row.date;
      if (!groups.has(key)) {
        const start = resolution === 'annual' ? `${key}-01-01` : resolution === 'monthly' ? `${key}-01` : key;
        let end = start;
        if (resolution === 'annual') end = `${key}-12-31`;
        if (resolution === 'monthly') {
          const date = utc(start);
          date.setUTCMonth(date.getUTCMonth() + 1, 0);
          end = iso(date);
        }
        const coveredStart = [start, history.first, first].sort().at(-1);
        const coveredEnd = [end, history.last, last].sort()[0];
        groups.set(key, {
          key, start, end, coveredStart, coveredEnd,
          expectedDays: countDays(coveredStart, coveredEnd),
          partialPeriod: start < history.first || end > history.last,
          sums: history.series.map(() => 0), days: history.series.map(() => 0), samples: history.series.map(() => 0)
        });
      }
      const group = groups.get(key);
      history.series.forEach((series, i) => {
        group.samples[i] += row.n[i] || 0;
        const value = row.v[i];
        if (typeof value !== 'number' || !Number.isFinite(value)) return;
        group.sums[i] += value;
        group.days[i] += 1;
      });
    });
    return [...groups.values()].sort((a, b) => a.start.localeCompare(b.start)).map(group => {
      const values = group.sums.map((sum, i) => group.days[i] ? sum / group.days[i] : null);
      return { ...group, values, chartValues: values.map((value, i) =>
        resolution !== 'daily' && group.days[i] / group.expectedDays < .95 ? null : value) };
    });
  }

  function csv(history, groups, resolution) {
    const header = ['period_start', 'period_end', 'grouping', 'partial_period', 'expected_elapsed_days'];
    history.series.forEach(series => header.push(`${series.key}_mean_mw`, `${series.key}_complete_days`, `${series.key}_observations`, `${series.key}_chart_eligible`));
    const rows = groups.map(group => {
      const row = [group.start, group.end, resolution, group.partialPeriod, group.expectedDays];
      history.series.forEach((series, i) => row.push(group.values[i] === null ? '' : group.values[i].toFixed(4), group.days[i], group.samples[i], group.chartValues[i] !== null));
      return row.join(',');
    });
    return '\uFEFF' + [header.join(','), ...rows].join('\r\n') + '\r\n';
  }


export { aggregate, csv, countDays };
