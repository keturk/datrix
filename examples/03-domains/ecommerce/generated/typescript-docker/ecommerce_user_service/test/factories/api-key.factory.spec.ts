import { buildApiKey } from './api-key.factory';

describe('buildApiKey', () => {
  it('should return a valid partial entity', () => {
    const result = buildApiKey();
    expect(result).toBeDefined();
    expect(result.keyHash).toBeDefined();
    expect(result.ownerId).toBeDefined();
    expect(result.keyPrefix).toBeDefined();
    expect(result.scopes).toBeDefined();
    expect(result.expiresAt).toBeDefined();
    expect(result.lastUsedAt).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      keyHash: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    };
    const result = buildApiKey(overrides);
    expect(result.keyHash).toBe(overrides.keyHash);
  });

  it('should produce different instances', () => {
    const a = buildApiKey();
    const b = buildApiKey();
    expect(a).not.toBe(b);
  });
});
