import { getServerSession } from 'next-auth';
import { authOptions } from './auth';
import { prisma } from './prisma';

export interface PlanCheck {
  allowed: boolean;
  reason?: string;
  userId?: string;
  plan?: string;
}

const PLAN_LIMITS = {
  FREE: {
    chatPerDay: 10,
    allowedExchanges: ['CRYPTO'],
    canTrade: false,
  },
  PRO: {
    chatPerDay: Infinity,
    allowedExchanges: ['CRYPTO', 'US', 'LSE', 'BME', 'TSE'],
    canTrade: true,
  },
} as const;

/**
 * Get current user from session. Returns null if not authenticated.
 */
export async function getCurrentUser() {
  const session = await getServerSession(authOptions);
  if (!session?.user?.id) return null;
  return session.user;
}

/**
 * Check and increment chat usage. Resets daily.
 */
export async function checkChatLimit(): Promise<PlanCheck> {
  const sessionUser = await getCurrentUser();
  if (!sessionUser) {
    return { allowed: false, reason: 'Not authenticated' };
  }

  const user = await prisma.user.findUnique({
    where: { id: sessionUser.id },
  });

  if (!user) {
    return { allowed: false, reason: 'User not found' };
  }

  const limits = PLAN_LIMITS[user.plan];
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  // Reset counter if it's a new day
  const resetDate = new Date(user.chatResetDate);
  resetDate.setHours(0, 0, 0, 0);

  if (today > resetDate) {
    await prisma.user.update({
      where: { id: user.id },
      data: { chatUsageToday: 1, chatResetDate: new Date() },
    });
    return { allowed: true, userId: user.id, plan: user.plan };
  }

  if (user.chatUsageToday >= limits.chatPerDay) {
    return {
      allowed: false,
      reason: `Daily chat limit reached (${limits.chatPerDay}/day). Upgrade to Pro for unlimited.`,
      userId: user.id,
      plan: user.plan,
    };
  }

  // Increment usage
  await prisma.user.update({
    where: { id: user.id },
    data: { chatUsageToday: user.chatUsageToday + 1 },
  });

  return { allowed: true, userId: user.id, plan: user.plan };
}

/**
 * Check if user can access signals for a given exchange.
 */
export async function checkMarketAccess(exchange: string): Promise<PlanCheck> {
  const sessionUser = await getCurrentUser();
  if (!sessionUser) {
    return { allowed: false, reason: 'Not authenticated' };
  }

  const plan = sessionUser.plan as keyof typeof PLAN_LIMITS;
  const limits = PLAN_LIMITS[plan];

  if (!(limits.allowedExchanges as readonly string[]).includes(exchange)) {
    return {
      allowed: false,
      reason: `${exchange} market requires Pro plan. Upgrade to access all 5 exchanges.`,
      userId: sessionUser.id,
      plan,
    };
  }

  return { allowed: true, userId: sessionUser.id, plan };
}

/**
 * Check if user can execute trades.
 * Also handles lazy downgrade after grace period expires.
 */
export async function checkTradeAccess(): Promise<PlanCheck> {
  const sessionUser = await getCurrentUser();
  if (!sessionUser) {
    return { allowed: false, reason: 'Not authenticated' };
  }

  // Always fetch from DB to get fresh plan + gracePeriodEnd
  const user = await prisma.user.findUnique({
    where: { id: sessionUser.id },
    select: { plan: true, gracePeriodEnd: true },
  });

  if (!user) {
    return { allowed: false, reason: 'User not found' };
  }

  // Lazy downgrade: grace period has expired — flip to FREE now
  if (user.gracePeriodEnd && user.gracePeriodEnd < new Date()) {
    await prisma.user.update({
      where: { id: sessionUser.id },
      data: { plan: 'FREE', gracePeriodEnd: null },
    });
    return {
      allowed: false,
      reason: 'Your subscription has ended. Upgrade to PRO to resume trading.',
      userId: sessionUser.id,
      plan: 'FREE',
    };
  }

  const plan = user.plan as keyof typeof PLAN_LIMITS;
  const limits = PLAN_LIMITS[plan];

  if (!limits.canTrade) {
    return {
      allowed: false,
      reason: 'Trading requires Pro plan. Upgrade to execute trades through your broker.',
      userId: sessionUser.id,
      plan,
    };
  }

  return { allowed: true, userId: sessionUser.id, plan };
}

/**
 * Get allowed exchanges for user's plan.
 */
export function getAllowedExchanges(plan: string): string[] {
  const exchanges = PLAN_LIMITS[plan as keyof typeof PLAN_LIMITS]?.allowedExchanges || PLAN_LIMITS.FREE.allowedExchanges;
  return [...exchanges];
}
