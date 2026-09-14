import { ShipmentEvent } from '../src/ecommerce_shipping_service/entities/shipping_db/shipment-event.entity';
import { ShipmentStatus } from '../src/enums/shipment-status.enum';

describe('ShipmentEvent Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new ShipmentEvent();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new ShipmentEvent();
    const timestampVal = new Date('2025-01-15T12:00:00Z');
    const statusVal = ShipmentStatus.Pending;
    const locationVal = 'test-value';
    const descriptionVal = 'test-text-content';
    const shipmentIdVal = '550e8400-e29b-41d4-a716-446655440000';
    entity.timestamp = timestampVal;
    entity.status = statusVal;
    entity.location = locationVal;
    entity.description = descriptionVal;
    entity.shipmentId = shipmentIdVal;
    expect(entity.timestamp).toEqual(timestampVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.location).toBe(locationVal);
    expect(entity.description).toBe(descriptionVal);
    expect(entity.shipmentId).toBe(shipmentIdVal);
  });

  it('should update field values', () => {
    const entity = new ShipmentEvent();
    const timestampVal = new Date('2025-06-20T15:30:00Z');
    const statusVal = ShipmentStatus.PickedUp;
    const locationVal = 'updated-value';
    const descriptionVal = 'updated-text-content';
    const shipmentIdVal = '660e8400-e29b-41d4-a716-446655440001';
    entity.timestamp = timestampVal;
    entity.status = statusVal;
    entity.location = locationVal;
    entity.description = descriptionVal;
    entity.shipmentId = shipmentIdVal;
    expect(entity.timestamp).toEqual(timestampVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.location).toBe(locationVal);
    expect(entity.description).toBe(descriptionVal);
    expect(entity.shipmentId).toBe(shipmentIdVal);
  });

  it('should have index on shipmentId', () => {
    const entity = new ShipmentEvent();
    entity.shipmentId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.shipmentId).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new ShipmentEvent();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
    expect(entity.id).toBeUndefined();
  });
});
