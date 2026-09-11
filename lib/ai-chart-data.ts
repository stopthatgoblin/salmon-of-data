export type Observation = { date: string; value: number };
export type ChartMetric = {
  data: Observation[];
  anchor: Observation;
  endpoints: number[];
  period: string;
};
export type ChartRecord = {
  time: number;
  observed?: number | null;
  s0?: number;
  s1?: number;
  s2?: number;
};
export function scenarioAt(metric: ChartMetric, at: number, horizon: string) {
  const start = Date.parse(metric.anchor.date),
    end = Date.parse(horizon);
  if (at < start || at > end) return {};
  const fraction = (at - start) / (end - start);
  return Object.fromEntries(
    metric.endpoints.map((v, i) => [
      's' + i,
      metric.anchor.value + (v - metric.anchor.value) * fraction,
    ]),
  );
}
// No artificial timestamps are inserted between observations, except an explicit
// null sentinel for a genuine source gap. This keeps future actuals continuous.
// Every timestamp in the scenario window receives all three frozen values.
export function buildChartData(
  metric: ChartMetric,
  horizon: string,
): ChartRecord[] {
  const rows = new Map<number, ChartRecord>();
  metric.data.forEach((p, i) => {
    const t = Date.parse(p.date),
      previous = metric.data[i - 1];
    if (previous) {
      const pt = Date.parse(previous.date);
      const limit =
        metric.period === 'quarter' ? 100 : metric.period === 'day' ? 2 : 45;
      if (t - pt > limit * 86400000) {
        const gap = (pt + t) / 2;
        rows.set(gap, { time: gap, observed: null });
      }
    }
    rows.set(t, { time: t, observed: p.value });
  });
  const anchor = Date.parse(metric.anchor.date),
    end = Date.parse(horizon);
  for (const time of [anchor, end])
    if (!rows.has(time)) rows.set(time, { time });
  return [...rows.values()]
    .sort((a, b) => a.time - b.time)
    .map((row) => ({ ...row, ...scenarioAt(metric, row.time, horizon) }));
}
