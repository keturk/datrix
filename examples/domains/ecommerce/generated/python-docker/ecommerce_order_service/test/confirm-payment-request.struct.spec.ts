import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { ConfirmPaymentRequest } from '../src/dto/confirm-payment-request.struct';

describe('ConfirmPaymentRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      paymentId: '550e8400-e29b-41d4-a716-446655440000',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ConfirmPaymentRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.paymentId).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ConfirmPaymentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when paymentId is missing', async () => {
    const payload = buildValidPayload();
    delete payload.paymentId;
    const instance = plainToInstance(ConfirmPaymentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
