import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { UpdateProfileRequest } from '../src/dto/update-profile-request.struct';
import { Address } from '../src/dto/address.struct';

describe('UpdateProfileRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      firstName: 'test-value',
      lastName: 'test-value',
      phoneNumber: '+15551234567',
      shippingAddress: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
      billingAddress: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(UpdateProfileRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.firstName).toBeDefined();
    expect(instance.lastName).toBeDefined();
    expect(instance.phoneNumber).toBeDefined();
    expect(instance.shippingAddress).toBeDefined();
    expect(instance.billingAddress).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(UpdateProfileRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

});
