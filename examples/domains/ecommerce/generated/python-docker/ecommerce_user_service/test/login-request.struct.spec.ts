import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { LoginRequest } from '../src/dto/login-request.struct';

describe('LoginRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      email: 'user@example.com',
      password: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(LoginRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.email).toBeDefined();
    expect(instance.password).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(LoginRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when email is missing', async () => {
    const payload = buildValidPayload();
    delete payload.email;
    const instance = plainToInstance(LoginRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when password is missing', async () => {
    const payload = buildValidPayload();
    delete payload.password;
    const instance = plainToInstance(LoginRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
