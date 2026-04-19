import { ShipmentItem } from '../../src/entities/shipment-item.entity';

/**
 * Build a partial ShipmentItem with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildShipmentItem(
  overrides?: Partial<ShipmentItem>,
): Partial<ShipmentItem> {
  return {
    productId: crypto.randomUUID(),
    quantity: 42,
    shipmentId: crypto.randomUUID(),
    ...overrides,
  };
}
