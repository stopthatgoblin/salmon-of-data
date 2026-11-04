import type { Metadata } from 'next';
import ROIElectricityDashboard from '@/components/roi-electricity/dashboard';
export const metadata: Metadata = {
  title: 'Republic of Ireland electricity',
  description: 'Explore Republic of Ireland electricity demand, generation, station estimates and East–West, Greenlink and North–South interconnector flows from EirGrid and SEMO public data.',
};
export default function Page() { return <ROIElectricityDashboard />; }
