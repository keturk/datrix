import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CheckAvailabilityRequest } from '../src/dto/check-availability-request.struct';

describe('CheckAvailabilityRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      items: [] as never[],
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CheckAvailabilityRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.items).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CheckAvailabilityRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when items is missing', async () => {
    const payload = buildValidPayload();
    delete payload.items;
    const instance = plainToInstance(CheckAvailabilityRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
