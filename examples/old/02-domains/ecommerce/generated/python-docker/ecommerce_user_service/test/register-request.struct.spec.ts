import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { RegisterRequest } from '../src/dto/register-request.struct';

describe('RegisterRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      email: 'user@example.com',
      password: 'test-value',
      firstName: 'test-value',
      lastName: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(RegisterRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.email).toBeDefined();
    expect(instance.password).toBeDefined();
    expect(instance.firstName).toBeDefined();
    expect(instance.lastName).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(RegisterRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when email is missing', async () => {
    const payload = buildValidPayload();
    delete payload.email;
    const instance = plainToInstance(RegisterRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when password is missing', async () => {
    const payload = buildValidPayload();
    delete payload.password;
    const instance = plainToInstance(RegisterRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when firstName is missing', async () => {
    const payload = buildValidPayload();
    delete payload.firstName;
    const instance = plainToInstance(RegisterRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when lastName is missing', async () => {
    const payload = buildValidPayload();
    delete payload.lastName;
    const instance = plainToInstance(RegisterRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
