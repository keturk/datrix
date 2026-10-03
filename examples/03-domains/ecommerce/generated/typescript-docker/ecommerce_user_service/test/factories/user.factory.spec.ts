import { buildUser } from './user.factory';

describe('buildUser', () => {
  it('should return a valid partial entity', () => {
    const result = buildUser();
    expect(result).toBeDefined();
    expect(result.email).toBeDefined();
    expect(result.passwordHash).toBeDefined();
    expect(result.firstName).toBeDefined();
    expect(result.lastName).toBeDefined();
    expect(result.phoneNumber).toBeDefined();
    expect(result.lastLoginAt).toBeDefined();
    expect(result.emailVerifiedAt).toBeDefined();
    expect(result.emailVerificationToken).toBeDefined();
    expect(result.passwordResetToken).toBeDefined();
    expect(result.passwordResetExpiry).toBeDefined();
    expect(result.shippingAddress).toBeDefined();
    expect(result.billingAddress).toBeDefined();
  });

  it('should apply overrides', () => {
    const overrides = {
      email: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}@example.com`,
    };
    const result = buildUser(overrides);
    expect(result.email).toBe(overrides.email);
  });

  it('should produce different instances', () => {
    const a = buildUser();
    const b = buildUser();
    expect(a).not.toBe(b);
  });
});
