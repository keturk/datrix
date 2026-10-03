import { validate } from 'class-validator';
import { plainToInstance } from 'class-transformer';
import { CreateDeviceRegistrationDto } from '../src/dto/create-device-registration.dto';
import { DevicePlatform } from '../src/enums/device-platform.enum';

describe('CreateDeviceRegistrationDto', () => {
  function buildValidPayload(): Record<string, unknown> {
    return {
      subject: 'test-value',
      token: 'test-value',
      platform: DevicePlatform.Ios,
    };
  }

  it('should pass validation with correct data', async () => {
    const payload = buildValidPayload();
    const dto = plainToInstance(CreateDeviceRegistrationDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBe(0);
  });

  it('should fail validation when subject is missing', async () => {
    const payload = buildValidPayload();
    delete payload.subject;
    const dto = plainToInstance(CreateDeviceRegistrationDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'subject');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when token is missing', async () => {
    const payload = buildValidPayload();
    delete payload.token;
    const dto = plainToInstance(CreateDeviceRegistrationDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'token');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

  it('should fail validation when platform is missing', async () => {
    const payload = buildValidPayload();
    delete payload.platform;
    const dto = plainToInstance(CreateDeviceRegistrationDto, payload);
    const errors = await validate(dto);
    expect(errors.length).toBeGreaterThan(0);
    const fieldErrors = errors.filter(e => e.property === 'platform');
    expect(fieldErrors.length).toBeGreaterThan(0);
  });

});
