/**
 * Agent Config API
 *
 * GET  /api/agent/config → Read agent config for current user
 * POST /api/agent/config → Create/update agent config
 */

import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { getCurrentUser, checkTradeAccess } from '@/lib/plan-guard';
import { prisma } from '@/lib/prisma';

const configSchema = z.object({
  enabled: z.boolean(),
  broker: z.enum(['ALPACA', 'BITGET']),
  maxPositionSizeUsd: z.number().min(100).max(10_000),
  maxConcurrentPositions: z.number().int().min(1).max(10),
  dailyLossLimitUsd: z.number().min(100).max(5_000),
  maxDrawdownPct: z.number().min(1).max(50),
  aggressiveness: z.number().min(0).max(1),
  allowedSymbols: z.array(z.string()).default([]),
});

export async function GET() {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    const config = await prisma.agentConfig.findUnique({
      where: { userId: user.id },
    });

    if (!config) {
      // Return defaults
      return NextResponse.json({
        enabled: false,
        broker: 'BITGET',
        maxPositionSizeUsd: 100,
        maxConcurrentPositions: 3,
        dailyLossLimitUsd: 500,
        maxDrawdownPct: 10,
        aggressiveness: 0.5,
        allowedSymbols: [],
      });
    }

    return NextResponse.json(config);
  } catch {
    return NextResponse.json({ error: 'Failed to fetch config' }, { status: 500 });
  }
}

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
    const parsed = configSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: parsed.error.errors[0].message },
        { status: 400 }
      );
    }

    const config = await prisma.agentConfig.upsert({
      where: { userId: user.id },
      update: parsed.data,
      create: {
        userId: user.id,
        ...parsed.data,
      },
    });

    return NextResponse.json(config);
  } catch {
    return NextResponse.json({ error: 'Failed to save config' }, { status: 500 });
  }
}
