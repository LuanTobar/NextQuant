/**
 * Order Sync API
 *
 * POST /api/orders/sync — Synchronize pending orders with broker
 */

import { NextResponse } from 'next/server';
import { getCurrentUser } from '@/lib/plan-guard';
import { syncUserOrders } from '@/lib/order-sync';

export async function POST() {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    const result = await syncUserOrders(user.id);

    return NextResponse.json({
      synced: result.synced,
      errors: result.errors.length > 0 ? result.errors : undefined,
    });
  } catch (error) {
    console.error('Order sync error:', error);
    return NextResponse.json({ error: 'Sync failed' }, { status: 500 });
  }
}
