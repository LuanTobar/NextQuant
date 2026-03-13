import { NextResponse } from 'next/server';
import { getLatestSignals } from '@/lib/questdb-client';
import { getCurrentUser, getAllowedExchanges } from '@/lib/plan-guard';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const user = await getCurrentUser();
    const allowedExchanges = getAllowedExchanges(user?.plan || 'FREE');

    const signals = await getLatestSignals();

    if (!signals || signals.length === 0) {
      return NextResponse.json([]);
    }

    // Map to MLSignal format expected by frontend
    const mapped = signals
      .filter((s) => allowedExchanges.includes(s.exchange || 'US'))
      .map((s) => ({
      timestamp: s.timestamp,
      symbol: s.symbol,
      exchange: s.exchange || 'US',
      current_price: s.current_price,
      signal: s.signal,
      causal_effect: s.causal_effect,
      causal_description: s.causal_description || '',
      predicted_close: s.predicted_close,
      confidence_low: s.confidence_low,
      confidence_high: s.confidence_high,
      regime: s.regime,
      regime_probabilities: inferRegimeProbabilities(s.regime),
      volatility: s.volatility,
    }));

    return NextResponse.json(mapped);
  } catch (error) {
    console.error('Failed to fetch signals:', error);
    return NextResponse.json([]);
  }
}

function inferRegimeProbabilities(regime: string): Record<string, number> {
  // Since QuestDB stores the classified regime but not full probabilities,
  // reconstruct approximate probabilities based on the winning regime
  switch (regime) {
    case 'LOW_VOL':
      return { LOW_VOL: 0.75, MEDIUM_VOL: 0.2, HIGH_VOL: 0.05 };
    case 'HIGH_VOL':
      return { LOW_VOL: 0.05, MEDIUM_VOL: 0.2, HIGH_VOL: 0.75 };
    case 'MEDIUM_VOL':
    default:
      return { LOW_VOL: 0.15, MEDIUM_VOL: 0.7, HIGH_VOL: 0.15 };
  }
}
