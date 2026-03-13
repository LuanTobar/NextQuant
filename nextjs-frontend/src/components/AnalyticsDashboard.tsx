'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AreaChart, Area, BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, ScatterChart, Scatter,
} from 'recharts';
import { CustomTooltip, moneyFormatter, pctFormatter } from './ui/CustomTooltip';

type Range = '7d' | '30d' | '90d' | 'all';

interface AnalyticsData {
  totalDecisions: number;
  totalPnl: number;
  approvals: number;
  rejections: number;
  dailyPnl: Array<{ date: string; pnl: number }>;
  cumulativePnl: Array<{ date: string; pnl: number }>;
  symbolStats: Array<{ symbol: string; wins: number; losses: number; total: number; winRate: number; pnl: number }>;
  confidenceData: Array<{ confidence: number; outcome: string }>;
}

const CHART_COLORS = [
  'var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)',
  'var(--chart-4)', 'var(--chart-5)',
];

// Shared axis / grid props
const AXIS_STYLE = { fill: '#6b7280', fontSize: 10 };
const GRID_STYLE = { strokeDasharray: '3 3', stroke: '#1f2937' };
const TOOLTIP_CURSOR = { stroke: '#374151', strokeDasharray: '4 4' };

function fmtDate(v: string) {
  return v.slice(5); // "2024-03-15" → "03-15"
}

