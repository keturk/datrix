import { IdempotencyKey } from '../../src/entities/idempotency-key.entity';

/**
 * Build a partial IdempotencyKey with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildIdempotencyKey(
  overrides?: Partial<IdempotencyKey>,
): Partial<IdempotencyKey> {
  return {
    key: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    operation: 'test',
    resourceId: crypto.randomUUID(),
    response: { key: 'value' },
    expiresAt: new Date('2025-01-15T12:00:00Z'),
    ...overrides,
  };
}
