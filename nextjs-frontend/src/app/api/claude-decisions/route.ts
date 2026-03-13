import { NextRequest, NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';
import { getCurrentUser } from '@/lib/plan-guard';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const symbol = searchParams.get('symbol');
    const limit = Math.min(parseInt(searchParams.get('limit') || '20'), 100);

    // Build where clause
    const where: Record<string, unknown> = { userId: user.id };
    if (symbol) {
      where.symbol = symbol;
    }

    // Fetch recent Claude decisions
    const decisions = await prisma.claudeDecision.findMany({
      where,
      orderBy: { createdAt: 'desc' },
      take: limit,
      select: {
        id: true,
        symbol: true,
        action: true,
        recommendation: true,
        confidence: true,
        expectedReturn: true,
        expectedPnl: true,
        riskRewardRatio: true,
        adjustedSize: true,
        entryPrice: true,
        exitPrice: true,
        actualPnl: true,
        outcome: true,
        executionStatus: true,
        latencyMs: true,
        claudeAnalysis: true,
        createdAt: true,
        closedAt: true,
      },
    });

    // Calculate aggregate scores per symbol
    const scoreData = await prisma.claudeDecision.groupBy({
      by: ['symbol'],
      where: {
        userId: user.id,
        action: 'OPEN_LONG',
        outcome: { not: null },
      },
      _count: { id: true },
      _sum: { actualPnl: true },
      _avg: { confidence: true },
    });

    // Calculate win counts separately
    const winData = await prisma.claudeDecision.groupBy({
      by: ['symbol'],
      where: {
        userId: user.id,
        action: 'OPEN_LONG',
        outcome: 'WIN',
      },
      _count: { id: true },
    });

    const winMap = new Map(winData.map(w => [w.symbol, w._count.id]));

    const scores = scoreData.map(s => ({
      symbol: s.symbol,
      totalTrades: s._count.id,
      wins: winMap.get(s.symbol) || 0,
      losses: s._count.id - (winMap.get(s.symbol) || 0),
      winRate: s._count.id > 0
        ? ((winMap.get(s.symbol) || 0) / s._count.id * 100)
        : 0,
      totalPnl: s._sum.actualPnl || 0,
      avgConfidence: s._avg.confidence || 0,
    }));

    // Summary stats
    const totalDecisions = decisions.length;
    const approvals = decisions.filter(d => d.recommendation === 'APPROVE').length;
    const rejections = decisions.filter(d => d.recommendation === 'REJECT').length;
    const reductions = decisions.filter(d => d.recommendation === 'REDUCE').length;
    const avgLatency = decisions.length > 0
      ? Math.round(decisions.reduce((sum, d) => sum + d.latencyMs, 0) / decisions.length)
      : 0;

    return NextResponse.json({
      decisions,
      scores,
      summary: {
        totalDecisions,
        approvals,
        rejections,
        reductions,
        approvalRate: totalDecisions > 0
          ? ((approvals + reductions) / totalDecisions * 100).toFixed(1)
          : '0',
        avgLatencyMs: avgLatency,
      },
    });
  } catch (error) {
    console.error('Failed to fetch Claude decisions:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
