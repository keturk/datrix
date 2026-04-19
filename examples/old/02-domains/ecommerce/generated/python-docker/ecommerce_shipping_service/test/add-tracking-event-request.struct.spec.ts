import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { AddTrackingEventRequest } from '../src/dto/add-tracking-event-request.struct';
import { ShipmentStatus } from '../src/enums/shipment-status.enum';

describe('AddTrackingEventRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      status: ShipmentStatus.Pending,
      location: 'test-value',
      description: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(AddTrackingEventRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.status).toBeDefined();
    expect(instance.location).toBeDefined();
    expect(instance.description).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(AddTrackingEventRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when status is missing', async () => {
    const payload = buildValidPayload();
    delete payload.status;
    const instance = plainToInstance(AddTrackingEventRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when location is missing', async () => {
    const payload = buildValidPayload();
    delete payload.location;
    const instance = plainToInstance(AddTrackingEventRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
