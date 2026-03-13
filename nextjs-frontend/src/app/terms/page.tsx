import Link from 'next/link';

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-nq-bg">
      <div className="max-w-3xl mx-auto px-6 py-12 space-y-8">
        <div className="flex items-center gap-3 mb-8">
          <Link href="/" className="text-nq-muted hover:text-nq-text transition">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
            </svg>
          </Link>
          <h1 className="text-2xl font-bold text-nq-text">Terms of Service</h1>
        </div>

        <div className="prose prose-invert max-w-none space-y-6 text-sm text-nq-muted leading-relaxed">
          <section>
            <h2 className="text-lg font-semibold text-nq-text">1. Acceptance of Terms</h2>
            <p>By accessing or using NexQuant (&quot;the Service&quot;), you agree to be bound by these Terms of Service. If you do not agree, do not use the Service.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">2. Description of Service</h2>
            <p>NexQuant provides AI-powered market signals, analytics, and optional automated trading through connected third-party brokers. The Service uses machine learning and causal inference models to generate investment signals.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">3. Not Financial Advice</h2>
            <p className="font-medium text-nq-yellow">NexQuant is NOT a registered investment advisor. All signals, predictions, and AI-generated content are for informational purposes only and do not constitute financial advice. Past performance does not guarantee future results. Trading involves risk of loss.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">4. Broker Connections</h2>
            <p>When you connect a broker account, you authorize NexQuant to place trades on your behalf according to your configured parameters. You are solely responsible for the funds in your brokerage accounts and all trading decisions.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">5. Risk Disclosure</h2>
            <p>Cryptocurrency and stock trading carry significant risk. You may lose some or all of your invested capital. NexQuant does not guarantee any returns. The autonomous trading agent acts within configured limits but market conditions can change rapidly.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">6. Limitation of Liability</h2>
            <p>NexQuant shall not be liable for any trading losses, system downtime, incorrect signals, or failed trade executions. The Service is provided &quot;as is&quot; without warranties of any kind.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">7. Data Security</h2>
            <p>Broker API keys are encrypted at rest. We do not store your brokerage account passwords. However, you are responsible for keeping your account credentials secure.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">8. Account Termination</h2>
            <p>We reserve the right to terminate or suspend your account at any time for violation of these terms. You may delete your account at any time through Settings.</p>
          </section>

          <p className="text-xs text-nq-muted/50 pt-4 border-t border-nq-border">
            Last updated: February 2026
          </p>
        </div>
      </div>
    </div>
  );
}
