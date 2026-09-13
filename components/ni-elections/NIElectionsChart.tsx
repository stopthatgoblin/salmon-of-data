'use client';

import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer
} from 'recharts';

interface Props {
    data: any[];
    series: string[];
    colors: Record<string, string>;
    metric: 'share' | 'votes';
}

export default function NIElectionsChart({ data, series, colors, metric }: Props) {
    const formatYAxis = (val: number) => {
        if (metric === 'share') {
            return `${val}%`;
        }
        return val.toLocaleString();
    };

    const CustomTooltip = ({ active, payload }: any) => {
        if (active && payload && payload.length) {
            const dataPoint = payload[0].payload;
            return (
                <div
                    className="bg-[var(--paper)] p-3 rounded-sm text-xs z-50 border"
                    style={{
                        borderColor: '#e5e7eb', // stone-200 approx
                        boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)' // shadow-md
                    }}
                >
                    <p className="font-bold mb-1">{dataPoint.Election} ({dataPoint.Year})</p>
                    <p className="mb-2" style={{ color: '#6b7280' }}>{dataPoint.Type}</p>
                    {payload.map((entry: any) => (
                        <div key={entry.name} className="flex items-center gap-2 mb-1">
                            <div className="w-2 h-2 rounded-full" style={{ backgroundColor: entry.color }}></div>
                            <span className="font-medium">{entry.name}:</span>
                            <span>
                                {metric === 'share'
                                    ? `${entry.value.toFixed(1)}%`
                                    : entry.value.toLocaleString()}
                            </span>
                        </div>
                    ))}
                </div>
            );
        }
        return null;
    };

    return (
        <div
            className="ni-chart"
            style={{
                borderColor: '#f5f5f4',
                boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.05)'
            }}
        >
            <ResponsiveContainer width="100%" height={420}>
                <LineChart
                    data={data}
                    margin={{ top: 10, right: 15, left: 0, bottom: 10 }}
                >
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />
                    <XAxis
                        dataKey="Year"
                        type="number"
                        domain={['dataMin', 'dataMax']}
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: '#687779', fontSize: 12 }}
                        tickCount={10}
                    />
                    <YAxis
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: '#687779', fontSize: 12 }}
                        tickFormatter={formatYAxis}
                        width={metric === 'votes' ? 60 : 40}
                    />
                    <Tooltip content={<CustomTooltip />} cursor={{ stroke: '#e5e7eb', strokeWidth: 1 }} />
                    <Legend content={<div className="chart-legend" style={{ paddingTop: 20 }}>{series.map(key => <span key={key}><i style={{ borderTop: `2px solid ${colors[key] || '#687779'}` }}/>{key}</span>)}</div>} />
                    {series.map((key) => (
                        <Line
                            key={key}
                            type="monotone"
                            dataKey={key}
                            stroke={colors[key] || '#687779'}
                            strokeWidth={2}
                            dot={{ r: 3, fill: colors[key] || '#687779', strokeWidth: 0 }}
                            activeDot={{ r: 5 }}
                            connectNulls
                            isAnimationActive={false}
                            legendType="circle"
                        />
                    ))}
                </LineChart>
            </ResponsiveContainer>

        </div>
    );
}
