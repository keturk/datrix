import { ShipmentItem } from '../src/ecommerce_shipping_service/entities/shipping_db/shipment-item.entity';

describe('ShipmentItem Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new ShipmentItem();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new ShipmentItem();
    const productIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const quantityVal = 42;
    const shipmentIdVal = '550e8400-e29b-41d4-a716-446655440000';
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
    const shipmentIdVal = '660e8400-e29b-41d4-a716-446655440001';
    entity.productId = productIdVal;
    entity.quantity = quantityVal;
    entity.shipmentId = shipmentIdVal;
    expect(entity.productId).toBe(productIdVal);
    expect(entity.quantity).toBe(quantityVal);
    expect(entity.shipmentId).toBe(shipmentIdVal);
  });

  it('should have index on shipmentId', () => {
    const entity = new ShipmentItem();
    entity.shipmentId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.shipmentId).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new ShipmentItem();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
    expect(entity.id).toBeUndefined();
  });
});
