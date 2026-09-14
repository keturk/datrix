import { Payment } from '../../src/entities/payment.entity';
import { PaymentMethod } from '../../src/enums/payment-method.enum';
import { PaymentStatus } from '../../src/enums/payment-status.enum';

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
    status: PaymentStatus.Pending,
    transactionId: `x`,
    gatewayResponse: 'test-value',
    errorMessage: 'test-value',
    processedAt: new Date(),
    ...overrides,
  };
}
