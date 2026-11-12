import type { Metadata } from 'next';
import GasLiveDashboard from '@/components/ireland-gas/live-dashboard';

export const metadata: Metadata = {
  title: 'All-Ireland gas',
  description: 'Where it came from, what it powered. Daily gas supply, electricity generation and other gas use across Ireland, with a growing historical archive.',
  alternates: { canonical: '/dashboards/ireland-gas/' },
};

export default function Page() {
  return <GasLiveDashboard />;
}
