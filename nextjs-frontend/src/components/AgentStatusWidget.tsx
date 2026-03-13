'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useDecisionStream } from '@/hooks/useDecisionStream';
import { NQProgress } from './ui/NQProgress';
import { AgentPanel } from './AgentPanel';

function fmt(n: number, decimals = 2) {
  return n.toFixed(decimals);
}

export function AgentStatusWidget() {
  const { agentStatus, connected } = useDecisionStream();
  const [panelOpen, setPanelOpen] = useState(false);

  const status = agentStatus;
  const prevStatusRef = useRef<string | null>(null);
  const [burstKey, setBurstKey] = useState(0);

  // Trigger pulse-burst animation on status transition
  useEffect(() => {
    const current = status?.status ?? null;
    if (prevStatusRef.current !== null && prevStatusRef.current !== current) {
      setBurstKey((k) => k + 1);
    }
    prevStatusRef.current = current;
  }, [status?.status]);

  const lossUsedPct =
    status && status.dailyLossLimitUsd > 0
      ? Math.min(100, (Math.abs(Math.min(0, status.dailyPnlUsd)) / status.dailyLossLimitUsd) * 100)
      : 0;

  const dailyPnlPositive = !status || status.dailyPnlUsd >= 0;

  return (
    <>
      {/* Status bar */}
      <div className="bg-nq-card border border-nq-border rounded-lg px-4 py-2.5 flex flex-wrap items-center gap-x-5 gap-y-2">
        {/* Status indicator */}
        <div className="flex items-center gap-1.5 shrink-0">
          {!connected || !status ? (
            <>
              <span className="w-2 h-2 rounded-full bg-nq-muted" />
              <span className="text-xs text-nq-muted">Agent offline</span>
            </>
          ) : status.status === 'running' ? (
            <>
              <span key={burstKey} className="relative flex h-2 w-2">
                <motion.span
                  key={`burst-${burstKey}`}
                  className="absolute inset-0 rounded-full bg-nq-green"
                  initial={{ scale: 1, opacity: 0.8 }}
                  animate={{ scale: 2.5, opacity: 0 }}
                  transition={{ duration: 0.7, ease: 'easeOut' }}
                />
                <span className="relative inline-flex w-2 h-2 rounded-full bg-nq-green animate-pulse" />
              </span>
              <span className="text-xs text-nq-green font-medium">Running</span>
            </>
          ) : (
            <>
              <span className="w-2 h-2 rounded-full bg-nq-yellow animate-pulse" />
              <span className="text-xs text-nq-yellow font-medium">Paused</span>
            </>
          )}
        </div>

        {/* Metrics — only shown when online */}
        {status && (
          <>
            <Metric
              label="Positions"
              value={`${status.openPositions}/${status.maxPositions}`}
            />
            <Metric
              label="Daily P&L"
              value={`${dailyPnlPositive ? '+' : ''}$${fmt(status.dailyPnlUsd)}`}
              valueClass={dailyPnlPositive ? 'text-nq-green' : 'text-nq-red'}
            />
            <Metric
              label="Decisions"
              value={status.decisionsToday}
            />
            <Metric
              label="Drawdown"
              value={`${fmt(status.drawdownPct)}%`}
              valueClass={status.drawdownPct > status.maxDrawdownPct * 0.8 ? 'text-nq-red' : 'text-nq-muted'}
            />
            <Metric
              label="Broker"
              value={status.broker.toUpperCase()}
            />

            {/* Daily loss progress */}
            {lossUsedPct > 0 && (
              <div className="flex items-center gap-1.5 ml-auto">
                <span className="text-[9px] text-nq-muted">Daily loss limit</span>
                <div className="w-20">
                  <NQProgress value={lossUsedPct} invert height="h-1.5" />
                </div>
                <span className="text-[9px] text-nq-muted">{fmt(lossUsedPct, 0)}%</span>
              </div>
            )}
          </>
        )}

        {/* Manage button */}
        <motion.button
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.96 }}
          onClick={() => setPanelOpen(true)}
          className="ml-auto text-[10px] px-2.5 py-1 rounded border border-nq-border text-nq-muted hover:text-nq-text hover:border-nq-accent transition-colors shrink-0"
        >
          Manage
        </motion.button>
      </div>

      {/* AgentPanel slide-over */}
      <AnimatePresence>
        {panelOpen && (
          <div className="fixed inset-0 z-50 flex justify-end">
            {/* Backdrop */}
            <motion.div
              className="absolute inset-0 bg-black/50"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setPanelOpen(false)}
            />
            {/* Panel — full-width on mobile, max-md on desktop */}
            <motion.div
              className="relative w-full sm:max-w-md bg-nq-bg border-l border-nq-border overflow-y-auto"
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', stiffness: 320, damping: 30 }}
            >
              {/* Drag handle (mobile) */}
              <div className="flex sm:hidden justify-center py-2">
                <div className="w-10 h-1 rounded-full bg-nq-border" />
              </div>
              <div className="flex items-center justify-between px-4 py-3 border-b border-nq-border">
                <h2 className="text-sm font-semibold text-nq-text">Agent Configuration</h2>
                <button
                  onClick={() => setPanelOpen(false)}
                  className="text-nq-muted hover:text-nq-text transition-colors text-lg leading-none w-8 h-8 flex items-center justify-center rounded hover:bg-nq-card"
                >
                  ✕
                </button>
              </div>
              <div className="p-4">
                <AgentPanel />
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}

function Metric({
  label,
  value,
  valueClass = 'text-nq-text',
}: {
  label: string;
  value: string | number;
  valueClass?: string;
}) {
  return (
    <div className="flex flex-col items-center leading-tight">
      <span className={`text-xs font-semibold ${valueClass}`}>{value}</span>
      <span className="text-[9px] text-nq-muted">{label}</span>
    </div>
  );
}
