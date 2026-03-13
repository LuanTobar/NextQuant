/**
 * Risk Profile API — Sprint 1.5
 *
 * GET  /api/risk-profile  → Return current user's risk profile (null if none)
 * POST /api/risk-profile  → Create / update profile, compute score, sync AgentConfig
 */

import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { getCurrentUser } from '@/lib/plan-guard';
import { prisma } from '@/lib/prisma';

// ── Scoring logic (mirrors trading-agent/src/risk/profiler.py) ─────────────────

const WEIGHTS: Record<string, Record<string, number>> = {
  investment_horizon: { SHORT: -0.2, MEDIUM: 0.0,  LONG:  0.2 },
  risk_tolerance:     { CONSERVATIVE: -0.3, MODERATE: 0.0, AGGRESSIVE: 0.3 },
  experience_level:   { BEGINNER: -0.2, INTERMEDIATE: 0.0, EXPERT: 0.2 },
  income_stability:   { UNSTABLE: -0.2, VARIABLE: 0.0, STABLE: 0.1 },
  loss_capacity:      { LOW: -0.2, MEDIUM: 0.0, HIGH: 0.2 },
  primary_goal:       {
    CAPITAL_PRESERVATION: -0.3, INCOME: -0.1,
    GROWTH: 0.1, SPECULATION: 0.3,
  },
};

const MIN_RAW = Object.values(WEIGHTS).reduce(
  (s, opts) => s + Math.min(...Object.values(opts)), 0
);
const MAX_RAW = Object.values(WEIGHTS).reduce(
  (s, opts) => s + Math.max(...Object.values(opts)), 0
);

function computeRiskScore(answers: Record<string, string>): {
  riskScore: number;
  riskCategory: string;
} {
  let raw = 0;
  for (const [dim, opts] of Object.entries(WEIGHTS)) {
    const answer = (answers[dim] ?? '').toUpperCase();
    raw += opts[answer] ?? 0;
  }
  const score = Math.max(0, Math.min(1, (raw - MIN_RAW) / (MAX_RAW - MIN_RAW)));

  let riskCategory = 'CONSERVATIVE';
  if      (score >= 0.75) riskCategory = 'SPECULATIVE';
  else if (score >= 0.50) riskCategory = 'AGGRESSIVE';
  else if (score >= 0.25) riskCategory = 'MODERATE';

  return { riskScore: Math.round(score * 10000) / 10000, riskCategory };
}

// ── Config derivation (mirrors trading-agent/src/risk/profile_adapter.py) ─────

const CONFIG_TABLE: Record<string, {
  maxPositionSizeUsd: number;
  maxConcurrentPositions: number;
  dailyLossLimitUsd: number;
  maxDrawdownPct: number;
  aggressiveness: number;
}> = {
  CONSERVATIVE: { maxPositionSizeUsd: 50,    maxConcurrentPositions: 2, dailyLossLimitUsd: 100,   maxDrawdownPct: 5,  aggressiveness: 0.15 },
  MODERATE:     { maxPositionSizeUsd: 150,   maxConcurrentPositions: 3, dailyLossLimitUsd: 400,   maxDrawdownPct: 12, aggressiveness: 0.45 },
  AGGRESSIVE:   { maxPositionSizeUsd: 500,   maxConcurrentPositions: 5, dailyLossLimitUsd: 1000,  maxDrawdownPct: 22, aggressiveness: 0.75 },
  SPECULATIVE:  { maxPositionSizeUsd: 1000,  maxConcurrentPositions: 8, dailyLossLimitUsd: 3000,  maxDrawdownPct: 40, aggressiveness: 0.92 },
};

// ── Request schema ─────────────────────────────────────────────────────────────

const riskProfileSchema = z.object({
  investmentHorizon: z.enum(['SHORT', 'MEDIUM', 'LONG']),
  riskTolerance:     z.enum(['CONSERVATIVE', 'MODERATE', 'AGGRESSIVE']),
  experienceLevel:   z.enum(['BEGINNER', 'INTERMEDIATE', 'EXPERT']),
  incomeStability:   z.enum(['UNSTABLE', 'VARIABLE', 'STABLE']),
  lossCapacity:      z.enum(['LOW', 'MEDIUM', 'HIGH']),
  primaryGoal:       z.enum(['CAPITAL_PRESERVATION', 'INCOME', 'GROWTH', 'SPECULATION']),
});

// ── Handlers ───────────────────────────────────────────────────────────────────

export async function GET() {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    const profile = await prisma.riskProfile.findUnique({
      where: { userId: user.id },
    });

    return NextResponse.json(profile ?? null);
  } catch {
    return NextResponse.json({ error: 'Failed to fetch risk profile' }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const user = await getCurrentUser();
    if (!user) {
      return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
    }

    const body = await req.json();
    const parsed = riskProfileSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(
        { error: parsed.error.errors[0].message },
        { status: 400 }
      );
    }

    const data = parsed.data;

    // Compute score server-side (same formula as Python profiler)
    const { riskScore, riskCategory } = computeRiskScore({
      investment_horizon: data.investmentHorizon,
      risk_tolerance:     data.riskTolerance,
      experience_level:   data.experienceLevel,
      income_stability:   data.incomeStability,
      loss_capacity:      data.lossCapacity,
      primary_goal:       data.primaryGoal,
    });

    const derived = CONFIG_TABLE[riskCategory] ?? CONFIG_TABLE.MODERATE;

    // Persist RiskProfile
    const profile = await prisma.riskProfile.upsert({
      where:  { userId: user.id },
      update: {
        ...data,
        riskScore,
        riskCategory,
        ...derived,
      },
      create: {
        userId: user.id,
        ...data,
        riskScore,
        riskCategory,
        ...derived,
      },
    });

    // Sync derived params to AgentConfig (create if missing, update limits if exists)
    await prisma.agentConfig.upsert({
      where:  { userId: user.id },
      update: {
        maxPositionSizeUsd:     derived.maxPositionSizeUsd,
        maxConcurrentPositions: derived.maxConcurrentPositions,
        dailyLossLimitUsd:      derived.dailyLossLimitUsd,
        maxDrawdownPct:         derived.maxDrawdownPct,
        aggressiveness:         derived.aggressiveness,
      },
      create: {
        userId:                 user.id,
        enabled:                false,
        maxPositionSizeUsd:     derived.maxPositionSizeUsd,
        maxConcurrentPositions: derived.maxConcurrentPositions,
        dailyLossLimitUsd:      derived.dailyLossLimitUsd,
        maxDrawdownPct:         derived.maxDrawdownPct,
        aggressiveness:         derived.aggressiveness,
      },
    });

    return NextResponse.json(profile, { status: 201 });
  } catch {
    return NextResponse.json({ error: 'Failed to save risk profile' }, { status: 500 });
  }
}
