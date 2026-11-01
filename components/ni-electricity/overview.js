// Adapted from NI electricity/dashboard/dist/app.js.
export function mountOverview(root, data, map, events, signal) {
  const format = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
  const n = value => format.format(value);
  const capacityUsage = (output, capacity) => capacity > 0 ? Math.abs(output) / capacity * 100 : null;
  const capacityPercent = value => value === null ? '—' : `${Math.round(value)}%`;
  const escape = value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const dialog = root.querySelector('#' + 'station-dialog');
  const tabs = [...root.querySelectorAll('[role="tab"]')];
  const svgNS = 'http://www.w3.org/2000/svg';
  const mobile = window.matchMedia('(max-width:1000px)');

  function renderPeaks() {
    const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/London', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
    const part = type => parts.find(value => value.type === type).value;
    const today = `${part('year')}-${part('month')}-${part('day')}`;
    root.querySelectorAll('[data-expected-peak]').forEach(element => {
      const peak = data.expectedPeaks?.date === today ? data.expectedPeaks[element.dataset.expectedPeak] : null;
      const available = Number.isFinite(peak?.value);
      element.textContent = `Today's expected peak: ${available ? n(peak.value) + ' MW' : 'unavailable'}`;
      element.title = available ? `${peak.basis} Forecast collected ${new Date(peak.retrievedAt).toLocaleString('en-GB', { timeZone: 'Europe/London' })}.` : 'A complete current-day source forecast is not available.';
    });
  }

  function positionMapConnections() {
    const path = root.querySelector('.moyle-flow');
    let target = { x: 864, y: 165 };
    if (!mobile.matches) {
      const svg = root.querySelector('#electricity-map');
      if (!svg.getScreenCTM || !svg.createSVGPoint) return;
      const matrix = svg.getScreenCTM();
      if (!matrix) return;
      const box = root.querySelector('[data-interconnector="moyle"]').getBoundingClientRect();
      if (!box.width || !box.height) return;
      const point = svg.createSVGPoint();
      point.x = box.left - 4;
      point.y = box.top + box.height * .45;
      target = point.matrixTransform(matrix.inverse());
      const toMap = (x, y) => {
        const point = svg.createSVGPoint();
        point.x = x;
        point.y = y;
        return point.matrixTransform(matrix.inverse());
      };
      // Measure the cards so leaders stay attached when titles or values wrap.
      const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
      for (const [id, x, y] of [['coolkeeragh', 458, 197], ['ballylumford', 740, 261], ['kilroot', 742.1, 296.6]]) {
        const card = root.querySelector(`[data-station="${id}"]`).getBoundingClientRect();
        const topLeft = toMap(card.left, card.top);
        const bottomRight = toMap(card.right, card.bottom);
        const edgeX = clamp(x, topLeft.x, bottomRight.x);
        const edgeY = clamp(y, topLeft.y, bottomRight.y);
        const middleX = (edgeX + x) / 2;
        root.querySelector(`[data-leader="${id}"]`).setAttribute('d', `M${edgeX} ${edgeY}L${middleX} ${edgeY}L${x} ${y}`);
      }
      const nsBox = root.querySelector('[data-interconnector="northSouth"]').getBoundingClientRect();
      const ns = toMap(nsBox.right + 4, nsBox.top + nsBox.height * .5);
      root.querySelector('.ns-flow').setAttribute('d', data.northSouth < 0
        ? `M400 410C365 450 ${ns.x + 40} ${ns.y} ${ns.x} ${ns.y}`
        : `M${ns.x} ${ns.y}C${ns.x + 40} ${ns.y} 365 450 400 410`);
    }
    // End immediately outside the card border, keeping the export arrow visible.
    path.setAttribute('d', data.moyle < 0
      ? `M752 254C850 254 ${target.x - 60} ${target.y} ${target.x} ${target.y}`
      : `M${target.x} ${target.y}C${target.x - 60} ${target.y} 850 254 752 254`);
  }

  ['Ireland', 'Scotland', 'England', 'Wales', 'Isle of Man'].forEach(name => {
    const path = document.createElementNS(svgNS, 'path');
    path.setAttribute('d', map[name]);
    path.setAttribute('class', 'context-land');
    root.querySelector('#' + 'land-context').append(path);
  });
  root.querySelector('#' + 'ni-land').setAttribute('d', map['Northern Ireland']);
  root.querySelector('#' + 'lakes').setAttribute('d', map.lakes);

  function renderOverview() {
  root.querySelector('#' + 'renewables-share').textContent = data.demand > 0
    ? `${Math.round((data.wind + data.solar) / data.demand * 100)}%`
    : '—';

  // Positive flows enter NI. The label and arrow use the same sign convention.
  const interconnectors = [
    {
      key: 'moyle', name: 'Moyle Interconnector', remote: 'Scotland', value: data.moyle,
      capacity: data.moyleAvailable, capacityLabel: 'available', colour: 'moyle',
      path: '.moyle-flow', marker: 'moyle-arrow',
      importPath: 'M989 149C925 148 861 173 752 254',
      exportPath: 'M752 254C861 173 925 148 989 149',
      note: 'Collector capacity assumption; see sources.'
    },
    {
      key: 'northSouth', name: 'North-South Interconnector', remote: 'ROI', value: data.northSouth,
      capacity: data.northSouthReferenceCapacity, capacityLabel: 'reference capacity', colour: 'ns',
      path: '.ns-flow', marker: 'ns-arrow', estimated: true,
      importPath: 'M345 510C385 510 365 450 400 410',
      exportPath: 'M400 410C365 450 385 510 345 510'
    }
  ];
  interconnectors.forEach(flow => {
    const importing = flow.value > 0;
    const exporting = flow.value < 0;
    const state = importing ? 'Importing' : exporting ? 'Exporting' : 'No net flow';
    const direction = importing ? `${flow.remote} → NI` : exporting ? `NI → ${flow.remote}` : `NI ↔ ${flow.remote}`;
    const amount = n(Math.abs(flow.value));
    const utilisation = capacityUsage(flow.value, flow.capacity);
    const capacityBasis = flow.capacityLabel === 'available' ? 'available capacity' : flow.capacityLabel;
    const card = root.querySelector(`[data-interconnector="${flow.key}"]`);
    card.setAttribute('aria-label', `${flow.name}: ${state.toLowerCase()} ${amount} megawatts, ${direction}. ${n(flow.capacity)} megawatts ${flow.capacityLabel}${flow.estimated ? '. Estimated flow' : ''}. ${capacityPercent(utilisation)} of ${capacityBasis}.`);
    card.innerHTML = `<div class="callout-heading"><span class="source-dot ${flow.colour}-colour"></span><span class="interconnector-name">${flow.name}</span></div>
      <div class="flow-value">${amount} <small>MW</small>${flow.estimated ? ' <span class="estimate-tag">est.</span>' : ''}</div>
      <div class="flow-direction"><strong>${state}</strong><span>${direction}</span></div>
      <div class="capacity-track"><span style="width:${Math.min(100, utilisation ?? 0)}%"></span><small class="capacity-percent" title="${utilisation === null ? 'No available capacity' : `${capacityPercent(utilisation)} of ${capacityBasis}`}">${capacityPercent(utilisation)}</small></div>
      <div class="flow-capacity"><b>${n(flow.capacity)} MW</b> ${flow.capacityLabel}</div>
      ${flow.note ? `<p class="fault-note">${flow.note}</p>` : ''}`;
    const path = root.querySelector(flow.path);
    path.setAttribute('d', exporting ? flow.exportPath : flow.importPath);
    path.dataset.direction = importing ? 'import' : exporting ? 'export' : 'balanced';
    if (flow.value !== 0) path.setAttribute('marker-end', `url(#${flow.marker})`);
    else path.removeAttribute('marker-end');
  });

  const stationOutput = data.stations.reduce((sum, station) => sum + station.output, 0);
  const totals = { ...data, imports: data.moyle + data.northSouth, renewables: data.wind + data.solar, stations: stationOutput, niOther: data.generation - data.wind - data.solar, renewablesPercent: Math.round((data.wind + data.solar) / data.demand * 100) };
  const dateFormat = new Intl.DateTimeFormat('en-GB', { day:'numeric', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit', timeZone:'Europe/London', timeZoneName:'short' });
  const stamp = value => dateFormat.format(new Date(value)).replace('GMT+0', 'GMT').replace('GMT+1', 'BST');
  root.querySelectorAll('[data-reading]').forEach(el => el.innerHTML = `${n(el.dataset.reading === 'imports' ? Math.abs(totals.imports) : totals[el.dataset.reading])} <small>MW</small>`);
  root.querySelectorAll('[data-share]').forEach(el => el.textContent = data.demand > 0 ? `${Math.round(totals[el.dataset.share] / data.demand * 100)}%` : '—');
  root.querySelector('#' + 'net-flow-label').textContent = totals.imports > 0 ? 'Net imports' : totals.imports < 0 ? 'Net exports' : 'Net flow';
  root.querySelector('#' + 'net-flow-share').hidden = totals.imports <= 0 || data.demand <= 0;
  root.querySelectorAll('[data-number]').forEach(el => el.textContent = n(totals[el.dataset.number]));
  root.querySelectorAll('[data-stamp]').forEach(el => el.textContent = data[el.dataset.stamp] ? stamp(data[el.dataset.stamp]) : 'Not recorded');
  root.querySelectorAll('[data-snapshot-time]').forEach(el => {el.dateTime = data.time; el.textContent = stamp(data.time);});
  root.querySelectorAll('[data-snapshot-short]').forEach(el => el.textContent = stamp(data.time));
  root.querySelectorAll('[data-report-link]').forEach(el => {if(data[el.dataset.reportLink]) el.href = `https://reports.sem-o.com/documents/${data[el.dataset.reportLink]}`;});
  data.stations.forEach(station => {
    const button = root.querySelector(`.plant-callout[data-station="${station.id}"]`);
    const utilisation = capacityUsage(station.output, station.available);
    const percentage = Math.min(100, utilisation ?? 0);
    button.setAttribute('aria-label', `${station.name}: estimated output ${n(station.output)} megawatts, ${n(station.available)} megawatts available. ${utilisation === null ? 'No available capacity.' : `${capacityPercent(utilisation)} of available capacity.`} Explore ${station.units.length} units.`);
    button.innerHTML = `<span class="plant-name">${escape(station.name)} <span class="plant-open" aria-hidden="true">↗</span></span>
      <span class="plant-reading"><strong>${n(station.output)}</strong><small>MW</small><span class="estimate-tag">est.</span></span>
      <span class="plant-meter capacity-track" aria-hidden="true"><span style="width:${percentage}%"></span><small class="capacity-percent" title="${utilisation === null ? 'No available capacity' : `${capacityPercent(utilisation)} of reported available capacity`}">${capacityPercent(utilisation)}</small></span>
      <span class="plant-capacity"><span><b>${n(station.available)} MW</b> available</span><span class="units-link">${station.units.length} units <span aria-hidden="true">↗</span></span></span>`;
    const marker = root.querySelector(`[data-map-plant="${station.id}"]`);
    marker.classList.toggle('muted', station.output === 0);
  });
  renderPeaks();
  positionMapConnections();
  }
  renderOverview();
  root.querySelectorAll('.plant-callout').forEach(button => {
    const marker = root.querySelector(`[data-map-plant="${button.dataset.station}"]`);
    ['mouseenter', 'focus'].forEach(event => button.addEventListener(event, () => marker.classList.add('is-hover')));
    ['mouseleave', 'blur'].forEach(event => button.addEventListener(event, () => marker.classList.remove('is-hover')));
  });

  function setView(view, { focus = false, updateHash = true } = {}) {
    const selected = ['overview', 'trends', 'definitions'].includes(view) ? view : 'overview';
    if (dialog.open) dialog.close();
    tabs.forEach(tab => {
      const active = tab.id === `tab-${selected}`;
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      root.querySelector('#' + tab.getAttribute('aria-controls')).hidden = !active;
      if (active && focus) tab.focus();
    });
    root.querySelector('.metrics').hidden = selected !== 'overview';
    root.querySelector('.snapshot-stamp').hidden = selected !== 'overview';
    root.dataset.view = selected;
    if (selected === 'overview') positionMapConnections();
    if (updateHash) history.replaceState(null, '', `#${selected}`);
    events.dispatchEvent(new CustomEvent('dashboard:viewchange', { detail: selected }));
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => setView(tab.getAttribute('aria-controls')));
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next === undefined) return;
      event.preventDefault();
      setView(tabs[next].getAttribute('aria-controls'), { focus: true });
    });
  });

  function renderStation(id) {
    dialog.dataset.activeStation = id;
    const station = data.stations.find(item => item.id === id);
    if (!station) return;
    const availableCount = station.units.filter(unit => unit.available > 0).length;
    root.querySelector('#' + 'station-switcher').innerHTML = data.stations.map(item => `<button data-switch="${item.id}" aria-pressed="${item.id === id}">${escape(item.name)}</button>`).join('');
    root.querySelector('#' + 'station-detail').innerHTML = `
      <div class="station-title-row"><h2 id="station-title">${escape(station.name)}</h2><span class="station-status">${availableCount} of ${station.units.length} units available</span></div>
      <div class="station-summary"><div><span>Estimated output</span><strong>${n(station.output)} <small>MW</small></strong></div><div><span>Reported available</span><strong>${n(station.available)} <small>MW</small></strong></div><div><span>Technical maximum</span><strong>${n(station.maximum)} <small>MW</small></strong></div></div>
      <table class="unit-table"><caption>Generating units <span class="estimate-tag">MW</span></caption><thead><tr><th scope="col">Unit / fuel</th><th scope="col">Output <span class="estimate-tag">est.</span></th><th scope="col">Available</th><th scope="col">Maximum</th></tr></thead><tbody>${station.units.map(unit => {
        const statusClass = !unit.available ? 'unavailable' : unit.status === 'Start instructed' ? 'starting' : unit.output ? 'running' : '';
        return `<tr><td><span class="unit-name">${escape(unit.name)}</span><span class="unit-fuel">${escape(unit.fuel)}</span><span class="unit-status ${statusClass}"><i></i>${escape(unit.status)}</span></td><td class="unit-output ${unit.output ? '' : 'unit-zero'}">${n(unit.output)}</td><td>${n(unit.available)}</td><td>${n(unit.maximum)}</td></tr>`;
      }).join('')}</tbody></table>`;
  }

  root.addEventListener('click', event => {
    const stationButton = event.target.closest('.plant-callout[data-station]');
    const switchButton = event.target.closest('[data-switch]');
    const viewButton = event.target.closest('button[data-view]');
    if (stationButton) {
      renderStation(stationButton.dataset.station);
      dialog.showModal();
    }
    if (switchButton) {
      renderStation(switchButton.dataset.switch);
      root.querySelector(`[data-switch="${switchButton.dataset.switch}"]`).focus();
    }
    if (viewButton) {
      setView(viewButton.dataset.view, { focus: true });
      const target = viewButton.dataset.anchor ? root.querySelector('#' + viewButton.dataset.anchor) : root.querySelector('.tabs');
      target.scrollIntoView({ block: 'start' });
    }
  }, { signal });
  root.querySelector('.close-dialog').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });

  function updateMapViewport() {
    root.querySelector('#' + 'electricity-map').setAttribute('viewBox', mobile.matches ? '260 75 620 480' : '70 20 1130 590');
    // Keep the sea name clear of station cards and inside the cropped mobile map.
    const seaLabel = root.querySelector('.sea-label');
    const [x, y] = mobile.matches ? [820, 510] : [840, 535];
    seaLabel.setAttribute('x', x);
    seaLabel.setAttribute('y', y);
    seaLabel.setAttribute('transform', `rotate(-12 ${x} ${y})`);
    positionMapConnections();
  }
  mobile.addEventListener('change', updateMapViewport, { signal });
  window.addEventListener('resize', positionMapConnections, { signal });
  updateMapViewport();
  setView(location.hash.slice(1), { updateHash: false });
  window.addEventListener('hashchange', () => {
    if (['#overview', '#trends', '#definitions'].includes(location.hash)) setView(location.hash.slice(1), { updateHash: false });
  }, { signal });
  events.addEventListener('dashboard:snapshot', event => {
    data = event.detail;
    const focused = document.activeElement?.closest('[data-switch]')?.dataset.switch;
    renderOverview();
    if (dialog.open) {
      renderStation(dialog.dataset.activeStation);
      if (focused) root.querySelector(`[data-switch="${focused}"]`)?.focus();
    }
  }, { signal });
  events.addEventListener('dashboard:clock', renderPeaks, { signal });
}
