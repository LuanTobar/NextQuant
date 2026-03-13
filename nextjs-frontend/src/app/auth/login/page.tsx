'use client';

import { signIn } from 'next-auth/react';
import { Suspense, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get('callbackUrl') || '/';
  const verified = searchParams.get('verified') === 'true';
  const reset = searchParams.get('reset') === 'true';
  const tokenError = searchParams.get('error');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    const result = await signIn('credentials', {
      email,
      password,
      redirect: false,
    });

    setLoading(false);

    if (result?.error) {
      setError('Invalid email or password');
    } else {
      router.push(callbackUrl);
    }
  };

  return (
    <div className="w-full max-w-md space-y-8">
      {/* Logo */}
      <div className="text-center">
        <div className="mx-auto h-12 w-12 rounded-xl bg-nq-accent flex items-center justify-center font-bold text-white text-lg">
          NQ
        </div>
        <h2 className="mt-4 text-2xl font-bold text-nq-text">
          Sign in to NexQuant
        </h2>
        <p className="mt-2 text-sm text-nq-muted">
          AI-powered investment signals
        </p>
      </div>

      {/* Success Banners */}
      {verified && (
        <div className="rounded-lg bg-nq-green/10 border border-nq-green/20 px-4 py-3 text-sm text-nq-green">
          Email verified successfully! You can now sign in.
        </div>
      )}
      {reset && (
        <div className="rounded-lg bg-nq-green/10 border border-nq-green/20 px-4 py-3 text-sm text-nq-green">
          Password reset successfully! Sign in with your new password.
        </div>
      )}
      {tokenError === 'expired-token' && (
        <div className="rounded-lg bg-nq-yellow/10 border border-nq-yellow/20 px-4 py-3 text-sm text-nq-yellow">
          Verification link expired. Please sign up again or request a new link.
        </div>
      )}
      {tokenError === 'invalid-token' && (
        <div className="rounded-lg bg-nq-red/10 border border-nq-red/20 px-4 py-3 text-sm text-nq-red">
          Invalid verification link.
        </div>
      )}

      {/* Email/Password Form */}
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

        <div>
          <div className="flex items-center justify-between mb-1">
            <label htmlFor="password" className="block text-sm font-medium text-nq-muted">
              Password
            </label>
            <Link href="/auth/forgot-password" className="text-xs text-nq-accent hover:underline">
              Forgot password?
            </Link>
          </div>
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

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-lg bg-nq-accent px-4 py-3 text-sm font-semibold text-white hover:bg-nq-accent/90 disabled:opacity-50 transition"
        >
          {loading ? 'Signing in...' : 'Sign in'}
        </button>
      </form>

      <p className="text-center text-sm text-nq-muted">
        Don&apos;t have an account?{' '}
        <Link href="/auth/signup" className="text-nq-accent hover:underline">
          Create one
        </Link>
      </p>
    </div>
  );
}

export default function LoginPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-nq-bg px-4">
      <Suspense fallback={<div className="text-nq-muted">Loading...</div>}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
