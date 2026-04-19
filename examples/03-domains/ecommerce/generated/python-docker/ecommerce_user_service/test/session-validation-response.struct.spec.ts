import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { SessionValidationResponse } from '../src/dto/session-validation-response.struct';

describe('SessionValidationResponse Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      valid: true,
      user: {} as any,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(SessionValidationResponse, payload);
    expect(instance).toBeDefined();
    expect(instance.valid).toBeDefined();
    expect(instance.user).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(SessionValidationResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when valid is missing', async () => {
    const payload = buildValidPayload();
    delete payload.valid;
    const instance = plainToInstance(SessionValidationResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
