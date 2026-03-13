'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';

const STEPS = ['Welcome', 'Broker', 'Risk Profile', 'Ready'];

// ── Questionnaire definition ──────────────────────────────────────────────────

type Question = {
  key: string;
  label: string;
  options: { value: string; label: string }[];
};

const QUESTIONS: Question[] = [
  {
    key: 'investmentHorizon',
    label: 'How long do you plan to hold investments?',
    options: [
      { value: 'SHORT',  label: 'Under 1 year' },
      { value: 'MEDIUM', label: '1–5 years'    },
      { value: 'LONG',   label: 'Over 5 years' },
    ],
  },
  {
    key: 'riskTolerance',
    label: 'If your portfolio fell 20% in a month, you would…',
    options: [
      { value: 'CONSERVATIVE', label: 'Sell immediately'           },
      { value: 'MODERATE',     label: 'Monitor and wait'           },
      { value: 'AGGRESSIVE',   label: 'Buy more — it\'s a dip'    },
    ],
  },
  {
    key: 'experienceLevel',
    label: 'Investment experience',
    options: [
      { value: 'BEGINNER',     label: 'Beginner (< 1 yr)'   },
      { value: 'INTERMEDIATE', label: 'Intermediate (1–5 yr)' },
      { value: 'EXPERT',       label: 'Expert (> 5 yr)'      },
    ],
  },
  {
    key: 'incomeStability',
    label: 'Income & financial cushion',
    options: [
      { value: 'UNSTABLE', label: 'Variable / need the money' },
      { value: 'VARIABLE', label: 'Some buffer'               },
      { value: 'STABLE',   label: 'Stable with wide margin'   },
    ],
  },
  {
    key: 'lossCapacity',
    label: 'Max loss without affecting your lifestyle',
    options: [
      { value: 'LOW',    label: 'Under 10%' },
      { value: 'MEDIUM', label: '10–25%'    },
      { value: 'HIGH',   label: 'Over 25%'  },
    ],
  },
  {
    key: 'primaryGoal',
    label: 'Primary investment goal',
    options: [
      { value: 'CAPITAL_PRESERVATION', label: 'Preserve capital'    },
      { value: 'INCOME',               label: 'Regular income'      },
      { value: 'GROWTH',               label: 'Long-term growth'    },
      { value: 'SPECULATION',          label: 'Max return (high risk)' },
    ],
  },
];

const CATEGORY_BADGE: Record<string, { label: string; color: string }> = {
  CONSERVATIVE: { label: 'Conservative',  color: 'text-blue-400  bg-blue-400/10'  },
  MODERATE:     { label: 'Moderate',      color: 'text-nq-green  bg-nq-green/10'  },
  AGGRESSIVE:   { label: 'Aggressive',    color: 'text-yellow-400 bg-yellow-400/10' },
  SPECULATIVE:  { label: 'Speculative',   color: 'text-red-400   bg-red-400/10'   },
};

// ── Component ─────────────────────────────────────────────────────────────────

