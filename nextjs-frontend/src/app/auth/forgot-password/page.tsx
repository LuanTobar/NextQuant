'use client';

import { useState } from 'react';
import Link from 'next/link';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const res = await fetch('/api/auth/forgot-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });

      if (res.status === 429) {
        setError('Too many requests. Please wait a moment.');
      } else {
        setSubmitted(true);
      }
    } catch {
      setError('Something went wrong. Please try again.');
    }

    setLoading(false);
  };

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-nq-bg px-4">
        <div className="w-full max-w-md space-y-6 text-center">
          <div className="mx-auto h-16 w-16 rounded-2xl bg-nq-green/10 flex items-center justify-center">
            <svg className="h-8 w-8 text-nq-green" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-nq-text">Check your email</h2>
          <p className="text-sm text-nq-muted leading-relaxed">
            If an account exists with <span className="text-nq-text">{email}</span>,
            you&apos;ll receive a password reset link shortly.
          </p>
          <Link
            href="/auth/login"
            className="inline-block text-sm text-nq-accent hover:underline"
          >
            ← Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-nq-bg px-4">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 rounded-xl bg-nq-accent flex items-center justify-center font-bold text-white text-lg">
            NQ
          </div>
          <h2 className="mt-4 text-2xl font-bold text-nq-text">
            Reset your password
          </h2>
          <p className="mt-2 text-sm text-nq-muted">
            Enter your email and we&apos;ll send you a reset link
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="rounded-lg bg-nq-red/10 border border-nq-red/20 px-4 py-3 text-sm text-nq-red">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-nq-muted mb-1">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-lg border border-nq-border bg-nq-card px-4 py-3 text-nq-text placeholder-nq-muted/50 focus:border-nq-accent focus:outline-none focus:ring-1 focus:ring-nq-accent transition"
              placeholder="you@example.com"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-nq-accent px-4 py-3 text-sm font-semibold text-white hover:bg-nq-accent/90 disabled:opacity-50 transition"
          >
            {loading ? 'Sending...' : 'Send reset link'}
          </button>
        </form>

        <p className="text-center text-sm text-nq-muted">
          Remember your password?{' '}
          <Link href="/auth/login" className="text-nq-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
