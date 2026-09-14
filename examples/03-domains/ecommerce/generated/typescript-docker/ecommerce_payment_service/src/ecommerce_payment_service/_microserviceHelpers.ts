/**
 * Microservice helper functions for generated TypeScript code.
 *
 * Uses axios for HTTP calls and opossum circuit breakers for resilience.
 * Service URLs are resolved from environment variables following the pattern
 * {SERVICE_NAME_UPPER}_URL (e.g., ORDERS_URL for the "orders" service).
 */
import axios, { type AxiosRequestConfig } from 'axios';
import CircuitBreaker from 'opossum';

// ── Service URL resolution ──────────────────────────────────────────────────

export function _msGetServiceUrl(service: string): string {
  const key = service.toUpperCase().replace(/-/g, '_') + '_URL';
  const url = process.env[key];
  if (!url) {
    throw new Error(
      `Service URL for "${service}" not configured. Set the ${key} environment variable.`,
    );
  }
  return url;
}

// ── HTTP calls ──────────────────────────────────────────────────────────────

export async function _msCall(
  service: string,
  method: string,
  path: string,
  options?: AxiosRequestConfig,
): Promise<unknown> {
  const baseUrl = _msGetServiceUrl(service);
  const response = await axios.request({
    method: method as AxiosRequestConfig['method'],
    url: `${baseUrl}${path}`,
    ...options,
  });
  return response.data;
}

export function _msCallAsync(
  service: string,
  method: string,
  path: string,
  options?: AxiosRequestConfig,
): void {
  const baseUrl = _msGetServiceUrl(service);
  // Fire-and-forget: intentionally discards the promise.
  axios
    .request({ method: method as AxiosRequestConfig['method'], url: `${baseUrl}${path}`, ...options })
    .catch(() => undefined);
}

export async function _msPost(
  service: string,
  path: string,
  body: unknown,
  options?: AxiosRequestConfig,
): Promise<unknown> {
  const baseUrl = _msGetServiceUrl(service);
  const response = await axios.post(`${baseUrl}${path}`, body, options);
  return response.data;
}

export async function _msPut(
  service: string,
  path: string,
  body: unknown,
  options?: AxiosRequestConfig,
): Promise<unknown> {
  const baseUrl = _msGetServiceUrl(service);
  const response = await axios.put(`${baseUrl}${path}`, body, options);
  return response.data;
}

export async function _msDelete(
  service: string,
  path: string,
  options?: AxiosRequestConfig,
): Promise<unknown> {
  const baseUrl = _msGetServiceUrl(service);
  const response = await axios.delete(`${baseUrl}${path}`, options);
  return response.data;
}

export async function _msCallWithOptions(
  service: string,
  method: string,
  path: string,
  options: AxiosRequestConfig,
): Promise<unknown> {
  return _msCall(service, method, path, options);
}

/** POST a UTF-8 string body with explicit headers (e.g. webhooks with HMAC). */
export async function _httpPostWithHeaders(
  url: string,
  body: string,
  headers: Record<string, string>,
): Promise<{ statusCode: number; body: unknown }> {
  const response = await axios.post(url, body, {
    headers,
    validateStatus: () => true,
  });
  let parsed: unknown = null;
  try {
    if (response.data === '' || response.data == null) {
      parsed = null;
    } else if (typeof response.data === 'object') {
      parsed = response.data;
    } else if (typeof response.data === 'string') {
      parsed = JSON.parse(response.data) as unknown;
    }
  } catch {
    parsed = null;
  }
  return { statusCode: response.status, body: parsed };
}

/** POST JSON webhook with standard HMAC and tracing headers. */
export async function _httpPostWebhook(
  url: string,
  body: string,
  signature: string,
  deliveryId: string,
): Promise<{ statusCode: number; body: unknown }> {
  const headers: Record<string, string> = {
    'X-Webhook-Signature': signature,
    'X-Webhook-Id': deliveryId,
    'Content-Type': 'application/json',
  };
  return _httpPostWithHeaders(url, body, headers);
}

// ── Discovery ───────────────────────────────────────────────────────────────

export async function _msDiscover(service: string): Promise<string> {
  return _msGetServiceUrl(service);
}

