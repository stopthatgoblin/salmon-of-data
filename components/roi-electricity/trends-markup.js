export const trendsMarkup = /* html */ `    <section id="trends" role="tabpanel" aria-labelledby="tab-trends" hidden>
      <div id="trends-content">
        <div class="trend-section-bar"><div class="trend-sections" role="group" aria-label="Electricity section"><button data-trend-section="generation" aria-pressed="true">Generation</button><button data-trend-section="demand" aria-pressed="false">Demand</button><button data-trend-section="interconnectors" aria-pressed="false">Interconnectors</button></div><p>Daily average power <span>· MW</span></p></div>
        <div class="trend-controls">
          <label class="trend-source-control">Source<select id="trend-source" aria-label="Source"></select></label>
          <div class="trend-group-control"><span id="trend-group-label">View</span><div class="trend-group" role="group" aria-labelledby="trend-group-label"><button data-resolution="daily" aria-pressed="true">Daily</button><button data-resolution="monthly" aria-pressed="false">Monthly</button><button data-resolution="annual" aria-pressed="false">Annual</button></div></div>
          <label>From year<select id="trend-from" aria-label="From year"></select></label>
          <label>To year<select id="trend-to" aria-label="To year"></select></label>
        </div>
        <div class="trend-chart-heading"><div><h3 id="trend-series-title">Wind</h3><span id="trend-method" class="trend-method"></span><strong id="trend-average" class="trend-average">- <small>MW</small></strong><p id="trend-average-label">Daily average over the selected range</p></div><div class="trend-period"><strong id="trend-period"></strong><span id="trend-resolution-label">Daily averages</span></div></div>
        <div class="trend-chart-wrap"><div id="trend-chart" class="trend-chart"></div><div id="trend-tooltip" class="trend-tooltip" hidden></div></div>
        <div class="trend-chart-footer"><div><span id="trend-coverage"></span><span id="trend-date-range"></span><span id="trend-partial-note" hidden>* Partial calendar period</span><p class="chart-attribution">Supported by EirGrid Group Data · <a href="https://www.smartgriddashboard.com/ie/open-data-license/" target="_blank" rel="noopener">Open Data Licence ↗</a></p></div><button class="text-button" data-view="definitions" data-anchor="historical-data">About the historical data ↗</button></div>
        <section class="trend-downloads" aria-labelledby="trend-download-heading"><div><h3 id="trend-download-heading">Download</h3><p>Save this chart as an image, or download the data.</p></div><div class="trend-download-actions"><button id="trend-image-png" class="download-link" type="button">Image · PNG <span aria-hidden="true">↓</span></button><a id="trend-image-svg" class="download-link" href="#trends" download>Image · SVG <span aria-hidden="true">↓</span></a><a id="trend-download" class="download-link" href="#trends" download>Data · CSV <span aria-hidden="true">↓</span></a></div><p id="trend-download-status" class="trend-download-status" role="status" aria-live="polite"></p></section>
      </div>
      <div id="trends-unavailable" class="trend-empty" hidden>Historical data could not be loaded. Please try again shortly.</div>
    </section>

`;
