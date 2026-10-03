import { ApiKey } from '../../src/entities/api-key.entity';

/**
 * Build a partial ApiKey with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildApiKey(
  overrides?: Partial<ApiKey>,
): Partial<ApiKey> {
  return {
    keyHash: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    ownerId: crypto.randomUUID(),
    keyPrefix: 'test',
    scopes: [],
    expiresAt: new Date('2025-01-15T12:00:00Z'),
    lastUsedAt: new Date('2025-01-15T12:00:00Z'),
    ...overrides,
  };
}
