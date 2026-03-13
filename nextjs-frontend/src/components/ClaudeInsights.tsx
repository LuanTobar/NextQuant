'use client';

import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { useSwipeable } from 'react-swipeable';
import { useDecisionStream, AgentDecision } from '@/hooks/useDecisionStream';

// ── Types from REST API (for scores + historical summary) ────────────────────

interface ClaudeDecision {
  id: string;
  symbol: string;
  action: string;
  recommendation: string;
  confidence: number;
  expectedReturn: number;
  expectedPnl: number;
  riskRewardRatio: number;
  adjustedSize: number | null;
  actualPnl: number | null;
  outcome: string | null;
  executionStatus: string;
  latencyMs: number;
  claudeAnalysis: {
    reasoning?: string;
    execute?: boolean;
    recommendation?: string;
  };
  createdAt: string;
}

interface SymbolScore {
  symbol: string;
  totalTrades: number;
  wins: number;
  losses: number;
  winRate: number;
  totalPnl: number;
  avgConfidence: number;
}

interface ClaudeData {
  decisions: ClaudeDecision[];
  scores: SymbolScore[];
  summary: {
    totalDecisions: number;
    approvals: number;
    rejections: number;
    reductions: number;
    approvalRate: string;
    avgLatencyMs: number;
  };
}

// ── Main component ────────────────────────────────────────────────────────────

const TABS = ['live', 'history', 'scores'] as const;
type Tab = typeof TABS[number];

