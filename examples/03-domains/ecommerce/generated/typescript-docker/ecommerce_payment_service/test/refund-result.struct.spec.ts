import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { RefundResult } from '../src/dto/refund-result.struct';

describe('RefundResult Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      success: true,
      refundTransactionId: 'test-value',
      error: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(RefundResult, payload);
    expect(instance).toBeDefined();
    expect(instance.success).toBeDefined();
    expect(instance.refundTransactionId).toBeDefined();
    expect(instance.error).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(RefundResult, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when success is missing', async () => {
    const payload = buildValidPayload();
    delete payload.success;
    const instance = plainToInstance(RefundResult, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
