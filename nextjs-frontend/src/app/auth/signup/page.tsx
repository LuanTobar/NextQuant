'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

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
      const res = await fetch('/api/auth/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password }),
      });

      const data = await res.json();

      if (!res.ok) {
        setError(data.error || 'Signup failed');
        setLoading(false);
        return;
      }

      // Redirect to verify email page instead of auto-login
      if (data.requiresVerification) {
        router.push('/auth/verify-email');
      } else {
        router.push('/auth/login');
      }
    } catch {
      setError('Something went wrong. Please try again.');
    }

    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-nq-bg px-4">
      <div className="w-full max-w-md space-y-8">
        {/* Logo */}
        <div className="text-center">
          <div className="mx-auto h-12 w-12 rounded-xl bg-nq-accent flex items-center justify-center font-bold text-white text-lg">
            NQ
          </div>
          <h2 className="mt-4 text-2xl font-bold text-nq-text">
            Create your account
          </h2>
          <p className="mt-2 text-sm text-nq-muted">
            Start with free crypto signals — upgrade anytime
          </p>
        </div>

        {/* Signup Form */}
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="rounded-lg bg-nq-red/10 border border-nq-red/20 px-4 py-3 text-sm text-nq-red">
              {error}
            </div>
          )}

          <div>
            <label htmlFor="name" className="block text-sm font-medium text-nq-muted mb-1">
              Name
            </label>
            <input
              id="name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full rounded-lg border border-nq-border bg-nq-card px-4 py-3 text-nq-text placeholder-nq-muted/50 focus:border-nq-accent focus:outline-none focus:ring-1 focus:ring-nq-accent transition"
              placeholder="Your name"
            />
          </div>

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
            <label htmlFor="password" className="block text-sm font-medium text-nq-muted mb-1">
              Password
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
            {loading ? 'Creating account...' : 'Create account'}
          </button>
        </form>

        <p className="text-center text-xs text-nq-muted leading-relaxed">
          By creating an account, you agree to our{' '}
          <Link href="/terms" className="text-nq-accent hover:underline">Terms of Service</Link>
          {' '}and{' '}
          <Link href="/privacy" className="text-nq-accent hover:underline">Privacy Policy</Link>.
        </p>

        <p className="text-center text-sm text-nq-muted">
          Already have an account?{' '}
          <Link href="/auth/login" className="text-nq-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
