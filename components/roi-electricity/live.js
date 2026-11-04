import { createLiveClient } from '../ni-electricity/live.js';
import { reconcileSnapshot } from './balance.js';

export function validateUpdate(name, next, current) {
  if (name === 'history') {
    if (next.dataBasis === 'unavailable' && next.days?.length === 0) return;
    const keys = ['wind','solar','otherROI','generation','demand','eastWest','greenlink','northSouth'];
    if (next.dataBasis !== 'public-source-history' || !next.days?.length || !Number.isFinite(Date.parse(next.generatedAt)) || !keys.every(key => next.series?.some(series => series.key === key))) throw new Error('Unverified ROI history');
    if (current?.days?.length && (next.first > current.first || next.last < current.last || Date.parse(next.generatedAt) < Date.parse(current.generatedAt))) throw new Error('ROI history moved backwards');
    return;
  }
  if (next.dataBasis !== 'public-source-capture' || !Number.isFinite(Date.parse(next.time)) || !Number.isFinite(Date.parse(next.retrievedAt))) throw new Error('Invalid ROI snapshot');
  if (current && Date.parse(next.time) < Date.parse(current.time)) throw new Error('ROI snapshot moved backwards');
  const balanced = reconcileSnapshot(next);
  for (const key of ['other', 'otherGeneration', 'reconciliation']) {
    if (!Number.isFinite(next[key]) || Math.abs(next[key] - balanced[key]) > .001) throw new Error('Invalid ROI balance');
  }
  if (next.stations?.length !== 11 || new Set(next.stations.map(s => s.id)).size !== 11) throw new Error('Incomplete ROI stations');
  if (current && next.stations.map(s => s.id).join() !== current.stations.map(s => s.id).join()) throw new Error('ROI station set changed');
}
const client = createLiveClient({
  api: '/api/electricity/roi/', fallback: '/data/roi-electricity/', validateUpdate,
  scheduleDescription: status => status.mode === 'local'
    ? 'Local overview collection runs every 15 minutes while the local server is running. History is collected daily after 07:00 Europe/London, with hourly retries if needed.'
    : status.mode === 'preview'
      ? 'Preview collection runs on demand; the temporary 15-minute watch updates the overview. History updates on a manual history or both run.'
      : 'Overview collection is scheduled every 15 minutes; history daily at 07:00 Europe/London. Upstream publication and runner queues can delay readings.',
});

export const mountLive = client.mountLive;
export async function readInitialDataset(name, signal) {
  const initial = await client.readInitialDataset(name, signal);
  if (name !== 'history' || initial.data.dataBasis !== 'unavailable') return initial;
  // A real bundled history remains usable before the remote dataset is seeded.
  try {
    const response = await fetch('/data/roi-electricity/history.json', {signal});
    if (!response.ok) return initial;
    const data = await response.json();
    validateUpdate('history', data, data);
    return {data, version:null};
  } catch (error) {
    if (signal.aborted) throw error;
    return initial;
  }
}
