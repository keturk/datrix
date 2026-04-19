import { Refund } from '../src/entities/refund.entity';
import { PaymentStatus } from '../src/enums/payment-status.enum';

describe('Refund Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new Refund();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new Refund();
    const amountVal = 99.99;
    const reasonVal = 'test-value';
    const statusVal = PaymentStatus.Pending;
    const refundTransactionIdVal = 'test-value';
    const errorMessageVal = 'test-value';
    const processedAtVal = new Date('2025-01-15T12:00:00Z');
    const paymentIdVal = 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11';
    entity.amount = amountVal;
    entity.reason = reasonVal;
    entity.status = statusVal;
    entity.refundTransactionId = refundTransactionIdVal;
    entity.errorMessage = errorMessageVal;
    entity.processedAt = processedAtVal;
    entity.paymentId = paymentIdVal;
    expect(entity.amount).toBe(amountVal);
    expect(entity.reason).toBe(reasonVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.refundTransactionId).toBe(refundTransactionIdVal);
    expect(entity.errorMessage).toBe(errorMessageVal);
    expect(entity.processedAt).toEqual(processedAtVal);
    expect(entity.paymentId).toBe(paymentIdVal);
  });

  it('should update field values', () => {
    const entity = new Refund();
    const amountVal = 149.99;
    const reasonVal = 'updated-value';
    const statusVal = PaymentStatus.Processing;
    const refundTransactionIdVal = 'updated-value';
    const errorMessageVal = 'updated-value';
    const processedAtVal = new Date('2025-06-20T15:30:00Z');
    const paymentIdVal = 'b1ffbc99-9c0b-4ef8-bb6d-6bb9bd380a22';
    entity.amount = amountVal;
    entity.reason = reasonVal;
    entity.status = statusVal;
    entity.refundTransactionId = refundTransactionIdVal;
    entity.errorMessage = errorMessageVal;
    entity.processedAt = processedAtVal;
    entity.paymentId = paymentIdVal;
    expect(entity.amount).toBe(amountVal);
    expect(entity.reason).toBe(reasonVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.refundTransactionId).toBe(refundTransactionIdVal);
    expect(entity.errorMessage).toBe(errorMessageVal);
    expect(entity.processedAt).toEqual(processedAtVal);
    expect(entity.paymentId).toBe(paymentIdVal);
  });

  it('should have server-managed fields', () => {
    const entity = new Refund();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});
