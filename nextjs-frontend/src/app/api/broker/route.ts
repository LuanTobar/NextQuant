import { NextRequest, NextResponse } from 'next/server';
import { getServerSession } from 'next-auth';
import { authOptions } from '@/lib/auth';
import { prisma } from '@/lib/prisma';
import { encrypt } from '@/lib/encryption';
import { z } from 'zod';

const brokerSchema = z.object({
  broker: z.enum(['ALPACA', 'BITGET']),
  apiKey: z.string().min(1, 'API key is required'),
  apiSecret: z.string().min(1, 'API secret is required'),
  label: z.string().optional(),
  // Extra fields: Alpaca environment (paper/live), Bitget passphrase + simulated flag
  environment: z.enum(['paper', 'live']).optional(),
  passphrase: z.string().optional(),
  simulated: z.boolean().optional(),
});

/**
 * GET /api/broker — List user's broker connections (never returns decrypted keys)
 */
export async function GET() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const connections = await prisma.brokerConnection.findMany({
    where: { userId: session.user.id },
    select: {
      id: true,
      broker: true,
      label: true,
      isActive: true,
      createdAt: true,
      updatedAt: true,
    },
  });

  return NextResponse.json(connections);
}

/**
 * POST /api/broker — Create or update a broker connection
 * Encrypts API keys before storing.
 */
export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const body = await req.json();
  const parsed = brokerSchema.safeParse(body);

  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.errors[0].message },
      { status: 400 }
    );
  }

  const { broker, apiKey, apiSecret, label, environment, passphrase, simulated } = parsed.data;

  // Build extra data (varies by broker)
  const extra: Record<string, unknown> = {};
  if (broker === 'ALPACA') {
    extra.environment = environment || 'paper';
  }
  if (broker === 'BITGET') {
    if (passphrase) extra.passphrase = passphrase;
    if (simulated) extra.simulated = true;
  }

  // Encrypt credentials
  const encryptedKey = encrypt(apiKey);
  const encryptedSecret = encrypt(apiSecret);
  const encryptedExtra = Object.keys(extra).length > 0 ? encrypt(JSON.stringify(extra)) : null;

  // Upsert: one connection per broker per user
  const connection = await prisma.brokerConnection.upsert({
    where: {
      userId_broker: {
        userId: session.user.id,
        broker,
      },
    },
    update: {
      encryptedKey,
      encryptedSecret,
      encryptedExtra,
      label: label || null,
      isActive: true,
    },
    create: {
      userId: session.user.id,
      broker,
      encryptedKey,
      encryptedSecret,
      encryptedExtra,
      label: label || null,
    },
  });

  return NextResponse.json({
    id: connection.id,
    broker: connection.broker,
    label: connection.label,
    isActive: connection.isActive,
    message: `${broker} connection saved successfully`,
  });
}

/**
 * DELETE /api/broker — Remove a broker connection
 */
export async function DELETE(req: NextRequest) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { searchParams } = new URL(req.url);
  const id = searchParams.get('id');

  if (!id) {
    return NextResponse.json({ error: 'Connection ID is required' }, { status: 400 });
  }

  // Ensure user owns this connection
  const connection = await prisma.brokerConnection.findFirst({
    where: { id, userId: session.user.id },
  });

  if (!connection) {
    return NextResponse.json({ error: 'Connection not found' }, { status: 404 });
  }

  await prisma.brokerConnection.delete({ where: { id } });

  return NextResponse.json({ message: 'Connection removed' });
}
