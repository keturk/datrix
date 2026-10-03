import { ShipmentEvent } from '../../src/entities/shipment-event.entity';
import { ShipmentStatus } from '../../src/enums/shipment-status.enum';

/**
 * Build a partial ShipmentEvent with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildShipmentEvent(
  overrides?: Partial<ShipmentEvent>,
): Partial<ShipmentEvent> {
  return {
    timestamp: new Date('2025-01-15T12:00:00Z'),
    status: ShipmentStatus.Pending,
    location: 'test',
    description: 'test',
    shipment: crypto.randomUUID(),
    ...overrides,
  };
}
