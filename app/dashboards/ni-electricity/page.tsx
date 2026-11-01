import type { Metadata } from 'next';
import NIElectricityDashboard from '@/components/ni-electricity/dashboard';

export const metadata: Metadata = {
  title: 'Northern Ireland electricity',
  description: 'Explore Northern Ireland electricity demand, generation, wind, solar and interconnector flows, with a live map and historical time series from EirGrid, SONI and SEMO public data.',
};

export default function Page() {
  return <NIElectricityDashboard />;
}
