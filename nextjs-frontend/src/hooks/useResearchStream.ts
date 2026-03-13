'use client';

import { useEffect, useRef, useState } from 'react';

export interface ResearchBrief {
  symbol: string;
  exchange: string;
  timestamp: string;
  signal: 'BUY' | 'SELL' | 'HOLD';
  ensemble_confidence: number;
  expected_return: number;
  predicted_close: number;
  regime: string;
  volatility: number;
  causal_effect: number;
  causal_n_significant: number;
  anomaly_detected: boolean;
  anomaly_type: string | null;
  anomaly_severity: number;
  alert_level: 'NORMAL' | 'CAUTION' | 'DANGER';
  market_sentiment: 'BULLISH' | 'NEUTRAL' | 'BEARISH';
}

/**
 * Subscribes to /api/stream/research (SSE) and maintains the latest
 * ResearchBrief per symbol. Reconnects automatically on error.
 */
export function useResearchStream() {
  const [briefs, setBriefs] = useState<Map<string, ResearchBrief>>(new Map());
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;

    function connect() {
      if (cancelled) return;

      const es = new EventSource('/api/stream/research');
      esRef.current = es;

      es.onopen = () => setConnected(true);

      es.onmessage = (e) => {
        try {
          const brief: ResearchBrief = JSON.parse(e.data);
          if (!brief.symbol) return;
          setBriefs((prev) => new Map(prev).set(brief.symbol, brief));
        } catch { /* malformed message */ }
      };

      es.onerror = () => {
        setConnected(false);
        es.close();
        esRef.current = null;
        // Reconnect after 3 s
        if (!cancelled) {
          retryRef.current = setTimeout(connect, 3_000);
        }
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (retryRef.current) clearTimeout(retryRef.current);
      esRef.current?.close();
    };
  }, []);

  return { briefs, connected };
}
