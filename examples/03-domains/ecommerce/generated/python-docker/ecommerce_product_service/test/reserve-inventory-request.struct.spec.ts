import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { ReserveInventoryRequest } from '../src/dto/reserve-inventory-request.struct';

describe('ReserveInventoryRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      reservationId: '550e8400-e29b-41d4-a716-446655440000',
      items: [] as never[],
      ttlSeconds: 42,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ReserveInventoryRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.reservationId).toBeDefined();
    expect(instance.items).toBeDefined();
    expect(instance.ttlSeconds).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ReserveInventoryRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when reservationId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.reservationId;
    const instance = plainToInstance(ReserveInventoryRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when items is missing', async () => {
    const payload = buildValidPayload();
    delete payload.items;
    const instance = plainToInstance(ReserveInventoryRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
