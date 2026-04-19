import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateUserDto } from '../src/dto/create-user.dto';
import { UserRole } from '../src/enums/user-role.enum';
import { UserStatus } from '../src/enums/user-status.enum';
import { Address } from '../src/dto/address.struct';

describe('CreateUserDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      email: `test-${Date.now()}@example.com`,
      passwordHash: 'SecureP@ss1',
      firstName: 'test-value',
      lastName: 'test-value',
      phoneNumber: '+15551234567',
      role: UserRole.Customer,
      status: UserStatus.Active,
      lastLoginAt: new Date('2025-01-15T12:00:00Z'),
      emailVerifiedAt: new Date('2025-01-15T12:00:00Z'),
      emailVerificationToken: 'test-value',
      passwordResetToken: 'test-value',
      passwordResetExpiry: new Date('2025-01-15T12:00:00Z'),
      shippingAddress: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
      billingAddress: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateUserDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when email is missing', async () => {
    const payload = buildValidPayload();
    delete payload.email;
    const dto = plainToInstance(CreateUserDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'email');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when passwordHash is missing', async () => {
    const payload = buildValidPayload();
    delete payload.passwordHash;
    const dto = plainToInstance(CreateUserDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'passwordHash');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when firstName is missing', async () => {
    const payload = buildValidPayload();
    delete payload.firstName;
    const dto = plainToInstance(CreateUserDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'firstName');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when lastName is missing', async () => {
    const payload = buildValidPayload();
    delete payload.lastName;
    const dto = plainToInstance(CreateUserDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'lastName');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });


  it('should fail validation when firstName exceeds max length 100', async () => {
    const payload = buildValidPayload();
    payload.firstName = 'x'.repeat(100 + 1);
    const dto = plainToInstance(CreateUserDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'firstName');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when lastName exceeds max length 100', async () => {
    const payload = buildValidPayload();
    payload.lastName = 'x'.repeat(100 + 1);
    const dto = plainToInstance(CreateUserDto, payload);
    const errors = await validate(dto);
    const fieldErrors = errors.filter(e => e.property === 'lastName');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});
