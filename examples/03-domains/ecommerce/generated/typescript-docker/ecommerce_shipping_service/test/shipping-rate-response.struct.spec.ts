import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { ShippingRateResponse } from '../src/dto/shipping-rate-response.struct';
import { ShippingCarrier } from '../src/enums/shipping-carrier.enum';

describe('ShippingRateResponse Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      carrier: ShippingCarrier.FedEx,
      rate: 10.50,
      estimatedDays: 42,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ShippingRateResponse, payload);
    expect(instance).toBeDefined();
    expect(instance.carrier).toBeDefined();
    expect(instance.rate).toBeDefined();
    expect(instance.estimatedDays).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ShippingRateResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when carrier is missing', async () => {
    const payload = buildValidPayload();
    delete payload.carrier;
    const instance = plainToInstance(ShippingRateResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when rate is missing', async () => {
    const payload = buildValidPayload();
    delete payload.rate;
    const instance = plainToInstance(ShippingRateResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when estimatedDays is missing', async () => {
    const payload = buildValidPayload();
    delete payload.estimatedDays;
    const instance = plainToInstance(ShippingRateResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
