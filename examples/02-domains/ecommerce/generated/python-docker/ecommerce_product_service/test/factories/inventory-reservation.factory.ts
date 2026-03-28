import { InventoryReservation } from '../../src/entities/inventory-reservation.entity';
import { ReservationStatus } from '../../src/enums/reservation-status.enum';

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
    status: ReservationStatus.Reserved,
    expiresAt: new Date(),
    productId: crypto.randomUUID(),
    ...overrides,
  };
}
