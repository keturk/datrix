import { buildShipment } from './shipment.factory';

describe('buildShipment', () => {
  it('should return a valid partial entity', () => {
    const result = buildShipment();
    expect(result).toBeDefined();
    expect(result.orderId).toBeDefined();
    expect(result.trackingNumber).toBeDefined();
    expect(result.carrier).toBeDefined();
    expect(result.status).toBeDefined();
    expect(result.destination).toBeDefined();
    expect(result.weight).toBeDefined();
    expect(result.estimatedDelivery).toBeDefined();
    expect(result.actualDelivery).toBeDefined();
    expect(result.failureReason).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      orderId: crypto.randomUUID(),
    };
    const result = buildShipment(overrides);
    expect(result.orderId).toBe(overrides.orderId);
  });

  it('should produce different instances', () => {
    const a = buildShipment();
    const b = buildShipment();
    expect(a).not.toBe(b);
  });
});
