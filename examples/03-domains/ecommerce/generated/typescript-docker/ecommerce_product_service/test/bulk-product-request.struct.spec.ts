import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { BulkProductRequest } from '../src/dto/bulk-product-request.struct';

describe('BulkProductRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      ids: ['550e8400-e29b-41d4-a716-446655440000'],
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(BulkProductRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.ids).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(BulkProductRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when ids is missing', async () => {
    const payload = buildValidPayload();
    delete payload.ids;
    const instance = plainToInstance(BulkProductRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
