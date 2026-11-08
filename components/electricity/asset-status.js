import metadata from '../../electricity/asset-status.json' with {type:'json'};
import {interconnectorIcon} from './icons.js';
export const celtic=metadata.celtic;
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function applicableOutages(assetId, data) {
  const at=Date.parse(data.time);
  return metadata.outages.filter(item=>item.assetId===assetId&&at>=Date.parse(item.start)&&at<Date.parse(item.end)&&at>=Date.parse(item.publishedAt));
}
export function assetStatusMarkup(assetId, data, {compact=false}={}) {
  const notes=applicableOutages(assetId,data);
  if(!notes.length)return '';
  // Individual unit scope matters, e.g. TH4 pumping is not a station outage.
  const shown=compact?notes.slice(0,2):notes;
  return `<span class="asset-return-notes">${shown.map(item=>compact?`<span class="asset-return" title="${escape(item.reason)}. Published ${item.publishedAt.slice(0,10)}; dates are estimates. Open station for source.">${escape(item.display)}</span>`:`<a class="asset-return" href="${escape(item.source??item.sources[0])}" target="_blank" rel="noopener" title="${escape(item.reason)}. Published ${item.publishedAt.slice(0,10)}; dates are estimates.">${escape(item.display)} <span aria-hidden="true">↗</span></a>`).join('')}</span>`;
}
export function celticMarkup([x,y]) {
  return `<div class="interconnector moyle celtic planned-connector" data-interconnector="celtic" style="--card-x:${x/1240*100}%;--card-y:${y/1360*100}%" aria-label="Celtic Interconnector, under construction. ${celtic.capacityMW} megawatts capacity. ${celtic.display}."><div class="callout-heading"><span class="source-dot moyle-colour"></span><span class="interconnector-name">Celtic Interconnector</span></div><div class="flow-value">${celtic.capacityMW} <small>MW capacity</small>${interconnectorIcon()}</div><div class="flow-direction"><strong>Under construction</strong><span>ROI ↔ France</span></div><div class="capacity-track planned-capacity-track" aria-hidden="true"></div><div class="flow-capacity"><a href="${celtic.source}" target="_blank" rel="noopener">${celtic.display} <span aria-hidden="true">↗</span></a></div></div>`;
}
