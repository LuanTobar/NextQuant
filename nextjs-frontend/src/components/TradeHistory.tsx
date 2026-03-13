'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';
import { toast } from 'sonner';

interface Order {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  orderType: string;
  status: string;
  brokerOrderId: string | null;
  filledPrice: number | null;
  filledQuantity: number | null;
  createdAt: string;
  brokerConnection: {
    broker: string;
    label: string | null;
  };
}

const statusColors: Record<string, string> = {
  PENDING: 'bg-nq-yellow/10 text-nq-yellow',
  FILLED: 'bg-nq-green/10 text-nq-green',
  PARTIALLY_FILLED: 'bg-nq-accent/10 text-nq-accent',
  CANCELLED: 'bg-nq-muted/10 text-nq-muted',
  REJECTED: 'bg-nq-red/10 text-nq-red',
};

type Filter = 'ALL' | 'PENDING' | 'FILLED' | 'CANCELLED';

export function TradeHistory() {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<Filter>('ALL');
  const [cancellingId, setCancellingId] = useState<string | null>(null);

  const { data: orders, isLoading } = useQuery({
    queryKey: ['trade-history'],
    queryFn: async () => {
      const res = await fetch('/api/orders');
      if (!res.ok) return [];
      return res.json() as Promise<Order[]>;
    },
    refetchInterval: 15000,
  });

  const handleCancel = async (orderId: string) => {
    setCancellingId(orderId);
    try {
      const res = await fetch(`/api/orders/${orderId}/cancel`, { method: 'POST' });
      if (res.ok) {
        queryClient.invalidateQueries({ queryKey: ['trade-history'] });
        queryClient.invalidateQueries({ queryKey: ['positions'] });
        toast.success('Order cancelled');
      } else {
        toast.error('Failed to cancel order');
      }
    } catch {
      toast.error('Failed to cancel order');
    }
    setCancellingId(null);
  };

  const filtered = (orders || []).filter((o) => {
    if (filter === 'ALL') return true;
    if (filter === 'CANCELLED') return ['CANCELLED', 'REJECTED'].includes(o.status);
    return o.status === filter;
  });

  const filters: { key: Filter; label: string }[] = [
    { key: 'ALL', label: 'All' },
    { key: 'PENDING', label: 'Pending' },
    { key: 'FILLED', label: 'Filled' },
    { key: 'CANCELLED', label: 'Closed' },
  ];

  if (isLoading) {
    return (
      <div className="bg-nq-card rounded-xl p-5 border border-nq-border">
        <h3 className="text-sm text-nq-muted mb-3">Trade History</h3>
        <div className="flex items-center justify-center h-16">
          <div className="h-5 w-5 rounded-full border-2 border-nq-accent border-t-transparent animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-nq-card rounded-xl p-5 border border-nq-border">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm text-nq-muted">Trade History</h3>
        <div className="flex items-center gap-2">
          {orders && orders.length > 0 && (
            <button
              onClick={() => {
                window.open('/api/reports/trades?format=csv', '_blank');
                toast.success('Downloading CSV...');
              }}
              className="text-[10px] px-2 py-0.5 rounded border border-nq-border text-nq-muted hover:text-nq-text transition"
            >
              Export CSV
            </button>
          )}
          <span className="text-xs text-nq-muted/60">{filtered.length} orders</span>
        </div>
      </div>

      {/* Filter tabs */}
      {orders && orders.length > 0 && (
        <div className="flex gap-1 mb-3">
          {filters.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={clsx(
                'px-2.5 py-1 rounded-md text-[10px] font-medium transition',
                filter === f.key
                  ? 'bg-nq-accent/10 text-nq-accent border border-nq-accent/30'
                  : 'text-nq-muted hover:text-nq-text border border-transparent'
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      )}

      {filtered.length === 0 ? (
        <div className="flex flex-col items-center py-4 text-center">
          <p className="text-xs text-nq-muted">
            {orders && orders.length > 0 ? 'No orders match filter' : 'No trades yet'}
          </p>
        </div>
      ) : (
        <div className="space-y-1.5 max-h-[250px] overflow-y-auto pr-1">
          {filtered.map((order) => (
            <div
              key={order.id}
              className="flex items-center justify-between rounded-lg bg-nq-bg/50 border border-nq-border px-3 py-2"
            >
              <div className="flex items-center gap-2.5">
                <div
                  className={clsx(
                    'h-6 w-6 rounded flex items-center justify-center text-[10px] font-bold',
                    order.side === 'BUY' ? 'bg-nq-green/10 text-nq-green' : 'bg-nq-red/10 text-nq-red'
                  )}
                >
                  {order.side === 'BUY' ? '↗' : '↘'}
                </div>
                <div>
                  <p className="text-xs font-medium text-nq-text">
                    {order.side} {order.quantity} {order.symbol}
                  </p>
                  <p className="text-[10px] text-nq-muted">
                    {order.brokerConnection.broker} · {order.orderType} ·{' '}
                    {new Date(order.createdAt).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {/* Filled info */}
                {order.filledPrice && (
                  <div className="text-right">
                    <p className="text-[10px] text-nq-text">${order.filledPrice.toFixed(2)}</p>
                    {order.filledQuantity && order.filledQuantity !== order.quantity && (
                      <p className="text-[9px] text-nq-muted">{order.filledQuantity}/{order.quantity}</p>
                    )}
                  </div>
                )}

                {/* Status badge */}
                <span
                  className={clsx(
                    'px-1.5 py-0.5 rounded-full text-[9px] font-medium',
                    statusColors[order.status] || statusColors.PENDING
                  )}
                >
                  {order.status}
                </span>

                {/* Cancel button for pending orders */}
                {['PENDING', 'PARTIALLY_FILLED'].includes(order.status) && (
                  <button
                    onClick={() => handleCancel(order.id)}
                    disabled={cancellingId === order.id}
                    className="text-[9px] px-1.5 py-0.5 rounded border border-nq-red/30 text-nq-red hover:bg-nq-red/10 transition disabled:opacity-50"
                  >
                    {cancellingId === order.id ? '...' : 'Cancel'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
