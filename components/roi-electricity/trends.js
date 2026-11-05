// Adapted from NI electricity/dashboard/dist/trends.js; aggregation and exports retained.
export function mountTrends(root, rawHistory, model, events, signal) {
  const panel = root.querySelector('#' + 'trends');
  if (!rawHistory || !rawHistory.days.length) {
    root.querySelector('#' + 'trends-content').hidden = true;
    root.querySelector('#' + 'trends-unavailable').hidden = false;
    return;
  }
  root.querySelector('#trends-content').hidden = false;
  root.querySelector('#trends-unavailable').hidden = true;
  // Keep the public view and its CSV aligned; station history remains in the source archive.
  const seriesChoices = [
    ['wind', 'Wind'], ['solar', 'Solar'], ['otherROI', 'Non-wind/solar generation'],
    ['generation', 'Total ROI generation'], ['demand', 'Electricity demand'],
    ['eastWest', 'East-West Interconnector'], ['greenlink', 'Greenlink Interconnector'], ['northSouth', 'North-South Interconnector']
  ];
  function displayedHistory(raw) {
    const indexes = seriesChoices.map(([key]) => raw.series.findIndex(series => series.key === key));
    return {
      ...raw,
      series: seriesChoices.map(([, label], i) => ({ ...raw.series[indexes[i]], label })),
      days: raw.days.map(row => ({ ...row, v: indexes.map(i => row.v[i]), n: indexes.map(i => row.n[i]) }))
    };
  }
  let history = displayedHistory(rawHistory);
  const source = root.querySelector('#' + 'trend-source');
  const from = root.querySelector('#' + 'trend-from');
  const to = root.querySelector('#' + 'trend-to');
  const chart = root.querySelector('#' + 'trend-chart');
  const tooltip = root.querySelector('#' + 'trend-tooltip');
  const download = root.querySelector('#' + 'trend-download');
  const pngDownload = root.querySelector('#' + 'trend-image-png');
  const svgDownload = root.querySelector('#' + 'trend-image-svg');
  const downloadStatus = root.querySelector('#' + 'trend-download-status');
  const display = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
  const whole = new Intl.NumberFormat('en-GB', { maximumFractionDigits: 0 });
  const day = value => new Date(`${value}T00:00:00Z`);
  const dateLabel = (value, options = {}) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC', ...options }).format(day(value));
  const shortDate = value => dateLabel(value, { year: undefined });
  const esc = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const labels = { daily: 'Daily', monthly: 'Monthly', annual: 'Annual' };
  let resolution = 'daily';
  let groups = [];
  let sourceIndex = 0;
  let csvUrl;
  let svgUrl;
  let imageSvg;
  let imageName;
  let hitRegions = [];
  let chartWidth = 1080;

  const firstYear = Number(history.first.slice(0, 4));
  const lastYear = Number(history.last.slice(0, 4));
  const currentYear = lastYear;
  for (let year = firstYear; year <= Math.max(lastYear, currentYear); year++) {
    from.add(new Option(year, year));
    to.add(new Option(year, year));
  }
  from.value = to.value = String(currentYear);
  const sections = {
    generation: ['wind', 'solar', 'otherROI', 'generation'],
    demand: ['demand'],
    interconnectors: ['eastWest', 'greenlink', 'northSouth']
  };
  const selectedSources = { generation: 'wind', demand: 'demand', interconnectors: 'eastWest' };
  let section = 'generation';

  function setSection(value) {
    section = value;
    source.replaceChildren();
    sections[value].forEach(key => {
      const series = history.series.find(item => item.key === key);
      const option = new Option(series.label, key);
      option.disabled = !series.days;
      source.append(option);
    });
    source.value = selectedSources[value];
    source.closest('label').hidden = value === 'demand';
    root.querySelectorAll('[data-trend-section]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.trendSection === value)));
  }
  setSection('generation');

  const averageBasis = () => resolution === 'daily' ? 'Daily averages' : `${labels[resolution]} means of daily averages`;

  function periodLabel(group) {
    if (resolution === 'annual') return group.key + (group.partialPeriod ? ' · part year' : '');
    if (resolution === 'monthly') return dateLabel(group.start, { day: undefined, month: 'long' });
    return dateLabel(group.start);
  }

  function niceStep(range) {
    const target = range / 4;
    const power = Math.pow(10, Math.floor(Math.log10(target || 1)));
    return ([1, 2, 2.5, 5, 10].find(value => value * power >= target) || 10) * power;
  }

  function chartMarkup(series, exportWidth = 0) {
    const interactive = !exportWidth;
    const W = exportWidth || Math.max(300, Math.round(chart.clientWidth || 1080)), H = W < 600 ? 310 : 370;
    if (interactive) chartWidth = W;
    const left = W < 600 ? 48 : 66, right = W < 600 ? 16 : 24, top = 24, bottom = 48;
    const width = W - left - right, height = H - top - bottom;
    const available = groups.filter(group => group.chartValues[sourceIndex] !== null);
    if (!available.length) {
      if (interactive) hitRegions = [];
      const tooSparse = groups.some(group => group.values[sourceIndex] !== null);
      return `<div class="trend-empty"><strong>${tooSparse ? 'Not enough complete days for this view' : 'No complete days in this range'}</strong><p>${tooSparse ? 'Monthly and annual points need at least 95% of elapsed days.' : series.first ? `Available readings: ${dateLabel(series.first)} to ${dateLabel(series.last)}.` : 'This source has no complete daily readings.'}</p>${tooSparse ? '<button class="text-button" id="trend-show-daily">Show daily averages ↗</button>' : series.first ? '<button class="text-button" id="trend-show-available">Show available years ↗</button>' : ''}</div>`;
    }
    const values = available.map(group => group.chartValues[sourceIndex]);
    const low = Math.min(0, ...values), high = Math.max(0, ...values);
    const step = niceStep(high - low || 10);
    const min = Math.floor(low / step) * step;
    let max = Math.ceil(high / step) * step;
    if (max === min) max = min + step;
    const span = max - min || 1;
    const x = i => groups.length === 1 ? left + width / 2 : left + i / (groups.length - 1) * width;
    const y = value => top + (max - value) / span * height;
    let markup = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-labelledby="trend-chart-title trend-chart-description"><title id="trend-chart-title">${esc(series.label)} · ${labels[resolution].toLowerCase()} average power in megawatts</title><desc id="trend-chart-description">${available.length} periods with readings. Missing periods are gaps. CSV download contains values and coverage counts.</desc>`;
    for (let value = min; value <= max + step / 100; value += step) {
      markup += `<line class="trend-grid${Math.abs(value) < .001 ? ' trend-zero' : ''}" x1="${left}" x2="${W - right}" y1="${y(value)}" y2="${y(value)}"/><text class="trend-axis" x="${left - 14}" y="${y(value) + 4}" text-anchor="end">${whole.format(value)}</text>`;
    }
    markup += `<text class="trend-axis trend-unit" x="${left - 14}" y="12" text-anchor="end">MW</text>`;
    let path = '', penDown = false;
    groups.forEach((group, i) => {
      const value = group.chartValues[sourceIndex];
      if (value === null) { penDown = false; return; }
      path += `${penDown ? 'L' : 'M'}${x(i).toFixed(2)},${y(value).toFixed(2)}`;
      penDown = true;
    });
    markup += `<path class="trend-line" d="${path}" style="stroke:${series.colour}"/>`;
    groups.forEach((group, i) => {
      const value = group.chartValues[sourceIndex];
      if (value === null) return;
      const isolated = (!groups[i - 1] || groups[i - 1].chartValues[sourceIndex] === null) && (!groups[i + 1] || groups[i + 1].chartValues[sourceIndex] === null);
      if (groups.length <= 36 || isolated) markup += `<circle cx="${x(i)}" cy="${y(value)}" r="3" fill="${series.colour}"/>`;
    });
    const tickIndexes = new Set([0, groups.length - 1]);
    const gap = Math.max(1, Math.ceil(groups.length / (W < 600 ? 3 : 6)));
    for (let i = gap; i < groups.length - Math.floor(gap / 2); i += gap) tickIndexes.add(i);
    [...tickIndexes].sort((a, b) => a - b).forEach(i => {
      const group = groups[i];
      let label = resolution === 'annual' ? group.key : resolution === 'monthly' ? dateLabel(group.start, { day: undefined, month: 'short' }) : shortDate(group.start);
      if (resolution !== 'daily' && group.partialPeriod) label += '*';
      if (resolution === 'daily' && from.value !== to.value) label += ` ${group.start.slice(0, 4)}`;
      markup += `<text class="trend-axis trend-date" x="${x(i)}" y="${H - 15}" text-anchor="${groups.length === 1 ? 'middle' : i === 0 ? 'start' : i === groups.length - 1 ? 'end' : 'middle'}">${esc(label)}</text>`;
    });
    if (!interactive) return markup + '</svg>';
    markup += `<line id="trend-cursor" class="trend-cursor" x1="0" x2="0" y1="${top}" y2="${H - bottom}" visibility="hidden"/><circle id="trend-cursor-dot" r="4.5" fill="${series.colour}" stroke="#fffdf8" stroke-width="2" visibility="hidden"/>`;
    // One transparent focusable target per available period also supports keyboard inspection.
    hitRegions = groups.map((group, i) => ({ x: x(i), y: group.chartValues[sourceIndex] === null ? null : y(group.chartValues[sourceIndex]) }));
    groups.forEach((group, i) => {
      const value = group.chartValues[sourceIndex];
      if (value === null) return;
      markup += `<circle class="trend-hit" data-period="${i}" cx="${x(i)}" cy="${y(value)}" r="8" tabindex="${i === groups.findIndex(g => g.chartValues[sourceIndex] !== null) ? '0' : '-1'}" role="img" aria-label="${esc(periodLabel(group))}: ${display.format(value)} megawatts; ${group.days[sourceIndex]} complete days"/>`;
    });
    return markup + '</svg>';
  }

  function exportImage(series, average) {
    const width = 1200, height = 710;
    const period = root.querySelector('#' + 'trend-period').textContent;
    const coverage = root.querySelector('#' + 'trend-coverage').textContent;
    const range = root.querySelector('#' + 'trend-date-range').textContent;
    const partial = resolution !== 'daily' && groups.some(group => group.partialPeriod) ? ' · * Partial calendar period' : '';
    const method = root.querySelector('#' + 'trend-method').textContent;
    // Export a self-contained chart at a consistent size, including fonts and attribution.
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(series.label)}: ${esc(averageBasis())}, ${esc(period)}">
      <style>text{font-family:Arial,Helvetica,sans-serif;fill:#182e32}.serif{font-family:Georgia,'Times New Roman',serif}.muted{fill:#5b686a}.trend-grid{stroke:#deded4;stroke-width:1;stroke-dasharray:2 4}.trend-zero{stroke:#a9b4aa;stroke-dasharray:none}.trend-axis{font:11px Arial,Helvetica,sans-serif;fill:#5b686a}.trend-unit{font-size:10px}.trend-line{fill:none;stroke-width:1.8;stroke-linejoin:round;stroke-linecap:round}</style>
      <rect width="${width}" height="${height}" fill="#faf6ef"/>
      <text class="serif" x="40" y="40" font-size="21">Salmon of Data<tspan fill="#ad3930">.</tspan></text><text x="1160" y="39" text-anchor="end" font-size="11" letter-spacing="1.5">REPUBLIC OF IRELAND ELECTRICITY · SAMPLE DATA</text>
      <line x1="40" x2="1160" y1="61" y2="61" stroke="#d9dbd0"/>
      <text class="serif" x="40" y="104" font-size="30">${esc(series.label)}</text><text class="serif" x="1160" y="102" text-anchor="end" font-size="25">${esc(period)}</text>
      <text class="serif" x="40" y="158" font-size="42">${display.format(average)}<tspan class="muted" font-family="Arial,Helvetica,sans-serif" font-size="13"> MW</tspan></text>
      <text class="muted" x="40" y="182" font-size="11">Daily average over the selected range${method ? ` · ${esc(method)}` : ''}</text>
      <text class="muted" x="1160" y="129" text-anchor="end" font-size="12">${esc(averageBasis())}</text>
      <svg x="40" y="205" width="1120" height="370" viewBox="0 0 1120 370">${chartMarkup(series, 1120).replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '')}</svg>
      <line x1="40" x2="1160" y1="599" y2="599" stroke="#d9dbd0"/>
      <text x="40" y="622" font-size="11">${esc(coverage)}</text><text class="muted" x="40" y="642" font-size="11">${esc(range + partial)}</text>
      <text class="muted" x="40" y="675" font-size="10">Supported by EirGrid Group Data · Daily average power</text><a href="https://www.smartgriddashboard.com/ie/open-data-license/"><text class="muted" x="40" y="693" font-size="9">EirGrid / SONI Open Data Licence; North-South is an NI balance estimate</text></a><text class="muted" x="1160" y="683" text-anchor="end" font-size="10">Average power · MW</text>
    </svg>`;
  }

  function prepareImage(series, average) {
    if (svgUrl) URL.revokeObjectURL(svgUrl);
    const hasChart = chart.querySelector('svg') !== null;
    pngDownload.disabled = !hasChart;
    svgDownload.hidden = !hasChart;
    downloadStatus.textContent = '';
    imageSvg = hasChart ? exportImage(series, average) : null;
    if (!imageSvg) { svgDownload.removeAttribute('href'); return; }
    svgUrl = URL.createObjectURL(new Blob([imageSvg], { type: 'image/svg+xml;charset=utf-8' }));
    imageName = `roi-electricity-${series.key}-${resolution}-${from.value}-${to.value}`;
    svgDownload.href = svgUrl;
    svgDownload.download = `${imageName}.svg`;
  }

  function showPeriod(index) {
    const group = groups[index];
    const point = hitRegions[index];
    if (!group || !point || point.y === null) return;
    const value = group.chartValues[sourceIndex];
    const cursor = root.querySelector('#' + 'trend-cursor');
    const dot = root.querySelector('#' + 'trend-cursor-dot');
    cursor.setAttribute('x1', point.x); cursor.setAttribute('x2', point.x); cursor.setAttribute('visibility', 'visible');
    dot.setAttribute('cx', point.x); dot.setAttribute('cy', point.y); dot.setAttribute('visibility', 'visible');
    tooltip.innerHTML = `<span>${esc(periodLabel(group))}</span><strong>${display.format(value)} <small>MW</small></strong><span>${group.days[sourceIndex]} of ${group.expectedDays} complete days${group.partialPeriod ? ' · partial period' : ''}</span>`;
    tooltip.hidden = false;
    tooltip.style.left = `${Math.max(12, Math.min(chart.clientWidth - 210, point.x / chartWidth * chart.clientWidth))}px`;
  }

  function hidePeriod() {
    tooltip.hidden = true;
    root.querySelector('#' + 'trend-cursor')?.setAttribute('visibility', 'hidden');
    root.querySelector('#' + 'trend-cursor-dot')?.setAttribute('visibility', 'hidden');
  }

  function render() {
    sourceIndex = history.series.findIndex(series => series.key === source.value);
    const series = history.series[sourceIndex];
    groups = model.aggregate(history, resolution, Number(from.value), Number(to.value));
    const acceptedDays = history.days.filter(row => row.date >= `${from.value}-01-01` && row.date <= `${to.value}-12-31` && row.v[sourceIndex] !== null);
    const average = acceptedDays.length ? acceptedDays.reduce((sum, row) => sum + row.v[sourceIndex], 0) / acceptedDays.length : null;
    const expected = groups.reduce((sum, group) => sum + group.expectedDays, 0);
    root.querySelector('#' + 'trend-series-title').textContent = series.label;
    root.querySelector('#' + 'trend-average').innerHTML = `${average === null ? '-' : display.format(average)} <small>MW</small>`;
    root.querySelector('#' + 'trend-method').textContent = series.method === 'estimated' ? 'Estimated · + import / − export' : ['eastWest', 'greenlink', 'northSouth'].includes(series.key) ? '+ import / − export' : '';
    root.querySelector('#' + 'trend-average-label').textContent = 'Daily average over the selected range';
    root.querySelector('#' + 'trend-period').textContent = from.value === to.value ? from.value : `${from.value}-${to.value}`;
    root.querySelector('#' + 'trend-resolution-label').textContent = averageBasis();
    root.querySelector('#' + 'trend-coverage').textContent = `${whole.format(acceptedDays.length)} of ${whole.format(expected)} complete days of public-source data`;
    root.querySelector('#' + 'trend-date-range').textContent = acceptedDays.length ? `${dateLabel(acceptedDays[0].date)} - ${dateLabel(acceptedDays[acceptedDays.length - 1].date)}` : 'No readings in this range';
    root.querySelector('#' + 'trend-partial-note').hidden = resolution === 'daily' || !groups.some(group => group.partialPeriod);
    chart.innerHTML = chartMarkup(series);
    chart.style.setProperty('--series-colour', series.colour);
    hidePeriod();
    if (csvUrl) URL.revokeObjectURL(csvUrl);
    csvUrl = URL.createObjectURL(new Blob([model.csv(history, groups, resolution)], { type: 'text/csv;charset=utf-8' }));
    download.href = csvUrl;
    download.download = `roi-electricity-${resolution}-${from.value}-${to.value}.csv`;
    prepareImage(series, average);
    const available = root.querySelector('#' + 'trend-show-available');
    available?.addEventListener('click', () => {
      from.value = series.first.slice(0, 4); to.value = series.last.slice(0, 4); render();
    });
    root.querySelector('#' + 'trend-show-daily')?.addEventListener('click', () => {
      resolution = 'daily';
      root.querySelectorAll('[data-resolution]').forEach(item => item.setAttribute('aria-pressed', String(item.dataset.resolution === 'daily')));
      render();
    });
  }

  source.addEventListener('change', () => { selectedSources[section] = source.value; render(); });
  root.querySelectorAll('[data-trend-section]').forEach(button => button.addEventListener('click', () => { setSection(button.dataset.trendSection); render(); }));
  pngDownload.addEventListener('click', async () => {
    if (!imageSvg) return;
    const svg = imageSvg, name = imageName;
    pngDownload.disabled = true;
    downloadStatus.textContent = 'Preparing image…';
    const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }));
    try {
      const image = new Image();
      await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; image.src = url; });
      const canvas = document.createElement('canvas');
      canvas.width = 2400; canvas.height = 1420;
      const context = canvas.getContext('2d');
      context.drawImage(image, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise((resolve, reject) => canvas.toBlob(value => value ? resolve(value) : reject(new Error('Image export failed')), 'image/png'));
      const pngUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = pngUrl; link.download = `${name}.png`; root.append(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(pngUrl), 60000);
      downloadStatus.textContent = 'Image ready · 2,400 × 1,420 px';
    } catch (error) {
      downloadStatus.textContent = 'PNG could not be created. Try the SVG download.';
    } finally {
      URL.revokeObjectURL(url);
      pngDownload.disabled = !imageSvg;
    }
  });
  from.addEventListener('change', () => { if (Number(from.value) > Number(to.value)) to.value = from.value; render(); });
  to.addEventListener('change', () => { if (Number(to.value) < Number(from.value)) from.value = to.value; render(); });
  root.querySelectorAll('[data-resolution]').forEach(button => {
    button.addEventListener('click', () => {
      resolution = button.dataset.resolution;
      root.querySelectorAll('[data-resolution]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      render();
    });
  });
  chart.addEventListener('pointermove', event => {
    const rect = chart.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width * chartWidth;
    let nearest = -1, distance = Infinity;
    hitRegions.forEach((point, i) => { if (point.y !== null && Math.abs(point.x - x) < distance) { nearest = i; distance = Math.abs(point.x - x); } });
    if (nearest >= 0 && distance < Math.max(18, (chartWidth - 90) / Math.max(1, groups.length - 1) / 2)) showPeriod(nearest);
    else hidePeriod();
  });
  chart.addEventListener('pointerleave', hidePeriod);
  chart.addEventListener('focusin', event => { if (event.target.dataset.period) showPeriod(Number(event.target.dataset.period)); });
  chart.addEventListener('focusout', hidePeriod);
  chart.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    const items = [...chart.querySelectorAll('[data-period]')];
    const current = items.indexOf(event.target);
    if (current < 0) return;
    event.preventDefault();
    const index = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : Math.max(0, Math.min(items.length - 1, current + (event.key === 'ArrowRight' ? 1 : -1)));
    event.target.tabIndex = -1; items[index].tabIndex = 0; items[index].focus();
  });

  function renderHistoryMetadata() {
  const coverageRows = history.series.map(series => `<tr><th scope="row">${esc(series.label)}</th><td>${series.first ? dateLabel(series.first) : '-'}</td></tr>`).join('');
  root.querySelector('#' + 'history-coverage-rows').innerHTML = coverageRows;
  }
  renderHistoryMetadata();
  events.addEventListener('dashboard:viewchange', event => { if (event.detail === 'trends') render(); }, { signal });
  events.addEventListener('dashboard:history', event => {
    history = displayedHistory(event.detail);
    // Extend the year selectors without changing the selected range or source.
    const selectedFrom = from.value, selectedTo = to.value;
    const years = new Set([...from.options].map(option => Number(option.value)));
    for (let year = Number(history.first.slice(0, 4)); year <= Number(history.last.slice(0, 4)); year++) {
      if (!years.has(year)) { from.add(new Option(year, year)); to.add(new Option(year, year)); }
    }
    from.value = selectedFrom; to.value = selectedTo;
    setSection(section);
    renderHistoryMetadata();
    render();
  }, { signal });
  window.addEventListener('resize', () => { if (!panel.hidden) render(); }, { signal });
  signal.addEventListener('abort', () => {
    if (csvUrl) URL.revokeObjectURL(csvUrl);
    if (svgUrl) URL.revokeObjectURL(svgUrl);
  }, { once: true });
  render();
}
