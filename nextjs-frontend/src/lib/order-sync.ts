/**
 * Order status synchronization.
 *
 * Queries the database for orders in non-terminal states (PENDING, PARTIALLY_FILLED),
 * calls the broker API to get current status, and updates our database.
 *
 * This ensures our local order history stays in sync with what the broker reports.
 */

import { prisma } from './prisma';
import { createBrokerClient } from './brokers';

/**
 * Sync all non-terminal orders for a given user.
 * Returns the number of orders updated.
 */
export async function syncUserOrders(userId: string): Promise<{
  synced: number;
  errors: string[];
}> {
  // Find orders that might have changed
  const pendingOrders = await prisma.order.findMany({
    where: {
      userId,
      status: { in: ['PENDING', 'PARTIALLY_FILLED'] },
      brokerOrderId: { not: null },
    },
    include: {
      brokerConnection: true,
    },
  });

  if (pendingOrders.length === 0) {
    return { synced: 0, errors: [] };
  }

  let synced = 0;
  const errors: string[] = [];

  // Group orders by broker connection to reuse clients
  const byConnection = new Map<string, typeof pendingOrders>();
  for (const order of pendingOrders) {
    const key = order.brokerConnectionId;
    if (!byConnection.has(key)) byConnection.set(key, []);
    byConnection.get(key)!.push(order);
  }

  for (const [, orders] of byConnection) {
    const connection = orders[0].brokerConnection;

    let client;
    try {
      client = createBrokerClient(connection);
    } catch (err) {
      errors.push(`Failed to create client for ${connection.broker}: ${err}`);
      continue;
    }

    for (const order of orders) {
      try {
        const brokerOrder = await client.getOrder(order.brokerOrderId!);

        // Map broker status to our enum
        const statusMap: Record<string, string> = {
          new: 'PENDING',
          partially_filled: 'PARTIALLY_FILLED',
          filled: 'FILLED',
          cancelled: 'CANCELLED',
          rejected: 'REJECTED',
        };

        const newStatus = statusMap[brokerOrder.status] || order.status;
        const hasChanged =
          newStatus !== order.status ||
          brokerOrder.filledQty !== (order.filledQuantity ?? undefined) ||
          brokerOrder.filledAvgPrice !== (order.filledPrice ?? undefined);

        if (hasChanged) {
          await prisma.order.update({
            where: { id: order.id },
            data: {
              status: newStatus as 'PENDING' | 'FILLED' | 'PARTIALLY_FILLED' | 'CANCELLED' | 'REJECTED',
              filledQuantity: brokerOrder.filledQty ?? order.filledQuantity,
              filledPrice: brokerOrder.filledAvgPrice ?? order.filledPrice,
              brokerResponse: brokerOrder.raw
                ? (brokerOrder.raw as unknown as Record<string, never>)
                : undefined,
            },
          });
          synced++;
        }
      } catch (err) {
        errors.push(
          `Failed to sync order ${order.id} (${order.brokerOrderId}): ${err instanceof Error ? err.message : err}`
        );
      }
    }
  }

  return { synced, errors };
}
