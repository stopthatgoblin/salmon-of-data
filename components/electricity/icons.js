// Small, code-native line icons matching the existing wind/solar illustrations.
export const generationTypes = {
  gas: {label:'Gas',path:'<path d="M12 3c.6 4.2-4.9 5.7-4.9 9.4 0 1.4.7 2.5 1.6 3.2-.1-2.6 2.2-3.7 3.2-5.4.1 2 3.1 3.5 3.1 6.1 1.3-1 2-2.4 2-4.1 0-2.9-1.7-5.7-5-9.2Z"/><path d="M7 10.6c-2 2-2.7 3.7-2.3 5.6a7.4 7.4 0 0 0 14.5-2.5c-.2-1.8-1.1-3.5-2.6-4.9"/>'},
  oil: {label:'Oil',path:'<path d="M12 3c-1.3 3-6.5 7.8-6.5 11.4a6.5 6.5 0 0 0 13 0C18.5 10.8 13.3 6 12 3Z"/><path d="M8.6 14.2a3.6 3.6 0 0 0 3.6 3.7"/>'},
  pumped: {label:'Pumped storage',path:'<path d="m2.5 16 6-11 5 9m-4.8-6.9 1.8 2 1.2-1.3M12 14l4.1-7 5.4 9M2.5 20c2-1.4 3.6 1.4 5.6 0s3.6 1.4 5.6 0 3.6 1.4 5.6 0M14.5 12l1.6 1.4 1.5-1.4"/>'},
  hydro: {label:'Hydro',path:'<path d="M2.5 10c2.4 0 2.4-2 4.8-2s2.4 2 4.8 2 2.4-2 4.8-2 2.4 2 4.6 2M2.5 15c2.4 0 2.4-2 4.8-2s2.4 2 4.8 2 2.4-2 4.8-2 2.4 2 4.6 2M2.5 20c2.4 0 2.4-2 4.8-2s2.4 2 4.8 2 2.4-2 4.8-2 2.4 2 4.6 2"/>'},
  biomass: {label:'Biomass',path:'<path d="M19.5 3.5C10 3.5 4.5 7 4.5 12a6.6 6.6 0 0 0 6.6 6.6c5.8 0 8.4-6.2 8.4-15.1Z"/><path d="M4 21 15 10m-5 5-.4-4.1M12 13l4.2-.1"/>'},
};

export function generationIcon(type) {
  const item = generationTypes[type];
  if (!item) throw new Error(`Unknown generation type: ${type}`);
  return `<span class="station-type-icon ${type}" title="${item.label}" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false">${item.path}</svg></span>`;
}

export function interconnectorIcon() {
  return '<span class="station-type-icon interconnector-icon" title="Interconnector" aria-hidden="true"><svg viewBox="0 0 24 24" focusable="false"><path d="m12 2-5 20m5-20 5 20M5 7h14M3 12h18M9.5 7l5 5m-5 0 6 7M14.5 7l-5 5m5 0-6 7M6 22h12M5 7v3m14-3v3M3 12v3m18-3v3"/></svg></span>';
}
