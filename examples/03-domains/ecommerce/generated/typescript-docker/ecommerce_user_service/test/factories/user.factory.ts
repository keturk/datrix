import { User } from '../../src/entities/user.entity';
import { Address } from '../../src/dto/address.struct';

/**
 * Build a partial User with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildUser(
  overrides?: Partial<User>,
): Partial<User> {
  return {
    email: `test_${crypto.randomUUID().replace(/-/g, '').slice(0, 8)}@example.com`,
    passwordHash: 'SecureP@ss1',
    firstName: 'TestName',
    lastName: 'test',
    phoneNumber: '15551234567',
    lastLoginAt: new Date('2025-01-15T12:00:00Z'),
    emailVerifiedAt: new Date('2025-01-15T12:00:00Z'),
    emailVerificationToken: 'user@example.com',
    passwordResetToken: 'test',
    passwordResetExpiry: new Date('2025-01-15T12:00:00Z'),
    shippingAddress: {street: 'test', city: 'test', state: 'test', zipCode: 'test', country: 'US', phone: '15551234567'} as Address,
    billingAddress: {street: 'test', city: 'test', state: 'test', zipCode: 'test', country: 'US', phone: '15551234567'} as Address,
    ...overrides,
  };
}