export function ClaudeInsights() {
  const [activeTab, setActiveTab] = useState<Tab>('live');

  // Swipe left/right to navigate tabs
  const swipeHandlers = useSwipeable({
    onSwipedLeft: () => {
      const idx = TABS.indexOf(activeTab);
      if (idx < TABS.length - 1) setActiveTab(TABS[idx + 1]);
    },
    onSwipedRight: () => {
      const idx = TABS.indexOf(activeTab);
      if (idx > 0) setActiveTab(TABS[idx - 1]);
    },
    trackTouch: true,
    delta: 40,
  });

  // Live decisions via SSE (real-time, <1s latency)
  const { decisions: liveDecisions, connected } = useDecisionStream();

  // Historical summary + scores via REST (slower-changing data, 60s poll)
  const { data, isLoading } = useQuery<ClaudeData>({
    queryKey: ['claude-decisions'],
    queryFn: async () => {
      const res = await fetch('/api/claude-decisions?limit=50');
      if (!res.ok) throw new Error('Failed to fetch');
      return res.json();
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const summary = data?.summary;
  const avgLatency = liveDecisions.length > 0
    ? Math.round(liveDecisions.reduce((s, d) => s + d.claude.latencyMs, 0) / liveDecisions.length)
    : summary?.avgLatencyMs ?? 0;

  return (
    <div className="bg-nq-card border border-nq-border rounded-lg overflow-hidden" {...swipeHandlers}>
      {/* Header */}
      <div className="px-4 pt-3.5 pb-3 border-b border-nq-border"
        style={{ background: 'linear-gradient(135deg, #10b98110 0%, #111827 60%)' }}
      >
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-nq-text flex items-center gap-2">
            🤖 Claude Intelligence
            {connected ? (
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-nq-green opacity-75" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-nq-green" />
              </span>
            ) : (
              <span className="w-1.5 h-1.5 bg-nq-muted rounded-full" />
            )}
          </h3>
          <span className="text-[10px] text-nq-muted font-mono">{avgLatency > 0 ? `${avgLatency}ms` : '—'}</span>
        </div>
      </div>
      <div className="p-4">

      {/* Summary bar (from REST) */}
      {summary && (
        <div className="grid grid-cols-4 gap-2 mb-3">
          <StatBox label="Decisions" value={summary.totalDecisions} />
          <StatBox label="Approved" value={`${summary.approvalRate}%`} color="text-nq-green" />
          <StatBox label="Rejected"  value={summary.rejections} color="text-nq-red" />
          <StatBox label="Reduced"   value={summary.reductions} color="text-nq-yellow" />
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 mb-3 border-b border-nq-border">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-2 py-1 text-[10px] font-medium transition-colors border-b-2 ${
              activeTab === tab
                ? 'text-nq-accent border-nq-accent'
                : 'text-nq-muted border-transparent hover:text-nq-text'
            }`}
          >
            {tab === 'live' ? 'Live' : tab === 'history' ? 'History' : 'Scores'}
            {tab === 'live' && liveDecisions.length > 0 && (
              <span className="ml-1 text-[8px] bg-nq-accent/20 text-nq-accent px-1 rounded-full">
                {liveDecisions.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'live' && <LiveTab decisions={liveDecisions} connected={connected} />}
      {activeTab === 'history' && (
        isLoading
          ? <div className="text-nq-muted text-xs animate-pulse">Loading…</div>
          : data
          ? <OverviewTab decisions={data.decisions} />
          : <Empty msg="No history yet." />
      )}
      {activeTab === 'scores' && (
        isLoading
          ? <div className="text-nq-muted text-xs animate-pulse">Loading…</div>
          : data
          ? <ScoresTab scores={data.scores} />
          : <Empty msg="No scores yet." />
      )}
      </div>
    </div>
  );
}

// ── Tabs ──────────────────────────────────────────────────────────────────────

function LiveTab({ decisions, connected }: { decisions: AgentDecision[]; connected: boolean }) {
  if (!connected && decisions.length === 0) {
    return <Empty msg="Waiting for agent decisions…" />;
  }
  if (decisions.length === 0) {
    return <Empty msg="No decisions yet this session." />;
  }

  return (
    <div className="space-y-2 max-h-[220px] overflow-y-auto">
      {decisions.map((d, i) => (
        <div
          key={`${d.symbol}-${d.timestamp}-${i}`}
          className="flex items-start gap-2 p-2 rounded bg-nq-bg border border-nq-border"
        >
          <RecBadge rec={d.claude.recommendation} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs font-semibold text-nq-text">{d.symbol}</span>
              <span className="text-[10px] text-nq-muted">{d.action}</span>
              {d.guardian.vetoed && (
                <span className="text-[9px] px-1 rounded bg-nq-red/20 text-nq-red">
                  VETOED
                </span>
              )}
              <span
                className={`text-[9px] px-1 rounded ${
                  d.status === 'EXECUTED'
                    ? 'bg-nq-green/20 text-nq-green'
                    : d.status === 'FAILED'
                    ? 'bg-nq-red/20 text-nq-red'
                    : 'bg-nq-border text-nq-muted'
                }`}
              >
                {d.status}
              </span>
            </div>
            <p className="text-[10px] text-nq-muted leading-tight mt-0.5 truncate">
              {d.claude.reasoning}
            </p>
            <div className="flex gap-2 mt-1 text-[9px] text-nq-muted">
              <span>Conf: {(d.claude.confidence * 100).toFixed(0)}%</span>
              <span>R/R: {d.claude.riskRewardRatio.toFixed(1)}x</span>
              <span>EV: {d.claude.expectedReturn > 0 ? '+' : ''}{(d.claude.expectedReturn * 100).toFixed(2)}%</span>
              <span>{d.claude.latencyMs}ms</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function OverviewTab({ decisions }: { decisions: ClaudeDecision[] }) {
  return (
    <div className="space-y-2 max-h-[200px] overflow-y-auto">
      {decisions.slice(0, 5).map((d) => (
        <div
          key={d.id}
          className="flex items-start gap-2 p-2 rounded bg-nq-bg border border-nq-border"
        >
          <RecBadge rec={d.recommendation} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-nq-text">{d.symbol}</span>
              <span className="text-[10px] text-nq-muted">{d.action}</span>
              {d.outcome && (
                <span
                  className={`text-[9px] px-1 rounded ${
                    d.outcome === 'WIN' ? 'bg-nq-green/20 text-nq-green' : 'bg-nq-red/20 text-nq-red'
                  }`}
                >
                  {d.outcome} {d.actualPnl != null && `$${d.actualPnl.toFixed(2)}`}
                </span>
              )}
            </div>
            <p className="text-[10px] text-nq-muted leading-tight mt-0.5 truncate">
              {d.claudeAnalysis?.reasoning ?? 'No reasoning available'}
            </p>
            <div className="flex gap-2 mt-1 text-[9px] text-nq-muted">
              <span>Conf: {(d.confidence * 100).toFixed(0)}%</span>
              <span>R/R: {d.riskRewardRatio.toFixed(1)}x</span>
              <span>EV: {d.expectedReturn > 0 ? '+' : ''}{(d.expectedReturn * 100).toFixed(2)}%</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ScoresTab({ scores }: { scores: SymbolScore[] }) {
  if (scores.length === 0) return <Empty msg="Scores update when positions close." />;

  return (
    <div className="space-y-2 max-h-[200px] overflow-y-auto">
      {[...scores].sort((a, b) => b.totalPnl - a.totalPnl).map((s) => (
        <div key={s.symbol} className="p-2 rounded bg-nq-bg border border-nq-border">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-nq-text">{s.symbol}</span>
            <span className={`text-xs font-bold ${s.totalPnl >= 0 ? 'text-nq-green' : 'text-nq-red'}`}>
              {s.totalPnl >= 0 ? '+' : ''}${s.totalPnl.toFixed(2)}
            </span>
          </div>
          <div className="flex gap-3 mt-1 text-[9px] text-nq-muted">
            <span>{s.totalTrades} trades</span>
            <span className="text-nq-green">{s.wins}W</span>
            <span className="text-nq-red">{s.losses}L</span>
            <span className={s.winRate >= 55 ? 'text-nq-green' : s.winRate < 45 ? 'text-nq-red' : 'text-nq-yellow'}>
              {s.winRate.toFixed(1)}% win
            </span>
            <span>Avg conf: {(s.avgConfidence * 100).toFixed(0)}%</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Shared helpers ────────────────────────────────────────────────────────────

function Empty({ msg }: { msg: string }) {
  return <div className="text-nq-muted text-xs py-2">{msg}</div>;
}

function StatBox({ label, value, color = 'text-nq-text' }: { label: string; value: string | number; color?: string }) {
  return (
    <div className="text-center">
      <div className={`text-sm font-bold ${color}`}>{value}</div>
      <div className="text-[9px] text-nq-muted">{label}</div>
    </div>
  );
}

function RecBadge({ rec, small = false }: { rec: string; small?: boolean }) {
  const styles: Record<string, string> = {
    APPROVE:  'bg-nq-green/20 text-nq-green',
    EXECUTE:  'bg-nq-green/20 text-nq-green',
    REJECT:   'bg-nq-red/20 text-nq-red',
    REDUCE:   'bg-nq-yellow/20 text-nq-yellow',
  };
  return (
    <span className={`${small ? 'text-[8px] px-1' : 'text-[9px] px-1.5 py-0.5'} rounded font-medium ${styles[rec] ?? 'bg-nq-border text-nq-muted'}`}>
      {rec}
    </span>
  );
}
