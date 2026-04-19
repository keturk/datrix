import { buildInventoryReservation } from './inventory-reservation.factory';

describe('buildInventoryReservation', () => {
  it('should return a valid partial entity', () => {
    const result = buildInventoryReservation();
    expect(result).toBeDefined();
    expect(result.reservationId).toBeDefined();
    expect(result.quantity).toBeDefined();
    expect(result.status).toBeDefined();
    expect(result.expiresAt).toBeDefined();
    expect(result.productId).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      reservationId: crypto.randomUUID(),
    };
    const result = buildInventoryReservation(overrides);
    expect(result.reservationId).toBe(overrides.reservationId);
  });

  it('should produce different instances', () => {
    const a = buildInventoryReservation();
    const b = buildInventoryReservation();
    expect(a).not.toBe(b);
  });
});
