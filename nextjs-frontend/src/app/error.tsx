'use client';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-nq-bg px-4">
      <div className="rounded-xl border border-nq-border bg-nq-card p-8 max-w-md text-center space-y-4">
        <div className="mx-auto h-16 w-16 rounded-2xl bg-nq-red/10 flex items-center justify-center">
          <svg className="h-8 w-8 text-nq-red" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-nq-text">Something went wrong</h2>
        <p className="text-sm text-nq-muted">
          {error.message || 'An unexpected error occurred. Please try again.'}
        </p>
        <button
          onClick={reset}
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition"
        >
          Try again
        </button>
      </div>
    </div>
  );
}