export async function _msHealth(service: string): Promise<boolean> {
  try {
    const url = _msGetServiceUrl(service);
    await axios.get(`${url}/health`, { timeout: 5000 });
    return true;
  } catch {
    return false;
  }
}

export async function _msIsAvailable(service: string): Promise<boolean> {
  return _msHealth(service);
}

export async function _msListServices(): Promise<string[]> {
  const suffix = '_URL';
  return Object.keys(process.env)
    .filter((k) => k.endsWith(suffix))
    .map((k) => k.slice(0, -suffix.length).toLowerCase().replace(/_/g, '-'));
}

export async function _msHealthCheckAll(): Promise<Record<string, boolean>> {
  const services = await _msListServices();
  const results = await Promise.all(
    services.map(async (svc) => [svc, await _msHealth(svc)] as const),
  );
  return Object.fromEntries(results);
}

// ── Resilience (circuit breaker via opossum) ────────────────────────────────

type _MicroserviceCircuitTask = () => Promise<unknown>;

const _opossumCircuitBreakers = new Map<
  string,
  CircuitBreaker<[_MicroserviceCircuitTask], unknown>
>();

function _getOrCreateMsCircuitBreaker(
  key: string,
  options?: {
    timeout?: number;
    errorThresholdPercentage?: number;
    resetTimeout?: number;
  },
): CircuitBreaker<[_MicroserviceCircuitTask], unknown> {
  let breaker = _opossumCircuitBreakers.get(key);
  if (!breaker) {
    breaker = new CircuitBreaker(
      async (task: _MicroserviceCircuitTask) => task(),
      {
        timeout: options?.timeout ?? 3000,
        errorThresholdPercentage: options?.errorThresholdPercentage ?? 50,
        resetTimeout: options?.resetTimeout ?? 30000,
      },
    );
    _opossumCircuitBreakers.set(key, breaker);
  }
  return breaker;
}

export async function _msWithCircuitBreaker<T>(
  key: string,
  fn: () => Promise<T>,
  options?: {
    timeout?: number;
    errorThresholdPercentage?: number;
    resetTimeout?: number;
  },
): Promise<T> {
  const breaker = _getOrCreateMsCircuitBreaker(key, options);
  const result = await breaker.fire(fn);
  return result as T;
}

export function _msGetCircuitState(key: string): string {
  const breaker = _opossumCircuitBreakers.get(key);
  if (!breaker) {
    return 'CLOSED';
  }
  if (breaker.halfOpen) {
    return 'HALF_OPEN';
  }
  if (breaker.opened) {
    return 'OPEN';
  }
  return 'CLOSED';
}

export function _msResetCircuit(key: string): void {
  const breaker = _opossumCircuitBreakers.get(key);
  if (breaker) {
    breaker.close();
  }
}

export async function _msWithRetry<T>(
  fn: () => Promise<T>,
  attempts: number,
  delayMs = 100,
): Promise<T> {
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (err) {
      if (i === attempts - 1) throw err;
      await new Promise((r) => setTimeout(r, delayMs));
    }
  }
  throw new Error('_msWithRetry: unreachable');
}

export async function _msWithExponentialBackoff<T>(
  fn: () => Promise<T>,
  attempts: number,
  baseDelayMs = 100,
): Promise<T> {
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (err) {
      if (i === attempts - 1) throw err;
      await new Promise((r) => setTimeout(r, baseDelayMs * 2 ** i));
    }
  }
  throw new Error('_msWithExponentialBackoff: unreachable');
}

export async function _msWithTimeout<T>(
  fn: () => Promise<T>,
  ms: number,
): Promise<T> {
  const timeoutPromise = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error(`Operation timed out after ${ms}ms`)), ms),
  );
  return Promise.race([fn(), timeoutPromise]);
}

const _bulkheadSemaphores = new Map<string, { current: number; max: number }>();

export async function _msWithBulkhead<T>(
  key: string,
  fn: () => Promise<T>,
  concurrency = 10,
): Promise<T> {
  let sem = _bulkheadSemaphores.get(key);
  if (!sem) {
    sem = { current: 0, max: concurrency };
    _bulkheadSemaphores.set(key, sem);
  }
  if (sem.current >= sem.max) {
    throw new Error(
      `Bulkhead "${key}" is at capacity (max ${sem.max} concurrent calls).`,
    );
  }
  sem.current++;
  try {
    return await fn();
  } finally {
    sem.current--;
  }
}

