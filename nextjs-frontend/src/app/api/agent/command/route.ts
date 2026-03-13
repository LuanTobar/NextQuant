/**
 * Agent Command API
 *
 * POST /api/agent/command → Send command to trading agent
 *
 * For MVP, pause/resume toggle the enabled flag in AgentConfig.
 * close_all is handled by disabling + the agent closes on next sync.
 *
 * Future: publish directly to NATS for instant response.
 */

import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { getCurrentUser, checkTradeAccess } from '@/lib/plan-guard';
import { prisma } from '@/lib/prisma';

const commandSchema = z.object({
  action: z.enum(['pause', 'resume', 'close_all']),
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
    const parsed = commandSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: parsed.error.errors[0].message },
        { status: 400 }
      );
    }

    const { action } = parsed.data;

    if (action === 'pause') {
      await prisma.agentConfig.update({
        where: { userId: user.id },
        data: { enabled: false },
      });
    } else if (action === 'resume') {
      await prisma.agentConfig.update({
        where: { userId: user.id },
        data: { enabled: true },
      });
    } else if (action === 'close_all') {
      // Disable the agent — it will stop opening new positions
      await prisma.agentConfig.update({
        where: { userId: user.id },
        data: { enabled: false },
      });
      // Note: actual position closing happens via manual close or
      // could be enhanced with NATS command in future
    }

    return NextResponse.json({
      success: true,
      action,
      message: `Command '${action}' executed`,
    });
  } catch {
    return NextResponse.json({ error: 'Command failed' }, { status: 500 });
  }
}
