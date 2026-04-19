import { ShipmentEvent } from '../src/entities/shipment-event.entity';
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
    const shipmentIdVal = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';
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
    const shipmentIdVal = 'b1ffbc99-9c0b-4ef8-bb6d-6bb9bd380a22';
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

  it('should have server-managed fields', () => {
    const entity = new ShipmentEvent();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});
