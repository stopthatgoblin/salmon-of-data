import map from './map-data.js';
import * as model from './history-model.js';
import { mountOverview } from './overview.js';
import { mountTrends } from './trends.js';
import { mountLive } from './live.js';
import { mountReplay } from '../electricity/replay.js';

export function mountElectricity(root, snapshot, history, signal, versions) {
  const events = new EventTarget();
  mountTrends(root, history, model, events, signal);
  mountOverview(root, snapshot, map, events, signal);
  mountLive(root, snapshot, history, mountReplay(root,'ni',snapshot,events,signal), signal, versions);
}
