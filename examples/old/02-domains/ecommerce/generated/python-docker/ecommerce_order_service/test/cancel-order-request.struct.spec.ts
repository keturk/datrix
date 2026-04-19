import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CancelOrderRequest } from '../src/dto/cancel-order-request.struct';

describe('CancelOrderRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      reason: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CancelOrderRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.reason).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(CancelOrderRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

});
