'use client';

import { motion } from 'framer-motion';

function progressColor(pct: number, invert = false): string {
  if (invert) {
    // Higher = worse (e.g. loss usage)
    return pct > 80 ? 'bg-nq-red' : pct > 50 ? 'bg-nq-yellow' : 'bg-nq-green';
  }
  return pct >= 70 ? 'bg-nq-green' : pct >= 45 ? 'bg-nq-yellow' : 'bg-nq-red';
}

export function NQProgress({
  value,
  max = 100,
  /** Invert color logic: high value = red (for risk/loss bars) */
  invert = false,
  className = '',
  height = 'h-1.5',
}: {
  value: number;
  max?: number;
  invert?: boolean;
  className?: string;
  height?: string;
}) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100));
  const color = progressColor(pct, invert);

  return (
    <div className={`w-full ${height} bg-nq-border rounded-full overflow-hidden ${className}`}>
      <motion.div
        className={`h-full rounded-full ${color}`}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      />
    </div>
  );
}
