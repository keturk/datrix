import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { RegisterDeviceRequest } from '../src/dto/register-device-request.struct';
import { DevicePlatform } from '../src/enums/device-platform.enum';

describe('RegisterDeviceRequest Struct', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      token: 'test-value',
      platform: DevicePlatform.Ios,
    };
  }

  it('should create a valid instance from payload', () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(RegisterDeviceRequest, payload);
    expect(instance).toBeDefined();
    expect(instance.token).toBeDefined();
    expect(instance.platform).toBeDefined();
  });

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const instance = plainToInstance(RegisterDeviceRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when token is missing', async () => {
    const payload = buildValidPayload();
    delete payload.token;
    const instance = plainToInstance(RegisterDeviceRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

  it('should fail validation when platform is missing', async () => {
    const payload = buildValidPayload();
    delete payload.platform;
    const instance = plainToInstance(RegisterDeviceRequest, payload);
    const errors = await validate(instance);
    expect(errors.length).toBeGreaterThan(0);
  });

});
