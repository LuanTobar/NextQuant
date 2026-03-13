'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { useResearchStream, ResearchBrief } from '@/hooks/useResearchStream';
import { NQBadge } from './ui/NQBadge';
import { NQProgress } from './ui/NQProgress';

// ── helpers ──────────────────────────────────────────────────────────────────

function alertVariant(level: ResearchBrief['alert_level']): 'green' | 'yellow' | 'red' {
  return { NORMAL: 'green', CAUTION: 'yellow', DANGER: 'red' }[level] as 'green' | 'yellow' | 'red';
}

function signalVariant(signal: ResearchBrief['signal']): 'green' | 'red' | 'yellow' {
  return { BUY: 'green', SELL: 'red', HOLD: 'yellow' }[signal] as 'green' | 'red' | 'yellow';
}

const alertBorderClass: Record<ResearchBrief['alert_level'], string> = {
  NORMAL:  'border-nq-green/30',
  CAUTION: 'border-nq-yellow/30',
  DANGER:  'border-nq-red/30',
};

const alertBgClass: Record<ResearchBrief['alert_level'], string> = {
  NORMAL:  'bg-nq-green/5',
  CAUTION: 'bg-nq-yellow/5',
  DANGER:  'bg-nq-red/8',
};

function sentimentIcon(sentiment: ResearchBrief['market_sentiment']) {
  return { BULLISH: '▲', BEARISH: '▼', NEUTRAL: '→' }[sentiment];
}

function sentimentColor(sentiment: ResearchBrief['market_sentiment']) {
  return { BULLISH: 'text-nq-green', BEARISH: 'text-nq-red', NEUTRAL: 'text-nq-muted' }[sentiment];
}

// ── sub-components ────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="bg-nq-bg border border-nq-border rounded-lg p-3 animate-pulse space-y-2">
      <div className="h-3 w-16 bg-nq-border rounded" />
      <div className="h-2 w-24 bg-nq-border rounded" />
      <div className="h-1.5 w-full bg-nq-border rounded-full" />
    </div>
  );
}

function BriefCard({ brief }: { brief: ResearchBrief }) {
  const confPct = Math.round(brief.ensemble_confidence * 100);

  return (
    <motion.div
      layout
      whileHover={{ scale: 1.02, y: -2 }}
      transition={{ type: 'spring', stiffness: 380, damping: 26 }}
      className={`rounded-lg border p-3 space-y-2 ${alertBorderClass[brief.alert_level]} ${alertBgClass[brief.alert_level]}`}
    >
      {/* Row 1: symbol + signal + alert */}
      <div className="flex items-center justify-between gap-1">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-bold text-nq-text">{brief.symbol}</span>
          <span className="text-[9px] text-nq-muted">{brief.exchange}</span>
        </div>
        <div className="flex items-center gap-1">
          <NQBadge variant={signalVariant(brief.signal)}>{brief.signal}</NQBadge>
          <NQBadge variant={alertVariant(brief.alert_level)} border>{brief.alert_level}</NQBadge>
        </div>
      </div>

      {/* Row 2: sentiment + regime */}
      <div className="flex items-center justify-between text-[10px]">
        <span className={`font-medium ${sentimentColor(brief.market_sentiment)}`}>
          {sentimentIcon(brief.market_sentiment)} {brief.market_sentiment}
        </span>
        <span className="text-nq-muted truncate max-w-[120px]">{brief.regime}</span>
      </div>

      {/* Row 3: confidence bar */}
      <div>
        <div className="flex justify-between text-[9px] text-nq-muted mb-1">
          <span>Confidence</span>
          <span>{confPct}%</span>
        </div>
        <NQProgress value={confPct} />
      </div>

      {/* Anomaly warning */}
      {brief.anomaly_detected && (
        <NQBadge variant="red" className="w-full justify-start text-[9px] px-2 py-1">
          ⚠ {brief.anomaly_type ?? 'Anomaly'} (sev {brief.anomaly_severity.toFixed(2)})
        </NQBadge>
      )}

      {/* EV + causal */}
      <div className="text-[9px] text-nq-muted">
        EV {brief.expected_return >= 0 ? '+' : ''}{(brief.expected_return * 100).toFixed(2)}%
        {' · '}Causal n={brief.causal_n_significant}
      </div>
    </motion.div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export function LiveSignalFeed() {
  const { briefs, connected } = useResearchStream();
  const items = Array.from(briefs.values()).sort((a, b) => {
    const alertRank = { DANGER: 0, CAUTION: 1, NORMAL: 2 };
    const sigRank   = { BUY: 0, SELL: 1, HOLD: 2 };
    const ar = alertRank[a.alert_level] - alertRank[b.alert_level];
    if (ar !== 0) return ar;
    return sigRank[a.signal] - sigRank[b.signal];
  });

  return (
    <div className="bg-nq-card border border-nq-border rounded-lg p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-nq-text flex items-center gap-1.5">
          📡 Live Signals
          {connected ? (
            <span className="inline-flex items-center gap-1 text-[9px] font-normal text-nq-green">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-nq-green opacity-75" />
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-nq-green" />
              </span>
              LIVE
            </span>
          ) : (
            <span className="text-[9px] font-normal text-nq-muted">connecting…</span>
          )}
        </h3>
        <span className="text-[10px] text-nq-muted">{items.length} symbol{items.length !== 1 ? 's' : ''}</span>
      </div>

      {/* Cards */}
      {items.length === 0 ? (
        <div className="grid grid-cols-2 gap-2">
          {[...Array(4)].map((_, i) => <SkeletonCard key={i} />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2 max-h-[340px] overflow-y-auto pr-1">
          <AnimatePresence initial={false}>
            {items.map((b) => (
              <motion.div
                key={b.symbol}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
              >
                <BriefCard brief={b} />
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}
