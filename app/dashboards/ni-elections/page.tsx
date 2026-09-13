import type { Metadata } from 'next';
import NIElectionsDashboard from '@/components/ni-elections/dashboard';
export const metadata: Metadata = { title: 'Northern Ireland elections', description: 'Explore historical Northern Ireland election results by party, community, election type, votes and vote share.' };
export default function Page() { return <NIElectionsDashboard/>; }
