import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { VerifyEmailRequest } from '../src/dto/verify-email-request.struct';

describe('VerifyEmailRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      token: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(VerifyEmailRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.token).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(VerifyEmailRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when token is missing', async () => {
    const payload = buildValidPayload();
    delete payload.token;
    const instance = plainToInstance(VerifyEmailRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
