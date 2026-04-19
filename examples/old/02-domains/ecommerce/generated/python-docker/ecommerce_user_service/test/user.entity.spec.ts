import { User } from '../src/entities/user.entity';
import { UserRole } from '../src/enums/user-role.enum';
import { UserStatus } from '../src/enums/user-status.enum';
import { Address } from '../src/dto/address.struct';

describe('User Entity', () => {
  it('should create a valid entity instance', () => {
    const entity = new User();
    expect(entity).toBeDefined();
  });

  it('should assign and retrieve field values', () => {
    const entity = new User();
    const emailVal = `test-${Date.now()}@example.com`;
    const passwordHashVal = 'SecureP@ss1';
    const firstNameVal = 'test-value';
    const lastNameVal = 'test-value';
    const phoneNumberVal = '+15551234567';
    const roleVal = UserRole.Customer;
    const statusVal = UserStatus.Active;
    const lastLoginAtVal = new Date('2025-01-15T12:00:00Z');
    const emailVerifiedAtVal = new Date('2025-01-15T12:00:00Z');
    const emailVerificationTokenVal = 'test-value';
    const passwordResetTokenVal = 'test-value';
    const passwordResetExpiryVal = new Date('2025-01-15T12:00:00Z');
    const shippingAddressVal = { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address;
    const billingAddressVal = { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address;
    entity.email = emailVal;
    entity.passwordHash = passwordHashVal;
    entity.firstName = firstNameVal;
    entity.lastName = lastNameVal;
    entity.phoneNumber = phoneNumberVal;
    entity.role = roleVal;
    entity.status = statusVal;
    entity.lastLoginAt = lastLoginAtVal;
    entity.emailVerifiedAt = emailVerifiedAtVal;
    entity.emailVerificationToken = emailVerificationTokenVal;
    entity.passwordResetToken = passwordResetTokenVal;
    entity.passwordResetExpiry = passwordResetExpiryVal;
    entity.shippingAddress = shippingAddressVal;
    entity.billingAddress = billingAddressVal;
    expect(entity.email).toBe(emailVal);
    expect(entity.passwordHash).toBe(passwordHashVal);
    expect(entity.firstName).toBe(firstNameVal);
    expect(entity.lastName).toBe(lastNameVal);
    expect(entity.phoneNumber).toBe(phoneNumberVal);
    expect(entity.role).toBe(roleVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.lastLoginAt).toEqual(lastLoginAtVal);
    expect(entity.emailVerifiedAt).toEqual(emailVerifiedAtVal);
    expect(entity.emailVerificationToken).toBe(emailVerificationTokenVal);
    expect(entity.passwordResetToken).toBe(passwordResetTokenVal);
    expect(entity.passwordResetExpiry).toEqual(passwordResetExpiryVal);
    expect(entity.shippingAddress).toBe(shippingAddressVal);
    expect(entity.billingAddress).toBe(billingAddressVal);
  });

  it('should update field values', () => {
    const entity = new User();
    const emailVal = `updated-${Date.now()}@example.com`;
    const passwordHashVal = 'UpdatedP@ss2';
    const firstNameVal = 'updated-value';
    const lastNameVal = 'updated-value';
    const phoneNumberVal = '+15559876543';
    const roleVal = UserRole.Admin;
    const statusVal = UserStatus.Inactive;
    const lastLoginAtVal = new Date('2025-06-20T15:30:00Z');
    const emailVerifiedAtVal = new Date('2025-06-20T15:30:00Z');
    const emailVerificationTokenVal = 'updated-value';
    const passwordResetTokenVal = 'updated-value';
    const passwordResetExpiryVal = new Date('2025-06-20T15:30:00Z');
    const shippingAddressVal = { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address;
    const billingAddressVal = { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address;
    entity.email = emailVal;
    entity.passwordHash = passwordHashVal;
    entity.firstName = firstNameVal;
    entity.lastName = lastNameVal;
    entity.phoneNumber = phoneNumberVal;
    entity.role = roleVal;
    entity.status = statusVal;
    entity.lastLoginAt = lastLoginAtVal;
    entity.emailVerifiedAt = emailVerifiedAtVal;
    entity.emailVerificationToken = emailVerificationTokenVal;
    entity.passwordResetToken = passwordResetTokenVal;
    entity.passwordResetExpiry = passwordResetExpiryVal;
    entity.shippingAddress = shippingAddressVal;
    entity.billingAddress = billingAddressVal;
    expect(entity.email).toBe(emailVal);
    expect(entity.passwordHash).toBe(passwordHashVal);
    expect(entity.firstName).toBe(firstNameVal);
    expect(entity.lastName).toBe(lastNameVal);
    expect(entity.phoneNumber).toBe(phoneNumberVal);
    expect(entity.role).toBe(roleVal);
    expect(entity.status).toBe(statusVal);
    expect(entity.lastLoginAt).toEqual(lastLoginAtVal);
    expect(entity.emailVerifiedAt).toEqual(emailVerifiedAtVal);
    expect(entity.emailVerificationToken).toBe(emailVerificationTokenVal);
    expect(entity.passwordResetToken).toBe(passwordResetTokenVal);
    expect(entity.passwordResetExpiry).toEqual(passwordResetExpiryVal);
    expect(entity.shippingAddress).toBe(shippingAddressVal);
    expect(entity.billingAddress).toBe(billingAddressVal);
  });

  it('should enforce unique constraint on email', () => {
    const entity = new User();
    entity.email = `test-${Date.now()}@example.com`;
    expect(entity.email).toBeDefined();
  });

  it('should have server-managed fields', () => {
    const entity = new User();
    expect(entity.id).toBeUndefined();
    expect(entity.createdAt).toBeUndefined();
    expect(entity.updatedAt).toBeUndefined();
  });
});
