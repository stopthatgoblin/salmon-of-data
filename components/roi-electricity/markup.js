import { trendsMarkup } from './trends-markup.js';
import { themeToggleMarkup } from '../electricity/theme.js';
import { replayMarkup } from '../electricity/replay.js';
import { celticMarkup } from '../electricity/asset-status.js';
import layout from '../../electricity/roi/layout.json' with {type:'json'};

export const dashboardMarkup = /* html */ `
  <h1 class="electricity-sr-only">Republic of Ireland electricity</h1>
  <div class="tabs">
    <div class="dashboard-tabs" role="tablist" aria-label="Dashboard views">
      <button id="tab-overview" role="tab" aria-selected="true" aria-controls="overview" tabindex="0">Overview</button>
      <button id="tab-trends" role="tab" aria-selected="false" aria-controls="trends" tabindex="-1">Trends</button>
      <button id="tab-definitions" role="tab" aria-selected="false" aria-controls="definitions" tabindex="-1">Definitions & sources</button>
    </div>
    <a class="dashboard-switch" href="/dashboards/ni-electricity/">Switch to NI <span aria-hidden="true">↗</span></a>
    ${themeToggleMarkup}
    <div class="snapshot-stamp"><span class="snapshot-label"><i></i> Checking for updates</span><time data-snapshot-time></time></div>
  </div>
  <p class="preview-note" hidden></p>
  <div class="metrics" aria-label="Electricity system summary, public-source readings">
    <div class="metric demand"><span>Electricity demand</span><strong data-reading="demand"></strong><p class="expected-peak" data-expected-peak="demand">Today's expected peak: unavailable</p></div>
    <div class="metric renewables"><span>ROI wind & solar</span><strong data-reading="renewables"></strong><p><b id="renewables-share"></b> of demand</p><p class="expected-peak" data-expected-peak="windSolar">Today's expected peak: unavailable</p></div>
    <div class="metric"><span>Generated in ROI</span><strong data-reading="generation"></strong><p><b data-share="generation"></b> of demand</p></div>
    <div class="metric"><span id="net-flow-label">Net imports</span><strong data-reading="imports"></strong><p id="net-flow-share"><b data-share="imports"></b> of demand</p></div>
  </div>
  <section id="overview" role="tabpanel" aria-labelledby="tab-overview">
    ${replayMarkup}
    <section class="map-section" aria-label="Map of electricity generation and imports">
      <div class="map-toolbar"><span>Select a power station to explore its units <span aria-hidden="true">↗</span></span></div>
      <div class="map-stage" id="map-stage">
        <svg id="electricity-map" viewBox="0 0 1240 1360" aria-label="Republic of Ireland power stations, with North-South, East-West and Greenlink interconnector flows" role="img">
          <defs>
            <clipPath id="map-clip"><rect width="1240" height="1180"/></clipPath>
            <marker id="import-arrow" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="9" markerHeight="9" orient="auto"><path d="M2 2 10 6 2 10" fill="none" stroke="#527d8b" stroke-width="1.5" stroke-linejoin="round"/></marker>
            <marker id="ns-arrow" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="9" markerHeight="9" orient="auto"><path d="M2 2 10 6 2 10" fill="none" stroke="#708b91" stroke-width="1.5" stroke-linejoin="round"/></marker>
            <symbol id="wind-icon" viewBox="0 0 32 32"><path d="M16 14v15m0-15-4-10c-1-3 2-4 3-1l3 9m-2 2 10-3c3-1 4 2 1 3l-10 2m-1-2-7 8c-2 2-4 0-2-2l7-8"/><circle cx="16" cy="14" r="2"/></symbol>
            <symbol id="solar-icon" viewBox="0 0 32 32"><circle cx="24" cy="7" r="4"/><path d="M24 0v1m0 12v1m7-7h-1M18 2l1 1m10 9-1-1M5 14h19l3 12H2zm2 0-1 12m13-12 2 12M4 20h21M14 26v4m-5 0h10"/></symbol>
            <symbol id="other-icon" viewBox="0 0 32 32"><path d="m16 3 12 7-12 7L4 10zm-12 14 12 7 12-7M4 24l12 7 12-7"/></symbol>
          </defs>
          <g clip-path="url(#map-clip)">
            <g id="land-context"></g><path id="roi-land" class="ni-land"/><path id="lakes" class="lakes"/>
            <text x="690" y="230" class="country-label" text-anchor="middle"><tspan x="690">NORTHERN</tspan><tspan x="690" dy="17">IRELAND</tspan></text>
            <text x="570" y="505" class="ni-label" text-anchor="middle"><tspan x="570">REPUBLIC OF</tspan><tspan x="570" dy="19">IRELAND</tspan></text>
            <text x="1150" y="894" class="country-label" text-anchor="middle">WALES</text>
            <text x="1110" y="90" class="country-label" text-anchor="middle">SCOTLAND</text>
            <text x="900" y="680" class="sea-label" text-anchor="middle" transform="rotate(-76 900 680)">Irish Sea</text>
            <text x="360" y="200" class="sea-label ocean-label" text-anchor="middle" transform="rotate(-20 360 200)">Atlantic Ocean</text>
            <g class="leaders" id="station-leaders"></g><g class="leaders connector-leaders" id="connector-leaders"></g>
            <g id="connector-flows"></g><g id="station-markers"></g>
            <g class="map-compass" transform="translate(280 1080)"><text x="0" y="0" text-anchor="middle">N</text><path d="M0 13v32m-5-25 5-7 5 7"/></g>
          </g>
        </svg>
        <div id="station-cards"></div><div id="connector-cards">${celticMarkup(layout.interconnectorCards.celtic)}</div>
        <div class="generation-label wind-label"><svg aria-hidden="true"><use href="#wind-icon"/></svg><span>Wind</span><strong data-reading="wind"></strong></div>
        <div class="generation-label other-label"><svg aria-hidden="true"><use href="#other-icon"/></svg><span>Other/<wbr>Unallocated</span><strong data-reading="other"></strong></div>
        <div class="generation-label solar-label"><svg aria-hidden="true"><use href="#solar-icon"/></svg><span>Solar</span><strong data-reading="solar"></strong></div>
      </div>
      <div class="map-footer">
        <div class="map-notes">
          <p class="chart-attribution">EirGrid actuals · SEMO dispatch-target estimates · <button class="text-button" data-view="definitions" data-anchor="data-sources">Sources ↗</button></p>
          <p class="map-methodology">Generated in ROI includes the signed reconciliation so domestic supply plus net imports equals demand.</p>
          <details class="balance-breakdown"><summary>Other/Unallocated breakdown</summary><dl><div><dt>Reported ROI generation</dt><dd data-reading="reportedGeneration"></dd></div><div><dt>Unallocated generation</dt><dd data-reading="otherGeneration"></dd></div><div><dt>Reconciliation to demand</dt><dd data-reading="reconciliation"></dd></div><div><dt>Other/Unallocated shown</dt><dd data-reading="other"></dd></div></dl></details>
          <p class="map-methodology">Positive interconnector values mean imports into ROI. Arrows show the corresponding direction; routes are schematic. Nearby station markers are slightly separated for legibility.</p>
        </div>
        <div class="map-footer-actions"><button class="text-button" data-view="definitions">How to read the numbers ↗</button><div class="chart-brand">SALMONOFDATA.COM</div></div>
      </div>
      <details class="electricity-connection"><summary>Data freshness & connection</summary><p id="refresh-health" role="status">Checking for updates…</p><button id="retry-live" class="text-button">Check again</button></details>
    </section>
  </section>
  ${trendsMarkup}
  <section id="definitions" role="tabpanel" aria-labelledby="tab-definitions" hidden>
    <div class="definitions-heading"><p class="eyebrow">Behind the numbers</p><h2>Understand <em>the numbers.</em></h2><p>What is measured, what is estimated, and what capacity really means.</p></div>
    <div class="definition-layout">
      <nav class="definition-nav" aria-label="Definitions contents"><a href="#metric-definitions">The metrics</a><a href="#estimates">Estimates & limitations</a><a href="#capacity">Understanding capacity</a><a href="#historical-data">Historical data</a><a href="#data-sources">Data & sources</a></nav>
      <div class="definition-content">
        <section id="metric-definitions"><h3>The metrics</h3><dl>
          <div><dt>Electricity demand</dt><dd>Power required by the ROI system, in megawatts (MW). Power is a reading at a point in time, rather than energy used over a day. Expected peaks use available published ROI forecasts; missing forecasts are omitted.</dd></div>
          <div><dt>Generated in ROI</dt><dd>Reported ROI generation plus the signed reconciliation to demand, excluding imports. This adjusted domestic-supply headline equals the map's domestic components, and together with signed net imports equals demand. The underlying reported generation and reconciliation are retained separately in the data and Other/Unallocated breakdown.</dd></div>
          <div><dt>Net interconnector flow</dt><dd>East-West, Greenlink and North-South flows combined. Positive means imports into ROI; negative means exports out of ROI. North-South uses the NI estimate with its sign reversed: −(NI demand − NI generation − Moyle imports). This makes the two views consistent. It does not establish either estimate as metered flow. Inputs share a common observation time and retain their source provenance.</dd></div>
          <div><dt>Wind & solar</dt><dd>Regional wind and solar totals, divided by demand for the headline share. These labels represent the whole Republic, rather than individual wind farms or solar parks. Other renewables, including hydro and biomass, remain in their station totals or Other/Unallocated.</dd></div>
          <div><dt>Power stations</dt><dd>Selected major generating stations at approximate site locations. Cards retain the NI dashboard's estimated output, available capacity bar and unit details. A flame indicates gas, a droplet oil, mountains pumped storage, waves hydro and a leaf biomass. Gas icons show the principal fuel; some plants also use distillate as a backup. Unit output is a last-published dispatch-target estimate, seeded from earlier meter data; unknown output remains unallocated.</dd></div>
          <div id="other-definition"><dt>Other/Unallocated</dt><dd>Unallocated generation plus a signed reconciliation. Unallocated generation = reported ROI generation − wind − solar − the station estimates shown. Reconciliation = ROI demand − reported ROI generation − net imports, using the shared NI-derived North-South estimate. Both terms remain signed. The reconciliation can reflect differences in storage accounting, source definitions, timing and measurement, so it is not identified as measured generation or assigned a fuel. The map components plus net imports sum to demand.</dd></div>
        </dl></section>
        <section id="estimates"><h3>Estimates & limitations</h3><p>Grid readings are reported actuals. Station outputs and North-South are estimates; dispatch publications can lag the grid readings. A carried-forward target is not a live meter measurement. Unknown outputs remain unallocated. History uses complete daily averages from public sources.</p><p><strong>North-South estimation:</strong> the NI dashboard uses NI demand − NI generation − signed Moyle imports, positive into NI. The analogous ROI residual is ROI demand − ROI generation − signed East-West imports − signed Greenlink imports, positive into ROI. This is the same balancing approach, using different inputs; it is not necessarily an equal-and-opposite reading.</p><p>A check of 96 matching quarter-hours on 3 November 2026 found a median absolute difference of 56.5 MW between the ROI residual and the sign-reversed NI residual, with a maximum difference of 373 MW. At the source timestamp 23:45, the ROI equation gave −242 MW; the sign-reversed NI equation gave +1 MW. These are calculated residuals, not direct tie-line measurements.</p><p>The discrepancy also appears in the all-island demand/generation/interconnector balance. It cannot be attributed just to the cross-border line. Pumping, battery charging/discharging, source definitions and measurement timing need reconciliation. EirGrid's <a href="https://cms.eirgrid.ie/sites/default/files/publications/SNSP_Calculation_Update_V1.0_EirGrid.pdf" target="_blank" rel="noopener">operational calculation notes</a> explicitly distinguish pump demand and battery flows, but do not establish the cause of every discrepancy in this check. This dashboard uses the NI-derived estimate with its sign reversed for ROI. The remaining signed demand reconciliation is included in Other/Unallocated and disclosed separately in its breakdown. The underlying reported ROI generation is retained in the dataset; the headline includes the signed reconciliation. This is a presentation and consistency choice; neither residual has been validated as metered flow.</p><p>The map shows a selected set of major stations, not a complete asset register. Station dots use approximate latitude and longitude. Leader lines connect displaced cards to their sites; nearby Cork Harbour and Dublin Bay stations are individually identified. Wind, solar and Other/Unallocated are regional labels.</p><p>East-West is shown between north County Dublin and north Wales; Greenlink between south County Wexford and Pembrokeshire. North-South crosses the Louth-Armagh border. The dashed Celtic route marks a future connection from Claycastle near Youghal toward Brittany and is excluded from all flows. These lines show geography and flow direction schematically, not exact cable or overhead-line routes. Celtic is shown separately as a planned project, with its current published programme and no operating flow.</p><p>North Wall TEG, Shannonbridge TEG, Huntstown TEG and Tarbert TEG are included. Poolbeg, Ringsend and Corduff Flexgen are also mapped. Moneypoint uses the current registered oil-fired units. Aughinish Alumina includes SK3 and SK4. Tarbert TEG is the existing temporary emergency plant; the retired oil station and future HVO project are excluded. Smaller plants, other temporary generation, batteries and unmatched generation remain in Other/Unallocated.</p></section>
        <section id="capacity"><h3>Understanding capacity</h3><p><strong>Available capacity</strong> is the denominator in each station bar. It comes from published SEMO availability declarations. The percentage is output divided by availability; a zero output does not establish an outage.</p><p><strong>Technical maximum</strong> in the unit drawer comes from the latest available SEMO technical offer report for the selected registered units. Published gross, net and export capacities can differ.</p><p>East-West and Greenlink each use a <strong>500 MW rated capacity</strong>. North-South uses a <strong>300 MW reference</strong>, following the NI prototype. These are fixed capacity references rather than real-time operating limits. Import and export limits may differ.</p></section>
        <section id="historical-data"><h3>Historical data</h3><p><strong>Time machine:</strong> choose an archived date and time from Overview. Older station readings are metered half-hour averages; recent captured readings retain their dispatch-estimate label. Grid inputs are 15-minute observations, and only times with every mapped station are selectable. Missing capacity is shown as unavailable. Negative pumped-storage output means pumping. Clock-change hours retain their UTC offsets. Return to live restores the latest accepted data.</p><p>Trends uses real EirGrid daily averages. A day is accepted only with all 96 source-labelled quarter-hours; missing values remain gaps and the unfinished current day is excluded. Monthly and annual charts require at least 95% of elapsed days. CSV downloads retain coverage counts and signed flows.</p><p>Non-wind/solar generation is reported ROI generation minus wind and solar, distinct from the overview's Other/Unallocated reconciliation. Historical North-South is the sign-reversed accepted NI daily balance estimate over the same complete quarter-hours. Earlier missing solar or interconnector readings are not assumed to be zero.</p><div class="history-table-wrap"><table class="history-coverage"><caption>First complete day by series</caption><thead><tr><th scope="col">Series</th><th scope="col">First complete day</th></tr></thead><tbody id="history-coverage-rows"></tbody></table></div><p>History is collected daily at 07:00 Europe/London. Complete accepted days are retained if a later source refresh is partial; the downloaded JSON records retained dates and their previous source edition.</p></section>
        <section id="data-sources"><h3>Data & sources</h3><p>The overview uses public EirGrid actuals and SEMO unit reports. Grid inputs share one observation time. Snapshot data retains source URLs, report filenames and the accepted NI version used for North-South.</p>
          <ul class="source-list">
            <li><a href="https://www.smartgriddashboard.com/" target="_blank" rel="noopener">EirGrid Smart Grid Dashboard <span>↗</span></a><small>Future ROI demand, generation, wind, solar and interconnection data; no live feed is connected here.</small></li>
            <li><a href="https://www.eirgrid.ie/grid/how-grid-works/how-does-electricity-work" target="_blank" rel="noopener">EirGrid: how electricity works <span>↗</span></a><small>East-West and Greenlink geography; Moyle belongs to the NI system.</small></li>
            <li><a href="https://greenlink.ie/" target="_blank" rel="noopener">Greenlink Interconnector <span>↗</span></a><small>500 MW link between County Wexford and Pembrokeshire.</small></li>
            <li><a href="https://www.eirgrid.ie/east-west-interconnector" target="_blank" rel="noopener">EirGrid: East-West Interconnector <span>↗</span></a><small>500 MW connection between Ireland and Wales.</small></li>
            <li><a href="https://cms.eirgrid.ie/sites/default/files/publications/AIRAA-2026-2035_Inputs-and-Assumptions-Ireland.pdf" target="_blank" rel="noopener">EirGrid: resource adequacy inputs and assumptions <span>↗</span></a><small>Interconnection reference capacities; not current operating limits.</small></li>
            <li><a href="https://esb.ie/what-we-do/generation-and-trading" target="_blank" rel="noopener">ESB generation portfolio <span>↗</span></a><small>Aghada, Moneypoint, Poolbeg, Dublin Bay, Ardnacrusha and Turlough Hill.</small></li>
            <li><a href="https://www.energiagroup.com/" target="_blank" rel="noopener">Energia Group <span>↗</span></a><small>Huntstown generation.</small></li>
            <li><a href="https://www.ssethermal.com/flexible-generation/operational/great-island/" target="_blank" rel="noopener">SSE: Great Island <span>↗</span></a><small>464 MW station on Waterford Harbour, County Wexford.</small></li>
            <li><a href="https://www.bordgaisenergy.ie/company/about-us" target="_blank" rel="noopener">Bord Gáis Energy: Whitegate <span>↗</span></a><small>445 MW station in Cork Harbour.</small></li>
            <li><a href="https://www.epuki.co.uk/about/our-power-stations/tynagh/" target="_blank" rel="noopener">EP UK Investments: Tynagh <span>↗</span></a><small>384 MW combined-cycle station in County Galway.</small></li>
            <li><a href="https://www.edenderrypower.ie/" target="_blank" rel="noopener">Edenderry Power <span>↗</span></a><small>Biomass generation in County Offaly.</small></li>
            <li><a href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noopener">Natural Earth <span>↗</span></a><small>Public-domain outlines reused from the NI dashboard. Lough Neagh outline: DAERA/NIEA, Open Government Licence v3.0.</small></li>
          </ul><p class="attribution">Independent dashboard by Salmon of Data. Not an official system-operator dashboard.</p>
        </section>
      </div>
    </div>
  </section>
  <nav class="electricity-bottom-nav" aria-label="Dashboard navigation"><a href="/#dashboards">← All dashboards</a></nav>
  <dialog id="station-dialog" aria-labelledby="station-title"><div class="dialog-inner"><div class="dialog-top"><p class="eyebrow">Power station · unit detail</p><button class="close-dialog" aria-label="Close unit details">×</button></div><nav id="station-switcher" aria-label="Choose power station"></nav><div id="station-detail"></div><p class="chart-attribution">SEMO dispatch-target estimates · Published availability and technical declarations</p><div class="dialog-footer"><span>Snapshot · <span data-snapshot-short></span></span><button class="text-button" data-view="definitions">Definitions & sources ↗</button></div></div></dialog>
`;
