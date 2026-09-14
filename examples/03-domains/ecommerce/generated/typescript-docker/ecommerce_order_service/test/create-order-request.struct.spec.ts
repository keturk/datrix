import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateOrderRequest } from '../src/dto/create-order-request.struct';
import { Address } from '../src/dto/address.struct';

describe('CreateOrderRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      items: [] as never[],
      shippingAddress: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
      billingAddress: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
      idempotencyKey: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CreateOrderRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.items).toBeDefined();
    expect(instance.shippingAddress).toBeDefined();
    expect(instance.billingAddress).toBeDefined();
    expect(instance.idempotencyKey).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CreateOrderRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when items is missing', async () => {
    const payload = buildValidPayload();
    delete payload.items;
    const instance = plainToInstance(CreateOrderRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when shippingAddress is missing', async () => {
    const payload = buildValidPayload();
    delete payload.shippingAddress;
    const instance = plainToInstance(CreateOrderRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
