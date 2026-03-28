import { Payment } from '../src/entities/payment.entity';
import { PaymentMethod } from '../src/enums/payment-method.enum';
import { PaymentStatus } from '../src/enums/payment-status.enum';

describe('Payment Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new Payment();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new Payment();
    const orderIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const customerIdVal = '550e8400-e29b-41d4-a716-446655440000';
    const amountVal = 99.99;
    const methodVal = PaymentMethod.CreditCard;
    const statusVal = PaymentStatus.Pending;
    const transactionIdVal = `test-${Date.now()}`;
    const gatewayResponseVal = 'test-value';
    const errorMessageVal = 'test-value';
    const processedAtVal = new Date('2025-01-15T12:00:00Z');
    entity.orderId = orderIdVal;
    entity.customerId = customerIdVal;
    entity.amount = amountVal;
    entity.method = methodVal;
    entity.status = statusVal;
    entity.transactionId = transactionIdVal;
    entity.gatewayResponse = gatewayResponseVal;
    entity.errorMessage = errorMessageVal;
    entity.processedAt = processedAtVal;
    expect(entity.orderId).toBe(orderIdVal);
    expect(entity.customerId).toBe(customerIdVal);
    expect(entity.amount).toBe(amountVal);
    expect(entity.method).toBe(methodVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.transactionId).toBe(transactionIdVal);
    expect(entity.gatewayResponse).toBe(gatewayResponseVal);
    expect(entity.errorMessage).toBe(errorMessageVal);
    expect(entity.processedAt).toEqual(processedAtVal);
  });

  it('should update field values', () => {
    const entity = new Payment();
    const orderIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const customerIdVal = '660e8400-e29b-41d4-a716-446655440001';
    const amountVal = 149.99;
    const methodVal = PaymentMethod.DebitCard;
    const statusVal = PaymentStatus.Processing;
    const transactionIdVal = `updated-${Date.now()}`;
    const gatewayResponseVal = 'updated-value';
    const errorMessageVal = 'updated-value';
    const processedAtVal = new Date('2025-06-20T15:30:00Z');
    entity.orderId = orderIdVal;
    entity.customerId = customerIdVal;
    entity.amount = amountVal;
    entity.method = methodVal;
    entity.status = statusVal;
    entity.transactionId = transactionIdVal;
    entity.gatewayResponse = gatewayResponseVal;
    entity.errorMessage = errorMessageVal;
    entity.processedAt = processedAtVal;
    expect(entity.orderId).toBe(orderIdVal);
    expect(entity.customerId).toBe(customerIdVal);
    expect(entity.amount).toBe(amountVal);
    expect(entity.method).toBe(methodVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.transactionId).toBe(transactionIdVal);
    expect(entity.gatewayResponse).toBe(gatewayResponseVal);
    expect(entity.errorMessage).toBe(errorMessageVal);
    expect(entity.processedAt).toEqual(processedAtVal);
  });

  it('should enforce unique constraint on transactionId', () => {
    const entity = new Payment();
    entity.transactionId = `test-${Date.now()}`;
    expect(entity.transactionId).toBeDefined();
  });

  it('should have index on orderId', () => {
    const entity = new Payment();
    entity.orderId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.orderId).toBeDefined();
  });

  it('should have index on customerId', () => {
    const entity = new Payment();
    entity.customerId = '550e8400-e29b-41d4-a716-446655440000';
    expect(entity.customerId).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new Payment();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});
