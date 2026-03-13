'use client';

import { Suspense, useState } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get('token');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!token) {
    return (
      <div className="w-full max-w-md space-y-6 text-center">
        <div className="mx-auto h-16 w-16 rounded-2xl bg-nq-red/10 flex items-center justify-center">
          <svg className="h-8 w-8 text-nq-red" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
          </svg>
        </div>
        <h2 className="text-2xl font-bold text-nq-text">Invalid reset link</h2>
        <p className="text-sm text-nq-muted">This password reset link is invalid or has expired.</p>
        <Link href="/auth/forgot-password" className="inline-block text-sm text-nq-accent hover:underline">
          Request a new link
        </Link>
      </div>
    );
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setLoading(true);

    try {
      const res = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || 'Reset failed');
      } else {
        router.push('/auth/login?reset=true');
      }
    } catch {
      setError('Something went wrong. Please try again.');
    }

    setLoading(false);
  };

  return (
    <div className="w-full max-w-md space-y-8">
      <div className="text-center">
        <div className="mx-auto h-12 w-12 rounded-xl bg-nq-accent flex items-center justify-center font-bold text-white text-lg">
          NQ
        </div>
        <h2 className="mt-4 text-2xl font-bold text-nq-text">
          Set new password
        </h2>
        <p className="mt-2 text-sm text-nq-muted">
          Enter your new password below
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="rounded-lg bg-nq-red/10 border border-nq-red/20 px-4 py-3 text-sm text-nq-red">
            {error}
          </div>
        )}

        <div>
          <label htmlFor="password" className="block text-sm font-medium text-nq-muted mb-1">
            New Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="w-full rounded-lg border border-nq-border bg-nq-card px-4 py-3 text-nq-text placeholder-nq-muted/50 focus:border-nq-accent focus:outline-none focus:ring-1 focus:ring-nq-accent transition"
            placeholder="Min. 8 characters"
          />
        </div>

        <div>
          <label htmlFor="confirmPassword" className="block text-sm font-medium text-nq-muted mb-1">
            Confirm Password
          </label>
          <input
            id="confirmPassword"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            className="w-full rounded-lg border border-nq-border bg-nq-card px-4 py-3 text-nq-text placeholder-nq-muted/50 focus:border-nq-accent focus:outline-none focus:ring-1 focus:ring-nq-accent transition"
            placeholder="Repeat password"
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-nq-accent px-4 py-3 text-sm font-semibold text-white hover:bg-nq-accent/90 disabled:opacity-50 transition"
        >
          {loading ? 'Resetting...' : 'Reset password'}
        </button>
      </form>

      <p className="text-center text-sm text-nq-muted">
        <Link href="/auth/login" className="text-nq-accent hover:underline">
          ← Back to sign in
        </Link>
      </p>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-nq-bg px-4">
      <Suspense fallback={<div className="text-nq-muted">Loading...</div>}>
        <ResetPasswordForm />
      </Suspense>
    </div>
  );
}
