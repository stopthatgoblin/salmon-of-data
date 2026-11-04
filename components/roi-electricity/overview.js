import {project,flowGeometry} from './flow-geometry.js';
import {reconcileSnapshot} from './balance.js';
import {generationIcon,interconnectorIcon} from './generation-icons.js';
// Republic of Ireland adaptation of the NI dashboard overview.
export function mountOverview(root, data, map, events, signal) {
  data = reconcileSnapshot(data);
  const captured = data.dataBasis === 'public-source-capture';
  const n = value => Number.isFinite(value) ? new Intl.NumberFormat('en-IE', { maximumFractionDigits: 0 }).format(value) : '—';
  const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const usage = (output, capacity) => Number.isFinite(output) && capacity > 0 ? Math.abs(output) / capacity * 100 : null;
  const percent = value => value === null ? '—' : `${Math.round(value)}%`;
  const dialog = root.querySelector('#station-dialog');
  const tabs = [...root.querySelectorAll('[role="tab"]')];
  const svg = root.querySelector('#electricity-map');
  const mobile = window.matchMedia('(max-width:1000px)');
  const NS = 'http://www.w3.org/2000/svg';
  // Same geographic projection as the source, reframed to show the full Republic.
  const {width:mapWidth,height:mapHeight} = svg.viewBox.baseVal;
  const stationPoint = station => {const point = project(station.location);return {x:point.x + (station.markerOffset?.[0] ?? 0), y:point.y + (station.markerOffset?.[1] ?? 0)};};
  const transform = `matrix(${130 / 190} 0 0 ${216 / 328} ${528 - 280 * 130 / 190} ${20.8 - 30 * 216 / 328})`;
  const addSVG = (tag, attributes, parent) => {
    const element = document.createElementNS(NS, tag);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    parent.append(element);
    return element;
  };
  for (const name of ['Northern Ireland', 'Scotland', 'England', 'Wales', 'Isle of Man']) {
    addSVG('path', { d:map[name], class:'context-land', 'data-country':name, transform }, root.querySelector('#land-context'));
  }
  for (const [id, key] of [['roi-land','Ireland'], ['lakes','lakes']]) {
    root.querySelector(`#${id}`).setAttribute('d', map[key]);
    root.querySelector(`#${id}`).setAttribute('transform', transform);
  }

  function renderPeaks() {
    const today = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Dublin',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
    root.querySelectorAll('[data-peak]').forEach(el => {
      const value = data.expectedPeaks?.[el.dataset.peak];
      el.textContent = n(value);
      el.closest('.expected-peak').hidden = data.expectedPeaks?.date !== today || !Number.isFinite(value);
    });
  }
  function renderReadings() {
    const readings = {...data, renewables:data.wind + data.solar, imports:data.interconnectors.reduce((sum, flow) => sum + flow.value, 0)};
    root.querySelectorAll('[data-reading]').forEach(el => {
      const key = el.dataset.reading;
      const value = key === 'imports' ? Math.abs(readings[key]) : readings[key];
      el.innerHTML = `${key === 'reconciliation' && value > 0 ? '+' : ''}${n(value)} <small>MW</small>${key === 'other' ? ' <sup>est.</sup>' : ''}`;
    });
    root.querySelectorAll('[data-share]').forEach(el => { el.textContent = data.demand > 0 ? percent(readings[el.dataset.share] / data.demand * 100) : '—'; });
    root.querySelector('#renewables-share').textContent = data.demand > 0 ? percent(readings.renewables / data.demand * 100) : '—';
    root.querySelector('#net-flow-label').textContent = readings.imports > 0 ? 'Net imports' : readings.imports < 0 ? 'Net exports' : 'Net flow';
    root.querySelector('#net-flow-share').hidden = readings.imports <= 0 || data.demand <= 0;
    renderPeaks();
    const stamp = new Intl.DateTimeFormat('en-IE', {day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'Europe/Dublin',timeZoneName:'short'}).format(new Date(data.time)).replace('GMT+0','GMT');
    root.querySelectorAll('[data-snapshot-time]').forEach(el => { el.dateTime = data.time; el.textContent = stamp; });
    root.querySelectorAll('[data-snapshot-short]').forEach(el => { el.textContent = stamp; });
    if (captured) {
      root.querySelector('.snapshot-label').innerHTML = '<i></i> Captured data';
      root.querySelector('.preview-note').textContent = 'Republic of Ireland · EirGrid actuals & SEMO estimates · Station outputs are estimates';
      root.querySelector('.metrics').setAttribute('aria-label','Electricity system summary, public-source readings');
      root.querySelector('.map-notes .chart-attribution').firstChild.textContent = 'EirGrid actuals · SEMO dispatch-target estimates & availability · ';
      const sources = data.sources.plants;
      const dispatchTime = new Intl.DateTimeFormat('en-IE',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit',timeZone:'Europe/Dublin',timeZoneName:'short'}).format(new Date(sources.dispatchCoverageThrough));
      root.querySelector('.map-notes .chart-attribution').firstChild.textContent = `EirGrid actuals · SEMO target estimates (reports through ${dispatchTime}) & availability · `;
      root.querySelector('#station-dialog .chart-attribution').textContent = 'SEMO dispatch-target estimates · Published availability and technical declarations · Not live metered output';
      root.querySelector('#station-dialog .dialog-footer>span').firstChild.textContent = 'Snapshot · ';
      root.querySelector('#metric-definitions dl>div:first-child dd').textContent = 'Power required by the ROI system, in megawatts (MW), from EirGrid. Expected peaks use available published ROI forecasts; a missing forecast is omitted.';
      root.querySelector('#metric-definitions dl>div:nth-child(3) dd').textContent = 'East–West, Greenlink and North–South flows combined. Positive means imports into ROI; negative means exports. North–South is the NI estimate with its sign reversed: −(NI demand − NI generation − Moyle imports), using grid inputs at the same observation time. This is a balance estimate, not a metered tie-line reading.';
      root.querySelector('#metric-definitions dl>div:nth-child(5) dd').textContent = 'Selected registered generating units at the mapped stations. Output is a last-published dispatch-target proxy, seeded from earlier half-hourly meter data (MWh converted to average MW). This follows the NI approach; it does not establish current metered output. Missing or expired numeric instructions show a dash. Huntstown TEG and Poolbeg Flexgen are included; batteries and neighbouring Cushaling peakers stay in Other/Unallocated. Icons indicate the station’s principal generation type.';
      root.querySelector('#estimates>p:first-of-type').textContent = 'Grid readings are reported actuals; station outputs and North–South are estimates. Dispatch publications lag the grid readings, and a carried-forward target is not a live meter measurement. Unknown outputs remain unallocated. Technical declarations come from the latest available publications. Trends shows complete daily averages from public sources.';
      root.querySelector('#estimates>p:last-of-type').textContent = 'Moneypoint uses the current registered oil-fired units. The original Tarbert oil station is excluded. This is a selected station set; smaller plants, temporary generation, batteries and other unmatched generation remain in Other/Unallocated. Signed residuals can be negative when proxy estimates and reported regional generation do not reconcile.';
      root.querySelector('#capacity>p:first-of-type').textContent = 'Available capacity comes from SEMO’s published outturn availability baseline and subsequent hourly changes. The percentage is the magnitude of estimated output divided by availability. Zero output does not establish an outage; zero declared availability is a separate observation.';
      root.querySelector('#capacity>p:nth-of-type(2)').textContent = 'Technical maximum in the drawer comes from the latest available SEMO technical offer report for the selected registered resource IDs. These values can differ from nominal station ratings. Snapshot source records retain report dates and unit mapping.';
      root.querySelector('#data-sources>p:first-of-type').textContent = 'The overview uses public EirGrid actuals and SEMO unit reports. ROI grid series and the accepted NI inputs share one timestamp. Plant estimates, availability and technical parameters retain their report provenance in snapshot.json. The overview is collected every 15 minutes; history is collected daily.';
      root.querySelector('#data-sources .source-list li:first-child small').textContent = 'Captured ROI demand, generation, wind, solar, East–West and Greenlink, plus matching NI inputs for the shared North–South estimate.';
      const sourceItem = document.createElement('li');
      sourceItem.innerHTML = '<a href="https://reports.sem-o.com/" target="_blank" rel="noopener">SEMO public reports <span>↗</span></a><small>Registered units, hourly dispatch instructions, D+1 meter seeds, outturn availability and technical offer data. Public IDs and report filenames are retained in the snapshot.</small>';
      if (!root.querySelector('#data-sources .source-list [href="https://reports.sem-o.com/"]')) root.querySelector('#data-sources .source-list').append(sourceItem);
    }

  }
  renderReadings();

  function stationContent(station) {
    const ratio = usage(station.output, station.available);
    return `<span class="plant-name">${escape(station.name)} <span class="plant-open" aria-hidden="true">↗</span></span>
      <span class="plant-reading"><strong>${n(station.output)}</strong><small>MW</small><span class="estimate-tag">est.</span>${generationIcon(station.generationType)}</span>
      <span class="plant-meter capacity-track" aria-hidden="true"><span style="width:${Math.min(100, ratio ?? 0)}%"></span><small class="capacity-percent">${percent(ratio)}</small></span>
      <span class="plant-capacity"><span><b>${n(station.available)} MW</b> available</span><span class="units-link">${station.units.length} ${station.units.length === 1 ? 'unit' : 'units'} ↗</span></span>`;
  }
  function flowContent(flow) {
    const importing = flow.value > 0;
    const state = importing ? 'Importing' : flow.value < 0 ? 'Exporting' : 'No net flow';
    const direction = importing ? `${flow.remote} → ROI` : flow.value < 0 ? `ROI → ${flow.remote}` : `ROI ↔ ${flow.remote}`;
    const ratio = usage(flow.value, flow.capacity);
    return `<div class="callout-heading"><span class="source-dot ${flow.id === 'northSouth' ? 'ns' : 'moyle'}-colour"></span><span class="interconnector-name">${escape(flow.name)}</span></div>
      <div class="flow-value">${n(Math.abs(flow.value))} <small>MW</small>${flow.estimated ? ' <span class="estimate-tag">est.</span>' : ''}${interconnectorIcon()}</div>
      <div class="flow-direction"><strong>${state}</strong>${flow.id === 'northSouth'
        ? `<span class="flow-route" aria-label="${direction}">${escape(direction)}</span>`
        : `<span class="flow-route" aria-label="${direction}"><span>ROI</span><b aria-hidden="true">${importing ? '←' : flow.value < 0 ? '→' : '↔'}</b><span>Wales</span></span>`}</div>
      <div class="capacity-track"><span style="width:${Math.min(100, ratio ?? 0)}%"></span><small class="capacity-percent">${percent(ratio)}</small></div>
      <div class="flow-capacity"><b>${n(flow.capacity)} MW</b> ${escape(flow.capacityLabel)}</div>`;
  }
  const stationCards = root.querySelector('#station-cards');
  data.stations.forEach(station => {
    const ratio = usage(station.output, station.available);
    const button = document.createElement('button');
    button.className = `plant-callout ${station.id}`;
    button.dataset.station = station.id;
    button.dataset.index = station.index;
    button.style.setProperty('--card-x', `${station.card[0] / mapWidth * 100}%`);
    button.style.setProperty('--card-y', `${station.card[1] / mapHeight * 100}%`);
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-label', `${station.name}, ${station.fuel}: ${captured ? 'estimated' : 'sample'} output ${n(station.output)} megawatts, ${n(station.available)} megawatts available. Explore ${station.units.length} ${captured ? 'registered' : 'illustrative'} units.`);
    button.innerHTML = stationContent(station);
    stationCards.append(button);
    const point = stationPoint(station);
    addSVG('path', { 'data-leader':station.id, d:`M${point.x} ${point.y}h-20` }, root.querySelector('#station-leaders'));
    const marker = addSVG('g', {class:`plant-dot${station.output === 0 ? ' muted' : ''}`, 'data-map-plant':station.id, 'data-station':station.id, role:'button', tabindex:'0', 'aria-haspopup':'dialog', 'aria-label':`Explore ${station.name}`}, root.querySelector('#station-markers'));
    addSVG('circle', {cx:point.x,cy:point.y,r:10}, marker);
    addSVG('circle', {cx:point.x,cy:point.y,r:4}, marker);
    addSVG('title', {}, marker).textContent = station.name;
    // Numbered markers keep neighbouring Dublin and Cork sites identifiable on mobile.
    addSVG('text', {x:point.x + (station.labelOffset?.[0] ?? 13),y:point.y + (station.labelOffset?.[1] ?? -10),class:'mobile-plant-index','aria-hidden':'true'}, marker).textContent = station.index;
    ['mouseenter','focus'].forEach(event => button.addEventListener(event, () => marker.classList.add('is-hover'), { signal }));
    ['mouseleave','blur'].forEach(event => button.addEventListener(event, () => marker.classList.remove('is-hover'), { signal }));
  });

  data.interconnectors.forEach(flow => {
    const importing = flow.value > 0;
    const state = importing ? 'Importing' : flow.value < 0 ? 'Exporting' : 'No net flow';
    const direction = importing ? `${flow.remote} → ROI` : flow.value < 0 ? `ROI → ${flow.remote}` : `ROI ↔ ${flow.remote}`;
    const ratio = usage(flow.value, flow.capacity);
    const card = document.createElement('div');
    card.className = `interconnector ${flow.id === 'northSouth' ? 'north-south' : 'moyle'} ${flow.id}`;
    card.dataset.interconnector = flow.id;
    card.style.setProperty('--card-x', `${flow.card[0] / mapWidth * 100}%`);
    card.style.setProperty('--card-y', `${flow.card[1] / mapHeight * 100}%`);
    card.setAttribute('aria-label', `${flow.name}: ${captured ? '' : 'sample '}${state.toLowerCase()} ${n(Math.abs(flow.value))} megawatts, ${direction}. ${n(flow.capacity)} megawatts ${flow.capacityLabel}.`);
    card.innerHTML = flowContent(flow);
    root.querySelector('#connector-cards').append(card);
    const geometry = flowGeometry(flow);
    const path = addSVG('path', {class:`flow-path ${flow.id === 'northSouth' ? 'ns-flow' : 'moyle-flow'}`, 'data-flow':flow.id, 'data-direction':importing ? 'import' : flow.value < 0 ? 'export' : 'balanced', d:geometry.path}, root.querySelector('#connector-flows'));
    if (flow.value !== 0) path.setAttribute('marker-end', `url(#${flow.id === 'northSouth' ? 'ns-arrow' : 'import-arrow'})`);
    addSVG('path', {'data-flow-leader':flow.id}, root.querySelector('#connector-leaders'));
  });

  function positionMapConnections() {
    if (mobile.matches) return;
    const matrix = svg.getScreenCTM();
    if (!matrix) return;
    const inverse = matrix.inverse();
    const toMap = (x,y) => new DOMPoint(x,y).matrixTransform(inverse);
    for (const station of data.stations) {
      const point = stationPoint(station);
      const card = root.querySelector(`.plant-callout[data-station="${station.id}"]`).getBoundingClientRect();
      const a = toMap(card.left, card.top), b = toMap(card.right, card.bottom);
      const edgeX = station.leaderSide === 'top' || station.leaderSide === 'bottom' ? (a.x + b.x) / 2 : Math.max(a.x, Math.min(b.x, point.x));
      const edgeY = station.leaderSide === 'top' ? a.y : station.leaderSide === 'bottom' ? b.y : ['left','right'].includes(station.leaderSide) ? (a.y + b.y) / 2 : Math.max(a.y + 10, Math.min(b.y - 10, point.y));
      const middleX = (edgeX + point.x) / 2;
      const route = station.leaderWaypoints?.map(([x,y]) => `L${x} ${y}`).join('') ?? `L${middleX} ${edgeY}`;
      root.querySelector(`[data-leader="${station.id}"]`).setAttribute('d', `M${edgeX} ${edgeY}${route}L${point.x} ${point.y}`);
    }
    for (const flow of data.interconnectors) {
      const box = root.querySelector(`[data-interconnector="${flow.id}"]`).getBoundingClientRect();
      const geometry = flowGeometry(flow);
      if (flow.id === 'northSouth') {
        const edge = toMap(box.left + box.width * .45, box.bottom);
        root.querySelector(`[data-flow-leader="${flow.id}"]`).setAttribute('d', `M${edge.x} ${edge.y}L${edge.x} 250L${geometry.remote.x} 250L${geometry.remote.x} ${geometry.remote.y}`);
      } else if (flow.id === 'eastWest') {
        // Keep both arrowheads clear of the card at the Welsh coastal endpoint.
        const edge = toMap(box.left + box.width * .68,box.bottom);
        root.querySelector(`[data-flow-leader="${flow.id}"]`).setAttribute('d', `M${edge.x} ${edge.y}L${geometry.remote.x} ${geometry.remote.y}`);
      } else {
        const edge = toMap(box.left,box.top + 20);
        root.querySelector(`[data-flow-leader="${flow.id}"]`).setAttribute('d', `M${edge.x} ${edge.y}L${geometry.remote.x} ${edge.y}L${geometry.remote.x} ${geometry.remote.y}`);
      }
    }
  }

  function renderStation(id) {
    const station = data.stations.find(item => item.id === id);
    if (!station) return;
    dialog.dataset.activeStation = id;
    const availableCount = station.units.filter(unit => unit.available > 0).length;
    const unitStatus = unit => captured
      ? unit.output === null ? 'Output unknown' : !unit.available ? 'Declared unavailable' : unit.basis === 'meter_seed' ? 'Earlier meter seed' : unit.basis?.includes('SYNC') ? 'Start instructed' : unit.output ? 'Last published target' : 'No generation indicated'
      : !unit.available ? 'Sample: unavailable' : unit.output ? 'Sample: generating' : 'Sample: no generation';
    root.querySelector('#station-switcher').innerHTML = data.stations.map(item => `<button data-switch="${item.id}" aria-pressed="${item.id === id}">${escape(item.name)}</button>`).join('');
    root.querySelector('#station-detail').innerHTML = `<div class="station-title-row"><h2 id="station-title">${generationIcon(station.generationType)}${escape(station.name)}</h2><span class="station-status">${availableCount} of ${station.units.length} units available</span></div>
      <p class="station-location">${escape(station.region)} · ${escape(station.fuel)}</p>
      <div class="station-summary"><div><span>Estimated output</span><strong>${n(station.output)} <small>MW</small></strong></div><div><span>Reported available</span><strong>${n(station.available)} <small>MW</small></strong></div><div><span>Technical maximum</span><strong>${n(station.maximum)} <small>MW</small></strong></div></div>
      <table class="unit-table"><caption>Generating units <span class="estimate-tag">${captured ? 'Estimated' : 'Sample'} · MW</span></caption><thead><tr><th scope="col">Unit / fuel</th><th scope="col">Output <span class="estimate-tag">est.</span></th><th scope="col">Available</th><th scope="col">Maximum</th></tr></thead><tbody>${station.units.map(unit => `<tr><td><span class="unit-name">${escape(unit.name)}</span><span class="unit-fuel">${escape(unit.fuel)}</span><span class="unit-status ${!unit.available ? 'unavailable' : unit.output ? 'running' : ''}"><i></i>${escape(unitStatus(unit))}</span></td><td class="unit-output ${unit.output ? '' : 'unit-zero'}">${n(unit.output)}</td><td>${n(unit.available)}</td><td>${n(unit.maximum)}</td></tr>`).join('')}</tbody></table>
      <p class="station-note">${escape(station.note)}</p>`;
  }

  function setView(view, {focus = false, updateHash = true} = {}) {
    const selected = ['overview','trends','definitions'].includes(view) ? view : 'overview';
    if (dialog.open) dialog.close();
    tabs.forEach(tab => {
      const active = tab.id === `tab-${selected}`;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      root.querySelector(`#${tab.getAttribute('aria-controls')}`).hidden = !active;
      if (active && focus) tab.focus();
    });
    root.querySelector('.metrics').hidden = selected !== 'overview';
    root.querySelector('.snapshot-stamp').hidden = selected !== 'overview';
    if(captured) root.querySelector('.preview-note').textContent = selected === 'overview'
      ? 'Republic of Ireland · EirGrid actuals & SEMO estimates · Station outputs are estimates'
      : selected === 'trends' ? (root.dataset.historyAvailable === 'true' ? 'Republic of Ireland · Historical daily averages' : 'Republic of Ireland · History not yet loaded')
      : 'Republic of Ireland · Definitions & sources';
    root.dataset.view = selected;
    if (selected === 'overview') positionMapConnections();
    if (updateHash) history.replaceState(null, '', `#${selected}`);
    events.dispatchEvent(new CustomEvent('dashboard:viewchange', {detail:selected}));
  }
  tabs.forEach((tab,index) => {
    tab.addEventListener('click', () => setView(tab.getAttribute('aria-controls')), {signal});
    tab.addEventListener('keydown', event => {
      const next = event.key === 'ArrowRight' ? (index + 1) % tabs.length : event.key === 'ArrowLeft' ? (index + tabs.length - 1) % tabs.length : event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : undefined;
      if (next === undefined) return;
      event.preventDefault();
      setView(tabs[next].getAttribute('aria-controls'), {focus:true});
    }, {signal});
  });
  root.addEventListener('click', event => {
    const station = event.target.closest('[data-station]');
    const switcher = event.target.closest('[data-switch]');
    const view = event.target.closest('button[data-view]');
    if (station) {renderStation(station.dataset.station); dialog.showModal();}
    if (switcher) {renderStation(switcher.dataset.switch); root.querySelector(`[data-switch="${switcher.dataset.switch}"]`).focus();}
    if (view) {
      setView(view.dataset.view, {focus:true});
      (root.querySelector(`#${view.dataset.anchor}`) ?? root.querySelector('.tabs')).scrollIntoView({block:'start'});
    }
  }, {signal});
  root.addEventListener('keydown', event => {
    if (event.target.matches('[data-map-plant]') && ['Enter',' '].includes(event.key)) {event.preventDefault(); event.target.dispatchEvent(new MouseEvent('click', {bubbles:true}));}
  }, {signal});
  root.querySelector('.close-dialog').addEventListener('click', () => dialog.close(), {signal});
  dialog.addEventListener('click', event => {if(event.target === dialog) dialog.close();}, {signal});
  mobile.addEventListener('change', positionMapConnections, {signal});
  window.addEventListener('resize', positionMapConnections, {signal});
  setView(location.hash.slice(1), {updateHash:false});
  window.addEventListener('hashchange', () => {
    const hash = location.hash.slice(1);
    if (['overview','trends','definitions'].includes(hash)) setView(hash, {updateHash:false});
    else if (hash && root.querySelector(`#${CSS.escape(hash)}`)?.closest('#definitions')) setView('definitions', {updateHash:false});
  }, {signal});
  events.addEventListener('dashboard:history', () => {
    root.dataset.historyAvailable = 'true';
    if (root.dataset.view === 'trends') root.querySelector('.preview-note').textContent = 'Republic of Ireland · Historical daily averages';
  }, {signal});
  events.addEventListener('dashboard:clock', renderPeaks, {signal});
  events.addEventListener('dashboard:snapshot', event => {
    data = reconcileSnapshot(event.detail);
    renderReadings();
    for (const station of data.stations) {
      const button = root.querySelector(`.plant-callout[data-station="${station.id}"]`);
      button.innerHTML = stationContent(station);
      button.setAttribute('aria-label', `${station.name}, estimated output ${n(station.output)} megawatts, ${n(station.available)} megawatts available. Explore ${station.units.length} registered units.`);
      root.querySelector(`[data-map-plant="${station.id}"]`).classList.toggle('muted', station.output === 0);
    }
    for (const flow of data.interconnectors) {
      const card = root.querySelector(`[data-interconnector="${flow.id}"]`);
      card.innerHTML = flowContent(flow);
      card.setAttribute('aria-label', `${flow.name}: ${n(Math.abs(flow.value))} megawatts, ${flow.value > 0 ? 'importing' : flow.value < 0 ? 'exporting' : 'no net flow'}.`);
      const path = root.querySelector(`[data-flow="${flow.id}"]`);
      path.setAttribute('d', flowGeometry(flow).path);
      path.dataset.direction = flow.value > 0 ? 'import' : flow.value < 0 ? 'export' : 'balanced';
      if (flow.value) path.setAttribute('marker-end', `url(#${flow.id === 'northSouth' ? 'ns-arrow' : 'import-arrow'})`);
      else path.removeAttribute('marker-end');
    }
    if (dialog.open) {
      const focused = document.activeElement?.dataset.switch;
      renderStation(dialog.dataset.activeStation);
      if (focused) root.querySelector(`[data-switch="${focused}"]`)?.focus();
    }
    if (root.dataset.view !== 'overview') root.querySelector('.preview-note').textContent = root.dataset.view === 'trends' ? (root.dataset.historyAvailable === 'true' ? 'Republic of Ireland · Historical daily averages' : 'Republic of Ireland · History not yet loaded') : 'Republic of Ireland · Definitions & sources';
    positionMapConnections();
  }, {signal});
  requestAnimationFrame(positionMapConnections);
}
