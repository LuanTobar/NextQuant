import { NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { prisma } from '@/lib/prisma';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const session = await getServerSession(authOptions);
    if (!session?.user?.id) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const decisions = await prisma.claudeDecision.findMany({
      where: { userId: session.user.id },
      orderBy: { createdAt: 'asc' },
    });

    // Group by month
    const monthly: Record<string, { pnl: number; trades: number; wins: number }> = {};

    for (const d of decisions) {
      const month = d.createdAt.toISOString().slice(0, 7); // YYYY-MM
      if (!monthly[month]) monthly[month] = { pnl: 0, trades: 0, wins: 0 };
      monthly[month].pnl += d.actualPnl || 0;
      monthly[month].trades++;
      if (d.outcome === 'WIN') monthly[month].wins++;
    }

    const summary = Object.entries(monthly)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([month, data]) => ({
        month,
        pnl: Math.round(data.pnl * 100) / 100,
        trades: data.trades,
        winRate: data.trades > 0 ? Math.round((data.wins / data.trades) * 100) : 0,
      }));

    const totalPnl = decisions.reduce((sum, d) => sum + (d.actualPnl || 0), 0);
    const totalWins = decisions.filter((d) => d.outcome === 'WIN').length;
    const totalTrades = decisions.length;

    return NextResponse.json({
      monthly: summary,
      overall: {
        totalPnl: Math.round(totalPnl * 100) / 100,
        totalTrades,
        winRate: totalTrades > 0 ? Math.round((totalWins / totalTrades) * 100) : 0,
        avgPnlPerTrade: totalTrades > 0 ? Math.round((totalPnl / totalTrades) * 100) / 100 : 0,
      },
    });
  } catch (error) {
    console.error('Performance report error:', error);
    return NextResponse.json({ error: 'Report failed' }, { status: 500 });
  }
}
