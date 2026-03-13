import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { prisma } from '@/lib/prisma';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    // Check PRO plan
    const user = await prisma.user.findUnique({
      where: { id: session.user.id },
      select: { plan: true },
    });
    if (user?.plan !== 'PRO') {
      return NextResponse.json({ error: 'Pro plan required' }, { status: 403 });
    }

    // Parse time range
    const range = req.nextUrl.searchParams.get('range') || '30d';
    const days = range === '7d' ? 7 : range === '90d' ? 90 : range === 'all' ? 365 : 30;
    const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000);

    const decisions = await prisma.claudeDecision.findMany({
      where: {
        userId: session.user.id,
        createdAt: { gte: since },
      },
      orderBy: { createdAt: 'asc' },
    });

    // Aggregate daily P&L
    const dailyPnl: Record<string, number> = {};
    const symbolStats: Record<string, { wins: number; losses: number; total: number; pnl: number }> = {};
    let approvals = 0;
    let rejections = 0;
    let totalPnl = 0;

    const confidenceData: Array<{ confidence: number; outcome: string }> = [];

    for (const d of decisions) {
      const day = d.createdAt.toISOString().split('T')[0];
      const pnl = d.actualPnl || 0;
      dailyPnl[day] = (dailyPnl[day] || 0) + pnl;
      totalPnl += pnl;

      if (!symbolStats[d.symbol]) {
        symbolStats[d.symbol] = { wins: 0, losses: 0, total: 0, pnl: 0 };
      }
      symbolStats[d.symbol].total++;
      symbolStats[d.symbol].pnl += pnl;

      if (d.outcome === 'WIN') symbolStats[d.symbol].wins++;
      if (d.outcome === 'LOSS') symbolStats[d.symbol].losses++;

      if (d.recommendation === 'APPROVE') approvals++;
      else rejections++;

      if (d.outcome) {
        confidenceData.push({ confidence: d.confidence, outcome: d.outcome });
      }
    }

    // Cumulative P&L
    const cumulativePnl: Array<{ date: string; pnl: number }> = [];
    let running = 0;
    for (const [date, pnl] of Object.entries(dailyPnl).sort()) {
      running += pnl;
      cumulativePnl.push({ date, pnl: Math.round(running * 100) / 100 });
    }

    return NextResponse.json({
      totalDecisions: decisions.length,
      totalPnl: Math.round(totalPnl * 100) / 100,
      approvals,
      rejections,
      dailyPnl: Object.entries(dailyPnl)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([date, pnl]) => ({ date, pnl: Math.round(pnl * 100) / 100 })),
      cumulativePnl,
      symbolStats: Object.entries(symbolStats).map(([symbol, stats]) => ({
        symbol,
        ...stats,
        winRate: stats.total > 0 ? Math.round((stats.wins / stats.total) * 100) : 0,
        pnl: Math.round(stats.pnl * 100) / 100,
      })),
      confidenceData,
    });
  } catch (error) {
    console.error('Analytics error:', error);
    return NextResponse.json({ error: 'Failed to load analytics' }, { status: 500 });
  }
}
