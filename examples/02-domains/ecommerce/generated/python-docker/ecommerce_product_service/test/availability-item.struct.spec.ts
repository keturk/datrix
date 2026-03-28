import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { AvailabilityItem } from '../src/dto/availability-item.struct';

describe('AvailabilityItem Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      productId: '550e8400-e29b-41d4-a716-446655440000',
      available: true,
      availableQuantity: 42,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(AvailabilityItem, payload);
    expect(instance).toBeDefined();
    expect(instance.productId).toBeDefined();
    expect(instance.available).toBeDefined();
    expect(instance.availableQuantity).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(AvailabilityItem, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when productId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.productId;
    const instance = plainToInstance(AvailabilityItem, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when available is missing', async () => {
    const payload = buildValidPayload();
    delete payload.available;
    const instance = plainToInstance(AvailabilityItem, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when availableQuantity is missing', async () => {
    const payload = buildValidPayload();
    delete payload.availableQuantity;
    const instance = plainToInstance(AvailabilityItem, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
