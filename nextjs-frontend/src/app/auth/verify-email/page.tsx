'use client';

import { useState } from 'react';
import Link from 'next/link';

export default function VerifyEmailPage() {
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);

  const handleResend = async () => {
    setSending(true);
    try {
      await fetch('/api/auth/send-verification', { method: 'POST' });
      setSent(true);
    } catch {
      // silent fail
    }
    setSending(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-nq-bg px-4">
      <div className="w-full max-w-md space-y-8 text-center">
        <div className="mx-auto h-16 w-16 rounded-2xl bg-nq-accent/10 flex items-center justify-center">
          <svg className="h-8 w-8 text-nq-accent" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
          </svg>
        </div>

        <div>
          <h2 className="text-2xl font-bold text-nq-text">Check your email</h2>
          <p className="mt-3 text-sm text-nq-muted leading-relaxed">
            We&apos;ve sent a verification link to your email address.
            Click the link to activate your NexQuant account.
          </p>
        </div>

        <div className="space-y-3">
          {sent ? (
            <p className="text-sm text-nq-green">Verification email resent!</p>
          ) : (
            <button
              onClick={handleResend}
              disabled={sending}
              className="text-sm text-nq-accent hover:underline disabled:opacity-50"
            >
              {sending ? 'Sending...' : "Didn't receive the email? Resend"}
            </button>
          )}

          <div>
            <Link
              href="/auth/login"
              className="inline-block text-sm text-nq-muted hover:text-nq-text transition"
            >
              ← Back to sign in
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
