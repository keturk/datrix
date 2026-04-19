import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { UpdateInventoryRequest } from '../src/dto/update-inventory-request.struct';

describe('UpdateInventoryRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      inventory: 42,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(UpdateInventoryRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.inventory).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(UpdateInventoryRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when inventory is missing', async () => {
    const payload = buildValidPayload();
    delete payload.inventory;
    const instance = plainToInstance(UpdateInventoryRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
