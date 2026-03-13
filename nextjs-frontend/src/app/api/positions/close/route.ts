/**
 * Close Position API
 *
 * POST /api/positions/close — Close an open position (full or partial)
 *
 * Body: { broker: "BITGET" | "ALPACA", symbol: "BTCUSDT", quantity?: number }
 * If quantity omitted, closes entire position.
 */

import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { getCurrentUser, checkTradeAccess } from '@/lib/plan-guard';
import { prisma } from '@/lib/prisma';
import { createBrokerClient } from '@/lib/brokers';

const closeSchema = z.object({
  broker: z.enum(['ALPACA', 'BITGET']),
  symbol: z.string().min(1),
  quantity: z.number().positive().optional(),
});

export async function POST(req: NextRequest) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    const tradeCheck = await checkTradeAccess();
    if (!tradeCheck.allowed) {
      return NextResponse.json({ error: tradeCheck.reason }, { status: 403 });
    }

    const body = await req.json();
    const parsed = closeSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: parsed.error.errors[0].message },
        { status: 400 }
      );
    }

    const { broker, symbol, quantity } = parsed.data;

    const connection = await prisma.brokerConnection.findFirst({
      where: {
        userId: user.id,
        broker,
        isActive: true,
      },
    });

    if (!connection) {
      return NextResponse.json(
        { error: `No active ${broker} connection` },
        { status: 400 }
      );
    }

    const client = createBrokerClient(connection);
    const result = await client.closePosition(symbol, quantity);

    // Save the closing order to our database
    await prisma.order.create({
      data: {
        userId: user.id,
        brokerConnectionId: connection.id,
        symbol,
        side: 'SELL',
        quantity: quantity || result.quantity,
        orderType: 'market',
        status: 'PENDING',
        brokerOrderId: result.brokerId,
      },
    });

    return NextResponse.json({
      brokerId: result.brokerId,
      symbol,
      quantity: quantity || result.quantity,
      status: result.status,
      message: `Position close submitted via ${broker}`,
    });
  } catch (error) {
    console.error('Close position error:', error);
    const message = error instanceof Error ? error.message : 'Close failed';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
