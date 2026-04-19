import { Shipment } from '../../src/entities/shipment.entity';
import { Address } from '../../src/dto/address.struct';
import { ShipmentStatus } from '../../src/enums/shipment-status.enum';
import { ShippingCarrier } from '../../src/enums/shipping-carrier.enum';

/**
 * Build a partial Shipment with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildShipment(
  overrides?: Partial<Shipment>,
): Partial<Shipment> {
  return {
    orderId: crypto.randomUUID(),
    trackingNumber: `x`,
    carrier: ShippingCarrier.FedEx,
    status: ShipmentStatus.Pending,
    destination: {} as Address,
    weight: 10.50,
    estimatedDelivery: new Date(),
    actualDelivery: new Date(),
    failureReason: 'test-value',
    ...overrides,
  };
}
