export type GasRegion = {
  totalGas: number; powerGas: number | null; otherGas: number | null; electricity: number | null;
  demand: number | null; demandShare: number | null; powerShare: number | null;
};

export type GasCoverage = { meteredHours: number; dispatchEstimateHours: number; estimateFromUtc: string };
export type GasManifest = {
  schema: number; days: { date: string; version: string; collectedAt: string; meteredHours: number | null; estimatedHours: number | null }[];
  latest: string; lastAttempt: string; lastSuccess: string | null; lastError: string | null;
  lastChecked?: string; lastDataChange?: string | null; lastComplete?: string | null;
  targetGasDay?: string; targetComplete?: boolean; outcome?: string; pending?: boolean;
  waitingForSource?: { source: string; gasDay: string; reason?: string } | null;
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
  electricityBasis: { meteredHours: number | null; dispatchEstimateHours: number | null; estimateFromUtc: string | null; description: string;
    regional?: { ni: GasCoverage | null; roi: GasCoverage | null } };
  niGasBasis: { grossNetFactor: number; modelVersion?: string; unitCount?: number; description: string };
  sourceChecks?: { pending?: { source: string; gasDay: string; region?: string; reason?: string }[] };
  sources: Record<string, string>;
  reuse: { entsogExtractionDate: string; entsogTerms: string; gniPolicy: string; electricityLicence: string; gniOperationalApiLicenceCoverageConfirmed?: boolean };
};
