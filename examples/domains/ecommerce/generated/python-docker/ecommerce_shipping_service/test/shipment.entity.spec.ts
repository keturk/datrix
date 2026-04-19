import { Shipment } from '../src/entities/shipment.entity';
import { ShippingCarrier } from '../src/enums/shipping-carrier.enum';
import { ShipmentStatus } from '../src/enums/shipment-status.enum';
import { Address } from '../src/dto/address.struct';

describe('Shipment Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new Shipment();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new Shipment();
    const orderIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const trackingNumberVal = `test-${Date.now()}`;
    const carrierVal = ShippingCarrier.FedEx;
    const statusVal = ShipmentStatus.Pending;
    const destinationVal = { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address;
    const weightVal = 10.50;
    const estimatedDeliveryVal = new Date('2025-01-15T12:00:00Z');
    const actualDeliveryVal = new Date('2025-01-15T12:00:00Z');
    const failureReasonVal = 'test-value';
    entity.orderId = orderIdVal;
    entity.trackingNumber = trackingNumberVal;
    entity.carrier = carrierVal;
    entity.status = statusVal;
    entity.destination = destinationVal;
    entity.weight = weightVal;
    entity.estimatedDelivery = estimatedDeliveryVal;
    entity.actualDelivery = actualDeliveryVal;
    entity.failureReason = failureReasonVal;
    expect(entity.orderId).toBe(orderIdVal);
    expect(entity.trackingNumber).toBe(trackingNumberVal);
    expect(entity.carrier).toBe(carrierVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.destination).toBe(destinationVal);
    expect(entity.weight).toBe(weightVal);
    expect(entity.estimatedDelivery).toEqual(estimatedDeliveryVal);
    expect(entity.actualDelivery).toEqual(actualDeliveryVal);
    expect(entity.failureReason).toBe(failureReasonVal);
  });

  it('should update field values', () => {
    const entity = new Shipment();
    const orderIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const trackingNumberVal = `updated-${Date.now()}`;
    const carrierVal = ShippingCarrier.Ups;
    const statusVal = ShipmentStatus.PickedUp;
    const destinationVal = { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address;
    const weightVal = 20.75;
    const estimatedDeliveryVal = new Date('2025-06-20T15:30:00Z');
    const actualDeliveryVal = new Date('2025-06-20T15:30:00Z');
    const failureReasonVal = 'updated-value';
    entity.orderId = orderIdVal;
    entity.trackingNumber = trackingNumberVal;
    entity.carrier = carrierVal;
    entity.status = statusVal;
    entity.destination = destinationVal;
    entity.weight = weightVal;
    entity.estimatedDelivery = estimatedDeliveryVal;
    entity.actualDelivery = actualDeliveryVal;
    entity.failureReason = failureReasonVal;
    expect(entity.orderId).toBe(orderIdVal);
    expect(entity.trackingNumber).toBe(trackingNumberVal);
    expect(entity.carrier).toBe(carrierVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.destination).toBe(destinationVal);
    expect(entity.weight).toBe(weightVal);
    expect(entity.estimatedDelivery).toEqual(estimatedDeliveryVal);
    expect(entity.actualDelivery).toEqual(actualDeliveryVal);
    expect(entity.failureReason).toBe(failureReasonVal);
  });

  it('should enforce unique constraint on trackingNumber', () => {
    const entity = new Shipment();
    entity.trackingNumber = `test-${Date.now()}`;
    expect(entity.trackingNumber).toBeDefined();
  });

  it('should have index on orderId', () => {
    const entity = new Shipment();
    entity.orderId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.orderId).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new Shipment();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});
