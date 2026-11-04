import map from './map-data.js';
import * as model from './history-model.js';
import { mountOverview } from './overview.js';
import { mountTrends } from './trends.js';
import { mountLive } from './live.js';
export function mountElectricity(root, snapshot, history, signal, versions) {
  const events = new EventTarget();
  let trendsMounted = Boolean(history?.days?.length);
  root.dataset.historyAvailable = String(trendsMounted);
  mountTrends(root, history, model, events, signal);
  events.addEventListener('dashboard:history', event => {
    root.dataset.historyAvailable = 'true';
    if (!trendsMounted) {
      trendsMounted = true;
      mountTrends(root, event.detail, model, events, signal);
    }
  }, {signal});
  mountOverview(root, snapshot, map, events, signal);
  mountLive(root, snapshot, history, events, signal, versions);
}
