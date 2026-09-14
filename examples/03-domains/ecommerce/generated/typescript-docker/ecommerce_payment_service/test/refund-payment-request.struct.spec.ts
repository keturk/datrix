import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { RefundPaymentRequest } from '../src/dto/refund-payment-request.struct';

describe('RefundPaymentRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      amount: 99.99,
      reason: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(RefundPaymentRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.amount).toBeDefined();
    expect(instance.reason).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(RefundPaymentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when amount is missing', async () => {
    const payload = buildValidPayload();
    delete payload.amount;
    const instance = plainToInstance(RefundPaymentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when reason is missing', async () => {
    const payload = buildValidPayload();
    delete payload.reason;
    const instance = plainToInstance(RefundPaymentRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
