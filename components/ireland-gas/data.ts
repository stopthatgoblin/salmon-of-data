import type { GasSnapshot, GasCoverage } from './types';

const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
export function regionalCoverage(snapshot: GasSnapshot, region: 'ni' | 'roi'): GasCoverage | null {
  if (snapshot.electricityBasis.regional) return snapshot.electricityBasis.regional[region];
  const basis = snapshot.electricityBasis;
  return basis.meteredHours !== null && basis.dispatchEstimateHours !== null && basis.estimateFromUtc !== null
    ? {meteredHours:basis.meteredHours,dispatchEstimateHours:basis.dispatchEstimateHours,estimateFromUtc:basis.estimateFromUtc} : null;
}
export function coverageText(snapshot: GasSnapshot, region?: 'ni' | 'roi'): string {
  if (!region) return `NI: ${coverageText(snapshot,'ni')} ROI: ${coverageText(snapshot,'roi')}`;
  const basis=regionalCoverage(snapshot,region);
  return basis ? `${basis.meteredHours} hours metered per unit${basis.dispatchEstimateHours ? `; up to ${basis.dispatchEstimateHours} hours of dispatch estimates` : ''}.`
    : 'Electricity readings unavailable; reported gas is retained.';
}

export function validSnapshot(input: unknown, day: string, version: string): input is GasSnapshot {
  const value=input as GasSnapshot;
  if (![1,2,3].includes(value?.schema) || value.gasDay!==day || value.version!==version
      || !Array.isArray(value.hourly) || value.hourly.length>25
      || (value.hourly.length<23 && !(value.schema===3 && value.hourly.length===0 && value.sourceChecks?.pending?.some(item=>item.source==='GNI hourly flows')))
      || !value.reuse || !value.sources || !value.electricityBasis || !value.niGasBasis || !value.units?.ni || !value.units?.roi) return false;
  if (!['scotland','corrib','niAllocated','roiAllocated','snipPhysical','stranraer','southNorth'].every(key=>finite(value.flows?.[key as keyof typeof value.flows]))) return false;
  const hours=(Date.parse(value.toUtc)-Date.parse(value.fromUtc))/3600000;
  return (['ni','roi'] as const).every(region=>{
    const row=value.regions?.[region];
    if (!row || !finite(row.totalGas) || row.totalGas<=0) return false;
    if (value.schema===3 && row.powerGas===null) {
      if (region!=='ni' || row.otherGas!==null || row.powerShare!==null || row.electricity!==null) return false;
    } else if (![row.powerGas,row.otherGas,row.powerShare].every(finite) || row.powerGas!<0 || row.otherGas!<0) return false;
    if (!(value.schema===3 && row.electricity===null) && (!finite(row.electricity) || row.electricity<0)) return false;
    if (!(value.schema>=2 && row.demand===null) && (!finite(row.demand) || row.demand<=0)) return false;
    if (row.demand===null || row.electricity===null) {
      if (row.demandShare!==null) return false;
    } else if (!finite(row.demandShare)) return false;
    if (value.schema===3) {
      const basis=value.electricityBasis.regional?.[region];
      if (row.electricity===null) {
        if (basis!==null || value.units[region].length!==0 || !value.sourceChecks?.pending?.some(item=>item.region===region)) return false;
      } else if (!basis || !value.units[region].length || !finite(basis.meteredHours) || basis.meteredHours<=0
          || !finite(basis.dispatchEstimateHours) || basis.dispatchEstimateHours<0 || basis.dispatchEstimateHours>6
          || basis.meteredHours+basis.dispatchEstimateHours!==hours) return false;
    }
    return true;
  });
}
