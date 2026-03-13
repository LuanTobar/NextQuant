'use client';

import { useState, useCallback } from 'react';
import { useSession } from 'next-auth/react';
import { useSwipeable } from 'react-swipeable';
import { motion, AnimatePresence } from 'framer-motion';
import { useQuery } from '@tanstack/react-query';
import type { MLSignal } from '@/types';
import clsx from 'clsx';
import { OrderConfirmation } from './OrderConfirmation';

// Mock signals (replaced by NATS WS in production)
const MOCK_SIGNALS: MLSignal[] = [
  {
    timestamp: new Date().toISOString(),
    symbol: 'AAPL',
    exchange: 'US',
    current_price: 185.32,
    signal: 'BUY',
    causal_effect: 0.65,
    causal_description: 'Price increase causes 65% volume spike',
    predicted_close: 187.1,
    confidence_low: 183.5,
    confidence_high: 190.7,
    regime: 'MEDIUM_VOL',
    regime_probabilities: { LOW_VOL: 0.15, MEDIUM_VOL: 0.7, HIGH_VOL: 0.15 },
    volatility: 0.22,
  },
  {
    timestamp: new Date().toISOString(),
    symbol: 'TSLA',
    exchange: 'US',
    current_price: 248.5,
    signal: 'SELL',
    causal_effect: -0.32,
    causal_description: 'Negative causal pressure on volume',
    predicted_close: 244.8,
    confidence_low: 238.0,
    confidence_high: 251.6,
    regime: 'HIGH_VOL',
    regime_probabilities: { LOW_VOL: 0.05, MEDIUM_VOL: 0.2, HIGH_VOL: 0.75 },
    volatility: 0.42,
  },
  {
    timestamp: new Date().toISOString(),
    symbol: 'MSFT',
    exchange: 'US',
    current_price: 376.8,
    signal: 'HOLD',
    causal_effect: 0.12,
    causal_description: 'Weak causal relationship',
    predicted_close: 377.5,
    confidence_low: 374.0,
    confidence_high: 381.0,
    regime: 'LOW_VOL',
    regime_probabilities: { LOW_VOL: 0.8, MEDIUM_VOL: 0.15, HIGH_VOL: 0.05 },
    volatility: 0.12,
  },
];

const signalColors = {
  BUY: { bg: 'bg-nq-green/10', text: 'text-nq-green', border: 'border-nq-green/30' },
  SELL: { bg: 'bg-nq-red/10', text: 'text-nq-red', border: 'border-nq-red/30' },
  HOLD: { bg: 'bg-nq-yellow/10', text: 'text-nq-yellow', border: 'border-nq-yellow/30' },
};

const exchangeLabels: Record<string, { label: string; flag: string; currency: string }> = {
  CRYPTO: { label: 'Crypto', flag: '₿', currency: 'USD' },
  US: { label: 'NYSE/NASDAQ', flag: '🇺🇸', currency: 'USD' },
  LSE: { label: 'London', flag: '🇬🇧', currency: 'GBP' },
  BME: { label: 'Madrid', flag: '🇪🇸', currency: 'EUR' },
  TSE: { label: 'Tokyo', flag: '🇯🇵', currency: 'JPY' },
};

const regimeLabels = {
  LOW_VOL: { label: 'Calm', color: 'text-nq-green' },
  MEDIUM_VOL: { label: 'Normal', color: 'text-nq-yellow' },
  HIGH_VOL: { label: 'Volatile', color: 'text-nq-red' },
};

