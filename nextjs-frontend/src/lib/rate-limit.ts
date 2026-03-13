/**
 * Sliding window rate limiter.
 * Uses Redis (ZADD/ZREMRANGEBYSCORE/ZCOUNT) when available,
 * falls back to in-memory when Redis is not configured.
 */
import { getRedis } from "./redis";

interface RateLimitResult {
  allowed: boolean;
  retryAfter?: number;
}

// ── Redis sliding window ──────────────────────────────────────────────────────

async function checkRedis(
  key: string,
  maxRequests: number,
  windowMs: number
): Promise<RateLimitResult | null> {
  const redis = await getRedis();
  if (!redis) return null;

  const now = Date.now();
  const windowStart = now - windowMs;
  const redisKey = `rl:${key}`;

  try {
    const pipeline = redis.multi();
    pipeline.zRemRangeByScore(redisKey, "-inf", windowStart.toString());
    pipeline.zCard(redisKey);
    pipeline.zAdd(redisKey, { score: now, value: now.toString() });
    pipeline.expire(redisKey, Math.ceil(windowMs / 1000) + 1);

    const results = await pipeline.exec();
    const count = (results?.[1] as number) ?? 0;

    if (count >= maxRequests) {
      const oldest = await redis.zRange(redisKey, 0, 0, { BY: "SCORE" });
      const oldestTs = oldest.length > 0 ? parseInt(oldest[0], 10) : now;
      const retryAfter = Math.ceil((oldestTs + windowMs - now) / 1000);
      await redis.zRem(redisKey, now.toString());
      return { allowed: false, retryAfter: Math.max(1, retryAfter) };
    }

    return { allowed: true };
  } catch (err) {
    console.warn("[RateLimit] Redis error, falling back to in-memory:", err);
    return null;
  }
}

// ── In-memory fallback ────────────────────────────────────────────────────────

const memStore = new Map<string, number[]>();

setInterval(() => {
  const now = Date.now();
  for (const [key, timestamps] of memStore.entries()) {
    const fresh = timestamps.filter((ts) => now - ts < 300_000);
    if (fresh.length === 0) memStore.delete(key);
    else memStore.set(key, fresh);
  }
}, 60_000);

function checkMemory(
  key: string,
  maxRequests: number,
  windowMs: number
): RateLimitResult {
  const now = Date.now();
  const timestamps = (memStore.get(key) ?? []).filter(
    (ts) => now - ts < windowMs
  );

  if (timestamps.length >= maxRequests) {
    const retryAfter = Math.ceil((timestamps[0] + windowMs - now) / 1000);
    memStore.set(key, timestamps);
    return { allowed: false, retryAfter: Math.max(1, retryAfter) };
  }

  timestamps.push(now);
  memStore.set(key, timestamps);
  return { allowed: true };
}

// ── Public API ────────────────────────────────────────────────────────────────

export class RateLimiter {
  constructor(
    private readonly maxRequests: number,
    private readonly windowMs: number
  ) {}

  async check(key: string): Promise<RateLimitResult> {
    const redisResult = await checkRedis(key, this.maxRequests, this.windowMs);
    return redisResult ?? checkMemory(key, this.maxRequests, this.windowMs);
  }
}

// Pre-configured limiters
export const signupLimiter = new RateLimiter(5, 60_000);         // 5/min per IP
export const loginLimiter = new RateLimiter(10, 60_000);         // 10/min per IP
export const chatLimiter = new RateLimiter(5, 60_000);           // 5/min per user
export const forgotPasswordLimiter = new RateLimiter(3, 60_000); // 3/min per IP
