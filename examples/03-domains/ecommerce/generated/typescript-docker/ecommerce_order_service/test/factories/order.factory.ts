import { Order } from '../../src/entities/order.entity';
import { Address } from '../../src/dto/address.struct';

/**
 * Build a partial Order with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildOrder(
  overrides?: Partial<Order>,
): Partial<Order> {
  return {
    customerId: crypto.randomUUID(),
    orderNumber: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    subtotal: 99.99,
    tax: 99.99,
    shippingCost: 99.99,
    discount: 99.99,
    shippingAddress: {street: 'test', city: 'test', state: 'test', zipCode: 'test', country: 'US', phone: '15551234567'} as Address,
    billingAddress: {street: 'test', city: 'test', state: 'test', zipCode: 'test', country: 'US', phone: '15551234567'} as Address,
    inventoryReservationId: crypto.randomUUID(),
    paymentId: crypto.randomUUID(),
    shipmentId: crypto.randomUUID(),
    cancellationReason: 'test',
    ...overrides,
  };
}
