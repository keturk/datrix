import { buildRefund } from './refund.factory';

describe('buildRefund', () => {
  it('should return a valid partial entity', () => {
    const result = buildRefund();
    expect(result).toBeDefined();
    expect(result.amount).toBeDefined();
    expect(result.reason).toBeDefined();
    expect(result.status).toBeDefined();
    expect(result.refundTransactionId).toBeDefined();
    expect(result.errorMessage).toBeDefined();
    expect(result.processedAt).toBeDefined();
    expect(result.paymentId).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      amount: 99.99,
    };
    const result = buildRefund(overrides);
    expect(result.amount).toBe(overrides.amount);
  });

  it('should produce different instances', () => {
    const a = buildRefund();
    const b = buildRefund();
    expect(a).not.toBe(b);
  });
});
