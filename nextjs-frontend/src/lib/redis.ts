/**
 * Shared Redis client for the Next.js server.
 * Falls back gracefully to null if REDIS_URL is not configured.
 */
import { createClient, type RedisClientType } from "redis";

let client: RedisClientType | null = null;

export async function getRedis(): Promise<RedisClientType | null> {
  if (!process.env.REDIS_URL) return null;

  if (client && client.isReady) return client;

  try {
    client = createClient({ url: process.env.REDIS_URL }) as RedisClientType;
    client.on("error", (err) => {
      console.warn("[Redis] connection error:", err.message);
    });
    await client.connect();
    return client;
  } catch (err) {
    console.warn("[Redis] failed to connect, rate limiting will use in-memory fallback:", err);
    client = null;
    return null;
  }
}
