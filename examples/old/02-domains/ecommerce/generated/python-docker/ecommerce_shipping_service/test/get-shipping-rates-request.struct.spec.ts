import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { GetShippingRatesRequest } from '../src/dto/get-shipping-rates-request.struct';
import { Address } from '../src/dto/address.struct';

describe('GetShippingRatesRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      destination: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
      weight: 10.50,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(GetShippingRatesRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.destination).toBeDefined();
    expect(instance.weight).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(GetShippingRatesRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when destination is missing', async () => {
    const payload = buildValidPayload();
    delete payload.destination;
    const instance = plainToInstance(GetShippingRatesRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when weight is missing', async () => {
    const payload = buildValidPayload();
    delete payload.weight;
    const instance = plainToInstance(GetShippingRatesRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
