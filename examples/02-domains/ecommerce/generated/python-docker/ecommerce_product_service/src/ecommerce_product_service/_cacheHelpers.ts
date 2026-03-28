/**
 * Cache helper functions for generated TypeScript code.
 *
 * Uses ioredis for Redis operations. The Redis client is lazily
 * initialized from the REDIS_URL environment variable.
 */
import Redis from 'ioredis';

let _redisClient: Redis | null = null;

export function _getRedis(): Redis {
  if (_redisClient === null) {
    if (!process.env.REDIS_URL) throw new Error('REDIS_URL environment variable is required');
    _redisClient = new Redis(process.env.REDIS_URL);
  }
  return _redisClient;
}

export async function _cacheGetOrSet<T>(
  key: string,
  factory: () => Promise<T>,
  ttl?: number,
): Promise<T> {
  const redis = _getRedis();
  const v = await redis.get(key);
  if (v !== null) return JSON.parse(v) as T;
  const nv = await factory();
  if (ttl != null) {
    await redis.set(key, JSON.stringify(nv), 'EX', ttl);
  } else {
    await redis.set(key, JSON.stringify(nv));
  }
  return nv;
}

export async function _cacheSetMany(
  entries: Record<string, unknown>,
  ttl?: number,
): Promise<void> {
  const redis = _getRedis();
  const pipeline = redis.pipeline();
  for (const [k, v] of Object.entries(entries)) {
    if (ttl != null) {
      pipeline.set(k, JSON.stringify(v), 'EX', ttl);
    } else {
      pipeline.set(k, JSON.stringify(v));
    }
  }
  await pipeline.exec();
}

export async function _cacheGetMany(
  keys: string[],
): Promise<Record<string, unknown>> {
  const redis = _getRedis();
  const values = await redis.mget(...keys);
  return Object.fromEntries(
    keys.map((k, i) => [k, values[i] ? JSON.parse(values[i]!) : null]),
  );
}

export async function _cacheLock(
  key: string,
  ttl?: number,
): Promise<boolean> {
  const redis = _getRedis();
  if (ttl != null) {
    return (await redis.set(key, '1', 'EX', ttl, 'NX')) === 'OK';
  }
  return (await redis.set(key, '1', 'NX')) === 'OK';
}

export async function _cacheCheckRateLimit(
  key: string,
  limit: number,
  windowSeconds: number,
): Promise<boolean> {
  const redis = _getRedis();
  const now = Math.floor(Date.now() / 1000);
  const raw = await redis.get(key);
  const bucket = raw
    ? (JSON.parse(raw) as { count: number; windowStart: number })
    : { count: 0, windowStart: now };
  if (now - bucket.windowStart >= windowSeconds) {
    bucket.windowStart = now;
    bucket.count = 0;
  }
  bucket.count++;
  await redis.set(key, JSON.stringify(bucket));
  return bucket.count <= limit;
}

export async function _cacheGetRateLimitStatus(
  key: string,
): Promise<{ count: number; windowStart: number }> {
  const redis = _getRedis();
  const raw = await redis.get(key);
  return raw
    ? (JSON.parse(raw) as { count: number; windowStart: number })
    : { count: 0, windowStart: 0 };
}
