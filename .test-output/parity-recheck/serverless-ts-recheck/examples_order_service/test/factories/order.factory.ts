import { Order } from '../../src/entities/order.entity';

/**
 * Build a partial Order with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildOrder(
  overrides?: Partial<Order>,
): Partial<Order> {
  return {
    id: crypto.randomUUID(),
    amount: 10.50,
    currency: 'test-value',
    status: 'test-value',
    ...overrides,
  };
}
