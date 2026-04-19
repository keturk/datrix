import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { UpdateShipmentStatusRequest } from '../src/dto/update-shipment-status-request.struct';
import { ShipmentStatus } from '../src/enums/shipment-status.enum';

describe('UpdateShipmentStatusRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      status: ShipmentStatus.Pending,
      location: 'test-value',
      description: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(UpdateShipmentStatusRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.status).toBeDefined();
    expect(instance.location).toBeDefined();
    expect(instance.description).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(UpdateShipmentStatusRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when status is missing', async () => {
    const payload = buildValidPayload();
    delete payload.status;
    const instance = plainToInstance(UpdateShipmentStatusRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
