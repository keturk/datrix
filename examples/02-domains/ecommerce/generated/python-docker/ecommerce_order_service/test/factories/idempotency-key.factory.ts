import { IdempotencyKey } from '../../src/entities/idempotency-key.entity';

/**
 * Build a partial IdempotencyKey with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildIdempotencyKey(
  overrides?: Partial<IdempotencyKey>,
): Partial<IdempotencyKey> {
  return {
    key: `x`,
    operation: `x`,
    resourceId: crypto.randomUUID(),
    response: {},
    expiresAt: new Date(),
    ...overrides,
  };
}