export function SwipeToInvest() {
  const { data: session } = useSession();
  const isPro = session?.user?.plan === 'PRO';
  const [currentIndex, setCurrentIndex] = useState(0);
  const [direction, setDirection] = useState<'left' | 'right' | null>(null);
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [showOrder, setShowOrder] = useState(false);

  const { data: signals, isLoading } = useQuery({
    queryKey: ['ml-signals'],
    queryFn: async () => {
      const res = await fetch('/api/signals');
      if (!res.ok) return MOCK_SIGNALS;
      const data = await res.json();
      return data.length > 0 ? data : MOCK_SIGNALS;
    },
    refetchInterval: 10000, // Poll every 10 seconds
  });

  const cards = signals || MOCK_SIGNALS;
  const currentCard = cards[currentIndex % cards.length];

  const handleSwipe = useCallback(
    (dir: 'left' | 'right') => {
      setDirection(dir);
      if (dir === 'right') {
        setWatchlist((prev) => [...new Set([...prev, currentCard.symbol])]);
        // Haptic feedback on mobile (silent no-op on desktop)
        if (typeof navigator !== 'undefined' && navigator.vibrate) {
          navigator.vibrate([30, 20, 30]);
        }
      }
      setTimeout(() => {
        setCurrentIndex((prev) => prev + 1);
        setDirection(null);
      }, 300);
    },
    [currentCard]
  );

  const handlers = useSwipeable({
    onSwipedLeft: () => handleSwipe('left'),
    onSwipedRight: () => handleSwipe('right'),
    trackMouse: true,
  });

  const sc = signalColors[currentCard.signal as keyof typeof signalColors] || signalColors.HOLD;
  const regime = regimeLabels[currentCard.regime as keyof typeof regimeLabels] || regimeLabels.MEDIUM_VOL;
  const expectedReturn = ((currentCard.predicted_close - currentCard.current_price) / currentCard.current_price * 100).toFixed(2);

  return (
    <div className="space-y-4">
      <div className="bg-nq-card rounded-xl p-5 border border-nq-border">
        <div className="flex justify-between items-center mb-4">
          <p className="text-sm text-nq-muted">AI Signals</p>
          <p className="text-xs text-nq-muted">Swipe right to add to watchlist</p>
        </div>

        <div {...handlers} className="relative h-[340px] flex items-center justify-center">
          <AnimatePresence mode="wait">
            <motion.div
              key={currentIndex}
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{
                scale: 1,
                opacity: 1,
                x: direction === 'left' ? -200 : direction === 'right' ? 200 : 0,
              }}
              exit={{ scale: 0.95, opacity: 0 }}
              transition={{ duration: 0.3 }}
              className={clsx(
                'w-full rounded-xl p-6 border cursor-grab active:cursor-grabbing',
                sc.bg,
                sc.border
              )}
            >
              {/* Symbol + Signal + Exchange */}
              <div className="flex justify-between items-start mb-4">
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-2xl font-bold">{currentCard.symbol}</h3>
                    {currentCard.exchange && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-nq-bg/80 border border-nq-border text-nq-muted">
                        {exchangeLabels[currentCard.exchange]?.flag || '🌐'}{' '}
                        {exchangeLabels[currentCard.exchange]?.label || currentCard.exchange}
                      </span>
                    )}
                  </div>
                  <p className="text-lg text-nq-muted">
                    {exchangeLabels[currentCard.exchange]?.currency === 'GBP' ? '£' :
                     exchangeLabels[currentCard.exchange]?.currency === 'EUR' ? '€' :
                     exchangeLabels[currentCard.exchange]?.currency === 'JPY' ? '¥' : '$'}
                    {currentCard.current_price.toFixed(2)}
                  </p>
                </div>
                <span
                  className={clsx(
                    'px-3 py-1 rounded-full text-sm font-semibold',
                    sc.bg,
                    sc.text
                  )}
                >
                  {currentCard.signal}
                </span>
              </div>

              {/* Prediction */}
              <div className="mb-4">
                <p className="text-xs text-nq-muted mb-1">AI Prediction</p>
                <p className="text-lg font-semibold">
                  ${currentCard.predicted_close.toFixed(2)}
                  <span className={clsx('text-sm ml-2', Number(expectedReturn) >= 0 ? 'text-nq-green' : 'text-nq-red')}>
                    ({Number(expectedReturn) >= 0 ? '+' : ''}{expectedReturn}%)
                  </span>
                </p>
                <p className="text-xs text-nq-muted">
                  Range: ${currentCard.confidence_low.toFixed(2)} - ${currentCard.confidence_high.toFixed(2)}
                </p>
              </div>

              {/* Regime + vol */}
              <div className="mb-4 flex items-center gap-2">
                <span
                  className={clsx(
                    'text-xs font-semibold px-2.5 py-1 rounded-full border',
                    currentCard.regime === 'LOW_VOL'
                      ? 'bg-nq-green/15 text-nq-green border-nq-green/30'
                      : currentCard.regime === 'HIGH_VOL'
                      ? 'bg-nq-red/15 text-nq-red border-nq-red/30'
                      : 'bg-nq-yellow/15 text-nq-yellow border-nq-yellow/30'
                  )}
                >
                  {regime.label}
                </span>
                <span className="text-xs text-nq-muted">
                  vol {(currentCard.volatility * 100).toFixed(1)}%
                </span>
              </div>

              {/* Causal Insight */}
              <div className="bg-nq-bg/70 rounded-lg p-3 border border-nq-border/60">
                <p className="text-[10px] text-nq-muted uppercase tracking-wide mb-1">Causal Insight</p>
                <p className="text-sm text-nq-text">{currentCard.causal_description}</p>
              </div>
            </motion.div>
          </AnimatePresence>
        </div>

        {/* Action buttons */}
        <div className="flex justify-center gap-4 mt-4">
          <button
            onClick={() => handleSwipe('left')}
            className="h-12 w-12 rounded-full border border-nq-red/30 text-nq-red flex items-center justify-center hover:bg-nq-red/10 transition"
            title="Skip"
          >
            ✕
          </button>
          <button
            onClick={() => setShowOrder(true)}
            className={clsx(
              'h-12 px-5 rounded-full border flex items-center justify-center gap-1.5 text-sm font-semibold transition',
              isPro
                ? 'border-nq-accent/30 text-nq-accent hover:bg-nq-accent/10'
                : 'border-nq-border text-nq-muted cursor-not-allowed opacity-50'
            )}
            disabled={!isPro}
            title={isPro ? 'Trade this signal' : 'Upgrade to Pro to trade'}
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
            </svg>
            Trade
          </button>
          <button
            onClick={() => handleSwipe('right')}
            className="h-12 w-12 rounded-full border border-nq-green/30 text-nq-green flex items-center justify-center hover:bg-nq-green/10 transition"
            title="Add to watchlist"
          >
            +
          </button>
        </div>
      </div>

      {/* Watchlist */}
      {watchlist.length > 0 && (
        <div className="bg-nq-card rounded-xl p-4 border border-nq-border">
          <p className="text-sm text-nq-muted mb-2">Watchlist</p>
          <div className="flex flex-wrap gap-2">
            {watchlist.map((sym) => (
              <span
                key={sym}
                className="bg-nq-accent/20 text-nq-accent px-3 py-1 rounded-full text-sm"
              >
                {sym}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Order confirmation modal */}
      <OrderConfirmation
        isOpen={showOrder}
        onClose={() => setShowOrder(false)}
        symbol={currentCard.symbol}
        exchange={currentCard.exchange}
        currentPrice={currentCard.current_price}
        signal={currentCard.signal as 'BUY' | 'SELL' | 'HOLD'}
        predictedClose={currentCard.predicted_close}
      />
    </div>
  );
}
