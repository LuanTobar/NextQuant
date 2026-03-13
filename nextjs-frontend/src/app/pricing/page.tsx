import Link from 'next/link';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';

const features: { label: string; free: string | boolean; pro: string | boolean }[] = [
  { label: 'Live ML signals',            free: true,        pro: true },
  { label: 'Research feed',              free: true,        pro: true },
  { label: 'AI chat (Claude)',           free: '10 / day',  pro: 'Unlimited' },
  { label: 'Live trading execution',     free: false,       pro: true },
  { label: 'Max position size',          free: '—',         pro: '$10,000' },
  { label: 'Concurrent positions',       free: '—',         pro: '10' },
  { label: 'Daily loss protection',      free: '—',         pro: 'Up to $5,000' },
  { label: 'Multi-exchange access',      free: 'Crypto',    pro: 'All 5 exchanges' },
  { label: 'Priority support',           free: false,       pro: true },
];

function Cell({ value }: { value: string | boolean }) {
  if (value === true) {
    return <span className="text-emerald-400 font-semibold">✓</span>;
  }
  if (value === false) {
    return <span className="text-zinc-600">—</span>;
  }
  return <span className="text-zinc-300 text-sm">{value}</span>;
}

export default async function PricingPage() {
  const session = await getServerSession(authOptions);
  const isLoggedIn = !!session?.user;
  const isPro = session?.user?.plan === 'PRO';

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-100">
      {/* Nav */}
      <nav className="border-b border-zinc-800 px-6 py-4 flex items-center justify-between">
        <Link href="/" className="text-xl font-bold tracking-tight text-white">
          NexQuant
        </Link>
        <div className="flex items-center gap-4">
          {isLoggedIn ? (
            <Link
              href="/"
              className="text-sm text-zinc-400 hover:text-white transition-colors"
            >
              Dashboard →
            </Link>
          ) : (
            <>
              <Link href="/auth/login" className="text-sm text-zinc-400 hover:text-white transition-colors">
                Sign in
              </Link>
              <Link
                href="/auth/signup"
                className="text-sm bg-zinc-800 hover:bg-zinc-700 text-white px-4 py-2 rounded-lg transition-colors"
              >
                Get started
              </Link>
            </>
          )}
        </div>
      </nav>

      {/* Hero */}
      <section className="max-w-4xl mx-auto px-6 pt-20 pb-12 text-center">
        <div className="inline-flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-medium px-3 py-1 rounded-full mb-6">
          Institutional-grade tools for independent traders
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-4">
          Professional Trading,{' '}
          <span className="text-emerald-400">Simplified</span>
        </h1>
        <p className="text-zinc-400 text-lg max-w-2xl mx-auto">
          ML-driven signals, multi-agent risk analysis, and live execution — all in one
          platform. Start free, upgrade when you&apos;re ready to trade.
        </p>
      </section>

      {/* Plan cards */}
      <section className="max-w-4xl mx-auto px-6 pb-16 grid sm:grid-cols-2 gap-6">
        {/* FREE card */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-2xl p-8 flex flex-col">
          <div className="mb-6">
            <p className="text-xs font-semibold uppercase tracking-widest text-zinc-500 mb-1">Free</p>
            <div className="flex items-end gap-1">
              <span className="text-4xl font-bold">$0</span>
              <span className="text-zinc-500 mb-1">/ mo</span>
            </div>
            <p className="text-zinc-400 text-sm mt-2">Explore the platform at no cost.</p>
          </div>

          {isLoggedIn ? (
            <span className="block text-center text-sm text-zinc-500 py-3 border border-zinc-700 rounded-xl">
              Current plan
            </span>
          ) : (
            <Link
              href="/auth/signup"
              className="block text-center text-sm font-medium bg-zinc-800 hover:bg-zinc-700 text-white py-3 rounded-xl transition-colors"
            >
              Get started free
            </Link>
          )}

          <ul className="mt-6 space-y-3 text-sm text-zinc-400">
            <li>✓ Live ML signals &amp; research feed</li>
            <li>✓ 10 AI chat messages per day</li>
            <li>✓ Crypto market access</li>
            <li className="text-zinc-600">✗ Live trading execution</li>
            <li className="text-zinc-600">✗ Multi-exchange access</li>
          </ul>
        </div>

        {/* PRO card */}
        <div className="bg-zinc-900 border border-emerald-500/40 rounded-2xl p-8 flex flex-col relative overflow-hidden">
          <div className="absolute top-0 right-0 bg-emerald-500 text-zinc-950 text-xs font-bold px-3 py-1 rounded-bl-xl">
            POPULAR
          </div>
          <div className="mb-6">
            <p className="text-xs font-semibold uppercase tracking-widest text-emerald-400 mb-1">Pro</p>
            <div className="flex items-end gap-1">
              <span className="text-4xl font-bold">$29</span>
              <span className="text-zinc-500 mb-1">/ mo</span>
            </div>
            <p className="text-zinc-400 text-sm mt-2">Everything in Free, plus live trading.</p>
          </div>

          {isPro ? (
            <span className="block text-center text-sm text-emerald-400 py-3 border border-emerald-500/30 rounded-xl">
              Current plan
            </span>
          ) : (
            <a
              href="/api/billing/create-checkout"
              className="block text-center text-sm font-medium bg-emerald-500 hover:bg-emerald-400 text-zinc-950 py-3 rounded-xl transition-colors font-semibold"
            >
              {isLoggedIn ? 'Upgrade to PRO' : 'Start free trial'}
            </a>
          )}

          <ul className="mt-6 space-y-3 text-sm text-zinc-300">
            <li>✓ Everything in Free</li>
            <li>✓ Unlimited AI chat</li>
            <li>✓ Live trading via Alpaca &amp; Bitget</li>
            <li>✓ All 5 global exchanges</li>
            <li>✓ Up to $10,000 per position</li>
            <li>✓ Up to 10 concurrent positions</li>
            <li>✓ $5,000 daily loss protection</li>
            <li>✓ Priority support</li>
          </ul>
        </div>
      </section>

      {/* Feature comparison table */}
      <section className="max-w-3xl mx-auto px-6 pb-24">
        <h2 className="text-xl font-semibold text-center mb-8 text-zinc-200">
          Full feature comparison
        </h2>
        <div className="border border-zinc-800 rounded-2xl overflow-hidden">
          {/* Header */}
          <div className="grid grid-cols-3 bg-zinc-900 border-b border-zinc-800 px-6 py-3">
            <span className="text-sm font-medium text-zinc-400">Feature</span>
            <span className="text-sm font-medium text-zinc-400 text-center">Free</span>
            <span className="text-sm font-medium text-emerald-400 text-center">Pro</span>
          </div>

          {/* Rows */}
          {features.map((row, i) => (
            <div
              key={row.label}
              className={`grid grid-cols-3 px-6 py-4 ${
                i % 2 === 0 ? 'bg-zinc-950' : 'bg-zinc-900/50'
              } border-b border-zinc-800 last:border-0`}
            >
              <span className="text-sm text-zinc-300">{row.label}</span>
              <span className="text-center"><Cell value={row.free} /></span>
              <span className="text-center"><Cell value={row.pro} /></span>
            </div>
          ))}
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="border-t border-zinc-800 py-16 text-center">
        <h2 className="text-2xl font-bold mb-3">Ready to start trading smarter?</h2>
        <p className="text-zinc-400 mb-8">
          Join NexQuant and let AI-driven signals work for you.
        </p>
        <div className="flex items-center justify-center gap-4 flex-wrap">
          <Link
            href="/auth/signup"
            className="bg-zinc-800 hover:bg-zinc-700 text-white px-6 py-3 rounded-xl font-medium transition-colors"
          >
            Start for free
          </Link>
          <a
            href="/api/billing/create-checkout"
            className="bg-emerald-500 hover:bg-emerald-400 text-zinc-950 px-6 py-3 rounded-xl font-semibold transition-colors"
          >
            Go PRO — $29/mo
          </a>
        </div>
      </section>
    </main>
  );
}
