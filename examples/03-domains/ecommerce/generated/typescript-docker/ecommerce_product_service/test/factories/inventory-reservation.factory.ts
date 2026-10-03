import { InventoryReservation } from '../../src/entities/inventory-reservation.entity';

/**
 * Build a partial InventoryReservation with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildInventoryReservation(
  overrides?: Partial<InventoryReservation>,
): Partial<InventoryReservation> {
  return {
    reservationId: crypto.randomUUID(),
    quantity: 42,
    expiresAt: new Date('2025-01-15T12:00:00Z'),
    product: crypto.randomUUID(),
    ...overrides,
  };
}
