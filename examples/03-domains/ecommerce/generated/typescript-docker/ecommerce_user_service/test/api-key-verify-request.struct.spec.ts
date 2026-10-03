import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { ApiKeyVerifyRequest } from '../src/dto/api-key-verify-request.struct';

describe('ApiKeyVerifyRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      keyHash: 'test-value',
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ApiKeyVerifyRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.keyHash).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(ApiKeyVerifyRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when keyHash is missing', async () => {
    const payload = buildValidPayload();
    delete payload.keyHash;
    const instance = plainToInstance(ApiKeyVerifyRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
