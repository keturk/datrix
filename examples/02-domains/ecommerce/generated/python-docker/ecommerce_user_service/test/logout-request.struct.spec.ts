import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { LogoutRequest } from '../src/dto/logout-request.struct';

describe('LogoutRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      revokeAll: true,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(LogoutRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.revokeAll).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(LogoutRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

});
