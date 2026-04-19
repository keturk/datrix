import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { ChangePasswordRequest } from '../src/dto/change-password-request.struct';

describe('ChangePasswordRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      currentPassword: 'test-value',
      newPassword: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ChangePasswordRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.currentPassword).toBeDefined();
    expect(instance.newPassword).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ChangePasswordRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when currentPassword is missing', async () => {
    const payload = buildValidPayload();
    delete payload.currentPassword;
    const instance = plainToInstance(ChangePasswordRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when newPassword is missing', async () => {
    const payload = buildValidPayload();
    delete payload.newPassword;
    const instance = plainToInstance(ChangePasswordRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
