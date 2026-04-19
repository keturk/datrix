import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { ReservationResponse } from '../src/dto/reservation-response.struct';

describe('ReservationResponse Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      success: true,
      reservationId: '550e8400-e29b-41d4-a716-446655440000',
      error: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ReservationResponse, payload);
    expect(instance).toBeDefined();
    expect(instance.success).toBeDefined();
    expect(instance.reservationId).toBeDefined();
    expect(instance.error).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ReservationResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when success is missing', async () => {
    const payload = buildValidPayload();
    delete payload.success;
    const instance = plainToInstance(ReservationResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
