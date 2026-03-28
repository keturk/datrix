import { OrderItem } from '../../src/entities/order-item.entity';

/**
 * Build a partial OrderItem with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildOrderItem(
  overrides?: Partial<OrderItem>,
): Partial<OrderItem> {
  return {
    productId: crypto.randomUUID(),
    productName: `x`,
    quantity: 42,
    unitPrice: 99.99,
    orderId: crypto.randomUUID(),
    ...overrides,
  };
}
