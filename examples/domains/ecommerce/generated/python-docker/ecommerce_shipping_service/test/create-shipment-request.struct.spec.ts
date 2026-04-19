import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateShipmentRequest } from '../src/dto/create-shipment-request.struct';
import { Address } from '../src/dto/address.struct';

describe('CreateShipmentRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      orderId: '550e8400-e29b-41d4-a716-446655440000',
      destination: { street: 'test-value', city: 'test-value', state: 'test-value', zipCode: 'test-value', country: 'US', phone: '+15551234567' } as Address,
      items: [] as never[],
      weight: 10.50,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CreateShipmentRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.orderId).toBeDefined();
    expect(instance.destination).toBeDefined();
    expect(instance.items).toBeDefined();
    expect(instance.weight).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CreateShipmentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when orderId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.orderId;
    const instance = plainToInstance(CreateShipmentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when destination is missing', async () => {
    const payload = buildValidPayload();
    delete payload.destination;
    const instance = plainToInstance(CreateShipmentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when items is missing', async () => {
    const payload = buildValidPayload();
    delete payload.items;
    const instance = plainToInstance(CreateShipmentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when weight is missing', async () => {
    const payload = buildValidPayload();
    delete payload.weight;
    const instance = plainToInstance(CreateShipmentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