export default function OnboardingPage() {
  const router = useRouter();
  const { data: session } = useSession();

  const [step, setStep]     = useState(0);
  const [saving, setSaving] = useState(false);

  // Risk questionnaire state
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [savedCategory, setSavedCategory] = useState<string | null>(null);

  const userName = session?.user?.name?.split(' ')[0] || 'there';

  const allAnswered = QUESTIONS.every(q => !!answers[q.key]);

  // ── Handlers ────────────────────────────────────────────────────────────────

  const saveRiskProfile = async () => {
    setSaving(true);
    try {
      const res = await fetch('/api/risk-profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(answers),
      });
      if (res.ok) {
        const profile = await res.json();
        setSavedCategory(profile?.riskCategory ?? null);
      }
    } catch { /* continue anyway */ }
    setSaving(false);
    setStep(3);
  };

  const handleNext = () => {
    if (step === 2) {
      saveRiskProfile();
    } else {
      setStep(step + 1);
    }
  };

  const completeOnboarding = async () => {
    setSaving(true);
    try {
      await fetch('/api/user/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name:                session?.user?.name,
          email:               session?.user?.email,
          onboardingCompleted: true,
        }),
      });
    } catch { /* ignore */ }
    setSaving(false);
    router.push('/');
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-nq-bg flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-lg space-y-8">

        {/* Progress dots */}
        <div className="flex items-center justify-center gap-2">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div className={`h-2.5 w-2.5 rounded-full transition ${
                i <= step ? 'bg-nq-accent' : 'bg-nq-border'
              }`} />
              {i < STEPS.length - 1 && (
                <div className={`h-0.5 w-8 transition ${
                  i < step ? 'bg-nq-accent' : 'bg-nq-border'
                }`} />
              )}
            </div>
          ))}
        </div>

        {/* Card */}
        <div className="rounded-xl border border-nq-border bg-nq-card p-8 space-y-6">

          {/* ── Step 0: Welcome ── */}
          {step === 0 && (
            <div className="text-center space-y-4">
              <div className="mx-auto h-16 w-16 rounded-2xl bg-nq-accent flex items-center justify-center font-bold text-white text-2xl">
                NQ
              </div>
              <h2 className="text-2xl font-bold text-nq-text">Welcome, {userName}!</h2>
              <p className="text-sm text-nq-muted leading-relaxed max-w-sm mx-auto">
                NexQuant combines causal inference ML with real-time market data across
                5 global exchanges. Let&apos;s get you set up in 60 seconds.
              </p>
            </div>
          )}

          {/* ── Step 1: Connect Broker ── */}
          {step === 1 && (
            <div className="text-center space-y-4">
              <div className="mx-auto h-16 w-16 rounded-2xl bg-nq-green/10 flex items-center justify-center">
                <svg className="h-8 w-8 text-nq-green" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
                </svg>
              </div>
              <h2 className="text-2xl font-bold text-nq-text">Connect a Broker</h2>
              <p className="text-sm text-nq-muted leading-relaxed max-w-sm mx-auto">
                Connect Alpaca (US stocks) or Bitget (crypto) to enable live trading.
                You can skip this and use signals only.
              </p>
              <div className="flex justify-center gap-3">
                <button
                  onClick={() => router.push('/settings')}
                  className="px-4 py-2 text-sm rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition"
                >
                  Connect Now
                </button>
                <button
                  onClick={() => setStep(2)}
                  className="px-4 py-2 text-sm rounded-lg border border-nq-border text-nq-muted hover:text-nq-text transition"
                >
                  Skip for now
                </button>
              </div>
            </div>
          )}

          {/* ── Step 2: Risk Questionnaire ── */}
          {step === 2 && (
            <div className="space-y-5">
              <div className="text-center space-y-1">
                <h2 className="text-xl font-bold text-nq-text">Risk Profile</h2>
                <p className="text-xs text-nq-muted">
                  6 quick questions — we&apos;ll calibrate the agent to match your risk appetite.
                </p>
              </div>

              {QUESTIONS.map((q) => (
                <div key={q.key} className="space-y-2">
                  <p className="text-sm font-medium text-nq-text">{q.label}</p>
                  <div className="flex flex-wrap gap-2">
                    {q.options.map((opt) => {
                      const selected = answers[q.key] === opt.value;
                      return (
                        <button
                          key={opt.value}
                          onClick={() => setAnswers(prev => ({ ...prev, [q.key]: opt.value }))}
                          className={`px-3 py-1.5 text-xs rounded-lg border transition ${
                            selected
                              ? 'bg-nq-accent border-nq-accent text-white'
                              : 'border-nq-border text-nq-muted hover:border-nq-accent/50 hover:text-nq-text'
                          }`}
                        >
                          {opt.label}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}

              {!allAnswered && (
                <p className="text-xs text-nq-muted text-center">
                  Answer all questions to continue
                </p>
              )}
            </div>
          )}

          {/* ── Step 3: Ready ── */}
          {step === 3 && (
            <div className="text-center space-y-4">
              <div className="mx-auto h-16 w-16 rounded-2xl bg-nq-green/10 flex items-center justify-center">
                <svg className="h-8 w-8 text-nq-green" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                </svg>
              </div>
              <h2 className="text-2xl font-bold text-nq-text">You&apos;re all set!</h2>

              {savedCategory && CATEGORY_BADGE[savedCategory] && (
                <div className="flex justify-center">
                  <span className={`px-3 py-1 text-xs font-medium rounded-full ${CATEGORY_BADGE[savedCategory].color}`}>
                    {CATEGORY_BADGE[savedCategory].label} investor profile
                  </span>
                </div>
              )}

              <p className="text-sm text-nq-muted leading-relaxed max-w-sm mx-auto">
                Your dashboard shows live ML signals. Swipe right to invest, left to skip.
                The agent is calibrated to your risk profile.
              </p>
            </div>
          )}
        </div>

        {/* Navigation */}
        <div className="flex justify-between">
          {step > 0 && step !== 1 ? (
            <button
              onClick={() => setStep(step - 1)}
              className="px-4 py-2 text-sm rounded-lg border border-nq-border text-nq-muted hover:text-nq-text transition"
            >
              Back
            </button>
          ) : <div />}

          {step < 3 ? (
            step === 1 ? <div /> : (
              <button
                onClick={handleNext}
                disabled={step === 2 && (!allAnswered || saving)}
                className="px-6 py-2 text-sm font-medium rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition disabled:opacity-40"
              >
                {saving ? 'Saving…' : step === 0 ? "Let's go" : 'Next'}
              </button>
            )
          ) : (
            <button
              onClick={completeOnboarding}
              disabled={saving}
              className="px-6 py-2 text-sm font-medium rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition disabled:opacity-50"
            >
              {saving ? 'Loading…' : 'Go to Dashboard'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
