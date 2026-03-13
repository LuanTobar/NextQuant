/**
 * Positions API
 *
 * GET /api/positions?broker=BITGET — Get real positions from broker,
 * enriched with average entry price from our Orders table.
 */

import { NextRequest, NextResponse } from 'next/server';
import { getCurrentUser } from '@/lib/plan-guard';
import { prisma } from '@/lib/prisma';
import { createBrokerClient } from '@/lib/brokers';

export async function GET(req: NextRequest) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    const broker = req.nextUrl.searchParams.get('broker');
    if (!broker || !['ALPACA', 'BITGET'].includes(broker)) {
      return NextResponse.json(
        { error: 'Invalid broker. Use ?broker=ALPACA or ?broker=BITGET' },
        { status: 400 }
      );
    }

    // Find active connection
    const connection = await prisma.brokerConnection.findFirst({
      where: {
        userId: user.id,
        broker: broker as 'ALPACA' | 'BITGET',
        isActive: true,
      },
    });

    if (!connection) {
      return NextResponse.json(
        { error: `No active ${broker} connection` },
        { status: 404 }
      );
    }

    const client = createBrokerClient(connection);
    const positions = await client.getPositions();

    // For Bitget (spot), avgEntryPrice comes from our Orders table
    // Alpaca already provides avgEntryPrice natively
    if (broker === 'BITGET') {
      // Compute weighted average entry price from filled BUY orders
      const filledBuys = await prisma.order.findMany({
        where: {
          userId: user.id,
          brokerConnectionId: connection.id,
          side: 'BUY',
          status: 'FILLED',
          filledPrice: { not: null },
          filledQuantity: { not: null },
        },
        select: {
          symbol: true,
          filledPrice: true,
          filledQuantity: true,
        },
      });

      // Group buys by symbol and compute weighted average
      const entryPrices = new Map<string, { totalCost: number; totalQty: number }>();
      for (const buy of filledBuys) {
        const existing = entryPrices.get(buy.symbol) || { totalCost: 0, totalQty: 0 };
        existing.totalCost += (buy.filledPrice || 0) * (buy.filledQuantity || 0);
        existing.totalQty += buy.filledQuantity || 0;
        entryPrices.set(buy.symbol, existing);
      }

      // Enrich positions with computed entry prices
      for (const pos of positions) {
        const entry = entryPrices.get(pos.symbol);
        if (entry && entry.totalQty > 0) {
          pos.avgEntryPrice = entry.totalCost / entry.totalQty;
          pos.unrealizedPl = (pos.currentPrice - pos.avgEntryPrice) * pos.quantity;
          pos.unrealizedPlPct = pos.avgEntryPrice > 0
            ? ((pos.currentPrice - pos.avgEntryPrice) / pos.avgEntryPrice) * 100
            : 0;
        }
      }
    }

    return NextResponse.json(positions);
  } catch (error) {
    console.error('Positions error:', error);
    const message = error instanceof Error ? error.message : 'Failed to fetch positions';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
