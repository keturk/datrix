import { buildIdempotencyKey } from './idempotency-key.factory';

describe('buildIdempotencyKey', () => {
  it('should return a valid partial entity', () => {
    const result = buildIdempotencyKey();
    expect(result).toBeDefined();
    expect(result.key).toBeDefined();
    expect(result.operation).toBeDefined();
    expect(result.resourceId).toBeDefined();
    expect(result.response).toBeDefined();
    expect(result.expiresAt).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      key: `x`,
    };
    const result = buildIdempotencyKey(overrides);
    expect(result.key).toBe(overrides.key);
  });

  it('should produce different instances', () => {
    const a = buildIdempotencyKey();
    const b = buildIdempotencyKey();
    expect(a).not.toBe(b);
  });
});
