import { Payment } from '../../src/entities/payment.entity';
import { PaymentMethod } from '../../src/enums/payment-method.enum';

/**
 * Build a partial Payment with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildPayment(
  overrides?: Partial<Payment>,
): Partial<Payment> {
  return {
    orderId: crypto.randomUUID(),
    customerId: crypto.randomUUID(),
    amount: 99.99,
    method: PaymentMethod.CreditCard,
    transactionId: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    gatewayResponse: 'test',
    errorMessage: 'test',
    processedAt: new Date('2025-01-15T12:00:00Z'),
    ...overrides,
  };
}
