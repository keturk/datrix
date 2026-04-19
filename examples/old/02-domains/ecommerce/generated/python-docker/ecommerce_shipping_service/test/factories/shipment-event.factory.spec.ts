import { buildShipmentEvent } from './shipment-event.factory';

describe('buildShipmentEvent', () => {
  it('should return a valid partial entity', () => {
    const result = buildShipmentEvent();
    expect(result).toBeDefined();
    expect(result.timestamp).toBeDefined();
    expect(result.status).toBeDefined();
    expect(result.location).toBeDefined();
    expect(result.description).toBeDefined();
    expect(result.shipmentId).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      timestamp: new Date(),
    };
    const result = buildShipmentEvent(overrides);
    expect(result.timestamp).toEqual(overrides.timestamp);
  });

  it('should produce different instances', () => {
    const a = buildShipmentEvent();
    const b = buildShipmentEvent();
    expect(a).not.toBe(b);
  });
});
