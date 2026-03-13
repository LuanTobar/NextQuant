'use client';

import { useEffect, useRef, useState } from 'react';

export interface AgentDecision {
  timestamp: string;
  userId: string;
  symbol: string;
  exchange: string;
  action: 'OPEN_LONG' | 'CLOSE' | 'HOLD';
  originalAction: string;
  quantity: number;
  price: number;
  reason: string;
  brokerOrderId: string | null;
  status: 'EXECUTED' | 'SKIPPED' | 'FAILED';
  guardian: { vetoed: boolean; severity: string; reason: string };
  claude: {
    recommendation: string;
    confidence: number;
    expectedReturn: number;
    riskRewardRatio: number;
    reasoning: string;
    latencyMs: number;
  };
}

export interface AgentStatus {
  timestamp: string;
  userId: string;
  status: 'running' | 'paused';
  broker: string;
  openPositions: number;
  maxPositions: number;
  dailyPnlUsd: number;
  dailyLossLimitUsd: number;
  drawdownPct: number;
  maxDrawdownPct: number;
  equity: number;
  peakEquity: number;
  decisionsToday: number;
  tradesExecutedToday: number;
  uptime: number;
}

const MAX_DECISIONS = 20;

function makeStream(
  url: string,
  onMessage: (data: string) => void,
  onConnect: (ok: boolean) => void,
  cancelled: () => boolean,
): EventSource | null {
  if (cancelled()) return null;

  const es = new EventSource(url);
  es.onopen = () => onConnect(true);
  es.onmessage = (e) => onMessage(e.data);
  es.onerror = () => {
    onConnect(false);
    es.close();
    if (!cancelled()) setTimeout(() => makeStream(url, onMessage, onConnect, cancelled), 3_000);
  };
  return es;
}

/**
 * Opens two SSE streams: /api/stream/decisions and /api/stream/status.
 * Maintains the last 20 agent decisions and the latest agent status.
 */
export function useDecisionStream() {
  const [decisions, setDecisions] = useState<AgentDecision[]>([]);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [connected, setConnected] = useState(false);

  const cancelledRef = useRef(false);
  const decEsRef = useRef<EventSource | null>(null);
  const stEsRef = useRef<EventSource | null>(null);

  useEffect(() => {
    cancelledRef.current = false;

    decEsRef.current = makeStream(
      '/api/stream/decisions',
      (data) => {
        try {
          const d: AgentDecision = JSON.parse(data);
          if (!d.symbol) return;
          setDecisions((prev) => [d, ...prev].slice(0, MAX_DECISIONS));
        } catch { /* skip */ }
      },
      (ok) => setConnected(ok),
      () => cancelledRef.current,
    );

    stEsRef.current = makeStream(
      '/api/stream/status',
      (data) => {
        try {
          const s: AgentStatus = JSON.parse(data);
          if (s.userId) setAgentStatus(s);
        } catch { /* skip */ }
      },
      () => {},
      () => cancelledRef.current,
    );

    return () => {
      cancelledRef.current = true;
      decEsRef.current?.close();
      stEsRef.current?.close();
    };
  }, []);

  return { decisions, agentStatus, connected };
}
