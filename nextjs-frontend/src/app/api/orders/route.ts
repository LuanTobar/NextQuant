/**
 * Orders API
 *
 * POST /api/orders → Place a new order through user's connected broker
 * GET  /api/orders → Get order history from database
 *
 * Flow for placing an order:
 *   1. Authenticate user (JWT session)
 *   2. Check trade access (Pro plan required)
 *   3. Find user's active broker connection for the appropriate broker
 *   4. Decrypt API keys from DB
 *   5. Create broker client and submit order
 *   6. Save order record to our database
 *   7. Return order confirmation
 */

import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { getCurrentUser } from '@/lib/plan-guard';
import { checkTradeAccess } from '@/lib/plan-guard';
import { prisma } from '@/lib/prisma';
import { createBrokerClient } from '@/lib/brokers';
import { syncUserOrders } from '@/lib/order-sync';

const orderSchema = z.object({
  symbol: z.string().min(1),
  side: z.enum(['buy', 'sell']),
  quantity: z.number().positive(),
  type: z.enum(['market', 'limit']).default('market'),
  timeInForce: z.enum(['day', 'gtc', 'ioc', 'fok']).optional(),
  limitPrice: z.number().positive().optional(),
  broker: z.enum(['ALPACA', 'BITGET']),
});

export async function POST(req: NextRequest) {
  try {
    // 1. Auth check
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    // 2. Plan check — trading requires Pro
    const tradeCheck = await checkTradeAccess();
    if (!tradeCheck.allowed) {
      return NextResponse.json(
        { error: tradeCheck.reason },
        { status: 403 }
      );
    }

    // 3. Parse & validate request body
    const body = await req.json();
    const parsed = orderSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: parsed.error.errors[0].message },
        { status: 400 }
      );
    }

    const { symbol, side, quantity, type, timeInForce, limitPrice, broker } = parsed.data;

    // 4. Find user's active connection for this broker
    const connection = await prisma.brokerConnection.findFirst({
      where: {
        userId: user.id,
        broker,
        isActive: true,
      },
    });

    if (!connection) {
      return NextResponse.json(
        { error: `No active ${broker} connection. Go to Settings to connect your broker.` },
        { status: 400 }
      );
    }

    // 5. Create broker client (decrypts keys internally)
    const client = createBrokerClient(connection);

    // 6. Place the order
    const brokerResponse = await client.placeOrder({
      symbol,
      side,
      quantity,
      type,
      timeInForce,
      limitPrice,
    });

    // 7. Save order to our database for history
    const order = await prisma.order.create({
      data: {
        userId: user.id,
        brokerConnectionId: connection.id,
        symbol,
        side: side.toUpperCase() as 'BUY' | 'SELL',
        quantity,
        orderType: type,
        status: 'PENDING',
        brokerOrderId: brokerResponse.brokerId,
      },
    });

    return NextResponse.json({
      id: order.id,
      brokerOrderId: brokerResponse.brokerId,
      symbol,
      side,
      quantity,
      type,
      status: brokerResponse.status,
      message: `Order submitted to ${broker}`,
    });
  } catch (error) {
    console.error('Order placement error:', error);
    const message = error instanceof Error ? error.message : 'Order failed';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function GET() {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    // Sync pending orders before returning (lightweight, only non-terminal)
    await syncUserOrders(user.id).catch(() => {});

    const orders = await prisma.order.findMany({
      where: { userId: user.id },
      orderBy: { createdAt: 'desc' },
      take: 50,
      select: {
        id: true,
        symbol: true,
        side: true,
        quantity: true,
        orderType: true,
        status: true,
        brokerOrderId: true,
        filledPrice: true,
        filledQuantity: true,
        createdAt: true,
        brokerConnection: {
          select: { broker: true, label: true },
        },
      },
    });

    return NextResponse.json(orders);
  } catch {
    return NextResponse.json({ error: 'Failed to fetch orders' }, { status: 500 });
  }
}
