import Link from 'next/link';

interface EmptyStateProps {
  icon?: React.ReactNode;
  title: string;
  description: string;
  ctaLabel?: string;
  ctaHref?: string;
  ctaAction?: () => void;
}

export function EmptyState({ icon, title, description, ctaLabel, ctaHref, ctaAction }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      {icon && (
        <div className="mb-3 text-nq-muted/50">
          {icon}
        </div>
      )}
      <h4 className="text-sm font-medium text-nq-text mb-1">{title}</h4>
      <p className="text-xs text-nq-muted max-w-xs leading-relaxed">{description}</p>
      {ctaLabel && ctaHref && (
        <Link
          href={ctaHref}
          className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition"
        >
          {ctaLabel}
        </Link>
      )}
      {ctaLabel && ctaAction && !ctaHref && (
        <button
          onClick={ctaAction}
          className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition"
        >
          {ctaLabel}
        </button>
      )}
    </div>
  );
}
