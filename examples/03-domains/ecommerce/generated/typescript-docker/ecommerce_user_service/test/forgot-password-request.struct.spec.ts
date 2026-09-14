import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { ForgotPasswordRequest } from '../src/dto/forgot-password-request.struct';

describe('ForgotPasswordRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      email: 'user@example.com',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ForgotPasswordRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.email).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ForgotPasswordRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when email is missing', async () => {
    const payload = buildValidPayload();
    delete payload.email;
    const instance = plainToInstance(ForgotPasswordRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
