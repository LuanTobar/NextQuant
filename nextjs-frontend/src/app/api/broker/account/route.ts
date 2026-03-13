/**
 * Broker Account API
 *
 * GET /api/broker/account?broker=ALPACA → Get account info (equity, buying power)
 *
 * This endpoint is used by the dashboard to show real portfolio data
 * when a broker is connected.
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

    // Create client and fetch account data
    const client = createBrokerClient(connection);
    const [account, positions] = await Promise.all([
      client.getAccount(),
      client.getPositions(),
    ]);

    return NextResponse.json({
      broker,
      account: {
        equity: account.equity,
        buyingPower: account.buyingPower,
        cash: account.cash,
        currency: account.currency,
      },
      positions: positions.map((p) => ({
        symbol: p.symbol,
        quantity: p.quantity,
        avgEntryPrice: p.avgEntryPrice,
        currentPrice: p.currentPrice,
        unrealizedPl: p.unrealizedPl,
        side: p.side,
      })),
    });
  } catch (error) {
    console.error('Broker account error:', error);
    const message = error instanceof Error ? error.message : 'Failed to fetch account';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
