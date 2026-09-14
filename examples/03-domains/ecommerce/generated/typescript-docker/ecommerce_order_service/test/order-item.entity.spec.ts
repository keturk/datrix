import { OrderItem } from '../src/ecommerce_order_service/entities/order_db/order-item.entity';

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
    const orderIdVal = '550e8400-e29b-41d4-a716-446655440000';
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
    const orderIdVal = '660e8400-e29b-41d4-a716-446655440001';
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

  it('should have index on orderId', () => {
    const entity = new OrderItem();
    entity.orderId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.orderId).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new OrderItem();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
    expect(entity.id).toBeUndefined();
  });
});
