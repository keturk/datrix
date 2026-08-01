import { buildOrder } from './order.factory';

describe('buildOrder', () => {
  it('should return a valid partial entity', () => {
    const result = buildOrder();
    expect(result).toBeDefined();
    expect(result.id).toBeDefined();
    expect(result.amount).toBeDefined();
    expect(result.currency).toBeDefined();
    expect(result.status).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      id: crypto.randomUUID(),
    };
    const result = buildOrder(overrides);
    expect(result.id).toBe(overrides.id);
  });

  it('should produce different instances', () => {
    const a = buildOrder();
    const b = buildOrder();
    expect(a).not.toBe(b);
  });
});
