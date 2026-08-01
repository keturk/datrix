import { Order } from '../src/examples_order_service/entities/db/order.entity';

describe('Order Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new Order();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new Order();
    const idVal = '550e8400-e29b-41d4-a716-446655440000';
    const amountVal = 10.50;
    const currencyVal = 'test-value';
    const statusVal = 'test-value';
    entity.id = idVal;
    entity.amount = amountVal;
    entity.currency = currencyVal;
    entity.status = statusVal;
    expect(entity.id).toBe(idVal);
    expect(entity.amount).toBe(amountVal);
    expect(entity.currency).toBe(currencyVal);
    expect(entity.status).toBe(statusVal);
  });

  it('should update field values', () => {
    const entity = new Order();
    const idVal = '660e8400-e29b-41d4-a716-446655440001';
    const amountVal = 20.75;
    const currencyVal = 'updated-value';
    const statusVal = 'updated-value';
    entity.id = idVal;
    entity.amount = amountVal;
    entity.currency = currencyVal;
    entity.status = statusVal;
    expect(entity.id).toBe(idVal);
    expect(entity.amount).toBe(amountVal);
    expect(entity.currency).toBe(currencyVal);
    expect(entity.status).toBe(statusVal);
  });

});
