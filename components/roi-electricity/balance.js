// One shared cross-border estimate, viewed from opposite jurisdictions.
// Preserve published ROI generation; put the signed reconciliation in Other.
export function reconcileSnapshot(snapshot) {
  const ni = snapshot.ni;
  for (const value of [snapshot.demand,snapshot.generation,snapshot.wind,snapshot.solar,ni?.demand,ni?.generation,ni?.moyle]) {
    if (!Number.isFinite(value)) throw new Error('Incomplete ROI/NI balance inputs');
  }
  if (ni.time !== snapshot.time) throw new Error('ROI and NI balance readings must have a common timestamp');
  const niNorthSouth = ni.demand - ni.generation - ni.moyle;
  const northSouth = -niNorthSouth;
  const interconnectors = snapshot.interconnectors.map(flow => {
    if (!Number.isFinite(flow.value)) throw new Error('Missing interconnector reading');
    return flow.id === 'northSouth' ? {...flow,value:northSouth,basis:'ni-balance-reversed'} : flow;
  });
  for (const id of ['eastWest','greenlink','northSouth']) {
    if (interconnectors.filter(flow => flow.id === id).length !== 1) throw new Error(`Missing or duplicate ${id} flow`);
  }
  if (snapshot.stations.some(station => station.output !== null && !Number.isFinite(station.output))) throw new Error('Invalid station estimate');
  const imports = interconnectors.reduce((sum,flow) => sum + flow.value,0);
  // Unknown station output stays unknown on its card and remains unallocated.
  const stationOutput = snapshot.stations.reduce((sum,station) => sum + (station.output ?? 0),0);
  const otherGeneration = snapshot.generation - snapshot.wind - snapshot.solar - stationOutput;
  const reconciliation = snapshot.demand - snapshot.generation - imports;
  return {...snapshot,interconnectors,imports,niNorthSouth,otherGeneration,reconciliation,other:otherGeneration+reconciliation,northSouthBasis:'ni-balance-reversed'};
}
