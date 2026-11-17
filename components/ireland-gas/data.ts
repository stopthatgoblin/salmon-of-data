import type { GasSnapshot } from './types';

export function validSnapshot(input: unknown, day: string, version: string): input is GasSnapshot {
  const value = input as GasSnapshot;
  if (![1, 2].includes(value?.schema) || value.gasDay !== day || value.version !== version || !Array.isArray(value.hourly) || value.hourly.length < 23 || value.hourly.length > 25) return false;
  return (['ni', 'roi'] as const).every(region => {
    const row = value.regions?.[region];
    if (!row || !['totalGas', 'powerGas', 'otherGas', 'electricity', 'powerShare'].every(key => Number.isFinite(row[key as keyof typeof row]))) return false;
    if (value.schema === 2 && row.demand === null) return row.demandShare === null;
    return Number.isFinite(row.demand) && row.demand! > 0 && Number.isFinite(row.demandShare);
  }) && ['scotland', 'corrib', 'niAllocated', 'roiAllocated', 'snipPhysical', 'stranraer', 'southNorth'].every(key => Number.isFinite(value.flows?.[key as keyof typeof value.flows]))
    && !!value.reuse && !!value.sources && !!value.electricityBasis && !!value.niGasBasis && !!value.units?.ni && !!value.units?.roi;
}
