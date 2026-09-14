import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { LoginResponse } from '../src/dto/login-response.struct';

describe('LoginResponse Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      user: {} as any,
      token: 'test-value',
      expiresAt: new Date('2025-01-15T12:00:00Z'),
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(LoginResponse, payload);
    expect(instance).toBeDefined();
    expect(instance.user).toBeDefined();
    expect(instance.token).toBeDefined();
    expect(instance.expiresAt).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(LoginResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when user is missing', async () => {
    const payload = buildValidPayload();
    delete payload.user;
    const instance = plainToInstance(LoginResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when token is missing', async () => {
    const payload = buildValidPayload();
    delete payload.token;
    const instance = plainToInstance(LoginResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when expiresAt is missing', async () => {
    const payload = buildValidPayload();
    delete payload.expiresAt;
    const instance = plainToInstance(LoginResponse, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
