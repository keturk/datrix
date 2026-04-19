import { buildShipmentItem } from './shipment-item.factory';

describe('buildShipmentItem', () => {
  it('should return a valid partial entity', () => {
    const result = buildShipmentItem();
    expect(result).toBeDefined();
    expect(result.productId).toBeDefined();
    expect(result.quantity).toBeDefined();
    expect(result.shipmentId).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      productId: crypto.randomUUID(),
    };
    const result = buildShipmentItem(overrides);
    expect(result.productId).toBe(overrides.productId);
  });

  it('should produce different instances', () => {
    const a = buildShipmentItem();
    const b = buildShipmentItem();
    expect(a).not.toBe(b);
  });
});
