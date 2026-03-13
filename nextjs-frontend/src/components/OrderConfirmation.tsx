'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import clsx from 'clsx';

interface OrderConfirmationProps {
  isOpen: boolean;
  onClose: () => void;
  symbol: string;
  exchange?: string;
  currentPrice: number;
  signal: 'BUY' | 'SELL' | 'HOLD';
  predictedClose: number;
}

export function OrderConfirmation({
  isOpen,
  onClose,
  symbol,
  exchange,
  currentPrice,
  signal,
  predictedClose,
}: OrderConfirmationProps) {
  const [quantity, setQuantity] = useState('1');
  const [orderType, setOrderType] = useState<'market' | 'limit'>('market');
  const [limitPrice, setLimitPrice] = useState(currentPrice.toFixed(2));
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);

  // Determine broker based on exchange
  const broker = exchange === 'CRYPTO' ? 'BITGET' : 'ALPACA';
  const side = signal === 'SELL' ? 'sell' : 'buy';
  const isBuy = side === 'buy';

  const estimatedTotal = Number(quantity) * (orderType === 'limit' ? Number(limitPrice) : currentPrice);
  const expectedReturn = ((predictedClose - currentPrice) / currentPrice * 100).toFixed(2);

  const handleSubmit = async () => {
    setSubmitting(true);
    setResult(null);

    try {
      const body: Record<string, unknown> = {
        symbol,
        side,
        quantity: Number(quantity),
        type: orderType,
        broker,
      };

      if (orderType === 'limit') {
        body.limitPrice = Number(limitPrice);
      }

      const res = await fetch('/api/orders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      const data = await res.json();

      if (res.ok) {
        setResult({
          success: true,
          message: `Order submitted! ${data.brokerOrderId ? `ID: ${data.brokerOrderId.slice(0, 8)}...` : ''}`,
        });
        // Auto-close after success
        setTimeout(() => {
          onClose();
          setResult(null);
          setQuantity('1');
        }, 2000);
      } else {
        setResult({ success: false, message: data.error || 'Order failed' });
      }
    } catch {
      setResult({ success: false, message: 'Network error' });
    }

    setSubmitting(false);
  };

  const inputClass =
    'w-full rounded-lg border border-nq-border bg-nq-bg px-3 py-2 text-sm text-nq-text placeholder-nq-muted/50 focus:border-nq-accent focus:outline-none transition';

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
                <div
                  className={clsx(
                    'h-10 w-10 rounded-lg flex items-center justify-center text-sm font-bold',
                    isBuy ? 'bg-nq-green/10 text-nq-green' : 'bg-nq-red/10 text-nq-red'
                  )}
                >
                  {isBuy ? '↗' : '↘'}
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-nq-text">
                    {side.toUpperCase()} {symbol}
                  </h3>
                  <p className="text-xs text-nq-muted">
                    via {broker} · {exchange || 'US'}
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="text-nq-muted hover:text-nq-text transition"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Price info */}
            <div className="rounded-lg bg-nq-bg/50 border border-nq-border p-3 mb-4">
              <div className="flex justify-between text-sm">
                <span className="text-nq-muted">Current Price</span>
                <span className="text-nq-text font-medium">${currentPrice.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-sm mt-1">
                <span className="text-nq-muted">AI Prediction</span>
                <span className={clsx('font-medium', Number(expectedReturn) >= 0 ? 'text-nq-green' : 'text-nq-red')}>
                  ${predictedClose.toFixed(2)} ({Number(expectedReturn) >= 0 ? '+' : ''}{expectedReturn}%)
                </span>
              </div>
            </div>

            {/* Form */}
            <div className="space-y-3 mb-5">
              {/* Order type */}
              <div className="flex gap-2">
                <button
                  onClick={() => setOrderType('market')}
                  className={clsx(
                    'flex-1 py-2 text-xs rounded-lg border transition',
                    orderType === 'market'
                      ? 'border-nq-accent bg-nq-accent/10 text-nq-accent'
                      : 'border-nq-border text-nq-muted hover:text-nq-text'
                  )}
                >
                  Market
                </button>
                <button
                  onClick={() => setOrderType('limit')}
                  className={clsx(
                    'flex-1 py-2 text-xs rounded-lg border transition',
                    orderType === 'limit'
                      ? 'border-nq-accent bg-nq-accent/10 text-nq-accent'
                      : 'border-nq-border text-nq-muted hover:text-nq-text'
                  )}
                >
                  Limit
                </button>
              </div>

              {/* Quantity */}
              <div>
                <label className="text-xs text-nq-muted mb-1 block">Quantity</label>
                <input
                  type="number"
                  min="0.001"
                  step="any"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  className={inputClass}
                  placeholder="1"
                />
              </div>

              {/* Limit price (conditional) */}
              {orderType === 'limit' && (
                <div>
                  <label className="text-xs text-nq-muted mb-1 block">Limit Price</label>
                  <input
                    type="number"
                    min="0"
                    step="any"
                    value={limitPrice}
                    onChange={(e) => setLimitPrice(e.target.value)}
                    className={inputClass}
                  />
                </div>
              )}

              {/* Estimated total */}
              <div className="flex justify-between text-sm pt-2 border-t border-nq-border">
                <span className="text-nq-muted">Estimated Total</span>
                <span className="text-nq-text font-semibold">
                  ${estimatedTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
              </div>
            </div>

            {/* Result message */}
            {result && (
              <div
                className={clsx(
                  'rounded-lg p-3 text-xs mb-4',
                  result.success ? 'bg-nq-green/10 text-nq-green' : 'bg-nq-red/10 text-nq-red'
                )}
              >
                {result.message}
              </div>
            )}

            {/* Submit button */}
            <button
              onClick={handleSubmit}
              disabled={submitting || !quantity || Number(quantity) <= 0}
              className={clsx(
                'w-full py-3 rounded-lg text-sm font-semibold transition disabled:opacity-50',
                isBuy
                  ? 'bg-nq-green text-white hover:bg-nq-green/90'
                  : 'bg-nq-red text-white hover:bg-nq-red/90'
              )}
            >
              {submitting
                ? 'Submitting...'
                : `${side.toUpperCase()} ${quantity} ${symbol}`}
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
