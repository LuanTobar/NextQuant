'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useQueryClient } from '@tanstack/react-query';
import clsx from 'clsx';

interface ClosePositionModalProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
  broker: string;
  quantity: number;
  currentPrice: number;
  avgEntryPrice: number;
  unrealizedPl: number;
}

export function ClosePositionModal({
  isOpen,
  onClose,
  symbol,
  broker,
  quantity,
  currentPrice,
  avgEntryPrice,
  unrealizedPl,
}: ClosePositionModalProps) {
  const queryClient = useQueryClient();
  const [closeQty, setCloseQty] = useState(String(quantity));
  const [isPartial, setIsPartial] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);

  const effectiveQty = isPartial ? Number(closeQty) : quantity;
  const estimatedProceeds = effectiveQty * currentPrice;
  const estimatedPl = avgEntryPrice > 0
    ? (currentPrice - avgEntryPrice) * effectiveQty
    : unrealizedPl;

  const handleClose = async () => {
    setSubmitting(true);
    setResult(null);

    try {
      const body: Record<string, unknown> = { broker, symbol };
      if (isPartial && Number(closeQty) < quantity) {
        body.quantity = Number(closeQty);
      }

      const res = await fetch('/api/positions/close', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const data = await res.json();

      if (res.ok) {
        setResult({ success: true, message: 'Position close submitted' });
        // Invalidate positions and orders queries
        queryClient.invalidateQueries({ queryKey: ['positions'] });
        queryClient.invalidateQueries({ queryKey: ['trade-history'] });
        setTimeout(() => {
          onClose();
          setResult(null);
        }, 1500);
      } else {
        setResult({ success: false, message: data.error || 'Close failed' });
      }
    } catch {
      setResult({ success: false, message: 'Network error' });
    }

    setSubmitting(false);
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="w-full max-w-sm mx-4 rounded-xl border border-nq-border bg-nq-card p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg flex items-center justify-center text-sm font-bold bg-nq-red/10 text-nq-red">
                  ↘
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-nq-text">Close {symbol}</h3>
                  <p className="text-xs text-nq-muted">via {broker}</p>
                </div>
              </div>
              <button onClick={onClose} className="text-nq-muted hover:text-nq-text transition">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Position info */}
            <div className="rounded-lg bg-nq-bg/50 border border-nq-border p-3 mb-4 space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-nq-muted">Quantity</span>
                <span className="text-nq-text font-medium">{quantity}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-nq-muted">Entry Price</span>
                <span className="text-nq-text">{avgEntryPrice > 0 ? `$${avgEntryPrice.toFixed(2)}` : '—'}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-nq-muted">Current Price</span>
                <span className="text-nq-text">${currentPrice.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm pt-1 border-t border-nq-border">
                <span className="text-nq-muted">Unrealized P&L</span>
                <span className={clsx('font-medium', unrealizedPl >= 0 ? 'text-nq-green' : 'text-nq-red')}>
                  {unrealizedPl >= 0 ? '+' : ''}${unrealizedPl.toFixed(2)}
                </span>
              </div>
            </div>

            {/* Partial close toggle */}
            <div className="mb-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isPartial}
                  onChange={(e) => setIsPartial(e.target.checked)}
                  className="h-4 w-4 rounded border-nq-border text-nq-accent focus:ring-nq-accent bg-nq-bg"
                />
                <span className="text-sm text-nq-text">Partial close</span>
              </label>

              {isPartial && (
                <div className="mt-2">
                  <input
                    type="number"
                    min="0.001"
                    max={quantity}
                    step="any"
                    value={closeQty}
                    onChange={(e) => setCloseQty(e.target.value)}
                    className="w-full rounded-lg border border-nq-border bg-nq-bg px-3 py-2 text-sm text-nq-text focus:border-nq-accent focus:outline-none"
                    placeholder={`Max: ${quantity}`}
                  />
                </div>
              )}
            </div>

            {/* Estimated proceeds */}
            <div className="flex justify-between text-sm mb-4 px-1">
              <span className="text-nq-muted">Est. Proceeds</span>
              <span className="text-nq-text font-semibold">
                ${estimatedProceeds.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                <span className={clsx('text-xs ml-1', estimatedPl >= 0 ? 'text-nq-green' : 'text-nq-red')}>
                  ({estimatedPl >= 0 ? '+' : ''}{estimatedPl.toFixed(2)})
                </span>
              </span>
            </div>

            {/* Result */}
            {result && (
              <div className={clsx('rounded-lg p-3 text-xs mb-4', result.success ? 'bg-nq-green/10 text-nq-green' : 'bg-nq-red/10 text-nq-red')}>
                {result.message}
              </div>
            )}

            {/* Submit */}
            <button
              onClick={handleClose}
              disabled={submitting || (isPartial && (Number(closeQty) <= 0 || Number(closeQty) > quantity))}
              className="w-full py-3 rounded-lg text-sm font-semibold bg-nq-red text-white hover:bg-nq-red/90 transition disabled:opacity-50"
            >
              {submitting ? 'Closing...' : `Close ${isPartial ? closeQty : 'All'} ${symbol}`}
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
