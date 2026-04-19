import { User } from '../../src/entities/user.entity';
import { Address } from '../../src/dto/address.struct';
import { UserRole } from '../../src/enums/user-role.enum';
import { UserStatus } from '../../src/enums/user-status.enum';

/**
 * Build a partial User with sensible defaults for testing.
 * Override any field via the `overrides` parameter.
 */
export function buildUser(
  overrides?: Partial<User>,
): Partial<User> {
  return {
    email: `test-${Date.now()}@example.com`,
    passwordHash: 'SecureP@ss1',
    firstName: `x`,
    lastName: `x`,
    phoneNumber: '+15551234567',
    role: UserRole.Customer,
    status: UserStatus.Active,
    lastLoginAt: new Date(),
    emailVerifiedAt: new Date(),
    emailVerificationToken: 'test-value',
    passwordResetToken: 'test-value',
    passwordResetExpiry: new Date(),
    shippingAddress: {} as Address,
    billingAddress: {} as Address,
    ...overrides,
  };
}
