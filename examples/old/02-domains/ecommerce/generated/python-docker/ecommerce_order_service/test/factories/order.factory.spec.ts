import { buildOrder } from './order.factory';

describe('buildOrder', () => {
  it('should return a valid partial entity', () => {
    const result = buildOrder();
    expect(result).toBeDefined();
    expect(result.customerId).toBeDefined();
    expect(result.orderNumber).toBeDefined();
    expect(result.status).toBeDefined();
    expect(result.subtotal).toBeDefined();
    expect(result.tax).toBeDefined();
    expect(result.shippingCost).toBeDefined();
    expect(result.discount).toBeDefined();
    expect(result.shippingAddress).toBeDefined();
    expect(result.billingAddress).toBeDefined();
    expect(result.inventoryReservationId).toBeDefined();
    expect(result.paymentId).toBeDefined();
    expect(result.shipmentId).toBeDefined();
    expect(result.cancellationReason).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      customerId: crypto.randomUUID(),
    };
    const result = buildOrder(overrides);
    expect(result.customerId).toBe(overrides.customerId);
  });

  it('should produce different instances', () => {
    const a = buildOrder();
    const b = buildOrder();
    expect(a).not.toBe(b);
  });
});
