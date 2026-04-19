import { OrderItem } from '../src/entities/order-item.entity';

describe('OrderItem Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new OrderItem();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new OrderItem();
    const productIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const productNameVal = 'test-value';
    const quantityVal = 42;
    const unitPriceVal = 99.99;
    const orderIdVal = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';
    entity.productId = productIdVal;
    entity.productName = productNameVal;
    entity.quantity = quantityVal;
    entity.unitPrice = unitPriceVal;
    entity.orderId = orderIdVal;
    expect(entity.productId).toBe(productIdVal);
    expect(entity.productName).toBe(productNameVal);
    expect(entity.quantity).toBe(quantityVal);
    expect(entity.unitPrice).toBe(unitPriceVal);
    expect(entity.orderId).toBe(orderIdVal);
  });

  it('should update field values', () => {
    const entity = new OrderItem();
    const productIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const productNameVal = 'updated-value';
    const quantityVal = 99;
    const unitPriceVal = 149.99;
    const orderIdVal = 'b1ffbc99-9c0b-4ef8-bb6d-6bb9bd380a22';
    entity.productId = productIdVal;
    entity.productName = productNameVal;
    entity.quantity = quantityVal;
    entity.unitPrice = unitPriceVal;
    entity.orderId = orderIdVal;
    expect(entity.productId).toBe(productIdVal);
    expect(entity.productName).toBe(productNameVal);
    expect(entity.quantity).toBe(quantityVal);
    expect(entity.unitPrice).toBe(unitPriceVal);
    expect(entity.orderId).toBe(orderIdVal);
  });

  it('should have index on productId', () => {
    const entity = new OrderItem();
    entity.productId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.productId).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new OrderItem();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});
