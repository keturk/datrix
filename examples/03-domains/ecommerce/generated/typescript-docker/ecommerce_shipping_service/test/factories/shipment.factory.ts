import { Shipment } from '../../src/entities/shipment.entity';
import { Address } from '../../src/dto/address.struct';
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
    trackingNumber: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    carrier: ShippingCarrier.FedEx,
    destination: {street: 'test', city: 'test', state: 'test', zipCode: 'test', country: 'US', phone: '15551234567'} as Address,
    weight: 5.50,
    estimatedDelivery: new Date('2025-01-15T12:00:00Z'),
    actualDelivery: new Date('2025-01-15T12:00:00Z'),
    failureReason: 'test',
    ...overrides,
  };
}
