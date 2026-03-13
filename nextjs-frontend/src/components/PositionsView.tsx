'use client';

import { useState } from 'react';
import { useSession } from 'next-auth/react';
import { useQuery } from '@tanstack/react-query';
import clsx from 'clsx';
import { ClosePositionModal } from './ClosePositionModal';

interface Position {
  symbol: string;
  quantity: number;
  avgEntryPrice: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPl: number;
  unrealizedPlPct: number;
  side: 'long' | 'short';
}

export function PositionsView() {
  const { data: session } = useSession();
  const isPro = session?.user?.plan === 'PRO';
  const [closeTarget, setCloseTarget] = useState<(Position & { broker: string }) | null>(null);

  // Fetch positions from all connected brokers
  const { data: bitgetPositions } = useQuery({
    queryKey: ['positions', 'BITGET'],
    queryFn: async () => {
      const res = await fetch('/api/positions?broker=BITGET');
      if (!res.ok) return [];
      return res.json() as Promise<Position[]>;
    },
    refetchInterval: 10000,
    enabled: isPro,
  });

  const { data: alpacaPositions } = useQuery({
    queryKey: ['positions', 'ALPACA'],
    queryFn: async () => {
      const res = await fetch('/api/positions?broker=ALPACA');
      if (!res.ok) return [];
      return res.json() as Promise<Position[]>;
    },
    refetchInterval: 10000,
    enabled: isPro,
  });

  const allPositions = [
    ...(bitgetPositions || []).map((p) => ({ ...p, broker: 'BITGET' as const })),
    ...(alpacaPositions || []).map((p) => ({ ...p, broker: 'ALPACA' as const })),
  ];

  if (!isPro) {
    return (
      <div className="bg-nq-card rounded-xl p-5 border border-nq-border">
        <h3 className="text-sm text-nq-muted mb-3">Open Positions</h3>
        <div className="flex flex-col items-center py-4 text-center">
          <p className="text-xs text-nq-muted">Upgrade to Pro to trade and view positions</p>
        </div>
      </div>
    );
  }

  if (allPositions.length === 0) {
    return (
      <div className="bg-nq-card rounded-xl p-5 border border-nq-border">
        <h3 className="text-sm text-nq-muted mb-3">Open Positions</h3>
        <div className="flex flex-col items-center py-4 text-center">
          <div className="h-8 w-8 rounded-full bg-nq-bg flex items-center justify-center mb-2">
            <svg className="h-4 w-4 text-nq-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 18 9 11.25l4.306 4.306a11.95 11.95 0 0 1 5.814-5.518l2.74-1.22m0 0-5.94-2.281m5.94 2.28-2.28 5.941" />
            </svg>
          </div>
          <p className="text-xs text-nq-muted">No open positions</p>
          <p className="text-xs text-nq-muted/60">Connect a broker and start trading</p>
        </div>
      </div>
    );
  }

  const totalValue = allPositions.reduce((s, p) => s + p.marketValue, 0);
  const totalPl = allPositions.reduce((s, p) => s + p.unrealizedPl, 0);

  return (
    <>
      <div className="bg-nq-card rounded-xl p-5 border border-nq-border">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm text-nq-muted">Open Positions</h3>
          <div className="flex items-center gap-2">
            <span className="text-xs text-nq-muted">{allPositions.length} positions</span>
            <span className={clsx('text-xs font-medium', totalPl >= 0 ? 'text-nq-green' : 'text-nq-red')}>
              {totalPl >= 0 ? '+' : ''}{totalPl.toFixed(2)}
            </span>
          </div>
        </div>

        {/* Summary bar */}
        <div className="flex items-center justify-between rounded-lg bg-nq-bg/50 border border-nq-border px-3 py-2 mb-3">
          <div>
            <p className="text-xs text-nq-muted">Total Value</p>
            <p className="text-sm font-semibold">${totalValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</p>
          </div>
          <div className="text-right">
            <p className="text-xs text-nq-muted">Unrealized P&L</p>
            <p className={clsx('text-sm font-semibold', totalPl >= 0 ? 'text-nq-green' : 'text-nq-red')}>
              {totalPl >= 0 ? '+' : ''}${Math.abs(totalPl).toFixed(2)}
            </p>
          </div>
        </div>

        {/* Position rows */}
        <div className="space-y-1.5 max-h-[280px] overflow-y-auto pr-1">
          {allPositions.map((pos) => (
            <div
              key={`${pos.broker}-${pos.symbol}`}
              className="flex items-center justify-between rounded-lg bg-nq-bg/50 border border-nq-border px-3 py-2 group hover:border-nq-accent/30 transition"
            >
              <div className="flex items-center gap-2.5">
                <div className={clsx(
                  'h-6 w-6 rounded flex items-center justify-center text-[10px] font-bold',
                  pos.side === 'long' ? 'bg-nq-green/10 text-nq-green' : 'bg-nq-red/10 text-nq-red'
                )}>
                  {pos.side === 'long' ? 'L' : 'S'}
                </div>
                <div>
                  <div className="flex items-center gap-1.5">
                    <p className="text-sm font-medium text-nq-text">{pos.symbol}</p>
                    <span className="text-[9px] px-1 py-0.5 rounded bg-nq-bg border border-nq-border text-nq-muted">
                      {pos.broker}
                    </span>
                  </div>
                  <p className="text-[10px] text-nq-muted">
                    {pos.quantity} @ ${pos.avgEntryPrice > 0 ? pos.avgEntryPrice.toFixed(2) : '—'}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-xs text-nq-text">${pos.currentPrice.toFixed(2)}</p>
                  <p className={clsx('text-[10px] font-medium', pos.unrealizedPl >= 0 ? 'text-nq-green' : 'text-nq-red')}>
                    {pos.unrealizedPl >= 0 ? '+' : ''}{pos.unrealizedPl.toFixed(2)}
                    {pos.unrealizedPlPct !== 0 && ` (${pos.unrealizedPlPct >= 0 ? '+' : ''}${pos.unrealizedPlPct.toFixed(1)}%)`}
                  </p>
                </div>
                <button
                  onClick={() => setCloseTarget(pos)}
                  className="opacity-0 group-hover:opacity-100 h-6 px-2 rounded text-[10px] font-medium border border-nq-red/30 text-nq-red hover:bg-nq-red/10 transition"
                >
                  Close
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {closeTarget && (
        <ClosePositionModal
          isOpen={!!closeTarget}
          onClose={() => setCloseTarget(null)}
          symbol={closeTarget.symbol}
          broker={closeTarget.broker}
          quantity={closeTarget.quantity}
          currentPrice={closeTarget.currentPrice}
          avgEntryPrice={closeTarget.avgEntryPrice}
          unrealizedPl={closeTarget.unrealizedPl}
        />
      )}
    </>
  );
}
