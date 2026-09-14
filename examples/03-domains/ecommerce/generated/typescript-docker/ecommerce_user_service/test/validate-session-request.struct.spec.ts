import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { ValidateSessionRequest } from '../src/dto/validate-session-request.struct';

describe('ValidateSessionRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      token: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ValidateSessionRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.token).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ValidateSessionRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when token is missing', async () => {
    const payload = buildValidPayload();
    delete payload.token;
    const instance = plainToInstance(ValidateSessionRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
