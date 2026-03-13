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

    const format = req.nextUrl.searchParams.get('format') || 'csv';
    const from = req.nextUrl.searchParams.get('from');
    const to = req.nextUrl.searchParams.get('to');

    const where: Record<string, unknown> = { userId: session.user.id };
    if (from || to) {
      where.createdAt = {};
      if (from) (where.createdAt as Record<string, unknown>).gte = new Date(from);
      if (to) (where.createdAt as Record<string, unknown>).lte = new Date(to);
    }

    const orders = await prisma.order.findMany({
      where,
      include: { brokerConnection: { select: { broker: true } } },
      orderBy: { createdAt: 'desc' },
      take: 1000,
    });

    if (format === 'csv') {
      const header = 'Date,Symbol,Side,Quantity,Type,Status,Filled Price,Filled Qty,Broker\n';
      const rows = orders.map((o) =>
        [
          o.createdAt.toISOString(),
          o.symbol,
          o.side,
          o.quantity,
          o.orderType,
          o.status,
          o.filledPrice ?? '',
          o.filledQuantity ?? '',
          o.brokerConnection.broker,
        ].join(',')
      ).join('\n');

      return new NextResponse(header + rows, {
        headers: {
          'Content-Type': 'text/csv',
          'Content-Disposition': `attachment; filename="nexquant_trades_${new Date().toISOString().split('T')[0]}.csv"`,
        },
      });
    }

    return NextResponse.json(orders);
  } catch (error) {
    console.error('Trade export error:', error);
    return NextResponse.json({ error: 'Export failed' }, { status: 500 });
  }
}