// ── Service Registry ─────────────────────────────────────────────────────────

const _SERVICE_REGISTRY_URL =
  process.env.SERVICE_REGISTRY_URL || 'http://localhost:7000';

export async function _msRegister(
  service: string,
  endpoint: string,
): Promise<void> {
  await axios.post(`${_SERVICE_REGISTRY_URL}/register`, {
    service,
    endpoint,
  });
}

export async function _msDeregister(service: string): Promise<void> {
  await axios.delete(`${_SERVICE_REGISTRY_URL}/deregister/${service}`);
}

// ── Events ───────────────────────────────────────────────────────────────────

const _EVENT_BUS_URL =
  process.env.EVENT_BUS_URL || 'http://localhost:7001';

const _eventHandlers: Record<string, Array<(...args: unknown[]) => void>> = (
  global as Record<string, unknown>
)._eventHandlers as typeof _eventHandlers ?? {};
(global as Record<string, unknown>)._eventHandlers = _eventHandlers;

export async function _msBroadcast(
  event: string,
  data: unknown,
): Promise<void> {
  await axios.post(`${_EVENT_BUS_URL}/broadcast`, { event, data });
}

export function _msSubscribe(
  event: string,
  handler: (...args: unknown[]) => void,
): void {
  (_eventHandlers[event] = _eventHandlers[event] ?? []).push(handler);
}

export async function _msPublish(
  event: string,
  payload: unknown,
): Promise<void> {
  await axios.post(`${_EVENT_BUS_URL}/publish`, { event, payload });
}

// ── Config ───────────────────────────────────────────────────────────────────

const _CONFIG_SERVICE_URL =
  process.env.CONFIG_SERVICE_URL || 'http://localhost:7002';

export async function _msGetConfig(key: string): Promise<unknown> {
  const response = await axios.get(`${_CONFIG_SERVICE_URL}/config/${key}`);
  return response.data;
}

export async function _msSetConfig(
  key: string,
  value: unknown,
): Promise<void> {
  await axios.put(`${_CONFIG_SERVICE_URL}/config/${key}`, value);
}

// ── Tracing ──────────────────────────────────────────────────────────────────

export function _msPropagateContext(
  headers: Record<string, string>,
): Record<string, string> {
  return {
    ...headers,
    'x-trace-id': ((global as Record<string, unknown>)._traceId as string) ?? '',
  };
}

export function _msGetTraceId(): string {
  return ((global as Record<string, unknown>)._traceId as string) ?? '';
}

export function _msSetTraceId(id: string): void {
  (global as Record<string, unknown>)._traceId = id;
}

// ── Load Balancing ───────────────────────────────────────────────────────────

const _instances: Record<string, string[]> = (
  global as Record<string, unknown>
)._instances as typeof _instances ?? {};
(global as Record<string, unknown>)._instances = _instances;

export function _msGetNextInstance(service: string): string {
  const list = _instances[service] ?? [_msGetServiceUrl(service)];
  return list[Math.floor(Math.random() * list.length)];
}

export function _msGetAllInstances(service: string): string[] {
  return _instances[service] ?? [_msGetServiceUrl(service)];
}

// ── Rate Limiting ────────────────────────────────────────────────────────────

const _rateLimit: Record<string, { count: number; windowStart: number }> = (
  global as Record<string, unknown>
)._rateLimit as typeof _rateLimit ?? {};
(global as Record<string, unknown>)._rateLimit = _rateLimit;

export async function _msCheckRateLimit(
  key: string,
  maxCount: number,
  windowSec: number,
): Promise<boolean> {
  const now = Math.floor(Date.now() / 1000);
  const bucket = _rateLimit[key] ?? { count: 0, windowStart: now };
  if (now - bucket.windowStart >= windowSec) {
    bucket.windowStart = now;
    bucket.count = 0;
  }
  bucket.count++;
  _rateLimit[key] = bucket;
  return bucket.count <= maxCount;
}

export async function _msGetRateLimitStatus(
  key: string,
): Promise<{ count: number; windowStart: number }> {
  return _rateLimit[key] ?? { count: 0, windowStart: 0 };
}
