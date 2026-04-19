import { ShipmentItem } from '../src/entities/shipment-item.entity';

describe('ShipmentItem Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new ShipmentItem();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new ShipmentItem();
    const productIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const quantityVal = 42;
    const shipmentIdVal = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';
    entity.productId = productIdVal;
    entity.quantity = quantityVal;
    entity.shipmentId = shipmentIdVal;
    expect(entity.productId).toBe(productIdVal);
    expect(entity.quantity).toBe(quantityVal);
    expect(entity.shipmentId).toBe(shipmentIdVal);
  });

  it('should update field values', () => {
    const entity = new ShipmentItem();
    const productIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const quantityVal = 99;
    const shipmentIdVal = 'b1ffbc99-9c0b-4ef8-bb6d-6bb9bd380a22';
    entity.productId = productIdVal;
    entity.quantity = quantityVal;
    entity.shipmentId = shipmentIdVal;
    expect(entity.productId).toBe(productIdVal);
    expect(entity.quantity).toBe(quantityVal);
    expect(entity.shipmentId).toBe(shipmentIdVal);
  });

  it('should have server-managed fields', () => {
    const entity = new ShipmentItem();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});
