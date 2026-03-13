import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-nq-bg px-4">
      <div className="rounded-xl border border-nq-border bg-nq-card p-8 max-w-md text-center space-y-4">
        <div className="text-6xl font-bold text-nq-accent/20">404</div>
        <h2 className="text-xl font-semibold text-nq-text">Page not found</h2>
        <p className="text-sm text-nq-muted">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <Link
          href="/"
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition"
        >
          Go to Dashboard
        </Link>
      </div>
    </div>
  );
}
