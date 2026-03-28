import { buildOrderItem } from './order-item.factory';

describe('buildOrderItem', () => {
  it('should return a valid partial entity', () => {
    const result = buildOrderItem();
    expect(result).toBeDefined();
    expect(result.productId).toBeDefined();
    expect(result.productName).toBeDefined();
    expect(result.quantity).toBeDefined();
    expect(result.unitPrice).toBeDefined();
    expect(result.orderId).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      productId: crypto.randomUUID(),
    };
    const result = buildOrderItem(overrides);
    expect(result.productId).toBe(overrides.productId);
  });

  it('should produce different instances', () => {
    const a = buildOrderItem();
    const b = buildOrderItem();
    expect(a).not.toBe(b);
  });
});
