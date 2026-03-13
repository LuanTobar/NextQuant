'use client';

import { useSession } from 'next-auth/react';
import { Header } from '@/components/Header';
import { AnalyticsDashboard } from '@/components/AnalyticsDashboard';
import Link from 'next/link';

export default function AnalyticsPage() {
  const { data: session } = useSession();
  const isPro = session?.user?.plan === 'PRO';

  if (!isPro) {
    return (
      <main className="min-h-screen">
        <Header />
        <div className="flex items-center justify-center py-32">
          <div className="text-center space-y-4">
            <div className="mx-auto h-16 w-16 rounded-2xl bg-nq-accent/10 flex items-center justify-center">
              <svg className="h-8 w-8 text-nq-accent" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 10.5V6.75a4.5 4.5 0 1 0-9 0v3.75m-.75 11.25h10.5a2.25 2.25 0 0 0 2.25-2.25v-6.75a2.25 2.25 0 0 0-2.25-2.25H6.75a2.25 2.25 0 0 0-2.25 2.25v6.75a2.25 2.25 0 0 0 2.25 2.25Z" />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-nq-text">Analytics is a Pro feature</h2>
            <p className="text-sm text-nq-muted max-w-sm">
              Upgrade to Pro to access advanced analytics, performance charts, and trading insights.
            </p>
            <Link
              href="/settings"
              className="inline-block px-5 py-2.5 text-sm font-medium rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition"
            >
              Upgrade to Pro
            </Link>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen">
      <Header />
      <AnalyticsDashboard />
    </main>
  );
}