function fmtMoney(v: number) {
  const abs = Math.abs(v);
  return abs >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`;
}

export function AnalyticsDashboard() {
  const [range, setRange] = useState<Range>('30d');

  const { data, isLoading } = useQuery({
    queryKey: ['analytics', range],
    queryFn: async () => {
      const res = await fetch(`/api/analytics?range=${range}`);
      if (!res.ok) throw new Error('Failed to load');
      return res.json() as Promise<AnalyticsData>;
    },
  });

  const ranges: { key: Range; label: string }[] = [
    { key: '7d', label: '7D' },
    { key: '30d', label: '30D' },
    { key: '90d', label: '90D' },
    { key: 'all', label: 'All' },
  ];

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center h-64">
        <div className="h-6 w-6 rounded-full border-2 border-nq-accent border-t-transparent animate-spin" />
      </div>
    );
  }

  const hasData = data && data.totalDecisions > 0;
  const pieData = data ? [
    { name: 'Approved', value: data.approvals },
    { name: 'Rejected', value: data.rejections },
  ] : [];

  return (
    <div className="p-4 max-w-[1400px] mx-auto space-y-6">
      {/* SVG gradient defs — referenced by chart fills */}
      <svg width="0" height="0" style={{ position: 'absolute' }}>
        <defs>
          <linearGradient id="gradAccent" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="var(--chart-1)" stopOpacity={0.25} />
            <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gradGreen" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor="var(--chart-2)" stopOpacity={0.25} />
            <stop offset="95%" stopColor="var(--chart-2)" stopOpacity={0} />
          </linearGradient>
        </defs>
      </svg>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-nq-text">Analytics</h2>
          <p className="text-sm text-nq-muted">AI trading performance insights</p>
        </div>
        <div className="flex gap-1">
          {ranges.map((r) => (
            <button
              key={r.key}
              onClick={() => setRange(r.key)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
                range === r.key
                  ? 'bg-nq-accent/10 text-nq-accent border border-nq-accent/30'
                  : 'text-nq-muted hover:text-nq-text border border-transparent'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard label="Total Decisions" value={data?.totalDecisions || 0} />
        <SummaryCard
          label="Total P&L"
          value={fmtMoney(data?.totalPnl || 0)}
          valueClass={(data?.totalPnl || 0) >= 0 ? 'text-nq-green' : 'text-nq-red'}
        />
        <SummaryCard
          label="Approval Rate"
          value={
            data && data.totalDecisions > 0
              ? `${Math.round((data.approvals / data.totalDecisions) * 100)}%`
              : '—'
          }
        />
        <SummaryCard label="Symbols Traded" value={data?.symbolStats.length || 0} />
      </div>

      {!hasData ? (
        <div className="rounded-xl border border-nq-border bg-nq-card p-12 text-center">
          <p className="text-nq-muted">
            No trading data yet for this period. Analytics will appear after the AI agent makes trading decisions.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Daily P&L — Line chart */}
          <div className="rounded-xl border border-nq-border bg-nq-card p-5">
            <h3 className="text-sm font-medium text-nq-text mb-4">Daily P&L</h3>
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={data.dailyPnl}>
                <CartesianGrid {...GRID_STYLE} />
                <XAxis dataKey="date" tick={AXIS_STYLE} tickFormatter={fmtDate} />
                <YAxis tick={AXIS_STYLE} tickFormatter={fmtMoney} />
                <Tooltip
                  content={<CustomTooltip formatter={moneyFormatter} />}
                  cursor={TOOLTIP_CURSOR}
                />
                <Line
                  type="monotone"
                  dataKey="pnl"
                  stroke="var(--chart-1)"
                  strokeWidth={2}
                  dot={false}
                  activeDot={{ r: 4, fill: 'var(--chart-1)', stroke: 'var(--nq-bg)', strokeWidth: 2 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Win Rate by Symbol — Bar chart */}
          <div className="rounded-xl border border-nq-border bg-nq-card p-5">
            <h3 className="text-sm font-medium text-nq-text mb-4">Win Rate by Symbol</h3>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={data.symbolStats}>
                <CartesianGrid {...GRID_STYLE} />
                <XAxis dataKey="symbol" tick={AXIS_STYLE} />
                <YAxis tick={AXIS_STYLE} domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                <Tooltip
                  content={<CustomTooltip formatter={pctFormatter} />}
                  cursor={{ fill: 'rgba(255,255,255,0.03)' }}
                />
                <Bar dataKey="winRate" fill="var(--chart-2)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Approval / Rejection Pie */}
          <div className="rounded-xl border border-nq-border bg-nq-card p-5">
            <h3 className="text-sm font-medium text-nq-text mb-4">Decision Distribution</h3>
            <ResponsiveContainer width="100%" height={250}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  dataKey="value"
                  label={({ name, value }) => `${name}: ${value}`}
                  labelLine={{ stroke: '#374151' }}
                >
                  {pieData.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i]} />
                  ))}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          </div>

          {/* Confidence Calibration — Scatter */}
          <div className="rounded-xl border border-nq-border bg-nq-card p-5">
            <h3 className="text-sm font-medium text-nq-text mb-4">Confidence Calibration</h3>
            <ResponsiveContainer width="100%" height={250}>
              <ScatterChart>
                <CartesianGrid {...GRID_STYLE} />
                <XAxis dataKey="confidence" name="Confidence" tick={AXIS_STYLE} domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                <YAxis dataKey="outcome" name="Outcome" tick={AXIS_STYLE} />
                <Tooltip cursor={{ strokeDasharray: '3 3' }} content={<CustomTooltip />} />
                <Scatter data={data.confidenceData} fill="var(--chart-1)" opacity={0.8} />
              </ScatterChart>
            </ResponsiveContainer>
          </div>

          {/* Cumulative P&L — Area chart with gradient */}
          <div className="rounded-xl border border-nq-border bg-nq-card p-5 lg:col-span-2">
            <h3 className="text-sm font-medium text-nq-text mb-4">Cumulative P&L</h3>
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={data.cumulativePnl}>
                <CartesianGrid {...GRID_STYLE} />
                <XAxis dataKey="date" tick={AXIS_STYLE} tickFormatter={fmtDate} />
                <YAxis tick={AXIS_STYLE} tickFormatter={fmtMoney} />
                <Tooltip
                  content={<CustomTooltip formatter={moneyFormatter} />}
                  cursor={TOOLTIP_CURSOR}
                />
                <defs>
                  <linearGradient id="gradCumPnl" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="var(--chart-1)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <Area
                  type="monotone"
                  dataKey="pnl"
                  stroke="var(--chart-1)"
                  fill="url(#gradCumPnl)"
                  strokeWidth={2}
                  activeDot={{ r: 4, fill: 'var(--chart-1)', stroke: 'var(--nq-bg)', strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryCard({
  label,
  value,
  valueClass = 'text-nq-text',
}: {
  label: string;
  value: string | number;
  valueClass?: string;
}) {
  return (
    <div className="rounded-xl border border-nq-border bg-nq-card p-4">
      <p className="text-xs text-nq-muted">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${valueClass}`}>{value}</p>
    </div>
  );
}
