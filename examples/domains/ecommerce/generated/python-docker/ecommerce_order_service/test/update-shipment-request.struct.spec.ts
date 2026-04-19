import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { UpdateShipmentRequest } from '../src/dto/update-shipment-request.struct';

describe('UpdateShipmentRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      shipmentId: '550e8400-e29b-41d4-a716-446655440000',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(UpdateShipmentRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.shipmentId).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(UpdateShipmentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when shipmentId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.shipmentId;
    const instance = plainToInstance(UpdateShipmentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
