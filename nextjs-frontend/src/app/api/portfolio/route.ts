import { NextResponse } from 'next/server';
import { getLatestPrices, getLatestSignals } from '@/lib/questdb-client';
import { getCurrentUser } from '@/lib/plan-guard';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }
    // Query latest prices and signals from QuestDB in parallel
    const [pricesResult, signalsResult] = await Promise.allSettled([
      getLatestPrices(),
      getLatestSignals(),
    ]);

    const priceRows = pricesResult.status === 'fulfilled' ? pricesResult.value : [];
    const signalRows = signalsResult.status === 'fulfilled' ? signalsResult.value : [];

    if (priceRows.length === 0) {
      return NextResponse.json(mockPortfolio());
    }

    // Build price and signal maps
    const prices: Record<string, number> = {};
    for (const row of priceRows) {
      prices[row.symbol] = row.close;
    }

    const signalMap: Record<string, { signal: string; predicted_close: number; regime: string }> = {};
    for (const s of signalRows) {
      signalMap[s.symbol] = {
        signal: s.signal,
        predicted_close: s.predicted_close,
        regime: s.regime,
      };
    }

    const positions = MOCK_POSITIONS.map((pos) => {
      const currentPrice = prices[pos.symbol] || pos.avg_price;
      const pnl = (currentPrice - pos.avg_price) * pos.quantity;
      const pnlPct = ((currentPrice - pos.avg_price) / pos.avg_price) * 100;
      const sig = signalMap[pos.symbol];
      return {
        ...pos,
        current_price: currentPrice,
        pnl: Math.round(pnl * 100) / 100,
        pnl_pct: Math.round(pnlPct * 100) / 100,
        signal: sig?.signal || 'N/A',
        predicted_close: sig?.predicted_close || currentPrice,
        regime: sig?.regime || 'N/A',
      };
    });

    const totalValue = positions.reduce(
      (sum, p) => sum + p.current_price * p.quantity,
      0
    );
    const totalPnl = positions.reduce((sum, p) => sum + p.pnl, 0);

    return NextResponse.json({
      total_value: Math.round(totalValue * 100) / 100,
      daily_pnl: Math.round(totalPnl * 100) / 100,
      daily_pnl_pct: Math.round((totalPnl / (totalValue - totalPnl)) * 10000) / 100,
      sharpe_ratio: 1.85,
      max_drawdown: -4.2,
      positions: positions.map((p) => ({
        ...p,
        weight: (p.current_price * p.quantity) / totalValue,
      })),
    });
  } catch {
    return NextResponse.json(mockPortfolio());
  }
}

const MOCK_POSITIONS = [
  { symbol: 'AAPL', quantity: 50, avg_price: 178.0 },
  { symbol: 'GOOGL', quantity: 40, avg_price: 135.0 },
  { symbol: 'MSFT', quantity: 20, avg_price: 365.0 },
  { symbol: 'AMZN', quantity: 30, avg_price: 150.0 },
  { symbol: 'TSLA', quantity: 15, avg_price: 240.0 },
];

function mockPortfolio() {
  return {
    total_value: 125430.5,
    daily_pnl: 1245.3,
    daily_pnl_pct: 1.0,
    sharpe_ratio: 1.85,
    max_drawdown: -4.2,
    positions: MOCK_POSITIONS.map((p) => ({
      ...p,
      current_price: p.avg_price * 1.03,
      pnl: p.avg_price * 0.03 * p.quantity,
      pnl_pct: 3.0,
      weight: 0.2,
      signal: 'N/A',
      predicted_close: p.avg_price * 1.03,
      regime: 'N/A',
    })),
  };
}
