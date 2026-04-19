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
    timestamp: new Date(),
    status: ShipmentStatus.Pending,
    location: `x`,
    description: 'test-text-content',
    shipmentId: crypto.randomUUID(),
    ...overrides,
  };
}
