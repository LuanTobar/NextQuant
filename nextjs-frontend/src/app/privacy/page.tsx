import Link from 'next/link';

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-nq-bg">
      <div className="max-w-3xl mx-auto px-6 py-12 space-y-8">
        <div className="flex items-center gap-3 mb-8">
          <Link href="/" className="text-nq-muted hover:text-nq-text transition">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
            </svg>
          </Link>
          <h1 className="text-2xl font-bold text-nq-text">Privacy Policy</h1>
        </div>

        <div className="prose prose-invert max-w-none space-y-6 text-sm text-nq-muted leading-relaxed">
          <section>
            <h2 className="text-lg font-semibold text-nq-text">1. Information We Collect</h2>
            <ul className="list-disc pl-5 space-y-1">
              <li><strong>Account data:</strong> email, name, hashed password</li>
              <li><strong>Broker credentials:</strong> encrypted API keys (AES-256)</li>
              <li><strong>Trading data:</strong> orders, positions, P&L from connected brokers</li>
              <li><strong>Usage data:</strong> chat messages, signal interactions, feature usage</li>
              <li><strong>Payment data:</strong> processed by Stripe (we do not store card numbers)</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">2. How We Use Your Data</h2>
            <ul className="list-disc pl-5 space-y-1">
              <li>Execute trades on your behalf via connected brokers</li>
              <li>Generate personalized signals and analytics</li>
              <li>Improve ML model accuracy and signal quality</li>
              <li>Process payments and manage subscriptions</li>
              <li>Send transactional emails (verification, password reset)</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">3. Data Encryption</h2>
            <p>All broker API keys and secrets are encrypted at rest using AES-256 encryption. Passwords are hashed using bcrypt with a cost factor of 12. All data in transit uses TLS 1.3.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">4. Third-Party Services</h2>
            <ul className="list-disc pl-5 space-y-1">
              <li><strong>Stripe:</strong> Payment processing</li>
              <li><strong>Resend:</strong> Transactional emails</li>
              <li><strong>Alpaca/Bitget:</strong> Trade execution (user-initiated)</li>
              <li><strong>Anthropic (Claude):</strong> AI analysis and trading decisions</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">5. Data Retention</h2>
            <p>Trading history and analytics data are retained for the lifetime of your account. Upon account deletion, all personal data is permanently removed within 30 days. Anonymized aggregate data may be retained for model improvement.</p>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">6. Your Rights</h2>
            <ul className="list-disc pl-5 space-y-1">
              <li>Access and export your trading data (CSV/PDF)</li>
              <li>Update or correct your personal information</li>
              <li>Delete your account and all associated data</li>
              <li>Disconnect broker connections at any time</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg font-semibold text-nq-text">7. Cookies</h2>
            <p>We use essential cookies for authentication (NextAuth session). No third-party tracking cookies are used.</p>
          </section>

          <p className="text-xs text-nq-muted/50 pt-4 border-t border-nq-border">
            Last updated: February 2026
          </p>
        </div>
      </div>
    </div>
  );
}
