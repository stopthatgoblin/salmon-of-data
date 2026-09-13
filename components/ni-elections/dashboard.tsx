'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import {
    NIElectionPartyRecord,
    NIElectionCategoryRecord,
    NIPartyColors,
    NICommunityColors
} from '@/types/ni-elections';
import { ChartDownload } from '@/components/chart-download';
import NIElectionsChart from '@/components/ni-elections/NIElectionsChart';

const ELECTION_TYPES = [
    "Assembly",
    "Westminster",
    "Local",
    "European",
    "Constitutional Convention",
    "Forum"
];

const DEFAULT_PARTIES = ["UUP", "DUP", "SDLP", "Sinn Féin", "Alliance", "TUV"];

export default function NIElectionsDashboard() {
    const chartRef = useRef<HTMLDivElement>(null);
    // Data State
    const [partyData, setPartyData] = useState<NIElectionPartyRecord[]>([]);
    const [categoryData, setCategoryData] = useState<NIElectionCategoryRecord[]>([]);
    const [partyColors, setPartyColors] = useState<NIPartyColors>({});
    const [communityColors, setCommunityColors] = useState<NICommunityColors | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(false);

    // Control State
    const [metric, setMetric] = useState<'share' | 'votes'>('share');
    const [viewBy, setViewBy] = useState<'party' | 'designation'>('party');
    const [selectedParties, setSelectedParties] = useState<string[]>(DEFAULT_PARTIES);
    const [selectedTypes, setSelectedTypes] = useState<string[]>(ELECTION_TYPES);
    const [excludeUncontested, setExcludeUncontested] = useState(true);
    const [partySearch, setPartySearch] = useState('');
    const [startYear, setStartYear] = useState<number>(1921);

    // Load Data
    useEffect(() => {
        async function loadData() {
            try {
                const [pRes, cRes, pcRes, ccRes] = await Promise.all([
                    fetch('/data/ni-elections/ni_elections_parties.json'),
                    fetch('/data/ni-elections/ni_elections_categories.json'),
                    fetch('/data/ni-elections/ni_elections_party_colours.json'),
                    fetch('/data/ni-elections/ni_elections_community_colours.json')
                ]);

                if (!pRes.ok || !cRes.ok || !pcRes.ok || !ccRes.ok) throw new Error('Failed to load data');

                const pData = await pRes.json() as NIElectionPartyRecord[];
                const cData = await cRes.json() as NIElectionCategoryRecord[];
                const pcData = await pcRes.json() as NIPartyColors;
                const ccData = await ccRes.json() as NICommunityColors;

                setPartyData(pData);
                setCategoryData(cData);
                // Merge TUV color
                setPartyColors({ ...pcData, "TUV": "#34e8eb" });
                // Lighten Unionist color
                setCommunityColors({ ...ccData, "Unionist": "#4ea7f5" }); // Using a lighter blue
            } catch (err) {
                console.error(err);
                setError(true);
            } finally {
                setLoading(false);
            }
        }
        loadData();
    }, []);

    // Get available years
    const availableYears = useMemo(() => {
        if (partyData.length === 0) return [1921];
        const years = Array.from(new Set(partyData.map(d => d.Year))).sort((a, b) => a - b);
        return years;
    }, [partyData]);

    // Derived Data for Chart
    const chartData = useMemo(() => {
        if (loading) return [];

        let rawData: any[] = viewBy === 'party' ? partyData : categoryData;

        // Filter by Start Year
        rawData = rawData.filter(d => d.Year >= startYear);

        // Filter by Type
        rawData = rawData.filter(d => selectedTypes.includes(d.Type));

        // Filter by Contested
        if (excludeUncontested) {
            rawData = rawData.filter(d => d.Contested === 1);
        }

        // Filter by Selected Parties (if viewBy party)
        if (viewBy === 'party') {
            rawData = rawData.filter(d => selectedParties.includes(d.Party));
        }

        // Group by Year and Election for Recharts
        const grouped = new Map<string, any>();

        rawData.forEach(record => {
            const key = `${record.Year}-${record.Election}`;
            if (!grouped.has(key)) {
                grouped.set(key, {
                    Year: record.Year,
                    Election: record.Election,
                    Type: record.Type
                });
            }
            const entry = grouped.get(key);
            const seriesKey = viewBy === 'party' ? record.Party : record.Category;
            const value = metric === 'share' ? record.VoteShare : record.Votes;
            entry[seriesKey] = value;
        });

        return Array.from(grouped.values()).sort((a, b) => a.Year - b.Year);

    }, [loading, viewBy, partyData, categoryData, selectedTypes, excludeUncontested, selectedParties, metric, startYear]);

    // Available Parties for Search
    const availableParties = useMemo(() => {
        const allParties = Array.from(new Set(partyData.map(d => d.Party))).sort();
        return allParties.filter(p => !selectedParties.includes(p));
    }, [partyData, selectedParties]);

    const filteredAvailableParties = useMemo(() => {
        if (!partySearch) return [];
        return availableParties.filter(p => p.toLowerCase().includes(partySearch.toLowerCase()));
    }, [availableParties, partySearch]);

    // Colors for Chart
    const currentColors = useMemo(() => {
        if (viewBy === 'party') return partyColors;
        return communityColors || {};
    }, [viewBy, partyColors, communityColors]);

    // Series Keys
    const currentSeries = useMemo(() => {
        if (viewBy === 'party') return selectedParties;
        return ["Unionist", "Nationalist", "Other"];
    }, [viewBy, selectedParties]);

    // Download Handlers
    const handleDownloadCSV = () => {
        if (!chartData.length) return;

        const headers = ['Year', 'Election', 'Type', ...currentSeries];
        const csvContent = [
            headers.join(','),
            ...chartData.map(row => {
                return headers.map(header => {
                    if (header === 'Year' || header === 'Election' || header === 'Type') return row[header];
                    return row[header] || 0;
                }).join(',');
            })
        ].join('\n');

        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', 'ni_elections_data.csv');
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-salmon border-t-transparent rounded-full animate-spin"></div>
            </div>
        );
    }

    if (error) return <main className="wrap not-found"><h1>Election data could not be loaded</h1><p>Please reload the page to try again.</p></main>;

    return (
        <main className="wrap ni-dashboard">
            <header className="tracker-heading"><div><a className="back-link" href="/#dashboards">← All dashboards</a><p className="eyebrow">Politics & society · Northern Ireland</p>
                <h1 className="font-serif text-3xl md:text-4xl lg:text-5xl font-medium text-[#1B1C1E] mb-2 tracking-tight">
                    Northern Ireland elections by vote and vote share
                </h1>
                <p className="text-lg text-gray-600 font-light max-w-3xl">
                    Historical voting data for all Northern Ireland-wide elections from 1921 to 2024.
                </p>
            </div></header>

            <div className="ni-layout">
                {/* Controls */}
                <div className="ni-controls space-y-3">
                    {/* Start Year */}
                    <div className="bg-[var(--muted)] p-4 rounded-sm border border-[var(--border)]">
                        <h3 className="font-bold text-xs uppercase tracking-widest text-gray-500 mb-2">Start Year</h3>
                        <select
                            aria-label="Start year"
                            value={startYear}
                            onChange={(e) => setStartYear(Number(e.target.value))}
                            className="w-full p-2 text-sm border border-[var(--border)] rounded-sm focus:outline-none focus:border-salmon bg-[var(--paper)]"
                        >
                            {availableYears.map(year => (
                                <option key={year} value={year}>{year}</option>
                            ))}
                        </select>
                    </div>

                    {/* Metric */}
                    <div className="bg-[var(--muted)] p-4 rounded-sm border border-[var(--border)]">
                        <h3 className="font-bold text-xs uppercase tracking-widest text-gray-500 mb-2">Metric</h3>
                        <div className="flex flex-col gap-2">
                            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                                <input
                                    type="radio"
                                    name="metric"
                                    checked={metric === 'share'}
                                    onChange={() => setMetric('share')}
                                    className="text-[var(--teal)] focus:ring-salmon"
                                />
                                Vote share (%)
                            </label>
                            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                                <input
                                    type="radio"
                                    name="metric"
                                    checked={metric === 'votes'}
                                    onChange={() => setMetric('votes')}
                                    className="text-[var(--teal)] focus:ring-salmon"
                                />
                                Total votes
                            </label>
                        </div>
                    </div>

                    {/* View By */}
                    <div className="bg-[var(--muted)] p-4 rounded-sm border border-[var(--border)]">
                        <h3 className="font-bold text-xs uppercase tracking-widest text-gray-500 mb-2">View by</h3>
                        <div className="flex rounded-sm border border-[var(--border)] overflow-hidden">
                            <button
                                aria-pressed={viewBy === 'party'}
                                onClick={() => setViewBy('party')}
                                className={`flex-1 py-2 text-sm font-medium transition-colors ${viewBy === 'party' ? 'bg-[var(--teal)] text-white' : 'bg-[var(--paper)] text-gray-600 hover:bg-[var(--muted)]'}`}
                            >
                                Party
                            </button>
                            <button
                                aria-pressed={viewBy === 'designation'}
                                onClick={() => setViewBy('designation')}
                                className={`flex-1 py-2 text-sm font-medium transition-colors ${viewBy === 'designation' ? 'bg-[var(--teal)] text-white' : 'bg-[var(--paper)] text-gray-600 hover:bg-[var(--muted)]'}`}
                            >
                                Community
                            </button>
                        </div>

                        {/* Party Selector */}
                        {viewBy === 'party' && (
                            <div className="mt-4">
                                <div className="mb-3">
                                    <label className="block text-xs font-medium text-gray-500 mb-1">Selected Parties</label>
                                    <div className="flex flex-wrap gap-2">
                                        {selectedParties.map(p => (
                                            <span key={p} className="inline-flex items-center px-2 py-1 rounded-sm text-xs font-medium bg-[var(--paper)] border border-[var(--border)] text-gray-700">
                                                <span className="w-2 h-2 rounded-full mr-1.5" style={{ backgroundColor: partyColors[p] || '#9ca3af' }}></span>
                                                {p}
                                                <button
                                                    aria-label={`Remove ${p}`}
                                                    onClick={() => setSelectedParties(prev => prev.filter(x => x !== p))}
                                                    className="ml-1.5 text-gray-400 hover:text-red-500"
                                                >
                                                    ×
                                                </button>
                                            </span>
                                        ))}
                                    </div>
                                </div>
                                <div className="relative">
                                    <input
                                        type="text"
                                        aria-label="Add a party"
                                        placeholder="Add a party..."
                                        value={partySearch}
                                        onChange={(e) => setPartySearch(e.target.value)}
                                        className="w-full px-3 py-2 text-sm border border-[var(--border)] rounded-sm focus:outline-none focus:border-salmon"
                                    />
                                    {partySearch && filteredAvailableParties.length > 0 && (
                                        <div className="absolute z-10 w-full mt-1 max-h-48 overflow-y-auto bg-[var(--paper)] border border-[var(--border)] rounded-sm shadow-lg">
                                            {filteredAvailableParties.map(p => (
                                                <button
                                                    key={p}
                                                    onClick={() => {
                                                        setSelectedParties(prev => [...prev, p]);
                                                        setPartySearch('');
                                                    }}
                                                    className="w-full text-left px-3 py-2 text-sm hover:bg-[var(--muted)] text-gray-700"
                                                >
                                                    {p}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Election Type */}
                    <div className="bg-[var(--muted)] p-4 rounded-sm border border-[var(--border)]">
                        <h3 className="font-bold text-xs uppercase tracking-widest text-gray-500 mb-2">Election Type</h3>
                        <div className="space-y-2">
                            {ELECTION_TYPES.map(type => (
                                <label key={type} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={selectedTypes.includes(type)}
                                        onChange={(e) => {
                                            if (e.target.checked) {
                                                setSelectedTypes(prev => [...prev, type]);
                                            } else {
                                                setSelectedTypes(prev => prev.filter(t => t !== type));
                                            }
                                        }}
                                        className="rounded-sm text-[var(--teal)] focus:ring-salmon border-gray-300"
                                    />
                                    {type}
                                </label>
                            ))}
                        </div>
                    </div>

                    {/* Exclude Uncontested */}
                    <div className="bg-[var(--muted)] p-4 rounded-sm border border-[var(--border)]">
                        <label className="flex items-start gap-2 text-sm text-gray-700 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={excludeUncontested}
                                onChange={(e) => setExcludeUncontested(e.target.checked)}
                                className="mt-1 rounded-sm text-[var(--teal)] focus:ring-salmon border-gray-300"
                            />
                            <span>Exclude partially uncontested elections</span>
                        </label>
                    </div>
                </div>

                {/* Chart Area */}
                <div className="ni-results">
                    <div ref={chartRef} className="bg-[var(--paper)] p-4 rounded-sm">
                        <h2 className="chart-title">
                            {metric === 'share' ? 'Vote share at Northern Ireland elections' : 'Votes received at Northern Ireland elections'}
                        </h2>

                        <p className="chart-subtitle">{startYear}–2024 · {viewBy === 'party' ? 'By party' : 'By community'}</p>
                        {chartData.length === 0 && <p role="status" className="ni-empty">No elections match these filters. Select an election type and at least one party, or switch to Community.</p>}
                        <NIElectionsChart
                            data={chartData}
                            series={currentSeries}
                            colors={currentColors}
                            metric={metric}
                        />
                        <div className="chart-caption">
                            <span className="chart-caption-text">{selectedTypes.length === ELECTION_TYPES.length ? 'All election types' : selectedTypes.length ? selectedTypes.join(', ') : 'No election types selected'}. {excludeUncontested ? 'Excludes' : 'Includes'} partially uncontested elections.</span>
                            <span className="chart-actions">
                                <button type="button" onClick={handleDownloadCSV} className="download-chart" disabled={!chartData.length}>Download CSV ↓</button>
                                {chartData.length > 0 && <ChartDownload chartRef={chartRef} filename="salmonofdata-ni-elections" freezeNote="Percentages are calculated based on the total valid votes cast in each election."/>}
                            </span>
                        </div>
                        <div className="chart-brand">SALMONOFDATA.COM</div>
                    </div>

                    <div className="p-6 bg-[var(--muted)] rounded-sm border border-[var(--border)] text-sm text-gray-600 space-y-2">
                        <p>
                            <strong>Note on uncontested elections:</strong> Some historical elections had significant numbers of uncontested seats. When "Exclude partially uncontested elections" is checked, these are removed to prevent skewed vote share calculations.
                        </p>
                        <p>
                            Percentages are calculated based on the total valid votes cast in each election.
                        </p>
                    </div>
                </div>
            </div>
        </main>
    );
}
