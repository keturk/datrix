import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { Address } from '../src/dto/address.struct';

describe('Address Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      street: 'test-value',
      city: 'test-value',
      state: 'test-value',
      zipCode: 'test-value',
      country: 'US',
      phone: '+15551234567',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(Address, payload);
    expect(instance).toBeDefined();
    expect(instance.street).toBeDefined();
    expect(instance.city).toBeDefined();
    expect(instance.state).toBeDefined();
    expect(instance.zipCode).toBeDefined();
    expect(instance.country).toBeDefined();
    expect(instance.phone).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(Address, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when street is missing', async () => {
    const payload = buildValidPayload();
    delete payload.street;
    const instance = plainToInstance(Address, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when city is missing', async () => {
    const payload = buildValidPayload();
    delete payload.city;
    const instance = plainToInstance(Address, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when state is missing', async () => {
    const payload = buildValidPayload();
    delete payload.state;
    const instance = plainToInstance(Address, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when zipCode is missing', async () => {
    const payload = buildValidPayload();
    delete payload.zipCode;
    const instance = plainToInstance(Address, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when country is missing', async () => {
    const payload = buildValidPayload();
    delete payload.country;
    const instance = plainToInstance(Address, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
