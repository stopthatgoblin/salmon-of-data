const api = '/api/electricity/';
const deadline = signal => AbortSignal.any([signal, AbortSignal.timeout(12000)]);

export function validateUpdate(name, next, current) {
  if (name === 'snapshot') {
    if (!['demand', 'generation', 'wind', 'solar', 'other', 'moyle', 'northSouth'].every(key => Number.isFinite(next[key])) || next.stations?.length !== 3 || !Number.isFinite(Date.parse(next.time)) || !Number.isFinite(Date.parse(next.retrievedAt))) throw new Error('Invalid snapshot');
    if (Date.parse(next.time) < Date.parse(current.time)) throw new Error('Snapshot moved backwards');
    if (Math.abs(next.demand - next.generation - next.moyle - next.northSouth) > .001) throw new Error('Invalid balance');
  } else {
    if (!next.days?.length || !['wind', 'solar', 'otherNI', 'moyle', 'northSouth', 'demand', 'generation'].every(key => next.series?.some(series => series.key === key)) || !Number.isFinite(Date.parse(next.generatedAt))) throw new Error('Invalid history');
    if (next.last < current.last || next.first > current.first || Date.parse(next.generatedAt) < Date.parse(current.generatedAt)) throw new Error('History moved backwards');
  }
}

export async function readInitialDataset(name, signal) {
  // The bundled accepted edition keeps local preview and temporary API outages
  // usable. Its age is always visible; successful polling replaces it in place.
  try {
    const response = await fetch(api + name + '.json', { signal: deadline(signal), cache: 'no-cache' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    validateUpdate(name, data, data);
    return { data, version: response.headers.get('X-Electricity-Version') };
  } catch (error) {
    if (signal.aborted) throw error;
    const response = await fetch(`/data/ni-electricity/${name}.json`, { signal });
    if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
    const data = await response.json();
    validateUpdate(name, data, data);
    return { data, version: null };
  }
}

export function mountLive(root, snapshot, history, events, signal, initialVersions = {}) {
  const data = { snapshot, history };
  const versions = { ...initialVersions };
  let busy = false;
  let status;
  let checked = false;
  let failures = 0;
  let lastContact = Object.values(initialVersions).some(Boolean) ? Date.now() : 0;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const date = value => value ? new Date(value).toLocaleString('en-GB', { timeZone: 'Europe/London' }) : 'not yet available';

  function showHealth() {
    events.dispatchEvent(new CustomEvent('dashboard:clock'));
    const label = root.querySelector('.snapshot-label');
    const health = root.querySelector('#refresh-health');
    const delayed = Date.now() - Date.parse(data.snapshot.time) > 45 * 60000;
    const failed = status?.snapshot?.ok === false;
    const checking = !checked || failures === 1 && lastContact && Date.now() - lastContact < 5 * 60000;
    const unavailable = checked && failures > 0 && !checking;
    const preview = status?.mode === 'preview';
    label.innerHTML = `<i></i> ${checking ? 'Checking for updates' : unavailable ? 'Connection unavailable' : delayed ? 'Delayed data' : failed ? 'Update delayed' : preview ? 'Preview readings' : 'Updates every 15 min'}`;
    label.dataset.health = checking ? 'checking' : unavailable || delayed || failed ? 'delayed' : 'ok';
    label.title = 'Grid observation time shown alongside. Station dispatch instructions are published in hourly batches.';
    if (checking) {
      health.textContent = 'Checking for updates. The observation time beside the tabs identifies the readings currently shown.';
      return;
    }
    if (unavailable) {
      health.textContent = 'The data service could not be reached. Showing the last loaded readings; this page retries every minute while visible and when you return.';
      return;
    }
    health.textContent = `${preview ? 'Preview collectors run on demand during review. Production is configured for overview collection every 15 minutes and history daily at 07:00 Europe/London.' : 'Overview collection is scheduled every 15 minutes; history daily at 07:00 Europe/London.'} GitHub schedules can run late. ${failed ? 'The last overview update failed; accepted readings are retained.' : 'Last successful overview collection: ' + date(status.snapshot?.lastSuccess) + '.'} ${status.history?.ok === false ? 'The last history update failed; accepted history is retained.' : 'Last successful history collection: ' + date(status.history?.lastSuccess) + '.'} ${delayed ? 'Grid readings are more than 45 minutes old.' : ''}`;
  }

  function showUpdate(name) {
    if (reducedMotion.matches) return;
    const selectors = name === 'snapshot' ? ['.metrics', '#overview'] : ['#trends'];
    selectors.map(selector => root.querySelector(selector)).filter(element => element && !element.hidden).forEach(element => {
      element.classList.remove('refresh-wipe');
      void element.offsetWidth;
      element.classList.add('refresh-wipe');
      element.addEventListener('animationend', () => element.classList.remove('refresh-wipe'), { once: true, signal });
    });
  }

  async function poll() {
    if (busy || signal.aborted || document.hidden) return;
    busy = true;
    try {
      const response = await fetch(api + 'manifest.json', { signal: deadline(signal), cache: 'no-cache' });
      if (!response.ok) throw new Error('Manifest unavailable');
      const manifest = await response.json();
      if (manifest.schema !== 1 || manifest.enabled !== true) throw new Error('Invalid manifest');
      status = manifest;
      checked = true;
      failures = 0;
      lastContact = Date.now();
      // A missing version in one dataset never prevents the other updating.
      await Promise.all(['snapshot', 'history'].map(async name => {
        const version = status[name]?.version;
        if (!version || version === versions[name]) return;
        try {
          const response = await fetch(api + name + '.json?v=' + encodeURIComponent(version), { signal: deadline(signal), cache: 'no-cache' });
          if (!response.ok || response.headers.get('X-Electricity-Version') !== version) return;
          const next = await response.json();
          validateUpdate(name, next, data[name]);
          if (signal.aborted) return;
          data[name] = next;
          versions[name] = version;
          events.dispatchEvent(new CustomEvent(`dashboard:${name}`, { detail: next }));
          showUpdate(name);
        } catch {
          // Keep the current valid view and retry propagation/network misses.
        }
      }));
    } catch {
      checked = true;
      failures++;
    } finally {
      if (!signal.aborted) showHealth();
      busy = false;
    }
  }

  showHealth();
  const timer = window.setInterval(poll, 60000);
  window.addEventListener('focus', poll, { signal });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void poll(); }, { signal });
  signal.addEventListener('abort', () => window.clearInterval(timer), { once: true });
  void poll();
}
