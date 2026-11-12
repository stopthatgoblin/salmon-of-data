export type GasRegion = {
  totalGas: number; powerGas: number; otherGas: number; electricity: number;
  demand: number; demandShare: number; powerShare: number;
};

export type GasSnapshot = {
  schema: number;
  gasDay: string;
  fromUtc: string;
  toUtc: string;
  snapshotAsOf: string;
  capturedAt?: string;
  version: string;
  flows: {
    scotland: number; corrib: number; niAllocated: number; roiAllocated: number;
    snipPhysical: number; stranraer: number; southNorth: number;
  };
  regions: { ni: GasRegion; roi: GasRegion };
  hourly: { time: string; scotland: number; corrib: number }[];
  units: {
    ni: { id: string; name: string; electricityGwh: number; gasGwh: number; starts: { time: string; gjLhv: number }[] }[];
    roi: { id: string; name: string | null; electricityGwh: number }[];
  };
  electricityBasis: { meteredHours: number; dispatchEstimateHours: number; estimateFromUtc: string; description: string };
  niGasBasis: { grossNetFactor: number; modelVersion?: string; description: string };
  sources: Record<string, string>;
  reuse: { entsogExtractionDate: string; entsogTerms: string; gniPolicy: string; electricityLicence: string; gniOperationalApiLicenceCoverageConfirmed?: boolean };
};
