import { Refund } from '../../src/entities/refund.entity';

/**
 * Build a partial Refund with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildRefund(
  overrides?: Partial<Refund>,
): Partial<Refund> {
  return {
    amount: 99.99,
    reason: 'test',
    refundTransactionId: 'test',
    errorMessage: 'test',
    processedAt: new Date('2025-01-15T12:00:00Z'),
    payment: crypto.randomUUID(),
    ...overrides,
  };
}
