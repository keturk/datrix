import { Order } from '../../src/entities/order.entity';
import { Address } from '../../src/dto/address.struct';
import { OrderStatus } from '../../src/enums/order-status.enum';

/**
 * Build a partial Order with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildOrder(
  overrides?: Partial<Order>,
): Partial<Order> {
  return {
    customerId: crypto.randomUUID(),
    orderNumber: `x`,
    status: OrderStatus.Pending,
    subtotal: 99.99,
    tax: 99.99,
    shippingCost: 99.99,
    discount: 99.99,
    shippingAddress: {} as Address,
    billingAddress: {} as Address,
    inventoryReservationId: crypto.randomUUID(),
    paymentId: crypto.randomUUID(),
    shipmentId: crypto.randomUUID(),
    cancellationReason: 'test-value',
    ...overrides,
  };
}
