'use client';

import { useSession } from 'next-auth/react';
import { useQuery } from '@tanstack/react-query';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip,
  AreaChart, Area,
} from 'recharts';

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f97316', '#ec4899'];

interface BrokerAccount {
  equity: number;
  buyingPower: number;
  cash: number;
  currency: string;
}

interface BrokerPosition {
  symbol: string;
  quantity: number;
  avgEntryPrice: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPl: number;
  unrealizedPlPct: number;
  side: string;
}

// Mock data for users without broker connections
const MOCK_DATA = {
  total_value: 52_358.40,
  daily_pnl: 1_245.30,
  daily_pnl_pct: 2.43,
  sharpe_ratio: 1.85,
  max_drawdown: -4.2,
  positions: [
    { symbol: 'AAPL', quantity: 50, weight: 0.29, pnl: 366.0 },
    { symbol: 'GOOGL', quantity: 40, weight: 0.20, pnl: 260.0 },
    { symbol: 'MSFT', quantity: 20, weight: 0.19, pnl: 236.0 },
    { symbol: 'AMZN', quantity: 30, weight: 0.17, pnl: 186.0 },
    { symbol: 'TSLA', quantity: 15, weight: 0.15, pnl: 127.5 },
  ],
  // 14-day equity sparkline (mock — replaced by real data when available)
  equity_curve: [
    48_200, 48_950, 49_100, 48_600, 49_800, 50_200, 50_800,
    50_300, 51_200, 51_900, 51_400, 52_000, 52_150, 52_358,
  ].map((v, i) => ({ t: i, v })),
};

