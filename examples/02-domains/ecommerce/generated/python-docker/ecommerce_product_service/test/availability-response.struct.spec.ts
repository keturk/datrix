import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { AvailabilityResponse } from '../src/dto/availability-response.struct';

describe('AvailabilityResponse Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      allAvailable: true,
      items: [] as never[],
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(AvailabilityResponse, payload);
    expect(instance).toBeDefined();
    expect(instance.allAvailable).toBeDefined();
    expect(instance.items).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(AvailabilityResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when allAvailable is missing', async () => {
    const payload = buildValidPayload();
    delete payload.allAvailable;
    const instance = plainToInstance(AvailabilityResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when items is missing', async () => {
    const payload = buildValidPayload();
    delete payload.items;
    const instance = plainToInstance(AvailabilityResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
