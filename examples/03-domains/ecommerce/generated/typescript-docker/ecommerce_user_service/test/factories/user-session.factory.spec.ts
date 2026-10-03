import { buildUserSession } from './user-session.factory';

describe('buildUserSession', () => {
  it('should return a valid partial entity', () => {
    const result = buildUserSession();
    expect(result).toBeDefined();
    expect(result.token).toBeDefined();
    expect(result.deviceName).toBeDefined();
    expect(result.ipAddress).toBeDefined();
    expect(result.userAgent).toBeDefined();
    expect(result.expiresAt).toBeDefined();
    expect(result.lastActivityAt).toBeDefined();
    expect(result.user).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      token: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}`,
    };
    const result = buildUserSession(overrides);
    expect(result.token).toBe(overrides.token);
  });

  it('should produce different instances', () => {
    const a = buildUserSession();
    const b = buildUserSession();
    expect(a).not.toBe(b);
  });
});
