import type { Metadata } from 'next';
import GasLiveDashboard from '@/components/ireland-gas/live-dashboard';

export const metadata: Metadata = {
  title: 'All-Ireland gas',
  description: 'Daily gas supply and use across the island of Ireland.',
  alternates: { canonical: '/dashboards/ireland-gas/' },
  robots: { index: false, follow: false },
};

export default function Page() {
  return <GasLiveDashboard />;
}
