import { Refund } from '../../src/entities/refund.entity';
import { PaymentStatus } from '../../src/enums/payment-status.enum';

/**
 * Build a partial Refund with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildRefund(
  overrides?: Partial<Refund>,
): Partial<Refund> {
  return {
    amount: 99.99,
    reason: `x`,
    status: PaymentStatus.Pending,
    refundTransactionId: 'test-value',
    errorMessage: 'test-value',
    processedAt: new Date(),
    paymentId: crypto.randomUUID(),
    ...overrides,
  };
}
