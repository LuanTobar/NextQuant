'use client';

export type NQBadgeVariant = 'green' | 'red' | 'yellow' | 'accent' | 'muted';

const VARIANT_STYLES: Record<NQBadgeVariant, string> = {
  green:  'bg-nq-green/20 text-nq-green border-nq-green/30',
  red:    'bg-nq-red/20 text-nq-red border-nq-red/30',
  yellow: 'bg-nq-yellow/20 text-nq-yellow border-nq-yellow/30',
  accent: 'bg-nq-accent/20 text-nq-accent border-nq-accent/30',
  muted:  'bg-nq-border/50 text-nq-muted border-nq-border',
};

export function NQBadge({
  children,
  variant = 'muted',
  border = false,
  className = '',
}: {
  children: React.ReactNode;
  variant?: NQBadgeVariant;
  border?: boolean;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-medium ${
        border ? 'border' : ''
      } ${VARIANT_STYLES[variant]} ${className}`}
    >
      {children}
    </span>
  );
}
