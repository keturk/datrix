import { buildPayment } from './payment.factory';

describe('buildPayment', () => {
  it('should return a valid partial entity', () => {
    const result = buildPayment();
    expect(result).toBeDefined();
    expect(result.orderId).toBeDefined();
    expect(result.customerId).toBeDefined();
    expect(result.amount).toBeDefined();
    expect(result.method).toBeDefined();
    expect(result.status).toBeDefined();
    expect(result.transactionId).toBeDefined();
    expect(result.gatewayResponse).toBeDefined();
    expect(result.errorMessage).toBeDefined();
    expect(result.processedAt).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      orderId: crypto.randomUUID(),
    };
    const result = buildPayment(overrides);
    expect(result.orderId).toBe(overrides.orderId);
  });

  it('should produce different instances', () => {
    const a = buildPayment();
    const b = buildPayment();
    expect(a).not.toBe(b);
  });
});
