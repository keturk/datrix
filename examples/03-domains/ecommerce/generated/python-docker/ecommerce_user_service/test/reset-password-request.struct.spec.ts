import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { ResetPasswordRequest } from '../src/dto/reset-password-request.struct';

describe('ResetPasswordRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      token: 'test-value',
      newPassword: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ResetPasswordRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.token).toBeDefined();
    expect(instance.newPassword).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ResetPasswordRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when token is missing', async () => {
    const payload = buildValidPayload();
    delete payload.token;
    const instance = plainToInstance(ResetPasswordRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when newPassword is missing', async () => {
    const payload = buildValidPayload();
    delete payload.newPassword;
    const instance = plainToInstance(ResetPasswordRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
