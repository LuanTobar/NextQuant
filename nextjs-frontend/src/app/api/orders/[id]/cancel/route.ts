/**
 * Cancel Order API
 *
 * POST /api/orders/{id}/cancel — Cancel a pending order
 */

import { NextRequest, NextResponse } from 'next/server';
import { getCurrentUser } from '@/lib/plan-guard';
import { prisma } from '@/lib/prisma';
import { createBrokerClient } from '@/lib/brokers';

export async function POST(
  _req: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    const order = await prisma.order.findFirst({
      where: {
        id: params.id,
        userId: user.id,
      },
      include: {
        brokerConnection: true,
      },
    });

    if (!order) {
      return NextResponse.json({ error: 'Order not found' }, { status: 404 });
    }

    if (!['PENDING', 'PARTIALLY_FILLED'].includes(order.status)) {
      return NextResponse.json(
        { error: `Cannot cancel order with status: ${order.status}` },
        { status: 400 }
      );
    }

    if (!order.brokerOrderId) {
      return NextResponse.json(
        { error: 'Order has no broker ID' },
        { status: 400 }
      );
    }

    const client = createBrokerClient(order.brokerConnection);
    const result = await client.cancelOrder(order.brokerOrderId);

    if (result.success) {
      await prisma.order.update({
        where: { id: order.id },
        data: { status: 'CANCELLED' },
      });
    }

    return NextResponse.json(result);
  } catch (error) {
    console.error('Cancel order error:', error);
    const message = error instanceof Error ? error.message : 'Cancel failed';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