export function PortfolioHealth() {
  const { data: session } = useSession();
  const isPro = session?.user?.plan === 'PRO';

  // Fetch real account data from connected brokers
  const { data: bitgetAccount } = useQuery({
    queryKey: ['broker-account', 'BITGET'],
    queryFn: async () => {
      const res = await fetch('/api/broker/account?broker=BITGET');
      if (!res.ok) return null;
      return res.json() as Promise<{ broker: string; account: BrokerAccount; positions: BrokerPosition[] }>;
    },
    refetchInterval: 15000,
    enabled: isPro,
  });

  const { data: alpacaAccount } = useQuery({
    queryKey: ['broker-account', 'ALPACA'],
    queryFn: async () => {
      const res = await fetch('/api/broker/account?broker=ALPACA');
      if (!res.ok) return null;
      return res.json() as Promise<{ broker: string; account: BrokerAccount; positions: BrokerPosition[] }>;
    },
    refetchInterval: 15000,
    enabled: isPro,
  });

  // Determine if we have real data
  const hasRealData = !!(bitgetAccount || alpacaAccount);

  // Build display data from real broker data or mock
  let totalValue = 0;
  let totalPnl = 0;
  let allPositions: { symbol: string; quantity: number; weight: number; pnl: number; broker: string }[] = [];

  if (hasRealData) {
    // Combine accounts
    if (bitgetAccount) {
      totalValue += bitgetAccount.account.equity;
      for (const p of bitgetAccount.positions) {
        totalPnl += p.unrealizedPl;
        allPositions.push({
          symbol: p.symbol,
          quantity: p.quantity,
          weight: 0, // computed below
          pnl: p.unrealizedPl,
          broker: 'BITGET',
        });
      }
    }
    if (alpacaAccount) {
      totalValue += alpacaAccount.account.equity;
      for (const p of alpacaAccount.positions) {
        totalPnl += p.unrealizedPl;
        allPositions.push({
          symbol: p.symbol,
          quantity: p.quantity,
          weight: 0,
          pnl: p.unrealizedPl,
          broker: 'ALPACA',
        });
      }
    }

    // Compute weights
    const totalMarketValue = allPositions.reduce((s, p) => {
      const pos = [...(bitgetAccount?.positions || []), ...(alpacaAccount?.positions || [])];
      const found = pos.find((pp) => pp.symbol === p.symbol);
      return s + (found?.marketValue || 0);
    }, 0);

    if (totalMarketValue > 0) {
      for (const p of allPositions) {
        const positions = [...(bitgetAccount?.positions || []), ...(alpacaAccount?.positions || [])];
        const found = positions.find((pp) => pp.symbol === p.symbol);
        p.weight = (found?.marketValue || 0) / totalMarketValue;
      }
    }
  }

  const displayPositions = hasRealData ? allPositions : MOCK_DATA.positions;
  const displayTotalValue = hasRealData ? totalValue : MOCK_DATA.total_value;
  const displayPnl = hasRealData ? totalPnl : MOCK_DATA.daily_pnl;
  const displayPnlPct = displayTotalValue > 0 ? (displayPnl / displayTotalValue) * 100 : 0;
  const isPositive = displayPnl >= 0;

  const pieData = displayPositions
    .filter((p) => p.weight > 0.01)
    .map((p) => ({
      name: p.symbol,
      value: Number((p.weight * 100).toFixed(1)),
    }));

  const accentColor = isPositive ? '#10b981' : '#ef4444';

  return (
    <div className="space-y-3">
      {/* Portfolio Value hero card — gradient tint */}
      <div
        className="rounded-xl p-5 border overflow-hidden relative"
        style={{
          background: `linear-gradient(135deg, ${accentColor}10 0%, #111827 60%)`,
          borderColor: `${accentColor}30`,
        }}
      >
        {/* Subtle glow circle in top-right */}
        <div
          className="absolute -top-10 -right-10 w-40 h-40 rounded-full blur-3xl opacity-20 pointer-events-none"
          style={{ background: accentColor }}
        />

        <div className="flex items-center justify-between mb-1 relative">
          <p className="text-xs font-medium text-nq-muted uppercase tracking-wide">Portfolio Value</p>
          {hasRealData ? (
            <span className="text-[9px] px-2 py-0.5 rounded-full bg-nq-green/15 text-nq-green border border-nq-green/25 font-medium">
              ● LIVE
            </span>
          ) : (
            <span className="text-[9px] text-nq-muted">14d</span>
          )}
        </div>

        <p className="text-3xl font-bold tracking-tight relative">
          ${displayTotalValue.toLocaleString('en-US', { minimumFractionDigits: 2 })}
        </p>
        <p className={`text-sm mt-0.5 font-medium relative ${isPositive ? 'text-nq-green' : 'text-nq-red'}`}>
          {isPositive ? '▲' : '▼'} {isPositive ? '+' : ''}${displayPnl.toFixed(2)} ({displayPnlPct.toFixed(2)}%)
          <span className="text-nq-muted font-normal ml-1 text-xs">{hasRealData ? 'unrealized' : 'today'}</span>
        </p>

        {/* 14-day equity sparkline */}
        <div className="h-16 mt-3 -mx-2 -mb-2">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={MOCK_DATA.equity_curve} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%"  stopColor={accentColor} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={accentColor} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <Area
                type="monotone"
                dataKey="v"
                stroke={accentColor}
                fill="url(#sparkGrad)"
                strokeWidth={2}
                dot={false}
                isAnimationActive
                animationDuration={1200}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Risk Metrics — colored left border */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-nq-card rounded-xl p-4 border border-nq-border border-l-2 border-l-nq-green">
          <p className="text-[10px] text-nq-muted uppercase tracking-wide">Sharpe</p>
          <p className="text-2xl font-bold text-nq-green mt-0.5">{MOCK_DATA.sharpe_ratio.toFixed(2)}</p>
          <p className="text-[9px] text-nq-muted mt-0.5">ratio</p>
        </div>
        <div className="bg-nq-card rounded-xl p-4 border border-nq-border border-l-2 border-l-nq-red">
          <p className="text-[10px] text-nq-muted uppercase tracking-wide">Drawdown</p>
          <p className="text-2xl font-bold text-nq-red mt-0.5">{MOCK_DATA.max_drawdown.toFixed(1)}%</p>
          <p className="text-[9px] text-nq-muted mt-0.5">max</p>
        </div>
      </div>

      {/* Allocation Pie */}
      {pieData.length > 0 && (
        <div className="bg-nq-card rounded-xl p-5 border border-nq-border">
          <p className="text-sm text-nq-muted mb-3">Allocation</p>
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={45}
                  outerRadius={75}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {pieData.map((_, idx) => (
                    <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: 'var(--nq-card)', border: '1px solid var(--nq-border)', borderRadius: 8 }}
                  labelStyle={{ color: 'var(--nq-text)' }}
                  formatter={(value: number) => [`${value.toFixed(1)}%`, 'Weight']}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="flex flex-wrap gap-3 mt-2 justify-center">
            {displayPositions.filter((p) => p.weight > 0.01).map((p, i) => (
              <div key={p.symbol} className="flex items-center gap-1 text-xs">
                <div className="h-2 w-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                <span>{p.symbol}</span>
                <span className="text-nq-muted">{(p.weight * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Positions list */}
      {displayPositions.length > 0 && (
        <div className="bg-nq-card rounded-xl p-5 border border-nq-border">
          <p className="text-sm text-nq-muted mb-3">Positions</p>
          <div className="space-y-2">
            {displayPositions.map((p) => (
              <div key={p.symbol} className="flex justify-between items-center text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{p.symbol}</span>
                  <span className="text-nq-muted text-xs">{p.quantity}</span>
                  {'broker' in p && (
                    <span className="text-[9px] px-1 rounded bg-nq-bg text-nq-muted">{(p as { broker: string }).broker}</span>
                  )}
                </div>
                <span className={p.pnl >= 0 ? 'text-nq-green' : 'text-nq-red'}>
                  {p.pnl >= 0 ? '+' : ''}${p.pnl.toFixed(2)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
