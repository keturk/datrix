import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateShipmentItem } from '../src/dto/create-shipment-item.struct';

describe('CreateShipmentItem Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      productId: '550e8400-e29b-41d4-a716-446655440000',
      quantity: 42,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CreateShipmentItem, payload);
    expect(instance).toBeDefined();
    expect(instance.productId).toBeDefined();
    expect(instance.quantity).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CreateShipmentItem, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when productId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.productId;
    const instance = plainToInstance(CreateShipmentItem, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when quantity is missing', async () => {
    const payload = buildValidPayload();
    delete payload.quantity;
    const instance = plainToInstance(CreateShipmentItem, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
